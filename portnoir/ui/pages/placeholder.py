from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ... import theme
from ..icons import icon


class PlaceholderPage(QWidget):
    """Shared layout for pages that arrive in later milestones."""
    TITLE, ICON, BLURB = "", "", ""

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        title = QLabel(self.TITLE)
        title.setObjectName("PageTitle")
        self.subtitle = QLabel("No device selected")
        self.subtitle.setObjectName("PageSubtitle")
        lay.addWidget(title)
        lay.addWidget(self.subtitle)
        lay.addStretch(1)
        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        glyph = QLabel()
        glyph.setPixmap(icon(self.ICON, color=theme.GLYPH).pixmap(72, 72))
        glyph.setAlignment(Qt.AlignCenter)
        blurb = QLabel(self.BLURB)
        blurb.setObjectName("Muted")
        blurb.setAlignment(Qt.AlignCenter)
        blurb.setWordWrap(True)
        self.body.addWidget(glyph)
        self.body.addWidget(blurb)
        lay.addLayout(self.body)
        lay.addStretch(2)

    def set_device_text(self, text: str) -> None:
        self.subtitle.setText(text)
