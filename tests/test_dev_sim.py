"""Tests for the local dev simulator.

These go through the real dispatcher, so they also cover the handler
registration in ``app.py`` — including the detail that Telegram marks commands
with a ``bot_command`` entity.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from _loader import load_script

from cheebot import repo
from cheebot.app import build_application

dev_sim = load_script("dev_sim")


@pytest.fixture
def app(tmp_path: Path):
    return build_application(dev_sim.dev_settings(tmp_path / "dev.db"))


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


def add_toilet(app, name: str = "Riverside WC") -> int:
    with app.bot_data["db"].connect() as conn:
        return repo.insert_toilet(conn, name=name, lat=16.775, lon=96.158)


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def test_commands_are_sent_as_message_text() -> None:
    item = dev_sim.parse_line("/start")

    assert item is not None
    assert (item.kind, item.text) == ("message", "/start")


def test_plain_text_is_a_message() -> None:
    assert dev_sim.parse_line("hello there").text == "hello there"


def test_location_line_is_parsed() -> None:
    item = dev_sim.parse_line("loc 16.7750 96.1580")

    assert item is not None
    assert item.kind == "location"
    assert (item.lat, item.lon) == (16.775, 96.158)


@pytest.mark.parametrize(
    "line", ["loc", "loc 16.7", "loc a b", "loc 91 0", "loc 0 181", "cb", "cb   "]
)
def test_bad_input_is_rejected(line: str) -> None:
    with pytest.raises(ValueError):
        dev_sim.parse_line(line)


def test_blank_lines_are_ignored() -> None:
    assert dev_sim.parse_line("   ") is None


@pytest.mark.parametrize("word", ["quit", "exit", "q", "QUIT"])
def test_quit_words(word: str) -> None:
    assert dev_sim.parse_line(word).kind == "quit"


def test_callback_and_inline_lines() -> None:
    assert dev_sim.parse_line("cb dup:new").data == "dup:new"
    assert dev_sim.parse_line("inline yangon").text == "yangon"


# --------------------------------------------------------------------------- #
# Telegram payload fidelity
# --------------------------------------------------------------------------- #


def test_commands_carry_a_bot_command_entity(app) -> None:
    """Without this entity PTB routes /start to the text handler instead."""
    simulator = dev_sim.Simulator(app)

    update = simulator.build(dev_sim.parse_line("/start"))
    plain = simulator.build(dev_sim.parse_line("hello"))

    assert update.effective_message.entities[0].type == "bot_command"
    assert update.effective_message.entities[0].length == len("/start")
    assert not plain.effective_message.entities


def test_dev_settings_never_uses_a_real_token(tmp_path: Path) -> None:
    """A dev tool must not pick up a production token from the environment."""
    settings = dev_sim.dev_settings(tmp_path / "dev.db")

    assert settings.bot_token == dev_sim.DEV_TOKEN
    assert settings.db_path == tmp_path / "dev.db"


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #


def test_start_reaches_the_command_handler(app, capsys) -> None:
    output = session(app, ["/start"], capsys)

    assert "Welcome to cheebot" in output
    assert "I didn't get that" not in output


def test_plain_text_falls_back_to_the_help_hint(app, capsys) -> None:
    output = session(app, ["just some text"], capsys)

    assert "I didn't get that" in output


def test_deep_link_opens_a_specific_toilet(app, capsys) -> None:
    toilet_id = add_toilet(app)

    output = session(app, [f"/start t_{toilet_id}"], capsys)

    assert "Riverside WC" in output


def test_find_command_searches(app, capsys) -> None:
    add_toilet(app)

    output = session(app, ["/find riverside"], capsys)

    assert "Riverside WC" in output


def test_nearest_flow_through_routing(app, capsys) -> None:
    add_toilet(app)

    output = session(app, ["/nearest", "loc 16.7751 96.1581"], capsys)

    assert "Send me your location" in output
    assert "Riverside WC" in output


def test_share_flow_through_routing_saves_a_toilet(app, capsys) -> None:
    output = session(
        app,
        ["/share", "loc 16.7000 96.1000", "Brand new toilet", "count"],
        capsys,
    )

    assert "Add a toilet" in output
    assert "Added" in output
    assert "1 toilets" in output
    with app.bot_data["db"].connect() as conn:
        assert repo.search_by_text(conn, "Brand new")[0]["name"] == "Brand new toilet"


def test_duplicate_prompt_and_different_place_button(app, capsys) -> None:
    existing = add_toilet(app)

    output = session(
        app,
        [
            "/share",
            "loc 16.77501 96.15801",  # ~1 m from the existing toilet
            "cb dup:new",
            "Second toilet",
        ],
        capsys,
    )

    assert "already on the map" in output
    assert f"cb dup:same:{existing}" in output
    assert "Second toilet" in output
    with app.bot_data["db"].connect() as conn:
        assert repo.count_toilets(conn) == 2


def test_report_button_hides_after_enough_users(app, capsys) -> None:
    toilet_id = add_toilet(app)
    simulator = dev_sim.Simulator(app, language_code="en")

    async def _inner() -> None:
        await simulator.start()
        try:
            for user_id in (1, 2, 3):
                simulator.user_id = user_id
                await simulator.handle(dev_sim.parse_line(f"cb report:{toilet_id}"))
        finally:
            await simulator.stop()

    asyncio.run(_inner())
    output = capsys.readouterr().out

    assert "Reported" in output
    with app.bot_data["db"].connect() as conn:
        assert repo.get_active_toilet(conn, toilet_id) is None


def test_inline_query_through_routing(app, capsys) -> None:
    add_toilet(app)

    output = session(app, ["inline riverside"], capsys)

    assert "1 result(s)" in output
    assert "Riverside WC" in output
