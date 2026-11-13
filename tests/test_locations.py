"""Typed and pasted locations: what counts as a point, and what does not."""

from __future__ import annotations

import pytest

from cheebot.locations import parse_point

YANGON = (16.7748, 96.1583)


@pytest.mark.parametrize(
    "text",
    [
        "16.7748, 96.1583",
        "16.7748,96.1583",
        "  16.7748 , 96.1583  ",
        "(16.7748, 96.1583)",
        "16.7748°, 96.1583°",
        "geo:16.7748,96.1583",
        "geo:16.7748,96.1583?z=17",
        "https://www.google.com/maps/@16.7748,96.1583,17z",
        "https://www.google.com/maps/place/Sule/data=!3m1!4b1!4m5!3d16.7748!4d96.1583",
        "https://maps.google.com/?q=16.7748,96.1583",
        "https://maps.google.com/?q=16.7748%2C96.1583",
        "https://www.google.com/maps/dir/?api=1&destination=16.7748,96.1583",
        "https://www.openstreetmap.org/#map=17/16.7748/96.1583",
        "https://www.openstreetmap.org/?mlat=16.7748&mlon=96.1583#map=17/16.7748/96.1583",
    ],
)
def test_a_point_is_recognised(text: str) -> None:
    assert parse_point(text) == pytest.approx(YANGON)


def test_southern_and_western_hemispheres_are_signed() -> None:
    assert parse_point("-33.8688, 151.2093") == pytest.approx((-33.8688, 151.2093))
    assert parse_point("-22.9068, -43.1729") == pytest.approx((-22.9068, -43.1729))


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "near the night market",
        "16.7748",
        "16.7748, 96.1583, 17z",  # a third number is not a point pair
        "91.0, 96.1583",  # latitude out of range
        "16.7748, 180.5",  # longitude out of range
        "12345, 67890",  # ids, not coordinates
        "Block 12, 16 Road",
        "https://maps.google.com/",
    ],
)
def test_text_without_a_point_is_rejected(text: str) -> None:
    assert parse_point(text) is None


def test_a_pair_inside_a_sentence_is_not_taken_for_a_point() -> None:
    """Only a message that is a point counts; prose must reach the hint instead."""
    assert parse_point("turn left at 16.7748, 96.1583 and keep going") is None


def test_an_out_of_range_link_is_rejected() -> None:
    assert parse_point("https://www.google.com/maps/@191.0,96.1583,17z") is None
