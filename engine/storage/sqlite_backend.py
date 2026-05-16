from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Iterable


class SQLiteBackend:
    """
    Persistent storage backend backed by a SQLite database.

    Schema
    ------
    events  (id TEXT PRIMARY KEY, ts REAL, service TEXT, kind TEXT, payload TEXT)
    aliases (name TEXT PRIMARY KEY, canonical TEXT)
    roots   (canonical TEXT PRIMARY KEY, root TEXT)

    Pass path=':memory:' for an in-process ephemeral store (useful for testing).
    """

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id      TEXT PRIMARY KEY,
                ts      REAL NOT NULL,
                service TEXT,
                kind    TEXT,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_ts ON events(ts);

            CREATE TABLE IF NOT EXISTS aliases (
                name      TEXT PRIMARY KEY,
                canonical TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS aliases_canonical ON aliases(canonical);

            CREATE TABLE IF NOT EXISTS roots (
                canonical TEXT PRIMARY KEY,
                root      TEXT NOT NULL
            );
        """)
        self._conn.commit()

    # ── Events ────────────────────────────────────────────────────────────────

    def append_event(self, event: dict) -> None:
        eid = event.get("id") or f"__auto_{uuid.uuid4().hex[:8]}"
        ts = float(event.get("ts", 0.0))
        service = event.get("service") or ""
        kind = event.get("kind") or ""
        payload = json.dumps(event)
        self._conn.execute(
            "INSERT OR REPLACE INTO events (id, ts, service, kind, payload) VALUES (?, ?, ?, ?, ?)",
            (eid, ts, service, kind, payload),
        )
        self._conn.commit()

    def get_event(self, event_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT payload FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def events_in_window(self, end_ts: float, seconds_before: float) -> list[dict]:
        start_ts = end_ts - seconds_before
        rows = self._conn.execute(
            "SELECT payload FROM events WHERE ts >= ? AND ts <= ? ORDER BY ts",
            (start_ts, end_ts),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def all_events(self) -> Iterable[dict]:
        cur = self._conn.execute("SELECT payload FROM events ORDER BY ts")
        for (payload,) in cur:
            yield json.loads(payload)

    def count_events(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    # ── Alias map ─────────────────────────────────────────────────────────────

    def set_alias(self, name: str, canonical: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO aliases (name, canonical) VALUES (?, ?)",
            (name, canonical),
        )
        self._conn.commit()

    def get_alias(self, name: str) -> str | None:
        row = self._conn.execute(
            "SELECT canonical FROM aliases WHERE name = ?", (name,)
        ).fetchone()
        return row[0] if row else None

    def remove_alias(self, name: str) -> None:
        self._conn.execute("DELETE FROM aliases WHERE name = ?", (name,))
        self._conn.commit()

    def get_members(self, canonical: str) -> set[str]:
        rows = self._conn.execute(
            "SELECT name FROM aliases WHERE canonical = ?", (canonical,)
        ).fetchall()
        return {r[0] for r in rows}

    def all_aliases(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT name, canonical FROM aliases").fetchall()
        return {r[0]: r[1] for r in rows}

    # ── Root map ──────────────────────────────────────────────────────────────

    def set_root(self, canonical: str, root: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO roots (canonical, root) VALUES (?, ?)",
            (canonical, root),
        )
        self._conn.commit()

    def get_root(self, canonical: str) -> str | None:
        row = self._conn.execute(
            "SELECT root FROM roots WHERE canonical = ?", (canonical,)
        ).fetchone()
        return row[0] if row else None

    def remove_root(self, canonical: str) -> None:
        self._conn.execute("DELETE FROM roots WHERE canonical = ?", (canonical,))
        self._conn.commit()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def clear(self) -> None:
        self._conn.executescript("""
            DELETE FROM events;
            DELETE FROM aliases;
            DELETE FROM roots;
        """)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
