import os
import socket
import time
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from portnoir.core.pairing import local_ip
from portnoir.ui.dialogs.pair_device import PairDeviceDialog


class DummyManager:
    def __init__(self):
        self.port = 8765
        self.calls = 0

    def new_pairing_payload(self):
        self.calls += 1
        return {"host": "10.0.0.5", "port": self.port}

    @property
    def device_paired(self):
        return None


def test_tick_uses_cached_host_without_recomputing_payload():
    app = QApplication.instance() or QApplication([])
    manager = DummyManager()
    dlg = PairDeviceDialog.__new__(PairDeviceDialog)
    dlg.manager = manager
    dlg._payload_json = '{"v":1}'
    dlg._expires = time.time() + 30
    dlg._host = "10.0.0.5"
    dlg.info = type("Info", (), {"setText": lambda self, text: setattr(self, "text", text)})()

    dlg._tick()

    assert manager.calls == 0
    assert "10.0.0.5:8765" in dlg.info.text
    app.quit()


def test_local_ip_prefers_private_lan_address_over_loopback():
    fake_socket = mock.MagicMock()
    fake_socket.getsockname.return_value = ("127.0.0.1",)
    fake_socket.__enter__ = mock.MagicMock(return_value=fake_socket)
    fake_socket.__exit__ = mock.MagicMock(return_value=None)

    with mock.patch("socket.socket", return_value=fake_socket), \
         mock.patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_DGRAM, 0, '', ('192.168.1.42', 0))]):
        assert local_ip() == "192.168.1.42"

