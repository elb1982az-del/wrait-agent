"""Local SQLite audit log for every Wraith decision and command."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict


def db_path() -> str:
    home = os.environ.get("HOME") or os.getcwd()
    return os.path.join(home, "wraith_audit.db")


def init_db() -> None:
    with sqlite3.connect(db_path()) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                level TEXT NOT NULL,
                command TEXT,
                output TEXT,
                allowed INTEGER,
                dry_run INTEGER,
                target TEXT,
                detail TEXT
            )"""
        )
        conn.commit()


def log(event: Dict[str, Any]) -> None:
    init_db()
    with sqlite3.connect(db_path()) as conn:
        conn.execute(
            """INSERT INTO events
               (ts, level, command, output, allowed, dry_run, target, detail)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                time.time(),
                str(event.get("level", "info")),
                event.get("command"),
                event.get("output"),
                1 if event.get("allowed") else 0,
                1 if event.get("dry_run") else 0,
                event.get("target"),
                json.dumps(event.get("detail", {}), ensure_ascii=False),
            ),
        )
        conn.commit()


def recent(limit: int = 200) -> list:
    init_db()
    with sqlite3.connect(db_path()) as conn:
        rows = conn.execute(
            "SELECT ts, level, command, allowed, dry_run, target, detail FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "ts": row[0], "level": row[1], "command": row[2],
            "allowed": bool(row[3]), "dry_run": bool(row[4]),
            "target": row[5], "detail": row[6],
        }
        for row in rows
    ]
