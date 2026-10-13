"""Wire protocol shared with the Android app (JSON text frames over WSS)."""
from __future__ import annotations

import json
import time
import uuid

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
