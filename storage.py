from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class EventStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    camera_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    score REAL NOT NULL,
                    snapshot_path TEXT,
                    message TEXT
                )
                """
            )

    def add_event(
        self,
        camera_name: str,
        status: str,
        score: float,
        snapshot_path: str | None = None,
        message: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events (created_at, camera_name, status, score, snapshot_path, message) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    camera_name,
                    status,
                    float(score),
                    snapshot_path,
                    message,
                ),
            )

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = min(max(limit, 1), 200)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, camera_name, status, score, snapshot_path, message FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
