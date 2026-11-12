"""Smoke tests for wiring: the app builds, handlers register, schema is created."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from telegram.error import Conflict

import cheebot.app as app_module
from cheebot.app import build_application
from cheebot.config import Settings


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


def test_application_builds_and_registers_handlers(tmp_path: Path) -> None:
    app = build_application(make_settings(tmp_path / "bot.db"))

    handler_count = sum(len(group) for group in app.handlers.values())
    assert handler_count > 10, "expected commands, buttons, callbacks and inline mode"
    assert app.error_handlers


def test_building_creates_the_database_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "bot.db"

    build_application(make_settings(db_path))

    assert db_path.exists()
    assert db_path.parent.is_dir()


def test_conflict_stops_the_application_instead_of_retrying(tmp_path: Path) -> None:
    """Two pollers on one token is the classic local-vs-deployed mistake."""
    application = build_application(make_settings(tmp_path / "bot.db"))
    context = SimpleNamespace(
        application=application,
        error=Conflict("terminated by other getUpdates request"),
    )

    asyncio.run(app_module._on_error(None, context))

    assert app_module.stop_reason(application) == "conflict"
    assert application.running is False


def test_other_errors_do_not_stop_the_application(tmp_path: Path) -> None:
    application = build_application(make_settings(tmp_path / "bot.db"))
    context = SimpleNamespace(application=application, error=ValueError("boom"))

    asyncio.run(app_module._on_error(None, context))

    assert app_module.stop_reason(application) is None
