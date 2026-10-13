"""WebSocket server for phones, per-device connection state and signals for the UI.

Direction of connection: the phone is the client. It finds the Mac via mDNS (or the
last known address), authenticates with its stored key and keeps retrying with
backoff. The Mac only has to listen, advertise and notice when a session ends.
Liveness uses WebSocket ping/pong (every 5 s, dead after 10 s without a pong).
"""
from __future__ import annotations

import asyncio
import logging
import socket
import ssl
import time
from enum import Enum

from PySide6.QtCore import QObject, Signal
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from . import protocol as P
from .discovery import Advertiser
from .pairing import DeviceStore, Identity, PairedDevice, PairingService, data_dir, local_ip

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
    server_error = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        directory = data_dir()
        self.identity = Identity.load_or_create(directory)
        self.store = DeviceStore(directory / "devices.json")
        self.pairing = PairingService(self.identity, self.store)
        self.advertiser = Advertiser()
        self.host_name = socket.gethostname().split(".")[0]
        self.port = P.DEFAULT_PORT
        self._server = None
        self._sessions: dict[str, ServerConnection] = {}

    # ---- lifecycle -------------------------------------------------------
    async def start(self) -> None:
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
            self.server_error.emit(f"Ports {P.DEFAULT_PORT}-{P.DEFAULT_PORT + 9} are all in use.")
            return
        try:
            await self.advertiser.start(self.identity.mac_id, self.host_name, local_ip(),
                                        self.port, self.identity.fingerprint)
        except Exception as exc:  # no network yet, mDNS blocked, ...
            log.warning("mDNS advertising failed: %s", exc)
            self.server_error.emit("Automatic reconnect needs a network connection (mDNS unavailable).")

    async def stop(self) -> None:
        for ws in list(self._sessions.values()):
            await ws.close(1001)
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        await self.advertiser.stop()

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
            async for raw in ws:
                try:
                    self.message_received.emit(device.id, P.decode(raw))
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
                                          mac_name=self.host_name)))
            self.device_paired.emit(device_id)
            self.devices_changed.emit()
            return self.store.get(device_id)
        if kind == P.AUTH_HELLO and device_id:
            device = self.pairing.verify(device_id, str(msg.get("key", "")))
            if device is None:
                return await self._reject(ws, "unknown_device")
            await ws.send(P.encode(P.make(P.AUTH_OK, mac_name=self.host_name)))
            return device
        return await self._reject(ws, "bad_handshake")

    @staticmethod
    async def _reject(ws: ServerConnection, reason: str) -> None:
        await ws.send(P.encode(P.make(P.AUTH_ERROR, reason=reason)))
        await ws.close(P.CLOSE_UNAUTHORIZED, reason)
        return None
