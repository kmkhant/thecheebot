"""Startup checks: token preflight, safe error output, log level parsing."""

from __future__ import annotations

import io
import json
import logging
import sys
import urllib.error
from email.message import Message

import pytest

import cheebot.__main__ as cli

TOKEN = "123456:secret-token-value"


def fake_urlopen(payload: dict | None = None, status: int = 200):
    def _open(request, timeout=None):
        if status >= 400:
            raise urllib.error.HTTPError(
                request.full_url, status, "error", Message(), io.BytesIO(b"{}")
            )
        body = json.dumps(payload or {}).encode()
        return io.BytesIO(body)

    return _open


def test_log_formatter_scrubs_the_token_from_messages_and_tracebacks() -> None:
    """PTB's base URL carries the token, so httpx errors can chain it in."""
    formatter = cli._ScrubFormatter(cli.LOG_FORMAT, TOKEN)

    try:
        raise RuntimeError(f"https://api.telegram.org/bot{TOKEN}/getMe failed")
    except RuntimeError:
        record = logging.LogRecord(
            "cheebot",
            logging.ERROR,
            __file__,
            1,
            "could not reach %s",
            (TOKEN,),
            sys.exc_info(),
        )

    rendered = formatter.format(record)

    assert TOKEN not in rendered
    assert rendered.count("<redacted>") == 2  # once in the message, once in the trace
    assert "api.telegram.org/bot<redacted>/getMe" in rendered


def test_log_formatter_installs_on_root_handlers(monkeypatch) -> None:
    handler = logging.StreamHandler(io.StringIO())
    monkeypatch.setattr(logging.getLogger(), "handlers", [handler])

    cli._install_token_scrubber(TOKEN)

    assert isinstance(handler.formatter, cli._ScrubFormatter)


def test_preflight_returns_the_bot_username(monkeypatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        fake_urlopen({"ok": True, "result": {"username": "cheebot_dev"}}),
    )

    username, error = cli.preflight(TOKEN)

    assert (username, error) == ("cheebot_dev", None)


@pytest.mark.parametrize("status", [401, 404])
def test_rejected_token_is_reported_without_the_token(monkeypatch, status) -> None:
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen(status=status))

    username, error = cli.preflight(TOKEN)

    assert username is None
    assert error == cli.BAD_TOKEN
    assert TOKEN not in error


def test_ok_false_payload_is_treated_as_a_bad_token(monkeypatch) -> None:
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen({"ok": False}))

    username, error = cli.preflight(TOKEN)

    assert username is None
    assert error == cli.BAD_TOKEN


def test_network_failure_is_explained_without_the_token(monkeypatch) -> None:
    def boom(request, timeout=None):
        raise urllib.error.URLError(OSError("no route to host"))

    monkeypatch.setattr("urllib.request.urlopen", boom)

    username, error = cli.preflight(TOKEN)

    assert username is None
    assert error is not None
    assert "Could not reach api.telegram.org" in error
    assert TOKEN not in error


def test_other_http_errors_report_the_status(monkeypatch) -> None:
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen(status=502))

    username, error = cli.preflight(TOKEN)

    assert username is None
    assert error is not None
    assert "HTTP 502" in error
    assert TOKEN not in error


def test_scrub_removes_the_token() -> None:
    assert cli._scrub(f"failed for {TOKEN} ok", TOKEN) == "failed for *** ok"
    assert cli._scrub("nothing here", "") == "nothing here"


def test_main_exits_cleanly_when_the_token_is_rejected(monkeypatch, capsys) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("CHEEBOT_USER_HASH_SALT", "salt")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen(status=401))

    code = cli.main()

    captured = capsys.readouterr()
    assert code == 1
    assert "Telegram rejected the bot token" in captured.err
    assert TOKEN not in captured.err + captured.out


def test_main_reports_missing_configuration(monkeypatch, capsys) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    code = cli.main()

    assert code == 1
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("DEBUG", logging.DEBUG), ("info", logging.INFO), ("WARNING", logging.WARNING)],
)
def test_log_level_parsing(monkeypatch, raw: str, expected: int) -> None:
    monkeypatch.setenv("CHEEBOT_LOG_LEVEL", raw)

    assert cli._log_level() == expected


def test_unknown_log_level_falls_back_to_info(monkeypatch, capsys) -> None:
    monkeypatch.setenv("CHEEBOT_LOG_LEVEL", "LOUD")

    assert cli._log_level() == logging.INFO
    assert "LOUD" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", True),
        ("true", True),
        ("YES", True),
        ("0", False),
        ("", False),
        ("maybe", False),
    ],
)
def test_flag_parsing(monkeypatch, raw: str, expected: bool) -> None:
    monkeypatch.setenv("CHEEBOT_DROP_PENDING", raw)

    assert cli._flag("CHEEBOT_DROP_PENDING") is expected
