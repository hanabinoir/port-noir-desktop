from __future__ import annotations

import asyncio
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PortPage(QWidget):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.device_id: str | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        title = QLabel("Port")
        title.setObjectName("PageTitle")
        self.subtitle = QLabel("No device selected")
        self.subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(self.subtitle)
        self.messages = QListWidget()
        self.messages.setObjectName("ChatMessages")
        self.messages.itemDoubleClicked.connect(self._open_file)
        layout.addWidget(self.messages, 1)
        controls = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Write a message")
        self.input.returnPressed.connect(self._send_text)
        self.attach = QPushButton("Attach")
        self.attach.clicked.connect(self._choose_file)
        self.send = QPushButton("Send")
        self.send.clicked.connect(self._send_text)
        controls.addWidget(self.input, 1)
        controls.addWidget(self.attach)
        controls.addWidget(self.send)
        layout.addLayout(controls)

    def set_device_text(self, text: str) -> None:
        self.subtitle.setText(text)

    def set_device(self, device_id: str | None) -> None:
        self.device_id = device_id
        self.refresh()

    def refresh(self) -> None:
        self.messages.clear()
        if not self.device_id:
            self.input.setEnabled(False)
            self.attach.setEnabled(False)
            self.send.setEnabled(False)
            return
        self.input.setEnabled(True)
        self.attach.setEnabled(True)
        self.send.setEnabled(True)
        for message in self.manager.chat_store.history(self.device_id):
            if message["type"] == "chat.text":
                text = message["body"]
            else:
                transfer = message.get("transfer_state") or ("sent" if message["delivered"] else "sending")
                text = f'File: {message["name"]} ({message["size"]:,} bytes) - {transfer}'
            direction = "You" if message["direction"] == "outgoing" else "Phone"
            delivery = "" if message["type"] == "chat.file" or message["delivered"] else " (sending)"
            item = QListWidgetItem(f"{direction}{delivery}: {text}")
            item.setData(Qt.UserRole, message["id"])
            self.messages.addItem(item)
        self.messages.scrollToBottom()

    def _send_text(self) -> None:
        body = self.input.text().strip()
        if not body or not self.device_id:
            return
        self.input.clear()
        asyncio.ensure_future(self.manager.send_chat_text(self.device_id, body))
        self.refresh()

    def _choose_file(self) -> None:
        if not self.device_id:
            return
        name, _ = QFileDialog.getOpenFileName(self, "Send file")
        if name:
            asyncio.ensure_future(self.manager.send_chat_file(self.device_id, Path(name)))
            self.refresh()

    def _open_file(self, item: QListWidgetItem) -> None:
        if not self.device_id:
            return
        message = next(
            (row for row in self.manager.chat_store.history(self.device_id)
             if row["id"] == item.data(Qt.UserRole)),
            None,
        )
        if not message or message["type"] != "chat.file":
            return
        blob = self.manager.chat_store.blob(self.device_id, message["blob"])
        if blob:
            QDesktopServices.openUrl(QUrl.fromLocalFile(blob["path"]))
