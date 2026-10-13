from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu,
                               QPushButton, QToolButton, QVBoxLayout, QWidget)

from ..core.connection import ConnectionState
from .icons import Icons, dot_icon, icon
from .state_style import STATE_COLOR

NAV_ITEMS = [("Port", Icons.PORT), ("Pictures", Icons.PICTURES), ("SMS", Icons.SMS), ("Dialpad", Icons.DIALPAD)]


class Sidebar(QWidget):
    page_changed = Signal(int)
    device_selected = Signal(str)
    add_device_requested = Signal()
    forget_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(248)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 20, 16, 16)
        root.setSpacing(6)

        brand = QLabel("PortNoir")
        brand.setObjectName("Brand")
        root.addWidget(brand)
        root.addSpacing(16)

        root.addWidget(self._caption("Device"))
        row = QHBoxLayout()
        row.setSpacing(4)
        self.combo = QComboBox()
        self.combo.setIconSize(QSize(10, 10))
        self.combo.currentIndexChanged.connect(self._on_combo)
        row.addWidget(self.combo, 1)
        self.more = QToolButton()
        self.more.setIcon(icon(Icons.MORE))
        self.more.setToolTip("Device options")
        self.more.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.more)
        menu.addAction(icon(Icons.FORGET, color="#E7E9EE"), "Forget this device").triggered.connect(
            lambda: self.current_device_id() and self.forget_requested.emit(self.current_device_id()))
        self.more.setMenu(menu)
        row.addWidget(self.more)
        root.addLayout(row)

        self.status = QLabel("Add a phone to get started")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        root.addSpacing(18)
        root.addWidget(self._caption("Features"))
        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setIconSize(QSize(20, 20))
        self.nav.setFocusPolicy(Qt.NoFocus)
        for label, name in NAV_ITEMS:
            self.nav.addItem(QListWidgetItem(icon(name), label))
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self.page_changed)
        root.addWidget(self.nav, 1)

        self.add_btn = QPushButton("  Add device")
        self.add_btn.setObjectName("primary")
        self.add_btn.setIcon(icon(Icons.ADD_DEVICE, color="#FFFFFF"))
        self.add_btn.clicked.connect(self.add_device_requested)
        root.addWidget(self.add_btn)

    @staticmethod
    def _caption(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Caption")
        return label

    def current_device_id(self) -> str | None:
        return self.combo.currentData()

    def set_devices(self, entries: list[tuple[str, str, ConnectionState]], selected: str | None) -> None:
        self.combo.blockSignals(True)
        self.combo.clear()
        has = bool(entries)
        if has:
            for device_id, name, state in entries:
                self.combo.addItem(dot_icon(STATE_COLOR[state]), name, device_id)
            self.combo.setCurrentIndex(max(0, self.combo.findData(selected)))
        else:
            self.combo.addItem("No devices")
        self.combo.setEnabled(has)
        self.more.setEnabled(has)
        self.combo.blockSignals(False)

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def _on_combo(self, _index: int) -> None:
        if (device_id := self.current_device_id()):
            self.device_selected.emit(device_id)
