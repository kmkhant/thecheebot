"""End-to-end handler tests: real Update objects, mocked Telegram calls.

Only the network boundary is faked, so these cover the actual flow logic —
draft state, duplicate detection, radius widening, deep links, inline mode.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from telegram import Bot, Update, User

from cheebot import repo
from cheebot.app import build_application
from cheebot.config import Settings
from cheebot.handlers import inline, menu, report, router, share
from cheebot.identity import hash_user_id

USER = {"id": 424242, "is_bot": False, "first_name": "Test"}
CHAT = {"id": 424242, "type": "private"}
DATE = 1_700_000_000

BOT_METHODS = (
    "send_message",
    "send_venue",
    "answer_callback_query",
    "answer_inline_query",
    "edit_message_text",
)


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


@pytest.fixture
def app(tmp_path: Path):
    application = build_application(make_settings(tmp_path / "bot.db"))
    # Stand in for the get_me() result that startup normally caches.
    application.bot._bot_user = User(
        id=1, is_bot=True, first_name="cheebot", username="cheebot_test"
    )
    return application


def context_for(app, *, args: list[str] | None = None, user_data: dict | None = None):
    return SimpleNamespace(
        bot=app.bot,
        application=app,
        user_data={} if user_data is None else user_data,
        args=args or [],
    )


def _message(message_id: int, **extra) -> dict:
    return {
        "message_id": message_id,
        "date": DATE,
        "chat": CHAT,
        "from": USER,
        **extra,
    }


def location_update(app, lat: float, lon: float, message_id: int = 10) -> Update:
    return Update.de_json(
        {
            "update_id": message_id,
            "message": _message(
                message_id, location={"latitude": lat, "longitude": lon}
            ),
        },
        app.bot,
    )


def text_update(app, text: str, message_id: int = 11) -> Update:
    return Update.de_json(
        {"update_id": message_id, "message": _message(message_id, text=text)},
        app.bot,
    )


def venue_update(app, lat: float, lon: float, message_id: int = 13) -> Update:
    """A forwarded place, which carries its point in ``venue``, not ``location``."""
    return Update.de_json(
        {
            "update_id": message_id,
            "message": _message(
                message_id,
                venue={
                    "location": {"latitude": lat, "longitude": lon},
                    "title": "Forwarded place",
                    "address": "Somewhere",
                },
            ),
        },
        app.bot,
    )


def callback_update(
    app, data: str, message_id: int = 12, user_id: int = USER["id"]
) -> Update:
    return Update.de_json(
        {
            "update_id": message_id,
            "callback_query": {
                "id": f"cb-{message_id}",
                "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
                "chat_instance": "instance",
                "data": data,
                "message": {
                    "message_id": message_id,
                    "date": DATE,
                    "chat": CHAT,
                    "from": {"id": 1, "is_bot": True, "first_name": "cheebot"},
                    "text": "prompt",
                },
            },
        },
        app.bot,
    )


def inline_update(app, query: str) -> Update:
    return Update.de_json(
        {
            "update_id": 20,
            "inline_query": {
                "id": "iq-1",
                "from": USER,
                "query": query,
                "offset": "",
            },
        },
        app.bot,
    )


def run_handler(coro_fn, *args, **kwargs) -> SimpleNamespace:
    """Run a handler with every outbound Bot call mocked out."""

    async def _inner():
        mocks = SimpleNamespace(
            **{name: AsyncMock(return_value=None) for name in BOT_METHODS}
        )
        patches = [
            patch.object(Bot, name, getattr(mocks, name)) for name in BOT_METHODS
        ]
        for item in patches:
            item.start()
        try:
            await coro_fn(*args, **kwargs)
        finally:
            for item in patches:
                item.stop()
        return mocks

    return asyncio.run(_inner())


def sent_texts(mocks: SimpleNamespace) -> list[str]:
    return [call.kwargs.get("text", "") for call in mocks.send_message.call_args_list]


def add_toilet(app, **kwargs) -> int:
    defaults = {"name": "Existing WC", "lat": 52.52, "lon": 13.405}
    defaults.update(kwargs)
    with app.bot_data["db"].connect() as conn:
        return repo.insert_toilet(conn, **defaults)


def toilet_count(app) -> int:
    with app.bot_data["db"].connect() as conn:
        return repo.count_toilets(conn)


# --------------------------------------------------------------------------- #
# Nearest
# --------------------------------------------------------------------------- #


def test_location_returns_a_venue_card(app) -> None:
    add_toilet(app, name="Central Station WC", lat=52.5201, lon=13.4051)

    mocks = run_handler(
        router.on_location, location_update(app, 52.52, 13.405), context_for(app)
    )

    assert mocks.send_venue.call_count == 1
    payload = mocks.send_venue.call_args.kwargs
    assert payload["title"] == "Central Station WC"
    assert payload["address"].startswith("1")
    assert payload["address"].endswith("m")


def test_search_widens_when_nothing_is_close(app) -> None:
    # ~4 km away: outside the 1 km default, inside the 25 km maximum.
    add_toilet(app, name="Far Away WC", lat=52.556, lon=13.405)

    mocks = run_handler(
        router.on_location, location_update(app, 52.52, 13.405), context_for(app)
    )

    assert mocks.send_venue.call_count == 1
    assert mocks.send_venue.call_args.kwargs["title"] == "Far Away WC"
    assert "widened" in sent_texts(mocks)[0]


def test_no_results_suggests_adding_one(app) -> None:
    mocks = run_handler(
        router.on_location, location_update(app, 52.52, 13.405), context_for(app)
    )

    assert mocks.send_venue.call_count == 0
    assert "/share" in sent_texts(mocks)[0]


def test_location_is_never_stored(app) -> None:
    run_handler(
        router.on_location, location_update(app, 52.52, 13.405), context_for(app)
    )

    assert toilet_count(app) == 0


# --------------------------------------------------------------------------- #
# Share
# --------------------------------------------------------------------------- #


def test_share_flow_saves_a_new_toilet(app) -> None:
    context = context_for(app, user_data={"draft": {"stage": "location"}})

    run_handler(router.on_location, location_update(app, 52.52, 13.405), context)
    assert context.user_data["draft"]["stage"] == "name"

    run_handler(router.on_text, text_update(app, "Corner kiosk toilet"), context)

    assert toilet_count(app) == 1
    assert "draft" not in context.user_data
    with app.bot_data["db"].connect() as conn:
        saved = repo.search_by_text(conn, "Corner kiosk")[0]
    assert saved["name"] == "Corner kiosk toilet"
    assert saved["lat"] == pytest.approx(52.52)


def test_share_prompts_when_a_duplicate_is_nearby(app) -> None:
    existing_id = add_toilet(app, lat=52.52, lon=13.405)
    context = context_for(app, user_data={"draft": {"stage": "location"}})

    mocks = run_handler(
        router.on_location, location_update(app, 52.52001, 13.40501), context
    )

    assert "already on the map" in sent_texts(mocks)[0]
    markup = mocks.send_message.call_args.kwargs["reply_markup"]
    buttons = {button.callback_data for row in markup.inline_keyboard for button in row}
    assert buttons == {f"dup:same:{existing_id}", "dup:new"}
    assert toilet_count(app) == 1


def test_choosing_different_place_creates_a_second_row(app) -> None:
    add_toilet(app, lat=52.52, lon=13.405)
    context = context_for(app, user_data={"draft": {"stage": "location"}})

    run_handler(router.on_location, location_update(app, 52.52001, 13.40501), context)
    run_handler(share.duplicate_callback, callback_update(app, "dup:new"), context)
    run_handler(router.on_text, text_update(app, "Second toilet"), context)

    assert toilet_count(app) == 2


def test_choosing_same_place_counts_a_confirmation(app) -> None:
    existing_id = add_toilet(app, lat=52.52, lon=13.405)
    context = context_for(app, user_data={"draft": {"stage": "location"}})

    run_handler(router.on_location, location_update(app, 52.52001, 13.40501), context)
    run_handler(
        share.duplicate_callback,
        callback_update(app, f"dup:same:{existing_id}"),
        context,
    )

    assert toilet_count(app) == 1
    with app.bot_data["db"].connect() as conn:
        toilet = repo.get_toilet(conn, existing_id)
    assert toilet is not None
    assert toilet["confirmations"] == 1
    assert "draft" not in context.user_data


def test_duplicate_answer_after_the_draft_is_gone_is_handled(app) -> None:
    mocks = run_handler(
        share.duplicate_callback, callback_update(app, "dup:new"), context_for(app)
    )

    assert mocks.edit_message_text.call_count == 1


def test_skipping_the_name_uses_a_default(app) -> None:
    context = context_for(app, user_data={"draft": {"stage": "location"}})

    run_handler(router.on_location, location_update(app, 52.52, 13.405), context)
    run_handler(share.skip_name, text_update(app, "⏭ Skip"), context)

    with app.bot_data["db"].connect() as conn:
        assert repo.search_by_text(conn, "Public toilet")[0]["name"] == "Public toilet"


def test_daily_limit_blocks_further_shares(app) -> None:
    user_hash = hash_user_id("test-salt", USER["id"])
    with app.bot_data["db"].connect() as conn:
        for _ in range(10):
            repo.log_submission(conn, user_hash)

    context = context_for(app)
    mocks = run_handler(share.prompt_share, text_update(app, "➕ Share"), context)

    assert "daily limit" in sent_texts(mocks)[0]
    assert "draft" not in context.user_data


def test_cancel_discards_the_draft(app) -> None:
    context = context_for(app, user_data={"draft": {"stage": "name"}})

    run_handler(menu.cancel, text_update(app, "✖️ Cancel"), context)

    assert "draft" not in context.user_data


def test_abandoning_the_location_step_is_explained(app) -> None:
    context = context_for(app, user_data={"draft": {"stage": "location"}})

    mocks = run_handler(router.on_text, text_update(app, "here"), context)

    assert "/cancel" in sent_texts(mocks)[0]


# --------------------------------------------------------------------------- #
# Adding a toilet somewhere else
# --------------------------------------------------------------------------- #


def test_share_accepts_typed_coordinates(app) -> None:
    context = context_for(app, user_data={"draft": {"stage": "location"}})

    run_handler(router.on_text, text_update(app, "16.7748, 96.1583"), context)
    assert context.user_data["draft"]["stage"] == "name"

    run_handler(router.on_text, text_update(app, "Sule corner"), context)

    with app.bot_data["db"].connect() as conn:
        saved = repo.search_by_text(conn, "Sule corner")[0]
    assert saved["lat"] == pytest.approx(16.7748)
    assert saved["lon"] == pytest.approx(96.1583)


def test_share_accepts_a_pasted_map_link(app) -> None:
    context = context_for(app, user_data={"draft": {"stage": "location"}})
    link = "https://www.google.com/maps/@16.7748,96.1583,17z"

    run_handler(router.on_text, text_update(app, link), context)

    assert context.user_data["draft"]["stage"] == "name"
    assert context.user_data["draft"]["lat"] == pytest.approx(16.7748)
    assert context.user_data["draft"]["lon"] == pytest.approx(96.1583)


def test_typed_coordinates_still_get_the_duplicate_check(app) -> None:
    add_toilet(app, lat=16.7748, lon=96.1583)
    context = context_for(app, user_data={"draft": {"stage": "location"}})

    mocks = run_handler(router.on_text, text_update(app, "16.7748, 96.1583"), context)

    assert "already on the map" in sent_texts(mocks)[0]
    assert context.user_data["draft"]["stage"] == "duplicate"


def test_text_that_is_not_a_point_is_explained(app) -> None:
    context = context_for(app, user_data={"draft": {"stage": "location"}})

    mocks = run_handler(
        router.on_text, text_update(app, "near the night market"), context
    )

    assert "coordinates" in sent_texts(mocks)[0]
    assert context.user_data["draft"]["stage"] == "location"


def test_a_forwarded_venue_starts_the_share_flow(app) -> None:
    context = context_for(app, user_data={"draft": {"stage": "location"}})

    run_handler(router.on_location, venue_update(app, 16.7748, 96.1583), context)

    assert context.user_data["draft"]["stage"] == "name"
    assert context.user_data["draft"]["lat"] == pytest.approx(16.7748)


def test_the_app_routes_a_forwarded_venue_like_a_location(app) -> None:
    """The handler filter, not just the handler, has to accept a venue."""
    add_toilet(app, lat=16.7748, lon=96.1583, name="Sule WC")

    async def _dispatch() -> None:
        await app.initialize()
        await app.process_update(venue_update(app, 16.7748, 96.1583))

    with patch.object(Bot, "initialize", AsyncMock()):
        mocks = run_handler(_dispatch)

    assert mocks.send_venue.call_count == 1


def test_nearest_accepts_typed_coordinates(app) -> None:
    add_toilet(app, lat=16.7748, lon=96.1583, name="Sule WC")
    context = context_for(app)
    context.user_data["flow"] = "nearest"

    mocks = run_handler(router.on_text, text_update(app, "16.7748, 96.1583"), context)

    assert mocks.send_venue.call_count == 1
    assert "flow" not in context.user_data


def test_nearest_explains_text_that_is_not_a_point(app) -> None:
    context = context_for(app)
    context.user_data["flow"] = "nearest"

    mocks = run_handler(router.on_text, text_update(app, "the big temple"), context)

    assert "coordinates" in sent_texts(mocks)[0]


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def test_three_reports_hide_a_toilet(app) -> None:
    toilet_id = add_toilet(app)

    for user_id in (1, 2, 3):
        run_handler(
            report.report_callback,
            callback_update(app, f"report:{toilet_id}", user_id=user_id),
            context_for(app),
        )

    with app.bot_data["db"].connect() as conn:
        assert repo.get_active_toilet(conn, toilet_id) is None


def test_one_user_cannot_report_twice(app) -> None:
    toilet_id = add_toilet(app)
    context = context_for(app)
    update = callback_update(app, f"report:{toilet_id}")

    run_handler(report.report_callback, update, context)
    run_handler(report.report_callback, update, context)
    mocks = run_handler(report.report_callback, update, context)

    assert "already reported" in mocks.answer_callback_query.call_args.kwargs["text"]
    with app.bot_data["db"].connect() as conn:
        assert repo.get_active_toilet(conn, toilet_id) is not None


def test_reporting_a_missing_toilet_does_not_crash(app) -> None:
    mocks = run_handler(
        report.report_callback, callback_update(app, "report:9999"), context_for(app)
    )

    assert (
        "no longer on the map" in mocks.answer_callback_query.call_args.kwargs["text"]
    )


def test_skip_without_a_draft_is_explained(app) -> None:
    mocks = run_handler(share.skip_name, text_update(app, "⏭ Skip"), context_for(app))

    assert "nothing to skip" in sent_texts(mocks)[0].lower()


# --------------------------------------------------------------------------- #
# Deep links
# --------------------------------------------------------------------------- #


def test_start_deep_link_opens_a_toilet(app) -> None:
    toilet_id = add_toilet(app, name="Deep Link WC")
    context = context_for(app, args=[f"t_{toilet_id}"])

    mocks = run_handler(menu.start, text_update(app, f"/start t_{toilet_id}"), context)

    assert mocks.send_venue.call_args.kwargs["title"] == "Deep Link WC"


def test_start_deep_link_to_a_hidden_toilet_says_it_is_gone(app) -> None:
    toilet_id = add_toilet(app)
    with app.bot_data["db"].connect() as conn:
        conn.execute("UPDATE toilets SET status = 'hidden' WHERE id = ?", (toilet_id,))

    mocks = run_handler(
        menu.start,
        text_update(app, "/start"),
        context_for(app, args=[f"t_{toilet_id}"]),
    )

    assert "no longer on the map" in sent_texts(mocks)[0]


def test_start_shows_the_welcome(app) -> None:
    mocks = run_handler(menu.start, text_update(app, "/start"), context_for(app))

    assert "Welcome to cheebot" in sent_texts(mocks)[0]


# --------------------------------------------------------------------------- #
# Inline mode
# --------------------------------------------------------------------------- #


def test_inline_query_returns_venues(app) -> None:
    add_toilet(app, name="Inline WC")

    mocks = run_handler(
        inline.inline_query, inline_update(app, "inline"), context_for(app)
    )

    results = mocks.answer_inline_query.call_args.kwargs["results"]
    assert [result.title for result in results] == ["Inline WC"]
    assert mocks.answer_inline_query.call_args.kwargs["button"] is None


def test_inline_query_can_resolve_an_exact_reference(app) -> None:
    toilet_id = add_toilet(app, name="Referenced WC")

    mocks = run_handler(
        inline.inline_query, inline_update(app, f"t_{toilet_id}"), context_for(app)
    )

    results = mocks.answer_inline_query.call_args.kwargs["results"]
    assert [result.title for result in results] == ["Referenced WC"]


def test_inline_query_with_no_matches_offers_the_add_button(app) -> None:
    mocks = run_handler(
        inline.inline_query, inline_update(app, "zzzz"), context_for(app)
    )

    assert mocks.answer_inline_query.call_args.kwargs["results"] == []
    button = mocks.answer_inline_query.call_args.kwargs["button"]
    assert button.start_parameter == "share"
