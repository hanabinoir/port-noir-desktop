"""Wire protocol shared with the Android app (JSON text frames over WSS)."""
from __future__ import annotations

import json
import time
import uuid
import re

PROTOCOL_VERSION = 1
SERVICE_TYPE = "_portnoir._tcp.local."   # mDNS / Bonjour service
DEFAULT_PORT = 8765

# Handshake (phone -> Mac): auth.pair on first contact, auth.hello afterwards
AUTH_PAIR = "auth.pair"      # {device_id, name, model, token}
AUTH_HELLO = "auth.hello"    # {device_id, key}
AUTH_PAIRED = "auth.paired"  # Mac -> phone: {key, mac_id, mac_name}
AUTH_OK = "auth.ok"          # Mac -> phone: {mac_name}
AUTH_ERROR = "auth.error"    # Mac -> phone: {reason}

# WebSocket close codes the phone treats as "stop reconnecting, you are unpaired"
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORGOTTEN = 4403
MAX_FILE_SIZE = 1024 * 1024 * 1024
_BLOB_ID = re.compile(r"^[a-f0-9]{32}$")
_MESSAGE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def make(type_: str, **fields) -> dict:
    return {"v": PROTOCOL_VERSION, "id": uuid.uuid4().hex, "type": type_,
            "ts": int(time.time() * 1000), **fields}


def encode(msg: dict) -> str:
    return json.dumps(msg, separators=(",", ":"))


def decode(raw: str | bytes) -> dict:
    msg = json.loads(raw)
    if not isinstance(msg, dict) or "type" not in msg:
        raise ValueError("malformed message")
    return msg


def valid_chat_message(msg: dict) -> bool:
    message_id = msg.get("id")
    if not isinstance(message_id, str) or _MESSAGE_ID.fullmatch(message_id) is None:
        return False
    if msg.get("type") == "chat.text":
        body = msg.get("body")
        return isinstance(body, str) and len(body.encode("utf-8")) <= 1024 * 1024
    if msg.get("type") == "chat.file":
        size = msg.get("size")
        return (
            isinstance(msg.get("name"), str)
            and 0 < len(msg["name"]) <= 255
            and not any(ord(char) < 32 or ord(char) == 127 for char in msg["name"])
            and isinstance(msg.get("mime"), str)
            and 0 < len(msg["mime"]) <= 255
            and isinstance(size, int)
            and not isinstance(size, bool)
            and 0 <= size <= MAX_FILE_SIZE
            and isinstance(msg.get("blob"), str)
            and _BLOB_ID.fullmatch(msg["blob"]) is not None
        )
    return False


def valid_transfer_progress(msg: dict) -> bool:
    done, size = msg.get("done"), msg.get("size")
    return (
        isinstance(msg.get("blob"), str)
        and _BLOB_ID.fullmatch(msg["blob"]) is not None
        and isinstance(done, int)
        and not isinstance(done, bool)
        and isinstance(size, int)
        and not isinstance(size, bool)
        and 0 <= done <= size <= MAX_FILE_SIZE
    )
