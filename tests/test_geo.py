from __future__ import annotations

import pytest

from cheebot.geo import bounding_box, format_distance, haversine_m


def test_haversine_zero_distance() -> None:
    assert haversine_m(10.0, 20.0, 10.0, 20.0) == pytest.approx(0.0, abs=1e-9)


def test_haversine_paris_to_london() -> None:
    # Reference distance is roughly 343.5 km.
    distance = haversine_m(48.8566, 2.3522, 51.5074, -0.1278)
    assert distance == pytest.approx(343_500, rel=0.01)


def test_haversine_is_symmetric() -> None:
    there = haversine_m(52.5, 13.4, 52.6, 13.5)
    back = haversine_m(52.6, 13.5, 52.5, 13.4)
    assert there == pytest.approx(back)


def test_haversine_one_degree_of_latitude() -> None:
    # One degree of latitude is about 111 km everywhere.
    assert haversine_m(0.0, 0.0, 1.0, 0.0) == pytest.approx(111_200, rel=0.01)


def test_bounding_box_contains_the_point() -> None:
    min_lat, max_lat, min_lon, max_lon = bounding_box(52.5, 13.4, 1_000)
    assert min_lat < 52.5 < max_lat
    assert min_lon < 13.4 < max_lon


def test_bounding_box_is_about_a_kilometre() -> None:
    # The box is a half-width of radius_m in each direction, so it spans ~2 km.
    min_lat, max_lat, _, _ = bounding_box(52.5, 13.4, 1_000)
    assert (max_lat - 52.5) == pytest.approx(0.009, abs=2e-3)
    assert (max_lat - min_lat) == pytest.approx(0.018, abs=2e-3)


def test_bounding_box_reports_antimeridian_wrap() -> None:
    _, _, _, max_lon = bounding_box(0.0, 179.999, 1_000)
    assert max_lon > 180.0, "callers rely on this to detect the wrap"


def test_bounding_box_near_pole_covers_all_longitudes() -> None:
    _, _, min_lon, max_lon = bounding_box(89.9999, 0.0, 5_000)
    assert (min_lon, max_lon) == (-180.0, 180.0)


@pytest.mark.parametrize(
    ("meters", "expected"),
    [
        (0, "0 m"),
        (84, "80 m"),
        (120, "120 m"),
        (1_000, "1.0 km"),
        (1_450, "1.4 km"),
        (9_900, "9.9 km"),
        (12_345, "12 km"),
    ],
)
def test_format_distance(meters: float, expected: str) -> None:
    assert format_distance(meters) == expected
