"""Regions cheebot can seed from.

Seeding happens one city at a time, because the public Overpass instance
restricts automated bulk use: a country-sized query is often rejected for
capacity, while a city-sized one goes through.

Adding a city is a line in ``CITIES``. Boxes are ``(south, west, north, east)``
in decimal degrees and only need to cover the built-up area, not the whole
administrative region.
"""

from __future__ import annotations

from dataclasses import dataclass

BBox = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class City:
    name: str
    country: str
    bbox: BBox  # south, west, north, east

    @property
    def label(self) -> str:
        return f"{self.name}, {self.country}"


@dataclass(frozen=True, slots=True)
class Country:
    """A whole-country area query, for when bulk coverage is wanted."""

    name: str
    iso: str  # ISO 3166-1 alpha-2, used by the Overpass area query


CITIES: dict[str, City] = {
    "yangon": City("Yangon", "Myanmar", (16.70, 96.05, 16.95, 96.30)),
    "mandalay": City("Mandalay", "Myanmar", (21.88, 96.02, 22.04, 96.16)),
    "naypyidaw": City("Naypyidaw", "Myanmar", (19.68, 96.00, 19.86, 96.18)),
    "bangkok": City("Bangkok", "Thailand", (13.63, 100.37, 13.89, 100.64)),
    "chiang-mai": City("Chiang Mai", "Thailand", (18.70, 98.90, 18.88, 99.07)),
    "phuket": City("Phuket", "Thailand", (7.75, 98.28, 8.03, 98.47)),
    "hat-yai": City("Hat Yai", "Thailand", (6.96, 100.42, 7.06, 100.53)),
    # Clipped just south of the Causeway so Johor Bahru is not included; a box
    # cannot follow the coastline, so this is the safe approximation.
    "singapore": City("Singapore", "Singapore", (1.20, 103.60, 1.465, 104.09)),
}

COUNTRIES: dict[str, Country] = {
    "myanmar": Country("Myanmar", "MM"),
    "thailand": Country("Thailand", "TH"),
    "singapore": Country("Singapore", "SG"),
}


def _normalise(name: str) -> str:
    """'Chiang Mai' and 'chiang_mai' both become 'chiang-mai'."""
    return "-".join(name.lower().split()).replace("_", "-")


def cities_for(preset: str) -> tuple[City, ...]:
    key = _normalise(preset)
    if key == "all":
        return tuple(CITIES.values())
    if key in CITIES:
        return (CITIES[key],)
    options = ", ".join([*CITIES, "all"])
    raise ValueError(f"Unknown city {preset!r}. Choose one of: {options}")


def countries_for(preset: str) -> tuple[Country, ...]:
    key = _normalise(preset)
    if key == "all":
        return tuple(COUNTRIES.values())
    if key in COUNTRIES:
        return (COUNTRIES[key],)
    options = ", ".join([*COUNTRIES, "all"])
    raise ValueError(f"Unknown preset {preset!r}. Choose one of: {options}")
