"""All database reads and writes live here, as plain functions over a Connection.

`find_within`, `nearest_toilets` and `search_by_text` are the only places that
know how spatial lookup works, so moving to Postgres/PostGIS later means
rewriting this module and nothing else.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from .geo import bounding_box, haversine_m

Row = sqlite3.Row


def utcnow() -> str:
    """Timestamp in a fixed-width UTC format so string comparison sorts correctly."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def hours_ago(hours: int) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #


def insert_toilet(
    conn: sqlite3.Connection,
    *,
    name: str,
    lat: float,
    lon: float,
    address: str | None = None,
    kind: str = "public",
    is_free: bool | None = None,
    is_accessible: bool | None = None,
    source: str = "user",
    osm_id: str | None = None,
    added_by: str | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO toilets
            (name, lat, lon, address, kind, is_free, is_accessible,
             source, osm_id, added_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            lat,
            lon,
            address,
            kind,
            None if is_free is None else int(is_free),
            None if is_accessible is None else int(is_accessible),
            source,
            osm_id,
            added_by,
            utcnow(),
        ),
    )
    row_id = cursor.lastrowid
    if row_id is None:  # pragma: no cover - SQLite sets this for every INSERT
        raise RuntimeError("insert_toilet did not return a row id")
    return row_id


def upsert_osm_toilet(
    conn: sqlite3.Connection,
    *,
    osm_id: str,
    name: str,
    lat: float,
    lon: float,
    address: str | None = None,
    is_free: bool | None = None,
    is_accessible: bool | None = None,
) -> tuple[int, bool]:
    """Insert or refresh an OSM-sourced toilet. Returns (id, was_created).

    Re-running an import updates coordinates instead of duplicating rows.
    """
    existing = conn.execute(
        "SELECT id FROM toilets WHERE osm_id = ?", (osm_id,)
    ).fetchone()
    if existing is None:
        new_id = insert_toilet(
            conn,
            name=name,
            lat=lat,
            lon=lon,
            address=address,
            is_free=is_free,
            is_accessible=is_accessible,
            source="osm",
            osm_id=osm_id,
        )
        return new_id, True

    conn.execute(
        """
        UPDATE toilets
           SET name = ?, lat = ?, lon = ?, address = ?,
               is_free = ?, is_accessible = ?
         WHERE id = ?
        """,
        (
            name,
            lat,
            lon,
            address,
            None if is_free is None else int(is_free),
            None if is_accessible is None else int(is_accessible),
            existing["id"],
        ),
    )
    return int(existing["id"]), False


def report_toilet(
    conn: sqlite3.Connection,
    toilet_id: int,
    user_hash: str,
    *,
    reason: str | None = None,
    hide_threshold: int = 3,
) -> tuple[bool, bool, int]:
    """Record a report. Returns (counted, hidden_just_now, report_count).

    A user can report the same toilet only once; repeat taps are ignored.
    """
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO reports (toilet_id, user_hash, reason, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (toilet_id, user_hash, reason, utcnow()),
    )
    if cursor.rowcount == 0:
        row = conn.execute(
            "SELECT report_count FROM toilets WHERE id = ?", (toilet_id,)
        ).fetchone()
        return False, False, int(row["report_count"]) if row else 0

    conn.execute(
        "UPDATE toilets SET report_count = report_count + 1 WHERE id = ?",
        (toilet_id,),
    )
    row = conn.execute(
        "SELECT report_count, status FROM toilets WHERE id = ?", (toilet_id,)
    ).fetchone()
    if row is None:
        return True, False, 0

    count = int(row["report_count"])
    if count >= hide_threshold and row["status"] == "active":
        conn.execute("UPDATE toilets SET status = 'hidden' WHERE id = ?", (toilet_id,))
        return True, True, count
    return True, False, count


def confirm_toilet(conn: sqlite3.Connection, toilet_id: int) -> None:
    """A user vouched that this toilet exists (used by the duplicate prompt)."""
    conn.execute(
        "UPDATE toilets SET confirmations = confirmations + 1 WHERE id = ?",
        (toilet_id,),
    )


def rename_toilet(
    conn: sqlite3.Connection, toilet_id: int, name: str, added_by: str
) -> bool:
    """Rename a place, but only one this user added. True if it was applied."""
    cursor = conn.execute(
        "UPDATE toilets SET name = ? WHERE id = ? AND added_by = ?",
        (name, toilet_id, added_by),
    )
    return cursor.rowcount > 0


def delete_toilet(conn: sqlite3.Connection, toilet_id: int, added_by: str) -> bool:
    """Remove a place this user added. True if a row was deleted.

    Ownership is part of the statement, so a forged callback id cannot delete
    somebody else's place. Ratings and reports cascade away with the row.
    """
    cursor = conn.execute(
        "DELETE FROM toilets WHERE id = ? AND added_by = ?", (toilet_id, added_by)
    )
    return cursor.rowcount > 0


def rate_toilet(
    conn: sqlite3.Connection, toilet_id: int, user_hash: str, score: int
) -> bool:
    """Store one user's 1-5 rating. Returns True if this is their first one.

    Rating again replaces the previous score, so the average can't be gamed by
    tapping the same button repeatedly.
    """
    if not 1 <= score <= 5:
        raise ValueError(f"score must be 1-5, got {score}")

    now = utcnow()
    existing = conn.execute(
        "SELECT id FROM ratings WHERE toilet_id = ? AND user_hash = ?",
        (toilet_id, user_hash),
    ).fetchone()
    conn.execute(
        """
        INSERT INTO ratings (toilet_id, user_hash, score, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (toilet_id, user_hash) DO UPDATE SET
            score = excluded.score,
            updated_at = excluded.updated_at
        """,
        (toilet_id, user_hash, score, now, now),
    )
    return existing is None


def log_submission(
    conn: sqlite3.Connection, user_hash: str, toilet_id: int | None = None
) -> None:
    conn.execute(
        "INSERT INTO submissions (user_hash, toilet_id, created_at) VALUES (?, ?, ?)",
        (user_hash, toilet_id, utcnow()),
    )


def set_user_language(conn: sqlite3.Connection, user_hash: str, language: str) -> None:
    """Remember a user's language choice, keyed by the same salted hash as the rest."""
    conn.execute(
        """
        INSERT INTO user_languages (user_hash, language, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT (user_hash) DO UPDATE SET
            language = excluded.language,
            updated_at = excluded.updated_at
        """,
        (user_hash, language, utcnow()),
    )


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #


def get_toilet(conn: sqlite3.Connection, toilet_id: int) -> Row | None:
    return conn.execute("SELECT * FROM toilets WHERE id = ?", (toilet_id,)).fetchone()


def get_active_toilet(conn: sqlite3.Connection, toilet_id: int) -> Row | None:
    return conn.execute(
        "SELECT * FROM toilets WHERE id = ? AND status = 'active'", (toilet_id,)
    ).fetchone()


def get_owned_toilet(
    conn: sqlite3.Connection, toilet_id: int, added_by: str
) -> Row | None:
    """One place, only if this user added it."""
    return conn.execute(
        "SELECT * FROM toilets WHERE id = ? AND added_by = ?",
        (toilet_id, added_by),
    ).fetchone()


def toilets_added_by(
    conn: sqlite3.Connection, added_by: str, limit: int = 20
) -> list[Row]:
    """A user's own contributions, newest first. Hidden places are not listed."""
    return conn.execute(
        """
        SELECT * FROM toilets
         WHERE added_by = ? AND status = 'active'
         ORDER BY id DESC
         LIMIT ?
        """,
        (added_by, limit),
    ).fetchall()


def count_toilets(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM toilets").fetchone()
    return int(row["n"])


def get_user_language(conn: sqlite3.Connection, user_hash: str) -> str | None:
    """The language this user last picked, or None if they never have."""
    row = conn.execute(
        "SELECT language FROM user_languages WHERE user_hash = ?", (user_hash,)
    ).fetchone()
    return row["language"] if row is not None else None


def nearest_toilets(
    conn: sqlite3.Connection,
    lat: float,
    lon: float,
    radius_m: float,
    limit: int = 5,
) -> list[tuple[Row, float]]:
    """Closest active toilets within radius_m, nearest first.

    A bounding-box pre-filter keeps the candidate set small on the index, then
    haversine gives the exact ranking inside the circle.
    """
    min_lat, max_lat, min_lon, max_lon = bounding_box(lat, lon, radius_m)

    if min_lon < -180.0:
        lon_clause, lon_params = "(lon >= ? OR lon <= ?)", (min_lon + 360.0, max_lon)
    elif max_lon > 180.0:
        lon_clause, lon_params = "(lon >= ? OR lon <= ?)", (min_lon, max_lon - 360.0)
    else:
        lon_clause, lon_params = "lon BETWEEN ? AND ?", (min_lon, max_lon)

    rows = conn.execute(
        f"""
        SELECT * FROM toilets
         WHERE status = 'active'
           AND lat BETWEEN ? AND ?
           AND {lon_clause}
        """,
        (min_lat, max_lat, *lon_params),
    ).fetchall()

    ranked = []
    for row in rows:
        distance = haversine_m(lat, lon, row["lat"], row["lon"])
        if distance <= radius_m:
            ranked.append((row, distance))
    ranked.sort(key=lambda item: item[1])
    return ranked[:limit]


def find_within(
    conn: sqlite3.Connection, lat: float, lon: float, radius_m: float
) -> tuple[Row, float] | None:
    """The single closest toilet inside radius_m, if any. Used for dedupe."""
    matches = nearest_toilets(conn, lat, lon, radius_m, limit=1)
    return matches[0] if matches else None


def search_by_text(conn: sqlite3.Connection, query: str, limit: int = 5) -> list[Row]:
    """Case-insensitive substring search over name and address."""
    term = f"%{_escape_like(query)}%"
    return conn.execute(
        r"""
        SELECT * FROM toilets
         WHERE status = 'active'
           AND (name LIKE ? ESCAPE '\' OR address LIKE ? ESCAPE '\')
         ORDER BY name
         LIMIT ?
        """,
        (term, term, limit),
    ).fetchall()


def rating_summary(
    conn: sqlite3.Connection, toilet_id: int
) -> tuple[float, int] | None:
    """(average, count) for one toilet, or None when nobody has rated it yet."""
    row = conn.execute(
        """
        SELECT AVG(score) AS avg_score, COUNT(*) AS n
          FROM ratings
         WHERE toilet_id = ?
        """,
        (toilet_id,),
    ).fetchone()
    if row is None or int(row["n"]) == 0:
        return None
    return float(row["avg_score"]), int(row["n"])


def ratings_for(
    conn: sqlite3.Connection, toilet_ids: list[int]
) -> dict[int, tuple[float, int]]:
    """Batch version of `rating_summary`, so result lists need one query."""
    if not toilet_ids:
        return {}
    placeholders = ", ".join("?" for _ in toilet_ids)
    rows = conn.execute(
        f"""
        SELECT toilet_id, AVG(score) AS avg_score, COUNT(*) AS n
          FROM ratings
         WHERE toilet_id IN ({placeholders})
         GROUP BY toilet_id
        """,
        toilet_ids,
    ).fetchall()
    return {
        int(row["toilet_id"]): (float(row["avg_score"]), int(row["n"])) for row in rows
    }


def count_submissions_since(
    conn: sqlite3.Connection, user_hash: str, since_iso: str
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM submissions
         WHERE user_hash = ? AND created_at >= ?
        """,
        (user_hash, since_iso),
    ).fetchone()
    return int(row["n"])


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
