from __future__ import annotations

import asyncio
import time

from PySide6.QtCore import QSettings
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget, QWidget

from ..core.connection import ConnectionManager, ConnectionState
from ..core.pairing import PairedDevice
from .dialogs.call import CallDialog
from .dialogs.pair_device import PairDeviceDialog
from .pages import DialpadPage, PicturesPage, PortPage, SmsPage
from .sidebar import Sidebar
from .state_style import STATE_LABEL


def _ago(ts: float) -> str:
    if not ts:
        return "never"
    secs = int(time.time() - ts)
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 86400:
        return f"{secs // 3600} h ago"
    return time.strftime("%b %d", time.localtime(ts))


class MainWindow(QMainWindow):
    def __init__(self, manager: ConnectionManager):
        super().__init__()
        self.manager = manager
        self._settings = QSettings()
        self._pair_dialog: PairDeviceDialog | None = None
        self.call_dialog = CallDialog(self)
        self.setWindowTitle("PortNoir")
        self.resize(1100, 720)
        self.setMinimumSize(820, 520)

        self.sidebar = Sidebar()
        self.stack = QStackedWidget()
        self.pages = [PortPage(), PicturesPage(), SmsPage(), DialpadPage()]
        for page in self.pages:
            self.stack.addWidget(page)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.sidebar)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        file_menu = self.menuBar().addMenu("File")
        add = file_menu.addAction("Add Device…")
        add.setShortcut(QKeySequence.New)
        add.triggered.connect(self.open_pair_dialog)

        self.sidebar.page_changed.connect(self.stack.setCurrentIndex)
        self.sidebar.device_selected.connect(self._on_device_selected)
        self.sidebar.add_device_requested.connect(self.open_pair_dialog)
        self.sidebar.forget_requested.connect(self._confirm_forget)
        self.pages[3].preview_call_requested.connect(
            lambda: self.call_dialog.show_incoming("Alex Morgan", "+81 90 1234 5678"))
        manager.devices_changed.connect(self.refresh_devices)
        manager.state_changed.connect(lambda *_: self.refresh_devices())
        manager.server_error.connect(lambda msg: self.sidebar.set_status(msg))
        self.refresh_devices()

    # ---- helpers ---------------------------------------------------------
    def _describe(self, device: PairedDevice) -> str:
        if self.manager.state_of(device.id) is ConnectionState.CONNECTED:
            return f"Connected on {device.last_ip}"
        return f"Offline, last seen {_ago(device.last_seen)}"

    def refresh_devices(self) -> None:
        devices = self.manager.devices()
        selected = self.sidebar.current_device_id() or self._settings.value("last_device", type=str)
        if selected not in {d.id for d in devices}:
            selected = devices[0].id if devices else None
        entries = [(d.id, d.name, self.manager.state_of(d.id)) for d in devices]
        self.sidebar.set_devices(entries, selected)
        device = next((d for d in devices if d.id == selected), None)
        if device:
            self._settings.setValue("last_device", device.id)
            status = self._describe(device)
            header = f"{device.name} ({STATE_LABEL[self.manager.state_of(device.id)].lower()})"
        else:
            status, header = "Add a phone to get started", "No device selected"
        self.sidebar.set_status(status)
        for page in self.pages:
            page.set_device_text(header)

    def _on_device_selected(self, _device_id: str) -> None:
        self.refresh_devices()

    def open_pair_dialog(self) -> None:
        self._pair_dialog = PairDeviceDialog(self.manager, self)
        self._pair_dialog.open()

    def _confirm_forget(self, device_id: str) -> None:
        device = self.manager.store.get(device_id)
        if device is None:
            return
        box = QMessageBox.question(self, "Forget device", f"Forget {device.name}? "
                                   "You will need to scan a new code to pair it again.")
        if box == QMessageBox.Yes:
            asyncio.ensure_future(self.manager.forget(device_id))
