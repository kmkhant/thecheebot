"""Tests for the OpenStreetMap importer's tag mapping (no network involved)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from _loader import load_script

from cheebot import repo
from cheebot.db import Database

import_osm = load_script("import_osm")


def node(element_id: int = 1001, **tags) -> dict:
    return {
        "type": "node",
        "id": element_id,
        "lat": 52.52,
        "lon": 13.405,
        "tags": {"amenity": "toilets", **tags},
    }


def test_node_is_mapped_with_coordinates() -> None:
    record = import_osm.to_record(node(name="Station WC"))

    assert record is not None
    assert record["osm_id"] == "node/1001"
    assert record["name"] == "Station WC"
    assert record["lat"] == pytest.approx(52.52)
    assert record["lon"] == pytest.approx(13.405)


def test_fee_tag_is_inverted_into_is_free() -> None:
    assert import_osm.to_record(node(fee="no"))["is_free"] is True
    assert import_osm.to_record(node(fee="yes"))["is_free"] is False


def test_unknown_fee_is_left_unset() -> None:
    assert import_osm.to_record(node())["is_free"] is None


def test_wheelchair_limited_is_treated_as_unknown() -> None:
    assert import_osm.to_record(node(wheelchair="yes"))["is_accessible"] is True
    assert import_osm.to_record(node(wheelchair="no"))["is_accessible"] is False
    assert import_osm.to_record(node(wheelchair="limited"))["is_accessible"] is None


def test_address_is_assembled_from_parts() -> None:
    element = node()
    element["tags"].update({"addr:street": "Main Street", "addr:housenumber": "12"})

    record = import_osm.to_record(element)

    assert record["address"] == "Main Street 12"


def test_missing_name_falls_back_to_a_neutral_label() -> None:
    assert import_osm.to_record(node())["name"] == "Public toilet"
    assert import_osm.to_record(node(operator="City of Berlin"))["name"] == (
        "City of Berlin"
    )


def test_way_uses_its_centre() -> None:
    element = {
        "type": "way",
        "id": 55,
        "center": {"lat": 48.1, "lon": 11.5},
        "tags": {"amenity": "toilets"},
    }

    record = import_osm.to_record(element)

    assert record["osm_id"] == "way/55"
    assert (record["lat"], record["lon"]) == (48.1, 11.5)


def test_element_without_a_position_is_skipped() -> None:
    element = {"type": "relation", "id": 7, "tags": {"amenity": "toilets"}}

    assert import_osm.to_record(element) is None


@pytest.mark.parametrize(
    "raw",
    ["52.4,13.3,52.6,13.5", "1,2,3,4"],
)
def test_parse_bbox_accepts_valid_input(raw: str) -> None:
    assert import_osm.parse_bbox(raw) == pytest.approx(
        tuple(float(part) for part in raw.split(","))
    )


@pytest.mark.parametrize("raw", ["52.4,13.3,52.6", "a,b,c,d", "52.6,13.3,52.4,13.5"])
def test_parse_bbox_rejects_bad_input(raw: str) -> None:
    with pytest.raises(import_osm.argparse.ArgumentTypeError):
        import_osm.parse_bbox(raw)


def test_private_and_staff_only_toilets_are_skipped() -> None:
    assert import_osm.to_record(node(access="private")) is None
    assert import_osm.to_record(node(access="no")) is None
    assert import_osm.to_record(node(access="yes")) is not None
    # Shops and malls the public can walk into are still worth listing.
    assert import_osm.to_record(node(access="customers")) is not None


def test_area_query_filters_by_country_area() -> None:
    query = import_osm.area_query("th", timeout=120)

    assert 'area["ISO3166-1"="TH"][admin_level=2]' in query
    assert 'nwr["amenity"="toilets"](area.search)' in query
    assert "timeout:120" in query


def test_bbox_query_uses_the_box() -> None:
    query = import_osm.bbox_query((1.0, 2.0, 3.0, 4.0), timeout=60)

    assert "(1.0,2.0,3.0,4.0)" in query
    assert "timeout:60" in query


def test_build_jobs_from_a_preset_covers_each_country() -> None:
    args = SimpleNamespace(preset="all", city=None, area=None, bbox=None, timeout=300)

    jobs = import_osm.build_jobs(args)

    assert len(jobs) == 3
    assert [job.label.split()[-1] for job in jobs] == ["(MM)", "(TH)", "(SG)"]
    assert all("area.search" in job.query for job in jobs)


def test_build_jobs_accepts_an_ad_hoc_bbox() -> None:
    args = SimpleNamespace(
        preset=None, city=None, area=None, bbox=(1.5, 2.5, 3.5, 4.5), timeout=60
    )

    jobs = import_osm.build_jobs(args)

    assert len(jobs) == 1
    assert "(1.5,2.5,3.5,4.5)" in jobs[0].query


def test_build_jobs_normalises_an_ad_hoc_area() -> None:
    args = SimpleNamespace(preset=None, city=None, area=" la ", bbox=None, timeout=60)

    jobs = import_osm.build_jobs(args)

    assert jobs[0].label == "area LA"
    assert '="LA"' in jobs[0].query


def test_build_jobs_from_a_city_uses_its_box() -> None:
    args = SimpleNamespace(preset=None, city="yangon", area=None, bbox=None, timeout=60)

    jobs = import_osm.build_jobs(args)

    assert len(jobs) == 1
    assert jobs[0].label == "Yangon, Myanmar"
    assert "(16.7,96.05,16.95,96.3)" in jobs[0].query


def test_build_jobs_city_all_covers_every_configured_city() -> None:
    args = SimpleNamespace(preset=None, city="all", area=None, bbox=None, timeout=60)

    jobs = import_osm.build_jobs(args)

    assert len(jobs) == len(import_osm.cities_for("all"))
    assert {job.label for job in jobs} >= {"Yangon, Myanmar", "Bangkok, Thailand"}


def test_writing_twice_updates_instead_of_duplicating(tmp_path: Path) -> None:
    database = Database(tmp_path / "import.db")
    database.init_schema()
    elements = [node(name="First name"), node(element_id=1002, name="Second")]

    inserted, updated, skipped = import_osm.write_records(database, elements)
    assert (inserted, updated, skipped) == (2, 0, 0)

    elements[0]["tags"]["name"] = "Renamed"
    inserted, updated, skipped = import_osm.write_records(database, elements)
    assert (inserted, updated, skipped) == (0, 2, 0)

    with database.connect() as conn:
        assert repo.count_toilets(conn) == 2
        assert repo.search_by_text(conn, "Renamed")[0]["name"] == "Renamed"


def test_elements_without_positions_are_counted_as_skipped(tmp_path: Path) -> None:
    database = Database(tmp_path / "import.db")
    database.init_schema()

    inserted, updated, skipped = import_osm.write_records(
        database, [{"type": "relation", "id": 9, "tags": {}}]
    )

    assert (inserted, updated, skipped) == (0, 0, 1)
