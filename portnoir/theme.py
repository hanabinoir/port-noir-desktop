"""Dark theme (default). All colours live here so a light theme can be added later."""
from __future__ import annotations

from string import Template

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

BG = "#0E0F12"
SURFACE = "#15171C"
SURFACE_ALT = "#1C1F26"
BORDER = "#2A2E37"
TEXT = "#E7E9EE"
TEXT_MUTED = "#8D93A1"
GLYPH = "#3A3F4B"
ACCENT = "#C8577A"        # port wine
ACCENT_HOVER = "#D8698B"
ACCENT_DIM = "rgba(200, 87, 122, 0.20)"
OK = "#3DDC97"
WARN = "#F2B84B"
ERR = "#F25F5C"
OFFLINE = "#5B6070"

_QSS = Template("""
* { font-size: 13px; }
QMainWindow, QDialog { background: $BG; }
#Sidebar { background: $SURFACE; border-right: 1px solid $BORDER; }
#Brand { font-size: 18px; font-weight: 700; color: $TEXT; }
#Caption { color: $TEXT_MUTED; font-size: 12px; font-weight: 600; }
#Muted { color: $TEXT_MUTED; }
#PageTitle { font-size: 22px; font-weight: 700; }
#PageSubtitle { color: $TEXT_MUTED; }
QComboBox { background: $SURFACE_ALT; border: 1px solid $BORDER; border-radius: 8px; padding: 7px 10px; }
QComboBox:hover { border-color: $ACCENT; }
QComboBox:disabled { color: $TEXT_MUTED; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: $SURFACE_ALT; border: 1px solid $BORDER; outline: none;
    selection-background-color: $ACCENT_DIM; selection-color: $TEXT; padding: 4px; }
QListWidget#Nav { background: transparent; border: none; outline: none; }
QListWidget#Nav::item { padding: 10px 12px; margin: 2px 0; border-radius: 8px; color: $TEXT_MUTED; }
QListWidget#Nav::item:hover { background: $SURFACE_ALT; color: $TEXT; }
QListWidget#Nav::item:selected { background: $ACCENT_DIM; color: $TEXT; }
QPushButton { background: $SURFACE_ALT; border: 1px solid $BORDER; border-radius: 8px; padding: 8px 14px; }
QPushButton:hover { border-color: $ACCENT; }
QPushButton:disabled { color: $TEXT_MUTED; }
QPushButton#primary { background: $ACCENT; border: none; color: white; font-weight: 600; }
QPushButton#primary:hover { background: $ACCENT_HOVER; }
QPushButton#success { background: $OK; border: none; color: $BG; font-weight: 600; }
QPushButton#danger { background: $ERR; border: none; color: white; font-weight: 600; }
QToolButton { background: transparent; border: none; border-radius: 6px; padding: 6px; }
QToolButton:hover { background: $SURFACE_ALT; }
QToolButton::menu-indicator { image: none; }
QMenu { background: $SURFACE_ALT; border: 1px solid $BORDER; padding: 4px; }
QMenu::item { padding: 6px 18px; border-radius: 4px; }
QMenu::item:selected { background: $ACCENT_DIM; }
QToolTip { background: $SURFACE_ALT; color: $TEXT; border: 1px solid $BORDER; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: $BORDER; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
""")


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    roles = {
        QPalette.Window: BG, QPalette.WindowText: TEXT, QPalette.Base: SURFACE,
        QPalette.AlternateBase: SURFACE_ALT, QPalette.Text: TEXT, QPalette.Button: SURFACE_ALT,
        QPalette.ButtonText: TEXT, QPalette.ToolTipBase: SURFACE_ALT, QPalette.ToolTipText: TEXT,
        QPalette.PlaceholderText: TEXT_MUTED, QPalette.Highlight: ACCENT,
        QPalette.HighlightedText: "#FFFFFF", QPalette.Link: ACCENT_HOVER,
    }
    for role, color in roles.items():
        pal.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(TEXT_MUTED))
    app.setPalette(pal)
    app.setStyleSheet(_QSS.safe_substitute(globals()))
