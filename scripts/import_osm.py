#!/usr/bin/env python3
"""Seed the database with public toilets from OpenStreetMap.

    python scripts/import_osm.py --city yangon
    python scripts/import_osm.py --city all
    python scripts/import_osm.py --bbox 16.70,96.05,16.95,96.30     # ad-hoc box
    python scripts/import_osm.py --preset thailand                 # whole country

Seeding is city by city by default: the public Overpass instance restricts
automated bulk use, and a city-sized request succeeds where a country-sized one
is often rejected for capacity. City boxes live in ``cheebot/seeds.py``.

Re-running is always safe: rows match on ``osm_id`` and are updated in place.
Toilets tagged ``access=private`` or ``access=no`` are skipped — they are not
places a visitor can use.

Data © OpenStreetMap contributors, published under the ODbL.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Make the project importable when this file is run directly from a checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from cheebot import repo
from cheebot.db import Database
from cheebot.seeds import cities_for, countries_for

DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
USER_AGENT = "cheebot-seed/0.1 (public toilet map; one request per country)"

BBOX_QUERY = """
[out:json][timeout:{timeout}];
nwr["amenity"="toilets"]({south},{west},{north},{east});
out center tags;
"""

AREA_QUERY = """
[out:json][timeout:{timeout}];
area["ISO3166-1"="{iso}"][admin_level=2]->.search;
nwr["amenity"="toilets"](area.search);
out center tags;
"""

# Statuses worth retrying: Overpass is frequently at capacity.
RETRYABLE = {429, 500, 502, 503, 504}

# Toilets explicitly not usable by visitors.
EXCLUDED_ACCESS = {"private", "no"}


class OverpassError(RuntimeError):
    """The query could not be completed."""


@dataclass(frozen=True, slots=True)
class Job:
    label: str
    query: str


# --------------------------------------------------------------------------- #
# Query building
# --------------------------------------------------------------------------- #


def parse_bbox(raw: str) -> tuple[float, float, float, float]:
    try:
        south, west, north, east = (float(part) for part in raw.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "bbox must be 'south,west,north,east'"
        ) from exc
    if not (south < north and west < east):
        raise argparse.ArgumentTypeError("bbox needs south < north and west < east")
    return south, west, north, east


def bbox_query(bbox: tuple[float, float, float, float], timeout: int) -> str:
    south, west, north, east = bbox
    return BBOX_QUERY.format(
        timeout=timeout, south=south, west=west, north=north, east=east
    )


def area_query(iso: str, timeout: int) -> str:
    return AREA_QUERY.format(timeout=timeout, iso=iso.upper())


def build_jobs(args: argparse.Namespace) -> list[Job]:
    """Turn the CLI selection into one query per region."""
    if args.city:
        return [
            Job(city.label, bbox_query(city.bbox, args.timeout))
            for city in cities_for(args.city)
        ]
    if args.bbox is not None:
        label = "bbox " + ",".join(f"{value:g}" for value in args.bbox)
        return [Job(label, bbox_query(args.bbox, args.timeout))]
    if args.area:
        iso = args.area.strip().upper()
        return [Job(f"area {iso}", area_query(iso, args.timeout))]
    return [
        Job(f"{country.name} ({country.iso})", area_query(country.iso, args.timeout))
        for country in countries_for(args.preset)
    ]


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #


def fetch_elements(
    job: Job, endpoint: str, timeout: int, attempts: int = 3
) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        endpoint,
        data=urllib.parse.urlencode({"data": job.query}).encode(),
        headers={"User-Agent": USER_AGENT},
    )

    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout + 60) as response:
                return json.load(response).get("elements", [])
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code not in RETRYABLE:
                break
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = f"network error: {getattr(exc, 'reason', exc)}"

        if attempt < attempts:
            wait = 15 * attempt
            print(f"  {last_error}; retrying in {wait}s …")
            time.sleep(wait)

    raise OverpassError(
        f"{last_error}. The public Overpass instance is often busy and restricts "
        "automated use: retry later, or point --endpoint at a mirror or a local "
        "instance."
    )


# --------------------------------------------------------------------------- #
# Mapping
# --------------------------------------------------------------------------- #


def _tri_state(value: str | None) -> bool | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"yes", "true", "1"}:
        return True
    if lowered in {"no", "false", "0"}:
        return False
    return None


def _address(tags: dict[str, str]) -> str | None:
    if tags.get("addr:full"):
        return tags["addr:full"].strip()
    street = " ".join(
        part for part in (tags.get("addr:street"), tags.get("addr:housenumber")) if part
    ).strip()
    parts = [part for part in (street, tags.get("addr:city")) if part]
    return ", ".join(parts) or None


def to_record(element: dict[str, Any]) -> dict[str, Any] | None:
    """Map one Overpass element to our schema, or None if it should be skipped."""
    if element.get("type") == "node":
        lat, lon = element.get("lat"), element.get("lon")
    else:
        center = element.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
    if lat is None or lon is None:
        return None

    tags: dict[str, str] = element.get("tags") or {}
    if (tags.get("access") or "").strip().lower() in EXCLUDED_ACCESS:
        return None

    fee = _tri_state(tags.get("fee"))
    wheelchair = (tags.get("wheelchair") or "").strip().lower()

    return {
        "osm_id": f"{element['type']}/{element['id']}",
        "name": (tags.get("name") or tags.get("operator") or "").strip()
        or "Public toilet",
        "lat": float(lat),
        "lon": float(lon),
        "address": _address(tags),
        # OSM tags whether a fee applies; our column is the inverse.
        "is_free": None if fee is None else not fee,
        # "limited" means partially accessible, which is neither yes nor no.
        "is_accessible": {"yes": True, "no": False}.get(wheelchair),
    }


def write_records(
    database: Database, elements: list[dict[str, Any]]
) -> tuple[int, int, int]:
    """Store parsed elements. Returns (inserted, updated, skipped)."""
    inserted = updated = skipped = 0
    with database.connect() as conn:
        for element in elements:
            record = to_record(element)
            if record is None:
                skipped += 1
                continue
            _, created = repo.upsert_osm_toilet(conn, **record)
            if created:
                inserted += 1
            else:
                updated += 1
    return inserted, updated, skipped


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--city",
        help="a city from cheebot/seeds.py ('yangon', 'chiang mai', ...), or 'all'",
    )
    selection.add_argument(
        "--preset",
        help="a whole-country area query; often rejected when Overpass is busy",
    )
    selection.add_argument(
        "--area",
        help="ad-hoc ISO 3166-1 alpha-2 country code, e.g. TH",
    )
    selection.add_argument(
        "--bbox",
        type=parse_bbox,
        help="ad-hoc 'south,west,north,east' box (decimal degrees)",
    )
    parser.add_argument(
        "--db",
        default=os.getenv("CHEEBOT_DB_PATH") or "cheebot.db",
        help="SQLite database path (default: CHEEBOT_DB_PATH or cheebot.db)",
    )
    parser.add_argument(
        "--endpoint",
        default=os.getenv("CHEEBOT_OVERPASS_URL") or DEFAULT_ENDPOINT,
        help="Overpass interpreter URL (default: the public instance)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Overpass query timeout in seconds (default: 300)",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=3,
        help="attempts per region on transient errors (default: 3)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=10.0,
        help="seconds to wait between regions (default: 10)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        jobs = build_jobs(args)
    except ValueError as exc:
        parser.error(str(exc))

    database = Database(args.db)
    database.init_schema()

    inserted = updated = skipped = 0
    failures: list[str] = []

    for index, job in enumerate(jobs, start=1):
        print(f"[{index}/{len(jobs)}] {job.label}")
        try:
            elements = fetch_elements(job, args.endpoint, args.timeout, args.attempts)
        except OverpassError as exc:
            print(f"  failed: {exc}")
            failures.append(job.label)
        else:
            count_in, count_up, count_skip = write_records(database, elements)
            inserted += count_in
            updated += count_up
            skipped += count_skip
            print(
                f"  {len(elements)} element(s): {count_in} inserted, "
                f"{count_up} updated, {count_skip} skipped"
            )
            if not elements:
                print(
                    "  nothing found — the area may not resolve, or OSM has no "
                    "coverage here"
                )

        if index < len(jobs):
            time.sleep(args.sleep)

    print(
        f"\nSeeded {len(jobs) - len(failures)}/{len(jobs)} region(s): "
        f"{inserted} inserted, {updated} updated, {skipped} skipped → {args.db}"
    )
    if failures:
        print("Failed: " + ", ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
