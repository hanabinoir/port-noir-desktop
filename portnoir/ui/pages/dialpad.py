from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QPushButton

from ..icons import Icons, icon
from .placeholder import PlaceholderPage


class DialpadPage(PlaceholderPage):
    TITLE = "Dialpad"
    ICON = Icons.DIALPAD
    BLURB = "Dial, answer and hang up calls from your Mac. Call audio stays on the phone."
    preview_call_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        btn = QPushButton("  Preview call window")
        btn.setIcon(icon(Icons.CALL, color="#E7E9EE"))
        btn.clicked.connect(self.preview_call_requested)
        self.body.addWidget(btn, 0, Qt.AlignHCenter)
