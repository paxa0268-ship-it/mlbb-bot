"""SQLite: foydalanuvchilar, kunlik limit, quiz natijalari. Hamma chaqiruv alohida thread'da bajariladi."""
from __future__ import annotations

import asyncio
import functools
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

TASHKENT = timezone(timedelta(hours=5))


def today() -> str:
    return datetime.now(TASHKENT).strftime("%Y-%m-%d")


def _threaded(fn):
    @functools.wraps(fn)
    async def wrapper(self, *args, **kwargs):
        def call():
            with self._lock:
                return fn(self, *args, **kwargs)

        return await asyncio.to_thread(call)

    return wrapper


class Database:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._init()

    def _init(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                joined_at   TEXT NOT NULL,
                last_seen   TEXT NOT NULL,
                requests    INTEGER NOT NULL DEFAULT 0,
                quiz_total  INTEGER NOT NULL DEFAULT 0,
                quiz_right  INTEGER NOT NULL DEFAULT 0,
                blocked     INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS usage (
                user_id INTEGER NOT NULL,
                day     TEXT NOT NULL,
                count   INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, day)
            );
            """
        )
        self._conn.commit()

    @_threaded
    def upsert_user(self, user_id: int, username: str | None, first_name: str | None) -> bool:
        """Foydalanuvchini saqlaydi. Yangi bo'lsa True qaytaradi."""
        now = datetime.now(TASHKENT).isoformat(timespec="seconds")
        row = self._conn.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row:
            self._conn.execute(
                "UPDATE users SET username=?, first_name=?, last_seen=?, blocked=0 WHERE user_id=?",
                (username, first_name, now, user_id),
            )
            is_new = False
        else:
            self._conn.execute(
                "INSERT INTO users (user_id, username, first_name, joined_at, last_seen) VALUES (?,?,?,?,?)",
                (user_id, username, first_name, now, now),
            )
            is_new = True
        self._conn.commit()
        return is_new

    @_threaded
    def get_user(self, user_id: int) -> dict | None:
        row = self._conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    @_threaded
    def inc_usage(self, user_id: int) -> int:
        day = today()
        self._conn.execute(
            "INSERT INTO usage (user_id, day, count) VALUES (?,?,1) "
            "ON CONFLICT(user_id, day) DO UPDATE SET count = count + 1",
            (user_id, day),
        )
        self._conn.execute("UPDATE users SET requests = requests + 1 WHERE user_id=?", (user_id,))
        self._conn.commit()
        return self._conn.execute(
            "SELECT count FROM usage WHERE user_id=? AND day=?", (user_id, day)
        ).fetchone()["count"]

    @_threaded
    def get_usage(self, user_id: int) -> int:
        row = self._conn.execute(
            "SELECT count FROM usage WHERE user_id=? AND day=?", (user_id, today())
        ).fetchone()
        return row["count"] if row else 0

    @_threaded
    def add_quiz_result(self, user_id: int, correct: bool) -> None:
        self._conn.execute(
            "UPDATE users SET quiz_total = quiz_total + 1, quiz_right = quiz_right + ? WHERE user_id=?",
            (1 if correct else 0, user_id),
        )
        self._conn.commit()

    @_threaded
    def mark_blocked(self, user_id: int) -> None:
        self._conn.execute("UPDATE users SET blocked=1 WHERE user_id=?", (user_id,))
        self._conn.commit()

    @_threaded
    def broadcast_targets(self) -> list[int]:
        rows = self._conn.execute("SELECT user_id FROM users WHERE blocked=0").fetchall()
        return [r["user_id"] for r in rows]

    @_threaded
    def stats(self) -> dict:
        c = self._conn
        day = today()
        return {
            "users": c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"],
            "blocked": c.execute("SELECT COUNT(*) n FROM users WHERE blocked=1").fetchone()["n"],
            "active_today": c.execute("SELECT COUNT(*) n FROM usage WHERE day=?", (day,)).fetchone()["n"],
            "requests_today": c.execute(
                "SELECT COALESCE(SUM(count),0) n FROM usage WHERE day=?", (day,)
            ).fetchone()["n"],
            "requests_total": c.execute("SELECT COALESCE(SUM(requests),0) n FROM users").fetchone()["n"],
            "quiz_total": c.execute("SELECT COALESCE(SUM(quiz_total),0) n FROM users").fetchone()["n"],
            "quiz_right": c.execute("SELECT COALESCE(SUM(quiz_right),0) n FROM users").fetchone()["n"],
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()
