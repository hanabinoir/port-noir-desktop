from __future__ import annotations

import io
import json
import time

import qrcode
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...core.connection import ConnectionManager
from ...core.pairing import TOKEN_TTL
from ..icons import Icons, icon


class PairDeviceDialog(QDialog):
    def __init__(self, manager: ConnectionManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.manager = manager
        self._payload_json = ""
        self._expires = 0.0
        self.setWindowTitle("Add device")
        self.setFixedWidth(400)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(12)
        title = QLabel("Pair an Android phone")
        title.setObjectName("PageTitle")
        steps = QLabel("On your phone, open PortNoir, go to Port, tap Add device and scan this code. "
                       "Both devices need to be on the same Wi-Fi network.")
        steps.setObjectName("Muted")
        steps.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(steps)

        self.qr = QLabel()
        self.qr.setFixedSize(280, 280)
        self.qr.setAlignment(Qt.AlignCenter)
        self.qr.setStyleSheet("background: white; border-radius: 14px;")
        lay.addWidget(self.qr, 0, Qt.AlignHCenter)

        self.info = QLabel()
        self.info.setObjectName("Muted")
        self.info.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.info)

        row = QHBoxLayout()
        refresh = QPushButton("  New code")
        refresh.setIcon(icon(Icons.REFRESH, color="#E7E9EE"))
        refresh.clicked.connect(self._regenerate)
        copy = QPushButton("  Copy code data")
        copy.setIcon(icon(Icons.COPY, color="#E7E9EE"))
        copy.setToolTip("For testing with the mock phone")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self._payload_json))
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addWidget(refresh)
        row.addWidget(copy)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        manager.device_paired.connect(self._on_paired)
        self.finished.connect(self._timer.stop)
        self._regenerate()
        self._timer.start(1000)

    def _regenerate(self) -> None:
        payload = self.manager.new_pairing_payload()
        self._payload_json = json.dumps(payload, separators=(",", ":"))
        self._expires = time.time() + TOKEN_TTL
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
        qr.add_data(self._payload_json)
        qr.make(fit=True)
        buf = io.BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
        pm = QPixmap()
        pm.loadFromData(buf.getvalue())
        self.qr.setPixmap(pm.scaled(256, 256, Qt.KeepAspectRatio, Qt.FastTransformation))
        self._tick()

    def _tick(self) -> None:
        left = int(self._expires - time.time())
        if left <= 0:
            self._regenerate()
            return
        self.info.setText(f"This Mac: {self.manager.new_pairing_payload()['host']}:{self.manager.port}\n"
                          f"Code refreshes in {left} s")

    def _on_paired(self, _device_id: str) -> None:
        self._timer.stop()
        self.info.setText("Paired. You can close this window.")
        QTimer.singleShot(700, self.accept)
