"""Headless check: pair a mock phone, drop it, reconnect it, reject a bad token, grab screenshots.

Run:  QT_QPA_PLATFORM=offscreen python tests/smoke_test.py
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

tmp = tempfile.mkdtemp()
os.environ["XDG_DATA_HOME"] = tmp
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
from qasync import QEventLoop  # noqa: E402

from portnoir.core.connection import ConnectionManager, ConnectionState  # noqa: E402
from portnoir.theme import apply_dark_theme  # noqa: E402
from portnoir.tools.mock_device import Rejected, run_phone  # noqa: E402
from portnoir.ui.dialogs.pair_device import PairDeviceDialog  # noqa: E402
from portnoir.ui.main_window import MainWindow  # noqa: E402

OUT = Path(os.environ.get("SHOT_DIR", tmp))


async def wait_for(manager, state, device_id=None, timeout=8):
    """Poll the real state (signals can fire before we subscribe)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        ids = [device_id] if device_id else [d.id for d in manager.devices()]
        if ids and all(manager.state_of(i) is state for i in ids):
            return ids[0]
        await asyncio.sleep(0.05)
    raise TimeoutError(f"never reached {state}")


async def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName("PortNoirTest")
    app.setApplicationName("PortNoirTest")
    apply_dark_theme(app)
    manager = ConnectionManager()
    await manager.start()
    window = MainWindow(manager)
    window.show()
    window.grab().save(str(OUT / "window_empty.png"))

    dlg = PairDeviceDialog(manager, window)
    dlg.show()
    dlg.grab().save(str(OUT / "pair_dialog.png"))
    dlg.reject()

    phone_file = Path(tmp) / "phone.json"
    payload = manager.new_pairing_payload()
    payload["host"] = "127.0.0.1"
    logs = []
    task = asyncio.create_task(run_phone(phone_file, payload, log=logs.append))
    dev_id = await wait_for(manager, ConnectionState.CONNECTED)
    print("paired + connected:", dev_id, logs)
    await asyncio.sleep(0.3)
    window.grab().save(str(OUT / "window_connected.png"))

    # drop the connection, expect DISCONNECTED, then reconnect with the stored key
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await wait_for(manager, ConnectionState.DISCONNECTED)
    print("disconnected ok")
    task = asyncio.create_task(run_phone(phone_file, None, log=logs.append))
    await wait_for(manager, ConnectionState.CONNECTED)
    print("reconnected with stored key ok")
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await wait_for(manager, ConnectionState.DISCONNECTED)

    # bad token must be rejected
    bad = dict(payload, token="nope")
    try:
        await asyncio.wait_for(run_phone(Path(tmp) / "bad.json", bad, log=logs.append), 5)
    except Rejected as exc:
        print("bad token rejected:", exc)

    # forget -> hello must now be rejected
    await manager.forget(dev_id)
    try:
        await asyncio.wait_for(run_phone(phone_file, None, log=logs.append), 5)
    except Rejected as exc:
        print("forgotten device rejected:", exc)

    await manager.stop()
    print("ALL OK")


app = QApplication(sys.argv)
loop = QEventLoop(app)
asyncio.set_event_loop(loop)
with loop:
    loop.run_until_complete(main())
