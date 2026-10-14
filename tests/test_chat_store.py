import tempfile
import unittest
from pathlib import Path

from portnoir.core.store import ChatStore


class ChatStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.store = ChatStore(root / "chat.sqlite3", root / "files")

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_history_is_deduplicated_and_acknowledgements_are_device_scoped(self):
        message = {"id": "message-1", "type": "chat.text", "ts": 1, "body": "hello"}
        self.store.add_message("phone-a", message, "outgoing")
        self.store.add_message("phone-a", message, "outgoing")
        self.store.acknowledge("phone-b", "message-1")
        self.assertEqual(len(self.store.history("phone-a")), 1)
        self.assertTrue(self.store.pending("phone-a"))
        self.store.acknowledge("phone-a", "message-1")
        self.assertEqual(self.store.pending("phone-a"), [])

    def test_upload_offsets_and_downloads_are_bound_to_the_paired_device(self):
        part = self.store.begin_upload(
            "phone-a", "a" * 32, "sample.bin", "application/octet-stream", 4,
        )
        part.write_bytes(b"data")
        final = self.store.complete_upload("phone-a", "a" * 32)
        self.assertEqual(final.read_bytes(), b"data")
        self.assertEqual(self.store.blob("phone-a", "a" * 32)["path"], str(final))
        self.assertIsNone(self.store.blob("phone-b", "a" * 32))
