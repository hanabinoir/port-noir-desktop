"""WebSocket server for phones, per-device connection state and signals for the UI.

Direction of connection: the phone is the client. It finds the Mac via mDNS (or the
last known address), authenticates with its stored key and keeps retrying with
backoff. The Mac only has to listen, advertise and notice when a session ends.
Liveness uses WebSocket ping/pong (every 5 s, dead after 10 s without a pong).
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import socket
import ssl
import time
import uuid
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from . import protocol as P
from .discovery import Advertiser
from .pairing import DeviceStore, Identity, PairedDevice, PairingService, data_dir, local_ip
from .store import ChatStore
from .transfer import TransferServer

log = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    # The phone walks through all five; the Mac only ever reports DISCONNECTED/CONNECTED.
    DISCONNECTED = "disconnected"
    DISCOVERING = "discovering"
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    CONNECTED = "connected"


class ConnectionManager(QObject):
    devices_changed = Signal()                 # paired-device list or metadata changed
    state_changed = Signal(str, object)        # device_id, ConnectionState
    device_paired = Signal(str)                # device_id
    message_received = Signal(str, dict)       # device_id, message (used from Milestone 2)
    transfer_progress = Signal(str, str, int, int)  # device_id, blob_id, bytes, total
    server_error = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        directory = data_dir()
        self.identity = Identity.load_or_create(directory)
        self.store = DeviceStore(directory / "devices.json")
        self.pairing = PairingService(self.identity, self.store)
        self.chat_store = ChatStore(directory / "portnoir.sqlite3", directory / "Transfers")
        self.advertiser = Advertiser()
        self.transfer = TransferServer(
            self.identity, self.pairing, self.chat_store, self._on_transfer_progress,
        )
        self.host_name = socket.gethostname().split(".")[0]
        self.port = P.DEFAULT_PORT
        self._server = None
        self._sessions: dict[str, ServerConnection] = {}
        self._advert_task = None

    def _on_transfer_progress(self, device_id: str, blob_id: str, done: int, total: int) -> None:
        state = "complete" if done >= total else f"{done}/{total}"
        self.chat_store.set_transfer_state(device_id, blob_id, state)
        self.transfer_progress.emit(device_id, blob_id, done, total)
        self.devices_changed.emit()

    # ---- lifecycle -------------------------------------------------------
    async def start(self) -> None:
        await self.transfer.start()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(self.identity.cert_path, self.identity.key_path)
        for port in range(P.DEFAULT_PORT, P.DEFAULT_PORT + 10):
            try:
                self._server = await serve(self._handle, "0.0.0.0", port, ssl=ctx,
                                           ping_interval=5, ping_timeout=10, max_size=8 * 2**20)
                self.port = port
                break
            except OSError:
                continue
        else:
            await self.transfer.stop()
            self.server_error.emit(f"Ports {P.DEFAULT_PORT}-{P.DEFAULT_PORT + 9} are all in use.")
            return
        self._advert_task = asyncio.ensure_future(self._advertise_loop())

    async def _advertise_loop(self) -> None:
        """Keep the mDNS record pointing at the current IP, and retry when the network is down or changes."""
        advertised: str | None = None
        warned = False
        while True:
            ip = local_ip()
            if ip != advertised and not ip.startswith("127."):
                try:
                    await self.advertiser.stop()
                    await self.advertiser.start(self.identity.mac_id, self.host_name, ip,
                                                self.port, self.identity.fingerprint,
                                                self.transfer.port)
                    advertised, warned = ip, False
                except Exception as exc:
                    log.warning("mDNS advertising failed: %s", exc)
                    if not warned:
                        warned = True
                        self.server_error.emit(
                            "Automatic reconnect needs a network connection (mDNS unavailable).")
            await asyncio.sleep(5)

    async def stop(self) -> None:
        task = getattr(self, "_advert_task", None)
        if task:
            task.cancel()
        for ws in list(self._sessions.values()):
            await ws.close(1001)
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        await self.advertiser.stop()
        await self.transfer.stop()
        self.chat_store.close()

    # ---- public API ------------------------------------------------------
    def devices(self) -> list[PairedDevice]:
        return self.store.all()

    def state_of(self, device_id: str) -> ConnectionState:
        return ConnectionState.CONNECTED if device_id in self._sessions else ConnectionState.DISCONNECTED

    def new_pairing_payload(self) -> dict:
        return self.pairing.new_payload(local_ip(), self.port, self.host_name)

    async def send(self, device_id: str, msg: dict) -> bool:
        ws = self._sessions.get(device_id)
        if ws is None:
            return False
        await ws.send(P.encode(msg))
        return True

    async def send_chat_text(self, device_id: str, body: str) -> dict:
        message = P.make("chat.text", body=body)
        self.chat_store.add_message(device_id, message, "outgoing")
        self.devices_changed.emit()
        ws = self._sessions.get(device_id)
        if ws is not None:
            await ws.send(P.encode(message))
        return message

    async def send_chat_file(self, device_id: str, source: Path) -> dict:
        blob_id = uuid.uuid4().hex
        name = source.name
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        path = self.chat_store.prepare_outgoing_blob(device_id, blob_id, name, mime, source)
        message = P.make("chat.file", name=name, size=path.stat().st_size,
                         mime=mime, blob=blob_id)
        self.chat_store.add_message(device_id, message, "outgoing")
        self.devices_changed.emit()
        ws = self._sessions.get(device_id)
        if ws is not None:
            await ws.send(P.encode(message))
        return message

    async def forget(self, device_id: str) -> None:
        ws = self._sessions.pop(device_id, None)
        self.store.remove(device_id)
        if ws is not None:
            await ws.close(P.CLOSE_FORGOTTEN, "forgotten")
        self.devices_changed.emit()

    # ---- server side -----------------------------------------------------
    async def _handle(self, ws: ServerConnection) -> None:
        ip = ws.remote_address[0] if ws.remote_address else ""
        device: PairedDevice | None = None
        try:
            device = await asyncio.wait_for(self._authenticate(ws, ip), timeout=10)
            if device is None:
                return
            old = self._sessions.get(device.id)
            self._sessions[device.id] = ws
            if old is not None:
                await old.close(1000, "replaced")
            device.last_seen, device.last_ip = time.time(), ip
            self.store.save()
            self.state_changed.emit(device.id, ConnectionState.CONNECTED)
            self.devices_changed.emit()
            for message in self.chat_store.pending(device.id):
                await ws.send(P.encode(message))
            async for raw in ws:
                try:
                    message = P.decode(raw)
                    if message.get("type") == "ack":
                        message_id = message.get("id", message.get("message_id", ""))
                        self.chat_store.acknowledge(device.id, str(message_id))
                        self.devices_changed.emit()
                    elif message.get("type") == "transfer.progress":
                        if P.valid_transfer_progress(message):
                            self.chat_store.set_transfer_state(
                                device.id, message["blob"],
                                ("complete" if message["done"] >= message["size"]
                                 else f'{message["done"]}/{message["size"]}'),
                            )
                            self.devices_changed.emit()
                        else:
                            log.warning("ignoring malformed transfer progress from %s", device.id)
                    else:
                        if message.get("type") in ("chat.text", "chat.file"):
                            if P.valid_chat_message(message):
                                self.message_received.emit(device.id, message)
                            else:
                                log.warning("ignoring malformed chat message from %s", device.id)
                        else:
                            self.message_received.emit(device.id, message)
                except ValueError:
                    log.debug("ignoring malformed frame")
        except (asyncio.TimeoutError, ConnectionClosed):
            pass
        except Exception:
            log.exception("session error")
        finally:
            if device and self._sessions.get(device.id) is ws:
                del self._sessions[device.id]
                device.last_seen = time.time()
                self.store.save()
                self.state_changed.emit(device.id, ConnectionState.DISCONNECTED)
                self.devices_changed.emit()

    async def _authenticate(self, ws: ServerConnection, ip: str) -> PairedDevice | None:
        try:
            msg = P.decode(await ws.recv())
        except ValueError:
            return await self._reject(ws, "bad_handshake")
        kind, device_id = msg.get("type"), str(msg.get("device_id", ""))
        if kind == P.AUTH_PAIR and device_id:
            if not self.pairing.consume_token(str(msg.get("token", ""))):
                return await self._reject(ws, "invalid_or_expired_token")
            key = self.pairing.register(device_id, str(msg.get("name") or "Android phone"),
                                        str(msg.get("model", "")), ip)
            await ws.send(P.encode(P.make(P.AUTH_PAIRED, key=key, mac_id=self.identity.mac_id,
                                          mac_name=self.host_name, transfer_port=self.transfer.port)))
            self.device_paired.emit(device_id)
            self.devices_changed.emit()
            return self.store.get(device_id)
        if kind == P.AUTH_HELLO and device_id:
            device = self.pairing.verify(device_id, str(msg.get("key", "")))
            if device is None:
                return await self._reject(ws, "unknown_device")
            await ws.send(P.encode(P.make(P.AUTH_OK, mac_name=self.host_name,
                                          transfer_port=self.transfer.port)))
            return device
        return await self._reject(ws, "bad_handshake")

    @staticmethod
    async def _reject(ws: ServerConnection, reason: str) -> None:
        await ws.send(P.encode(P.make(P.AUTH_ERROR, reason=reason)))
        await ws.close(P.CLOSE_UNAUTHORIZED, reason)
        return None
