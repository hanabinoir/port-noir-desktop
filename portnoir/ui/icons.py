"""Material Design Icons via qtawesome (the 'mdi6' set). Missing names never crash the UI."""
from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from .. import theme


class Icons:
    PORT = "mdi6.swap-horizontal-circle-outline"
    PICTURES = "mdi6.image-multiple-outline"
    SMS = "mdi6.message-text-outline"
    DIALPAD = "mdi6.dialpad"
    ADD_DEVICE = "mdi6.qrcode-scan"
    MORE = "mdi6.dots-vertical"
    FORGET = "mdi6.link-off"
    REFRESH = "mdi6.refresh"
    COPY = "mdi6.content-copy"
    CALL = "mdi6.phone"
    HANGUP = "mdi6.phone-hangup"
    PERSON = "mdi6.account-circle-outline"


def icon(name: str, color: str = theme.TEXT_MUTED, selected: str = theme.ACCENT) -> QIcon:
    try:
        return qta.icon(name, color=color, color_active=theme.TEXT, color_selected=selected)
    except Exception:
        return QIcon()


def dot_icon(color: str, size: int = 10) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(0, 0, size, size)
    p.end()
    return QIcon(pm)
