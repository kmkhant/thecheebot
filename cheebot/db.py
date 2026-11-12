"""SQLite storage: connection handling and schema migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 3

_INITIAL = """
CREATE TABLE IF NOT EXISTS toilets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    lat           REAL    NOT NULL,
    lon           REAL    NOT NULL,
    address       TEXT,
    kind          TEXT    NOT NULL DEFAULT 'public',
    is_free       INTEGER,          -- 1 yes, 0 no, NULL unknown
    is_accessible INTEGER,          -- 1 yes, 0 no, NULL unknown
    source        TEXT    NOT NULL DEFAULT 'user',   -- 'user' | 'osm'
    osm_id        TEXT    UNIQUE,   -- e.g. 'node/123456' from OpenStreetMap
    added_by      TEXT,             -- salted hash, never a real user id
    status        TEXT    NOT NULL DEFAULT 'active',  -- 'active' | 'hidden'
    report_count  INTEGER NOT NULL DEFAULT 0,
    confirmations INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_toilets_lat_lon ON toilets (lat, lon);
CREATE INDEX IF NOT EXISTS idx_toilets_status ON toilets (status);
CREATE INDEX IF NOT EXISTS idx_toilets_name ON toilets (name);

CREATE TABLE IF NOT EXISTS reports (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    toilet_id  INTEGER NOT NULL REFERENCES toilets (id) ON DELETE CASCADE,
    user_hash  TEXT    NOT NULL,
    reason     TEXT,
    created_at TEXT    NOT NULL,
    UNIQUE (toilet_id, user_hash)   -- one report per user per toilet
);

CREATE TABLE IF NOT EXISTS submissions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_hash  TEXT    NOT NULL,
    toilet_id  INTEGER REFERENCES toilets (id) ON DELETE SET NULL,
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_submissions_user ON submissions (user_hash, created_at);
"""

_RATINGS = """
CREATE TABLE IF NOT EXISTS ratings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    toilet_id  INTEGER NOT NULL REFERENCES toilets (id) ON DELETE CASCADE,
    user_hash  TEXT    NOT NULL,
    score      INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    UNIQUE (toilet_id, user_hash)   -- one rating per user per toilet
);

CREATE INDEX IF NOT EXISTS idx_ratings_toilet ON ratings (toilet_id);
"""

_USER_LANGUAGES = """
CREATE TABLE IF NOT EXISTS user_languages (
    user_hash  TEXT PRIMARY KEY,
    language   TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# Append-only: never edit a released entry, or existing databases drift.
MIGRATIONS: list[tuple[int, str]] = [
    (1, _INITIAL),
    (2, _RATINGS),
    (3, _USER_LANGUAGES),
]


class Database:
    """Thin wrapper that opens a short-lived connection per operation.

    SQLite handles this fine for bot-sized workloads and it keeps the code free
    of cross-thread connection juggling.
    """

    def __init__(self, path: str | Path):
        self.path = str(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            # WAL lets the importer write while the bot serves reads.
            conn.execute("PRAGMA journal_mode = WAL")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version >= SCHEMA_VERSION:
                return
            for target, script in MIGRATIONS:
                if version < target:
                    conn.executescript(script)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
