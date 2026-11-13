"""Recognise a location from typed or pasted text.

Not everyone adds a toilet while standing next to it: they may have noted it
earlier, or they are adding it for someone else. Telegram's pin picker covers
most of that, but on a desktop client pasting a map link or a pair of
coordinates is the reliable route. This module turns such text into a point.

Only input that already carries coordinates is accepted. Turning a place name
into a point would need a geocoder, which the bot deliberately does not depend
on — search is local, over the database.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlsplit

# A signed decimal with at most three integer digits — enough for any latitude
# or longitude, and narrow enough that an id or a year is not mistaken for one.
_NUMBER = r"(-?\d{1,3}(?:\.\d+)?)"

# "16.7748, 96.1583", "(16.7748, 96.1583)", "16.7748°, 96.1583°". Anchored: a
# message that merely contains two numbers (a name, an address) is not a point.
_BARE = re.compile(rf"^\(?\s*{_NUMBER}\s*°?\s*,\s*°?\s*{_NUMBER}\s*°?\s*\)?$")

# Android's geo: scheme, e.g. geo:16.7748,96.1583?z=17
_GEO_URI = re.compile(rf"^geo:\s*{_NUMBER}\s*,\s*{_NUMBER}")

# Google Maps URLs embed the point in several places. The @ form is what the
# address bar shows; !3d!4d is what the place pages and shared links use.
_AT = re.compile(rf"@{_NUMBER}\s*,\s*{_NUMBER}")
_EMBEDDED = re.compile(rf"!3d{_NUMBER}!4d{_NUMBER}")

# OpenStreetMap keeps the viewport in the fragment: #map=17/16.7748/96.1583
_OSM_FRAGMENT = re.compile(rf"#map=\d+(?:\.\d+)?/{_NUMBER}/{_NUMBER}")

# Query parameters that carry a point, in the forms the big map sites use.
_PAIR_KEYS = ("q", "query", "ll", "sll", "center", "destination", "daddr")


def parse_point(text: str) -> tuple[float, float] | None:
    """Return ``(lat, lon)`` if ``text`` holds a usable point, else ``None``.

    A pair outside the valid ranges is rejected rather than clamped, because a
    wrong but plausible point is worse than asking again.
    """
    text = text.strip()
    if not text:
        return None

    for pattern, anchored in (
        (_BARE, True),
        (_GEO_URI, False),
        (_EMBEDDED, False),
        (_AT, False),
        (_OSM_FRAGMENT, False),
    ):
        match = pattern.fullmatch(text) if anchored else pattern.search(text)
        if match is None:
            continue
        point = _valid(*match.groups())
        if point is not None:
            return point

    return _from_query(text)


def _from_query(text: str) -> tuple[float, float] | None:
    """Read the point out of a URL's query string, if it has one."""
    if "?" not in text:
        return None
    try:
        params = parse_qs(urlsplit(text).query)
    except ValueError:
        return None

    for key in _PAIR_KEYS:
        for raw in params.get(key, ()):
            match = _BARE.match(unquote(raw).strip())
            if match is not None:
                point = _valid(*match.groups())
                if point is not None:
                    return point

    # OpenStreetMap's "show my location" links use separate parameters.
    if params.get("mlat") and params.get("mlon"):
        return _valid(params["mlat"][0], params["mlon"][0])
    return None


def _valid(lat_raw: str, lon_raw: str) -> tuple[float, float] | None:
    try:
        lat, lon = float(lat_raw), float(lon_raw)
    except ValueError:
        return None
    if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
        return lat, lon
    return None
