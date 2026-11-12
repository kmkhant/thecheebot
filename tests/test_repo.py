from __future__ import annotations

import sqlite3

import pytest

from cheebot import repo
from cheebot.db import Database


@pytest.fixture
def conn(tmp_path):
    database = Database(tmp_path / "test.db")
    database.init_schema()
    with database.connect() as connection:
        yield connection


def add(
    conn: sqlite3.Connection,
    name: str = "Public toilet",
    lat: float = 0.0,
    lon: float = 0.0,
    **kwargs,
) -> int:
    return repo.insert_toilet(conn, name=name, lat=lat, lon=lon, **kwargs)


def test_insert_and_read_back(conn: sqlite3.Connection) -> None:
    toilet_id = add(conn, name="Central Station WC", lat=52.52, lon=13.405)

    toilet = repo.get_toilet(conn, toilet_id)
    assert toilet is not None
    assert toilet["name"] == "Central Station WC"
    assert toilet["lat"] == pytest.approx(52.52)
    assert toilet["lon"] == pytest.approx(13.405)
    assert toilet["status"] == "active"
    assert toilet["source"] == "user"
    assert toilet["created_at"]


def test_nearest_is_ordered_by_distance(conn: sqlite3.Connection) -> None:
    far = add(conn, "Far", lat=0.01)  # ~1.1 km
    near = add(conn, "Near", lat=0.001)  # ~111 m
    middle = add(conn, "Middle", lat=0.005)  # ~557 m

    ranked = repo.nearest_toilets(conn, 0.0, 0.0, radius_m=5_000, limit=5)

    assert [row["id"] for row, _ in ranked] == [near, middle, far]
    assert ranked[0][1] == pytest.approx(111, rel=0.05)


def test_nearest_respects_radius(conn: sqlite3.Connection) -> None:
    add(conn, "Just outside", lat=0.02)  # ~2.2 km

    assert repo.nearest_toilets(conn, 0.0, 0.0, radius_m=1_000) == []


def test_nearest_skips_hidden_toilets(conn: sqlite3.Connection) -> None:
    toilet_id = add(conn, lat=0.001)
    conn.execute("UPDATE toilets SET status = 'hidden' WHERE id = ?", (toilet_id,))

    assert repo.nearest_toilets(conn, 0.0, 0.0, radius_m=5_000) == []


def test_nearest_handles_the_antimeridian(conn: sqlite3.Connection) -> None:
    add(conn, "Across the line", lat=0.0, lon=179.9999)

    ranked = repo.nearest_toilets(conn, 0.0, -179.9999, radius_m=1_000)

    assert len(ranked) == 1


def test_nearest_limit_is_applied(conn: sqlite3.Connection) -> None:
    for i in range(10):
        add(conn, f"WC {i}", lat=0.0001 * (i + 1))

    assert len(repo.nearest_toilets(conn, 0.0, 0.0, radius_m=5_000, limit=3)) == 3


def test_find_within_matches_close_and_ignores_far(conn: sqlite3.Connection) -> None:
    add(conn, "Existing", lat=0.0001)  # ~11 m away

    match = repo.find_within(conn, 0.0, 0.0, radius_m=30)
    assert match is not None
    assert match[0]["name"] == "Existing"

    assert repo.find_within(conn, 0.0, 0.0, radius_m=5) is None


def test_search_matches_name_and_address(conn: sqlite3.Connection) -> None:
    add(conn, "Riverside WC", address="12 Mill Lane")
    add(conn, "Market Hall", address="Riverside Road")

    names = {row["name"] for row in repo.search_by_text(conn, "riverside")}

    assert names == {"Riverside WC", "Market Hall"}


def test_search_treats_wildcards_literally(conn: sqlite3.Connection) -> None:
    add(conn, "100% Clean")
    add(conn, "Plain")

    assert len(repo.search_by_text(conn, "100%")) == 1
    assert repo.search_by_text(conn, "100_") == []


def test_search_skips_hidden_toilets(conn: sqlite3.Connection) -> None:
    toilet_id = add(conn, "Gone")
    conn.execute("UPDATE toilets SET status = 'hidden' WHERE id = ?", (toilet_id,))

    assert repo.search_by_text(conn, "Gone") == []


def test_reporting_hides_after_threshold(conn: sqlite3.Connection) -> None:
    toilet_id = add(conn)

    counted, hidden, count = repo.report_toilet(
        conn, toilet_id, "user-a", hide_threshold=3
    )
    assert (counted, hidden, count) == (True, False, 1)

    repo.report_toilet(conn, toilet_id, "user-b", hide_threshold=3)
    counted, hidden, count = repo.report_toilet(
        conn, toilet_id, "user-c", hide_threshold=3
    )

    assert (counted, hidden, count) == (True, True, 3)
    assert repo.get_active_toilet(conn, toilet_id) is None


def test_reporting_twice_from_one_user_counts_once(conn: sqlite3.Connection) -> None:
    toilet_id = add(conn)

    repo.report_toilet(conn, toilet_id, "user-a", hide_threshold=3)
    counted, hidden, count = repo.report_toilet(
        conn, toilet_id, "user-a", hide_threshold=3
    )

    assert (counted, hidden, count) == (False, False, 1)


def test_confirm_toilet_increments_counter(conn: sqlite3.Connection) -> None:
    toilet_id = add(conn)

    repo.confirm_toilet(conn, toilet_id)

    toilet = repo.get_toilet(conn, toilet_id)
    assert toilet is not None
    assert toilet["confirmations"] == 1


def test_submission_rate_limit_counts_recent_only(conn: sqlite3.Connection) -> None:
    repo.log_submission(conn, "user-a")
    repo.log_submission(conn, "user-a")
    repo.log_submission(conn, "user-b")
    conn.execute(
        "INSERT INTO submissions (user_hash, created_at) VALUES (?, ?)",
        ("user-a", repo.hours_ago(48)),
    )

    assert repo.count_submissions_since(conn, "user-a", repo.hours_ago(24)) == 2


def test_osm_import_is_idempotent(conn: sqlite3.Connection) -> None:
    first_id, created = repo.upsert_osm_toilet(
        conn, osm_id="node/1", name="Old name", lat=1.0, lon=2.0
    )
    assert created is True

    second_id, created_again = repo.upsert_osm_toilet(
        conn, osm_id="node/1", name="New name", lat=1.5, lon=2.5
    )

    assert created_again is False
    assert second_id == first_id
    assert repo.count_toilets(conn) == 1
    toilet = repo.get_toilet(conn, first_id)
    assert toilet is not None
    assert toilet["name"] == "New name"
    assert toilet["lat"] == pytest.approx(1.5)
    assert toilet["source"] == "osm"


def test_failed_write_rolls_back(tmp_path) -> None:
    """The connect() context manager must not leave half-applied batches."""
    database = Database(tmp_path / "rollback.db")
    database.init_schema()

    with pytest.raises(sqlite3.IntegrityError), database.connect() as conn:
        repo.insert_toilet(conn, name="Should vanish", lat=1.0, lon=2.0)
        # name is NOT NULL, so this second statement fails.
        conn.execute(
            "INSERT INTO toilets (name, lat, lon, created_at) "
            "VALUES (NULL, 0, 0, 'now')"
        )

    with database.connect() as conn:
        assert repo.count_toilets(conn) == 0
