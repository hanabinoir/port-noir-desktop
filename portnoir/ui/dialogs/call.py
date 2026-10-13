from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ... import theme
from ..icons import Icons, icon


class CallDialog(QDialog):
    """Separate always-on-top call window. Wired to real call events in Milestone 5."""
    answer_clicked = Signal()
    hangup_clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Call")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setFixedSize(320, 430)
        self._elapsed = 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 32, 28, 28)
        lay.setSpacing(6)

        avatar = QLabel()
        avatar.setPixmap(icon(Icons.PERSON, color=theme.GLYPH).pixmap(96, 96))
        avatar.setAlignment(Qt.AlignCenter)
        self.name = QLabel("Unknown")
        self.name.setObjectName("PageTitle")
        self.number = QLabel("")
        self.number.setObjectName("Muted")
        self.state = QLabel("Incoming call")
        note = QLabel("Audio plays on the phone")
        note.setObjectName("Muted")
        for w in (self.name, self.number, self.state, note):
            w.setAlignment(Qt.AlignCenter)

        row = QHBoxLayout()
        row.setSpacing(16)
        self.answer_btn = QPushButton("  Answer")
        self.answer_btn.setObjectName("success")
        self.answer_btn.setIcon(icon(Icons.CALL, color=theme.BG))
        self.hangup_btn = QPushButton("  Hang up")
        self.hangup_btn.setObjectName("danger")
        self.hangup_btn.setIcon(icon(Icons.HANGUP, color="#FFFFFF"))
        row.addWidget(self.answer_btn)
        row.addWidget(self.hangup_btn)

        lay.addWidget(avatar)
        lay.addWidget(self.name)
        lay.addWidget(self.number)
        lay.addSpacing(10)
        lay.addWidget(self.state)
        lay.addStretch(1)
        lay.addWidget(note)
        lay.addSpacing(8)
        lay.addLayout(row)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.answer_btn.clicked.connect(self._on_answer)
        self.hangup_btn.clicked.connect(self._on_hangup)

    def show_incoming(self, name: str, number: str) -> None:
        self.name.setText(name or "Unknown caller")
        self.number.setText(number)
        self.state.setText("Incoming call")
        self.answer_btn.show()
        self._timer.stop()
        self.show()
        self.raise_()
        self.activateWindow()

    def set_active(self) -> None:
        self.answer_btn.hide()
        self._elapsed = 0
        self._tick()
        self._timer.start(1000)

    def _tick(self) -> None:
        self.state.setText(f"{self._elapsed // 60:02d}:{self._elapsed % 60:02d}")
        self._elapsed += 1

    def _on_answer(self) -> None:
        self.answer_clicked.emit()
        self.set_active()

    def _on_hangup(self) -> None:
        self.hangup_clicked.emit()
        self._timer.stop()
        self.close()
