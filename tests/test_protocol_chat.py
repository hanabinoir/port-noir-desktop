import unittest

from portnoir.core.protocol import valid_chat_message, valid_transfer_progress


class ChatProtocolTests(unittest.TestCase):
    def test_validates_chat_text_and_file_metadata(self):
        self.assertTrue(valid_chat_message({
            "id": "a" * 32, "type": "chat.text", "body": "hello",
        }))
        self.assertFalse(valid_chat_message({
            "id": "a" * 32, "type": "chat.text", "body": 7,
        }))
        self.assertTrue(valid_chat_message({
            "id": "a" * 32, "type": "chat.file", "name": "image.png",
            "mime": "image/png", "size": 3, "blob": "b" * 32,
        }))
        self.assertFalse(valid_chat_message({
            "id": "a" * 32, "type": "chat.file", "name": "image.png",
            "mime": "image/png", "size": 3, "blob": "../outside",
        }))

    def test_validates_transfer_progress_bounds(self):
        self.assertTrue(valid_transfer_progress({
            "blob": "a" * 32, "done": 2, "size": 3,
        }))
        self.assertFalse(valid_transfer_progress({
            "blob": "a" * 32, "done": 4, "size": 3,
        }))
