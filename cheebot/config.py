"""Runtime configuration read from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, normalize_language

load_dotenv()


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


# Shipped in .env.example. Starting with it would make every stored user hash
# reversible by anyone who reads the public repo, so it is rejected outright.
INSECURE_SALT = "change-me-to-a-long-random-string"


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    db_path: Path
    default_radius_m: int
    max_radius_m: int
    results_limit: int
    dedupe_radius_m: int
    report_hide_threshold: int
    daily_share_limit: int
    user_hash_salt: str
    default_language: str = DEFAULT_LANGUAGE


def load_settings() -> Settings:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise ConfigError(
            "TELEGRAM_BOT_TOKEN is not set. Get one from @BotFather and put it in .env"
        )

    salt = (os.getenv("CHEEBOT_USER_HASH_SALT") or "").strip()
    if not salt:
        raise ConfigError(
            "CHEEBOT_USER_HASH_SALT is not set. Use any long random string; "
            "it keeps user ids from being stored in plain text."
        )
    if salt == INSECURE_SALT:
        raise ConfigError(
            "CHEEBOT_USER_HASH_SALT is still the example value. Generate one with\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(32))"\n'
            "and put it in .env. A published salt makes every stored user hash "
            "reversible."
        )

    default_radius = _int("CHEEBOT_DEFAULT_RADIUS_M", 1_000)
    max_radius = _int("CHEEBOT_MAX_RADIUS_M", 25_000)
    if default_radius <= 0 or max_radius < default_radius:
        raise ConfigError(
            "CHEEBOT_DEFAULT_RADIUS_M must be positive and no larger than "
            "CHEEBOT_MAX_RADIUS_M"
        )

    raw_language = (os.getenv("CHEEBOT_DEFAULT_LANGUAGE") or "").strip()
    default_language = (
        normalize_language(raw_language) if raw_language else DEFAULT_LANGUAGE
    )
    if default_language is None:
        raise ConfigError(
            "CHEEBOT_DEFAULT_LANGUAGE must be one of "
            f"{', '.join(SUPPORTED_LANGUAGES)}, got {raw_language!r}"
        )

    return Settings(
        bot_token=token,
        db_path=Path(os.getenv("CHEEBOT_DB_PATH") or "cheebot.db"),
        default_radius_m=default_radius,
        max_radius_m=max_radius,
        results_limit=_int("CHEEBOT_RESULTS_LIMIT", 5),
        dedupe_radius_m=_int("CHEEBOT_DEDUPE_RADIUS_M", 30),
        report_hide_threshold=_int("CHEEBOT_REPORT_HIDE_THRESHOLD", 3),
        daily_share_limit=_int("CHEEBOT_DAILY_SHARE_LIMIT", 10),
        user_hash_salt=salt,
        default_language=default_language,
    )
