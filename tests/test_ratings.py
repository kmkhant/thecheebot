"""1-5 star ratings: storage, migration, card copy and the bot flow."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from _loader import load_script

import cheebot.db as db_module
from cheebot import keyboards, repo, texts
from cheebot.app import build_application

dev_sim = load_script("dev_sim")


@pytest.fixture
def conn(tmp_path: Path):
    database = db_module.Database(tmp_path / "test.db")
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


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #


def test_unrated_toilet_has_no_summary(conn: sqlite3.Connection) -> None:
    assert repo.rating_summary(conn, add(conn)) is None


def test_first_rating_is_recorded(conn: sqlite3.Connection) -> None:
    toilet_id = add(conn)

    assert repo.rate_toilet(conn, toilet_id, "user-a", 4) is True
    assert repo.rating_summary(conn, toilet_id) == (4.0, 1)


def test_rating_again_replaces_the_score(conn: sqlite3.Connection) -> None:
    toilet_id = add(conn)
    repo.rate_toilet(conn, toilet_id, "user-a", 2)

    assert repo.rate_toilet(conn, toilet_id, "user-a", 5) is False

    # One row, not two: tapping the buttons must not inflate the count.
    assert repo.rating_summary(conn, toilet_id) == (5.0, 1)


def test_average_and_count_span_users(conn: sqlite3.Connection) -> None:
    toilet_id = add(conn)
    for user, score in (("a", 1), ("b", 5), ("c", 3)):
        repo.rate_toilet(conn, toilet_id, user, score)

    average, count = repo.rating_summary(conn, toilet_id)

    assert count == 3
    assert average == pytest.approx(3.0)


@pytest.mark.parametrize("score", [-1, 0, 6])
def test_out_of_range_scores_are_rejected(conn: sqlite3.Connection, score: int) -> None:
    toilet_id = add(conn)

    with pytest.raises(ValueError):
        repo.rate_toilet(conn, toilet_id, "user-a", score)

    assert repo.rating_summary(conn, toilet_id) is None


def test_schema_check_rejects_out_of_range_scores(conn: sqlite3.Connection) -> None:
    toilet_id = add(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO ratings (toilet_id, user_hash, score, created_at, updated_at)"
            " VALUES (?, 'user-a', 6, 'now', 'now')",
            (toilet_id,),
        )


def test_deleting_a_toilet_removes_its_ratings(conn: sqlite3.Connection) -> None:
    toilet_id = add(conn)
    repo.rate_toilet(conn, toilet_id, "user-a", 4)

    conn.execute("DELETE FROM toilets WHERE id = ?", (toilet_id,))

    assert repo.rating_summary(conn, toilet_id) is None
    assert conn.execute("SELECT COUNT(*) AS n FROM ratings").fetchone()["n"] == 0


def test_ratings_for_fetches_many_toilets_in_one_go(conn: sqlite3.Connection) -> None:
    first = add(conn, "First")
    second = add(conn, "Second")
    unrated = add(conn, "Unrated")
    repo.rate_toilet(conn, first, "user-a", 5)
    repo.rate_toilet(conn, second, "user-a", 1)
    repo.rate_toilet(conn, second, "user-b", 3)

    assert repo.ratings_for(conn, [first, second, unrated]) == {
        first: (5.0, 1),
        second: (2.0, 2),
    }
    assert repo.ratings_for(conn, []) == {}


# --------------------------------------------------------------------------- #
# Migration
# --------------------------------------------------------------------------- #


def test_migration_adds_ratings_without_losing_data(tmp_path: Path) -> None:
    """A deployed database sits at version 1; upgrading must keep its rows."""
    path = tmp_path / "v1.db"
    legacy = sqlite3.connect(path)
    legacy.row_factory = sqlite3.Row
    legacy.executescript(db_module._INITIAL)
    legacy.execute("PRAGMA user_version = 1")
    legacy.execute(
        "INSERT INTO toilets (name, lat, lon, created_at)"
        " VALUES ('Old WC', 16.775, 96.158, '2024-01-01T00:00:00+00:00')"
    )
    legacy.commit()
    legacy.close()

    database = db_module.Database(path)
    database.init_schema()

    with database.connect() as conn:
        assert (
            conn.execute("PRAGMA user_version").fetchone()[0]
            == db_module.SCHEMA_VERSION
        )
        assert repo.count_toilets(conn) == 1
        assert repo.rate_toilet(conn, 1, "user-a", 5) is True
        assert repo.rating_summary(conn, 1) == (5.0, 1)


def test_running_the_migration_twice_is_harmless(tmp_path: Path) -> None:
    path = tmp_path / "twice.db"
    database = db_module.Database(path)

    database.init_schema()
    database.init_schema()

    with database.connect() as conn:
        assert (
            conn.execute("PRAGMA user_version").fetchone()[0]
            == db_module.SCHEMA_VERSION
        )


# --------------------------------------------------------------------------- #
# Card copy and keyboard
# --------------------------------------------------------------------------- #


def test_describe_shows_the_average_and_count(conn: sqlite3.Connection) -> None:
    toilet = repo.get_toilet(conn, add(conn, address="12 Mill Lane"))

    described = texts.describe("en", toilet, rating=(4.2, 7))

    assert "★4.2 (7)" in described
    assert "12 Mill Lane" in described


def test_describe_omits_the_rating_when_unrated(conn: sqlite3.Connection) -> None:
    toilet = repo.get_toilet(conn, add(conn))

    assert "★" not in texts.describe("en", toilet)


def test_toilet_actions_offer_five_rating_buttons() -> None:
    markup = keyboards.toilet_actions("en", 7, 16.775, 96.158)

    data = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]

    assert [item for item in data if item.startswith("rate:")] == [
        f"rate:7:{score}" for score in range(1, 6)
    ]
    assert "report:7" in data


# --------------------------------------------------------------------------- #
# Flow, through the real dispatcher
# --------------------------------------------------------------------------- #


@pytest.fixture
def app(tmp_path: Path):
    return build_application(dev_sim.dev_settings(tmp_path / "dev.db"))


def add_toilet(app, name: str = "Riverside WC") -> int:
    with app.bot_data["db"].connect() as conn:
        return repo.insert_toilet(conn, name=name, lat=16.775, lon=96.158)


def summary(app, toilet_id: int) -> tuple[float, int] | None:
    with app.bot_data["db"].connect() as conn:
        return repo.rating_summary(conn, toilet_id)


def session(app, lines: list[str], capsys) -> str:
    """Feed terminal lines through the real application and return the output."""
    simulator = dev_sim.Simulator(app, language_code="en")

    async def _inner() -> None:
        await simulator.start()
        try:
            for line in lines:
                item = dev_sim.parse_line(line)
                assert item is not None, line
                await simulator.handle(item)
        finally:
            await simulator.stop()

    asyncio.run(_inner())
    return capsys.readouterr().out


def test_cards_show_a_rating_button_row(app, capsys) -> None:
    toilet_id = add_toilet(app)

    output = session(app, ["/find riverside"], capsys)

    assert f"cb rate:{toilet_id}:5" in output


def test_rating_from_a_card_is_saved(app, capsys) -> None:
    toilet_id = add_toilet(app)

    output = session(app, [f"cb rate:{toilet_id}:5"], capsys)

    assert "Thanks! You rated this ★5." in output
    assert summary(app, toilet_id) == (5.0, 1)


def test_rating_again_updates_instead_of_stacking(app, capsys) -> None:
    toilet_id = add_toilet(app)

    output = session(app, [f"cb rate:{toilet_id}:2", f"cb rate:{toilet_id}:4"], capsys)

    assert "Updated: ★4." in output
    assert summary(app, toilet_id) == (4.0, 1)


def test_card_shows_the_average_after_rating(app, capsys) -> None:
    toilet_id = add_toilet(app)
    session(app, [f"cb rate:{toilet_id}:4"], capsys)

    output = session(app, ["/find riverside"], capsys)

    assert "★4.0 (1)" in output


def test_nearest_cards_carry_the_average(app, capsys) -> None:
    toilet_id = add_toilet(app)
    session(app, [f"cb rate:{toilet_id}:3"], capsys)

    output = session(app, ["/nearest", "loc 16.7751 96.1581"], capsys)

    assert "★3.0 (1)" in output


def test_rating_a_missing_toilet_says_it_is_gone(app, capsys) -> None:
    output = session(app, ["cb rate:9999:5"], capsys)

    assert "no longer on the map" in output


def test_rating_a_hidden_toilet_is_refused(app, capsys) -> None:
    toilet_id = add_toilet(app)
    with app.bot_data["db"].connect() as conn:
        conn.execute("UPDATE toilets SET status = 'hidden' WHERE id = ?", (toilet_id,))

    output = session(app, [f"cb rate:{toilet_id}:5"], capsys)

    assert "no longer on the map" in output
    assert summary(app, toilet_id) is None
