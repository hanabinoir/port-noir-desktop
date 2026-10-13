from __future__ import annotations

import asyncio
import logging
import sys

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from .core.connection import ConnectionManager
from .theme import apply_dark_theme
from .ui.main_window import MainWindow


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("PortNoir")
    app.setOrganizationName("PortNoir")
    apply_dark_theme(app)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    closing = asyncio.Event()
    app.aboutToQuit.connect(closing.set)

    async def run() -> None:
        manager = ConnectionManager()
        await manager.start()
        window = MainWindow(manager)
        window.show()
        await closing.wait()
        await manager.stop()

    with loop:
        loop.run_until_complete(run())


if __name__ == "__main__":
    main()
