"""Persistent chat history and file metadata."""
from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path


class ChatStore:
    def __init__(self, database: Path, files_dir: Path):
        self.files_dir = files_dir
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(database)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                type TEXT NOT NULL,
                ts INTEGER NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                mime TEXT NOT NULL DEFAULT '',
                size INTEGER NOT NULL DEFAULT 0,
                blob TEXT NOT NULL DEFAULT '',
                delivered INTEGER NOT NULL DEFAULT 0,
                transfer_state TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS messages_device_ts ON messages(device_id, ts, id);
            CREATE TABLE IF NOT EXISTS blobs (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                name TEXT NOT NULL,
                mime TEXT NOT NULL,
                size INTEGER NOT NULL,
                path TEXT NOT NULL,
                state TEXT NOT NULL
            );
            """
        )
        columns = {row["name"] for row in self._db.execute("PRAGMA table_info(messages)")}
        if "transfer_state" not in columns:
            self._db.execute("ALTER TABLE messages ADD COLUMN transfer_state TEXT NOT NULL DEFAULT ''")
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def add_message(self, device_id: str, message: dict, direction: str) -> None:
        kind = str(message.get("type", ""))
        self._db.execute(
            """INSERT OR IGNORE INTO messages
               (id, device_id, direction, type, ts, body, name, mime, size, blob, delivered)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(message["id"]), device_id, direction, kind, int(message.get("ts") or time.time() * 1000),
             str(message.get("body", "")), str(message.get("name", "")), str(message.get("mime", "")),
             int(message.get("size") or 0), str(message.get("blob", "")),
             int(direction == "incoming")),
        )
        self._db.commit()

    def history(self, device_id: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM messages WHERE device_id=? ORDER BY ts, rowid", (device_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def pending(self, device_id: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM messages WHERE device_id=? AND direction='outgoing' AND delivered=0 "
            "ORDER BY ts, rowid", (device_id,)
        ).fetchall()
        return [self._to_protocol(row) for row in rows]

    @staticmethod
    def _to_protocol(row: sqlite3.Row) -> dict:
        message = {"v": 1, "id": row["id"], "type": row["type"], "ts": row["ts"]}
        if row["type"] == "chat.text":
            message["body"] = row["body"]
        else:
            message.update(name=row["name"], mime=row["mime"], size=row["size"], blob=row["blob"])
        return message

    def acknowledge(self, device_id: str, message_id: str) -> None:
        self._db.execute(
            "UPDATE messages SET delivered=1 WHERE device_id=? AND id=?",
            (device_id, message_id),
        )
        self._db.commit()

    def set_transfer_state(self, device_id: str, blob_id: str, state: str) -> None:
        self._db.execute(
            "UPDATE messages SET transfer_state=? WHERE device_id=? AND blob=?",
            (state, device_id, blob_id),
        )
        self._db.commit()

    def prepare_outgoing_blob(self, device_id: str, blob_id: str, name: str,
                              mime: str, source: Path) -> Path:
        target = self.files_dir / f"{blob_id}{Path(name).suffix[:32]}"
        shutil.copyfile(source, target)
        self._db.execute(
            "INSERT OR REPLACE INTO blobs VALUES (?, ?, ?, ?, ?, ?, 'ready')",
            (blob_id, device_id, name, mime, target.stat().st_size, str(target)),
        )
        self._db.commit()
        return target

    def begin_upload(self, device_id: str, blob_id: str, name: str, mime: str, size: int) -> Path:
        row = self._db.execute("SELECT * FROM blobs WHERE id=?", (blob_id,)).fetchone()
        if row:
            if row["device_id"] != device_id or row["size"] != size:
                raise ValueError("blob metadata does not match the existing transfer")
            return Path(row["path"])
        part = self.files_dir / f"{blob_id}.part"
        self._db.execute(
            "INSERT INTO blobs VALUES (?, ?, ?, ?, ?, ?, 'uploading')",
            (blob_id, device_id, name, mime, size, str(part)),
        )
        self._db.commit()
        return part

    def complete_upload(self, device_id: str, blob_id: str) -> Path:
        row = self._db.execute(
            "SELECT * FROM blobs WHERE id=? AND device_id=?", (blob_id, device_id)
        ).fetchone()
        if row is None:
            raise ValueError("unknown upload")
        path = Path(row["path"])
        if path.name.endswith(".part"):
            final_path = self.files_dir / f'{blob_id}{Path(row["name"]).suffix[:32]}'
            path.replace(final_path)
            path = final_path
        self._db.execute("UPDATE blobs SET path=?, state='ready' WHERE id=?",
                         (str(path), blob_id))
        self._db.commit()
        return path

    def blob(self, device_id: str, blob_id: str) -> dict | None:
        row = self._db.execute(
            "SELECT * FROM blobs WHERE id=? AND device_id=? AND state='ready'",
            (blob_id, device_id),
        ).fetchone()
        return dict(row) if row else None

    def upload(self, device_id: str, blob_id: str) -> dict | None:
        row = self._db.execute(
            "SELECT * FROM blobs WHERE id=? AND device_id=?",
            (blob_id, device_id),
        ).fetchone()
        return dict(row) if row else None
