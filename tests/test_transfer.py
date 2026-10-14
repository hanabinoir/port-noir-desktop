import tempfile
import unittest
from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from portnoir.core.pairing import DeviceStore, Identity, PairingService
from portnoir.core.store import ChatStore
from portnoir.core.transfer import TransferServer


class TransferTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        identity = Identity.load_or_create(root)
        devices = DeviceStore(root / "devices.json")
        pairing = PairingService(identity, devices)
        self.key = pairing.register("phone-a", "Phone", "Test", "127.0.0.1")
        self.store = ChatStore(root / "chat.sqlite3", root / "files")
        transfer = TransferServer(identity, pairing, self.store, lambda *_: None)
        app = web.Application()
        app.router.add_route("*", "/blob/{blob_id}", transfer._blob)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.store.close()
        self.temp_dir.cleanup()

    def _headers(self):
        return {"X-Device-ID": "phone-a", "Authorization": f"Bearer {self.key}"}

    async def test_authenticated_chunked_upload_and_range_download(self):
        blob_id = "a" * 32
        metadata = {
            **self._headers(),
            "X-File-Name": "sample.bin",
            "X-File-Mime": "application/octet-stream",
            "X-File-Size": "4",
            "Content-Range": "bytes 0-1/4",
        }
        first = await self.client.put(f"/blob/{blob_id}", data=b"ab", headers=metadata)
        self.assertEqual((await first.json())["offset"], 2)
        status = await self.client.head(f"/blob/{blob_id}", headers=self._headers())
        self.assertEqual(status.headers["Upload-Offset"], "2")

        metadata["Content-Range"] = "bytes 2-3/4"
        second = await self.client.put(f"/blob/{blob_id}", data=b"cd", headers=metadata)
        self.assertTrue((await second.json())["complete"])

        download = await self.client.get(f"/blob/{blob_id}", headers=self._headers())
        self.assertEqual(await download.read(), b"abcd")
        ranged = await self.client.get(
            f"/blob/{blob_id}", headers={**self._headers(), "Range": "bytes=1-2"},
        )
        self.assertEqual(ranged.status, 206)
        self.assertEqual(await ranged.read(), b"bc")

    async def test_blob_rejects_unpaired_devices(self):
        response = await self.client.get(f"/blob/{'b' * 32}")
        self.assertEqual(response.status, 401)
