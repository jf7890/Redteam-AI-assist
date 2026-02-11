from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Any


class SQLiteCache:
    """A tiny SQLite-backed key-value cache.

    - Process-safe (SQLite handles cross-process locking).
    - Optional TTL per entry.
    - Stores values as JSON strings.

    This is intentionally minimal for an internal MVP++ deployment.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # One connection per process.
        self._conn = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              created_at REAL NOT NULL,
              expires_at REAL
            );
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at);")
        self._conn.commit()

        self._lock = Lock()

    def get_json(self, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            row = self._conn.execute("SELECT value, expires_at FROM cache WHERE key=?", (key,)).fetchone()
            if not row:
                return None
            value, expires_at = row
            if expires_at is not None and float(expires_at) < now:
                self._conn.execute("DELETE FROM cache WHERE key=?", (key,))
                self._conn.commit()
                return None

        try:
            return json.loads(value)
        except Exception:
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        now = time.time()
        expires_at = now + ttl_seconds if ttl_seconds else None
        payload = json.dumps(value, ensure_ascii=True, separators=(",", ":"))

        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache(key,value,created_at,expires_at) VALUES(?,?,?,?)",
                (key, payload, now, expires_at),
            )
            self._conn.commit()

    def prune(self, max_entries: int | None = None) -> None:
        """Remove expired entries and optionally cap the cache size."""

        now = time.time()
        with self._lock:
            self._conn.execute(
                "DELETE FROM cache WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )

            if max_entries is not None:
                row = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()
                count = int(row[0]) if row else 0
                if count > max_entries:
                    to_delete = count - max_entries
                    self._conn.execute(
                        "DELETE FROM cache WHERE key IN (SELECT key FROM cache ORDER BY created_at ASC LIMIT ?)",
                        (to_delete,),
                    )

            self._conn.commit()
