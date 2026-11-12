"""Managing your own places: listing, renaming and deleting."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from _loader import load_script

import cheebot.db as db_module
from cheebot import i18n, repo
from cheebot.app import build_application
from cheebot.config import Settings
from cheebot.identity import hash_user_id

dev_sim = load_script("dev_sim")

ME = 4242
SOMEONE_ELSE = 999


@pytest.fixture
def conn(tmp_path: Path):
    database = db_module.Database(tmp_path / "test.db")
    database.init_schema()
    with database.connect() as connection:
        yield connection


def make_settings(db_path: Path) -> Settings:
    return Settings(
        bot_token="123456:TEST-TOKEN-NOT-REAL",
        db_path=db_path,
        default_radius_m=1_000,
        max_radius_m=25_000,
        results_limit=5,
        dedupe_radius_m=30,
        report_hide_threshold=3,
        daily_share_limit=10,
        user_hash_salt="test-salt",
        default_language="en",
    )


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #


def test_toilets_added_by_lists_only_mine_newest_first(
    conn: sqlite3.Connection,
) -> None:
    first = repo.insert_toilet(conn, name="Mine A", lat=0.0, lon=0.0, added_by="me")
    second = repo.insert_toilet(conn, name="Mine B", lat=0.0, lon=0.0, added_by="me")
    repo.insert_toilet(conn, name="Theirs", lat=0.0, lon=0.0, added_by="other")
    repo.insert_toilet(conn, name="Imported", lat=0.0, lon=0.0, source="osm")

    names = [row["name"] for row in repo.toilets_added_by(conn, "me")]

    assert names == ["Mine B", "Mine A"]
    assert [first, second] == sorted([first, second])
    assert repo.toilets_added_by(conn, "nobody") == []


def test_toilets_added_by_hides_hidden_rows(conn: sqlite3.Connection) -> None:
    toilet_id = repo.insert_toilet(conn, name="Hidden", lat=0, lon=0, added_by="me")
    conn.execute("UPDATE toilets SET status = 'hidden' WHERE id = ?", (toilet_id,))

    assert repo.toilets_added_by(conn, "me") == []


def test_toilets_added_by_respects_the_limit(conn: sqlite3.Connection) -> None:
    for i in range(5):
        repo.insert_toilet(conn, name=f"Mine {i}", lat=0, lon=0, added_by="me")

    assert len(repo.toilets_added_by(conn, "me", limit=2)) == 2


def test_delete_requires_ownership(conn: sqlite3.Connection) -> None:
    toilet_id = repo.insert_toilet(conn, name="Mine", lat=0, lon=0, added_by="me")

    assert repo.delete_toilet(conn, toilet_id, "someone-else") is False
    assert repo.get_toilet(conn, toilet_id) is not None

    assert repo.delete_toilet(conn, toilet_id, "me") is True
    assert repo.get_toilet(conn, toilet_id) is None


def test_delete_takes_ratings_and_reports_with_it(conn: sqlite3.Connection) -> None:
    toilet_id = repo.insert_toilet(conn, name="Mine", lat=0, lon=0, added_by="me")
    repo.rate_toilet(conn, toilet_id, "rater", 4)
    repo.report_toilet(conn, toilet_id, "reporter")

    repo.delete_toilet(conn, toilet_id, "me")

    assert conn.execute("SELECT COUNT(*) AS n FROM ratings").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM reports").fetchone()["n"] == 0


def test_rename_requires_ownership(conn: sqlite3.Connection) -> None:
    toilet_id = repo.insert_toilet(conn, name="Old", lat=0, lon=0, added_by="me")

    assert repo.rename_toilet(conn, toilet_id, "New", "someone-else") is False
    assert repo.get_toilet(conn, toilet_id)["name"] == "Old"

    assert repo.rename_toilet(conn, toilet_id, "New", "me") is True
    assert repo.get_toilet(conn, toilet_id)["name"] == "New"


def test_get_owned_toilet_checks_the_owner(conn: sqlite3.Connection) -> None:
    toilet_id = repo.insert_toilet(conn, name="Mine", lat=0, lon=0, added_by="me")

    assert repo.get_owned_toilet(conn, toilet_id, "me") is not None
    assert repo.get_owned_toilet(conn, toilet_id, "other") is None


# --------------------------------------------------------------------------- #
# Flow, through the real dispatcher
# --------------------------------------------------------------------------- #


@pytest.fixture
def app(tmp_path: Path):
    return build_application(make_settings(tmp_path / "dev.db"))


def owner_hash(app, user_id: int = ME) -> str:
    return hash_user_id(app.bot_data["settings"].user_hash_salt, user_id)


def add_toilet(app, name: str = "My WC", user_id: int = ME) -> int:
    with app.bot_data["db"].connect() as conn:
        return repo.insert_toilet(
            conn,
            name=name,
            lat=16.775,
            lon=96.158,
            added_by=owner_hash(app, user_id),
        )


def session(app, lines: list[str], capsys, user_id: int = ME) -> str:
    simulator = dev_sim.Simulator(app, chat_id=user_id, language_code="en")

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


def stored_name(app, toilet_id: int) -> str | None:
    with app.bot_data["db"].connect() as conn:
        row = repo.get_toilet(conn, toilet_id)
    return row["name"] if row is not None else None


def test_my_places_is_empty_for_a_new_user(app, capsys) -> None:
    output = session(app, ["/mine"], capsys)

    assert i18n.t("en", "mine_empty") in output


def test_my_places_lists_only_my_additions(app, capsys) -> None:
    add_toilet(app, "Mine A")
    add_toilet(app, "Theirs", user_id=SOMEONE_ELSE)

    output = session(app, ["/mine"], capsys)

    assert "Mine A" in output
    assert "Theirs" not in output


def test_my_places_offers_manage_buttons(app, capsys) -> None:
    toilet_id = add_toilet(app)

    output = session(app, ["/mine"], capsys)

    assert f"cb ren:{toilet_id}" in output
    assert f"cb del:{toilet_id}" in output


def test_the_button_on_the_menu_opens_the_list(app, capsys) -> None:
    add_toilet(app)

    output = session(app, [i18n.t("en", "menu_mine")], capsys)

    assert dev_sim.plain(i18n.t("en", "mine_header")) in output


def test_delete_asks_first_and_then_removes(app, capsys) -> None:
    toilet_id = add_toilet(app)

    output = session(app, [f"cb del:{toilet_id}", f"cb del:ok:{toilet_id}"], capsys)

    assert "can't be undone" in output
    assert i18n.t("en", "deleted") in output
    assert stored_name(app, toilet_id) is None


def test_cancelling_a_delete_keeps_the_place(app, capsys) -> None:
    toilet_id = add_toilet(app, "Keep me")
    session(app, [f"cb del:{toilet_id}"], capsys)

    output = session(app, [f"cb del:no:{toilet_id}"], capsys)

    # The card comes back in its original form; the row was never touched.
    assert "Keep me" in output
    assert stored_name(app, toilet_id) == "Keep me"


def test_deleting_twice_says_it_is_already_gone(app, capsys) -> None:
    toilet_id = add_toilet(app)
    session(app, [f"cb del:{toilet_id}", f"cb del:ok:{toilet_id}"], capsys)

    output = session(app, [f"cb del:ok:{toilet_id}"], capsys)

    assert i18n.t("en", "not_found") in output


def test_cannot_delete_someone_elses_place(app, capsys) -> None:
    toilet_id = add_toilet(app, "Theirs", user_id=SOMEONE_ELSE)

    output = session(app, [f"cb del:{toilet_id}", f"cb del:ok:{toilet_id}"], capsys)

    assert i18n.t("en", "not_yours") in output
    assert stored_name(app, toilet_id) == "Theirs"


def test_rename_updates_the_name(app, capsys) -> None:
    toilet_id = add_toilet(app, "Old name")

    output = session(app, [f"cb ren:{toilet_id}", "New name"], capsys)

    assert i18n.t("en", "ask_new_name") in output
    assert "Renamed to New name" in output
    assert stored_name(app, toilet_id) == "New name"


def test_cancelling_a_rename_changes_nothing(app, capsys) -> None:
    toilet_id = add_toilet(app, "Old name")

    session(app, [f"cb ren:{toilet_id}", i18n.t("en", "menu_cancel")], capsys)
    session(app, ["something else"], capsys)

    assert stored_name(app, toilet_id) == "Old name"


def test_cannot_rename_someone_elses_place(app, capsys) -> None:
    toilet_id = add_toilet(app, "Theirs", user_id=SOMEONE_ELSE)

    output = session(app, [f"cb ren:{toilet_id}", "Hijacked"], capsys)

    assert i18n.t("en", "not_yours") in output
    assert stored_name(app, toilet_id) == "Theirs"


def test_the_row_disappears_from_the_map(app, capsys) -> None:
    toilet_id = add_toilet(app, "Riverside WC")
    assert "Riverside WC" in session(app, ["/find riverside"], capsys)

    session(app, [f"cb del:{toilet_id}", f"cb del:ok:{toilet_id}"], capsys)

    assert "Riverside WC" not in session(app, ["/find riverside"], capsys)


def test_a_rename_is_whitespace_normalised(app, capsys) -> None:
    toilet_id = add_toilet(app, "Old name")

    session(app, [f"cb ren:{toilet_id}", "  New   name  "], capsys)

    assert stored_name(app, toilet_id) == "New name"
