"""Entry point: python -m cheebot"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request

from telegram import Update
from telegram.error import Conflict, InvalidToken, NetworkError, TelegramError

from .app import CONFLICT_HELP, build_application, stop_reason
from .config import ConfigError, load_settings

logger = logging.getLogger("cheebot")

TELEGRAM_API = "https://api.telegram.org"

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

BAD_TOKEN = (
    "Telegram rejected the bot token.\n"
    "  Check TELEGRAM_BOT_TOKEN in .env; it looks like 123456:ABC-DEF…\n"
    "  For a fresh one: @BotFather → /revoke → /token."
)


def _log_level() -> int:
    """CHEEBOT_LOG_LEVEL=DEBUG turns on the chatty library logs too."""
    name = (os.getenv("CHEEBOT_LOG_LEVEL") or "INFO").strip().upper()
    level = logging.getLevelNamesMapping().get(name)
    if level is None:
        print(
            f"Ignoring unknown CHEEBOT_LOG_LEVEL {name!r}; using INFO", file=sys.stderr
        )
        return logging.INFO
    return level


def _flag(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


class _ScrubFormatter(logging.Formatter):
    """Strip the bot token from every log line, tracebacks included.

    PTB builds its request URL as ``.../bot<token>/<method>``, so an httpx
    error chained into a traceback can carry the token. Logs get pasted into
    issues and bug reports, so it never gets to stay there.
    """

    def __init__(self, fmt: str, token: str) -> None:
        super().__init__(fmt)
        self._token = token

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        return text.replace(self._token, "<redacted>") if self._token else text


def _install_token_scrubber(token: str) -> None:
    """Apply the scrubber to whatever handlers ``basicConfig`` installed."""
    for handler in logging.getLogger().handlers:
        handler.setFormatter(_ScrubFormatter(LOG_FORMAT, token))


def _scrub(text: str, token: str) -> str:
    """Never let the token reach a terminal, log file or bug report."""
    return text.replace(token, "***") if token else text


def preflight(token: str) -> tuple[str | None, str | None]:
    """Call getMe so a bad token fails cleanly, before PTB logs a traceback.

    PTB's own InvalidToken message quotes the token, so catching it after the
    fact still writes the secret to the log. Checking here keeps it out.

    Returns (username, error_message).
    """
    request = urllib.request.Request(f"{TELEGRAM_API}/bot{token}/getMe")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 404):
            return None, BAD_TOKEN
        return None, f"Telegram returned HTTP {exc.code} while checking the token."
    except (urllib.error.URLError, TimeoutError) as exc:
        reason = type(getattr(exc, "reason", exc)).__name__
        return (
            None,
            f"Could not reach api.telegram.org ({reason}). Check your connection.",
        )

    result = payload.get("result") or {}
    username = result.get("username")
    if not payload.get("ok") or not username:
        return None, BAD_TOKEN
    return username, None


def main() -> int:
    logging.basicConfig(
        level=_log_level(),
        format=LOG_FORMAT,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        config = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    _install_token_scrubber(config.bot_token)

    username, error = preflight(config.bot_token)
    if error is not None:
        print(_scrub(error, config.bot_token), file=sys.stderr)
        return 1

    app = build_application(config)
    logger.info(
        "connected as @%s — polling (db=%s, pid=%d)",
        username,
        config.db_path,
        os.getpid(),
    )
    logger.info("send /start to me in Telegram to try it; Ctrl-C to stop")

    # Long polling: no public HTTPS endpoint, no webhook, works behind NAT.
    try:
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=_flag("CHEEBOT_DROP_PENDING"),
        )
    except InvalidToken:  # revoked between the check and startup
        print(BAD_TOKEN, file=sys.stderr)
        return 1
    except Conflict:
        print(CONFLICT_HELP, file=sys.stderr)
        return 1
    except NetworkError as exc:
        print(
            _scrub(f"Could not reach api.telegram.org: {exc}", config.bot_token),
            file=sys.stderr,
        )
        return 1
    except TelegramError as exc:
        print(_scrub(f"Telegram error: {exc}", config.bot_token), file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover - Ctrl-C during startup
        return 0

    # A Conflict stops the application from inside the error handler rather than
    # raising, because PTB retries polling errors instead of propagating them.
    if stop_reason(app) == "conflict":
        print(CONFLICT_HELP, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
