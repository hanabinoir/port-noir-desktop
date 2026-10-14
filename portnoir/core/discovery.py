"""Advertise the Mac on the LAN so paired phones can find it again (mDNS / Bonjour)."""
from __future__ import annotations

import logging
import re
import socket

from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

from .protocol import SERVICE_TYPE

log = logging.getLogger(__name__)


class Advertiser:
    def __init__(self) -> None:
        self._azc: AsyncZeroconf | None = None
        self._info: ServiceInfo | None = None

    async def start(self, mac_id: str, name: str, ip: str, port: int, fingerprint: str,
                    transfer_port: int = 0) -> None:
        safe = (re.sub(r"[^A-Za-z0-9-]", "-", name)[:32] or "mac") + "-" + mac_id[:6]
        self._info = ServiceInfo(
            SERVICE_TYPE, f"{safe}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(ip)], port=port,
            properties={"v": "1", "id": mac_id, "name": name, "fp": fingerprint[:16],
                        "https_port": str(transfer_port)},
            server=f"{safe}.local.")
        self._azc = AsyncZeroconf()
        await self._azc.async_register_service(self._info)
        log.info("Advertising %s on %s:%d", safe, ip, port)

    async def stop(self) -> None:
        if self._azc:
            if self._info:
                await self._azc.async_unregister_service(self._info)
            await self._azc.async_close()
            self._azc = self._info = None
