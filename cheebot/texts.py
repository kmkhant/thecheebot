"""Formatting of user-facing copy.

The prose itself lives in :mod:`cheebot.i18n`; this module only assembles it:
escaping, truncation and the multi-part strings (welcome, help, venue cards).
"""

from __future__ import annotations

import html
import re
import sqlite3

from .geo import format_distance
from .i18n import t

NAME_MAX_LEN = 64


def escape(text: str) -> str:
    """Escape user text for inclusion in an HTML message."""
    return html.escape(text)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_name(language: str, raw: str | None) -> str:
    """Normalise a user-supplied name, falling back to a neutral label.

    The fallback is stored like any other name, so it is written in the
    language of the person adding the place.
    """
    if not raw:
        return t(language, "default_toilet_name")
    name = _clean(raw)[:NAME_MAX_LEN]
    return name or t(language, "default_toilet_name")


def truncate(text: str, limit: int = NAME_MAX_LEN) -> str:
    text = _clean(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def welcome(language: str, bot_username: str | None) -> str:
    body = t(language, "welcome")
    if bot_username:
        body += "\n\n" + t(language, "welcome_inline", username=escape(bot_username))
    return body + "\n\n" + t(language, "welcome_footer")


def help_text(language: str, bot_username: str | None) -> str:
    body = t(language, "help")
    if bot_username:
        body += "\n\n" + t(language, "help_inline", username=escape(bot_username))
    return body


def about(language: str) -> str:
    return t(language, "about")


def describe(
    language: str,
    toilet: sqlite3.Row,
    distance_m: float | None = None,
    rating: tuple[float, int] | None = None,
) -> str:
    """One-line summary used as the address line on a venue card."""
    parts: list[str] = []
    if distance_m is not None:
        parts.append(format_distance(distance_m))
    if rating is not None:
        average, count = rating
        parts.append(f"★{average:.1f} ({count})")
    if toilet["address"]:
        parts.append(toilet["address"])
    if toilet["is_free"] == 1:
        parts.append(t(language, "word_free"))
    elif toilet["is_free"] == 0:
        parts.append(t(language, "word_paid"))
    if toilet["is_accessible"] == 1:
        parts.append(t(language, "word_accessible"))
    return " · ".join(parts) or t(language, "public_toilet")


def nearest_header(language: str, radius_m: float, widened_from: int | None) -> str:
    if widened_from is None:
        return t(language, "nearest_header_default", radius=format_distance(radius_m))
    return t(
        language,
        "nearest_header_widened",
        widened=format_distance(widened_from),
        radius=format_distance(radius_m),
    )


def share_confirmed(language: str, link: str) -> str:
    return t(language, "share_confirmed", link=link)
