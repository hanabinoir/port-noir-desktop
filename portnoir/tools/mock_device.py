"""Fake Android phone for developing the Mac app without a device.

First run (pair):  python -m portnoir.tools.mock_device --payload '<JSON from "Copy payload">'
Later runs:        python -m portnoir.tools.mock_device         (reconnects with the stored key)
Stop it with Ctrl-C, start it again, and watch the sidebar status change.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import ssl
import uuid
from pathlib import Path

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from portnoir.core import protocol as P

STATE_FILE = Path.home() / ".portnoir-mock-phone.json"
BACKOFF = [1, 2, 5, 10, 30]


class Rejected(Exception):
    pass


def _load(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _save(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2))


async def session(state: dict, path: Path, name: str, log=print) -> None:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # we pin the certificate fingerprint instead
    async with connect(f"wss://{state['host']}:{state['port']}", ssl=ctx,
                       ping_interval=5, ping_timeout=10) as ws:
        der = ws.transport.get_extra_info("ssl_object").getpeercert(binary_form=True)
        if hashlib.sha256(der).hexdigest() != state["fp"]:
            raise Rejected("certificate fingerprint mismatch")
        if state.get("key"):
            await ws.send(P.encode(P.make(P.AUTH_HELLO, device_id=state["device_id"], key=state["key"])))
        else:
            await ws.send(P.encode(P.make(P.AUTH_PAIR, device_id=state["device_id"], name=name,
                                          model="Mock Phone", token=state["token"])))
        reply = P.decode(await ws.recv())
        if reply["type"] == P.AUTH_PAIRED:
            state["key"] = reply["key"]
            state.pop("token", None)
            _save(path, state)
            log("paired")
        elif reply["type"] != P.AUTH_OK:
            raise Rejected(reply.get("reason", "rejected"))
        log("connected")
        async for raw in ws:
            message = P.decode(raw)
            if message.get("type") in ("chat.text", "chat.file"):
                await ws.send(P.encode(P.make("ack", id=message.get("id", ""))))
    log("disconnected")


async def run_phone(path: Path = STATE_FILE, payload: dict | None = None,
                    name: str = "Mock Pixel", log=print) -> None:
    state = _load(path)
    if payload:
        state = {"device_id": state.get("device_id") or uuid.uuid4().hex[:16], "host": payload["host"],
                 "port": payload["port"], "fp": payload["fp"], "token": payload["token"]}
    if not state:
        raise SystemExit("No stored pairing. Pass --payload once.")
    attempt = 0
    while True:
        try:
            await session(state, path, name, log)
            attempt = 0
        except Rejected as exc:
            log(f"rejected: {exc}")
            if exc.args and exc.args[0] in ("unknown_device", "invalid_or_expired_token"):
                path.unlink(missing_ok=True)
            raise
        except (OSError, ConnectionClosed, asyncio.TimeoutError) as exc:
            log(f"connection failed: {exc!r}")
        delay = BACKOFF[min(attempt, len(BACKOFF) - 1)]
        attempt += 1
        log(f"retrying in {delay}s")
        await asyncio.sleep(delay)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", help="JSON copied from the pairing dialog")
    ap.add_argument("--name", default="Mock Pixel")
    args = ap.parse_args()
    try:
        asyncio.run(run_phone(payload=json.loads(args.payload) if args.payload else None, name=args.name))
    except (KeyboardInterrupt, Rejected):
        pass


if __name__ == "__main__":
    main()
