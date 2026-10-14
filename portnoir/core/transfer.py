"""Authenticated HTTPS endpoint for chat file transfers."""
from __future__ import annotations

import base64
import binascii
import re
import ssl
from pathlib import Path

from aiohttp import web
from aiohttp.helpers import content_disposition_header

from .pairing import PairingService
from .store import ChatStore

_BLOB_ID = re.compile(r"^[a-f0-9]{32}$")
_CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
_MAX_FILE_SIZE = 1024 * 1024 * 1024


class TransferServer:
    def __init__(self, identity, pairing: PairingService, store: ChatStore, on_progress):
        self.identity = identity
        self.pairing = pairing
        self.store = store
        self.on_progress = on_progress
        self.port = 0
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application(client_max_size=_MAX_FILE_SIZE)
        app.router.add_route("*", "/blob/{blob_id}", self._blob)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(self.identity.cert_path, self.identity.key_path)
        for port in range(8766, 8776):
            site = web.TCPSite(self._runner, "0.0.0.0", port, ssl_context=context)
            try:
                await site.start()
            except OSError:
                continue
            self.port = port
            return
        await self._runner.cleanup()
        self._runner = None
        raise OSError("Ports 8766-8775 are all in use.")

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    def _device(self, request: web.Request):
        device_id = request.headers.get("X-Device-ID", "")
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return None
        return self.pairing.verify(device_id, authorization[7:])

    async def _blob(self, request: web.Request) -> web.StreamResponse:
        if not _BLOB_ID.fullmatch(request.match_info["blob_id"]):
            raise web.HTTPBadRequest(text="Invalid blob ID")
        device = self._device(request)
        if device is None:
            raise web.HTTPUnauthorized(text="Invalid device credentials")
        blob_id = request.match_info["blob_id"]
        if request.method == "HEAD":
            upload = self.store.upload(device.id, blob_id)
            if upload is None:
                raise web.HTTPNotFound()
            path = Path(upload["path"])
            return web.Response(headers={"Upload-Offset": str(path.stat().st_size if path.exists() else 0),
                                         "Upload-Length": str(upload["size"])})
        if request.method == "PUT":
            return await self._upload(request, device.id, blob_id)
        if request.method == "GET":
            blob = self.store.blob(device.id, blob_id)
            if blob is None:
                raise web.HTTPNotFound()
            return web.FileResponse(Path(blob["path"]), headers={
                "Content-Type": blob["mime"] or "application/octet-stream",
                "Content-Disposition": content_disposition_header(
                    "attachment", filename=Path(blob["name"]).name,
                ),
            })
        raise web.HTTPMethodNotAllowed(request.method, ["GET", "HEAD", "PUT"])

    async def _upload(self, request: web.Request, device_id: str, blob_id: str) -> web.Response:
        encoded_name = request.headers.get("X-File-Name-Base64")
        if encoded_name is not None:
            if re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", encoded_name) is None:
                raise web.HTTPBadRequest(text="Invalid encoded filename")
            try:
                raw_name = base64.urlsafe_b64decode(encoded_name + "=" * (-len(encoded_name) % 4))
                decoded_name = raw_name.decode("utf-8")
            except (binascii.Error, UnicodeDecodeError) as exc:
                raise web.HTTPBadRequest(text="Invalid encoded filename") from exc
        else:
            decoded_name = request.headers.get("X-File-Name", "file")
        if any(ord(char) < 32 or ord(char) == 127 for char in decoded_name):
            raise web.HTTPBadRequest(text="Invalid filename")
        name = Path(decoded_name.replace("\\", "/")).name[:255] or "file"
        mime = request.headers.get("X-File-Mime", "application/octet-stream")[:255]
        try:
            size = int(request.headers.get("X-File-Size", ""))
        except ValueError as exc:
            raise web.HTTPBadRequest(text="Missing or invalid file size") from exc
        if size < 0 or size > _MAX_FILE_SIZE:
            raise web.HTTPRequestEntityTooLarge(max_size=_MAX_FILE_SIZE, actual_size=size)
        try:
            path = self.store.begin_upload(device_id, blob_id, name, mime, size)
        except ValueError as exc:
            raise web.HTTPConflict(text=str(exc)) from exc
        existing = path.stat().st_size if path.exists() else 0
        content_range = request.headers.get("Content-Range")
        if content_range:
            match = _CONTENT_RANGE.fullmatch(content_range)
            if not match:
                raise web.HTTPBadRequest(text="Invalid Content-Range")
            start, end, total = map(int, match.groups())
            if start != existing or total != size or end < start or end >= total:
                raise web.HTTPConflict(text=f"Expected upload offset {existing}")
            expected_chunk = end - start + 1
        else:
            if existing:
                raise web.HTTPConflict(text=f"Expected Content-Range at offset {existing}")
            expected_chunk = size
        received = 0
        reported = existing
        mode = "ab" if existing else "wb"
        with path.open(mode) as output:
            async for chunk in request.content.iter_chunked(64 * 1024):
                received += len(chunk)
                if received > expected_chunk:
                    raise web.HTTPBadRequest(text="Chunk exceeds Content-Range")
                output.write(chunk)
                current = existing + received
                if current - reported >= 1024 * 1024 or received == expected_chunk:
                    self.on_progress(device_id, blob_id, current, size)
                    reported = current
        if received != expected_chunk:
            raise web.HTTPBadRequest(text="Incomplete upload chunk")
        offset = existing + received
        if offset == size:
            self.store.complete_upload(device_id, blob_id)
        return web.json_response({"offset": offset, "complete": offset == size})
