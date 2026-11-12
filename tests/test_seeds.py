from __future__ import annotations

import pytest

from cheebot.seeds import CITIES, COUNTRIES, cities_for, countries_for


def test_city_lookup_handles_spaces_and_case() -> None:
    assert cities_for("Chiang Mai")[0].name == "Chiang Mai"
    assert cities_for("chiang_mai")[0].name == "Chiang Mai"
    assert cities_for("  YANGON  ")[0].name == "Yangon"


def test_city_all_returns_every_configured_city() -> None:
    assert len(cities_for("all")) == len(CITIES)


def test_every_city_box_is_ordered_and_plausible() -> None:
    for key, city in CITIES.items():
        south, west, north, east = city.bbox
        assert south < north, f"{key} needs south < north"
        assert west < east, f"{key} needs west < east"
        assert south >= -90 and north <= 90, f"{key} latitude out of range"
        assert west >= -180 and east <= 180, f"{key} longitude out of range"
        # A city box should be tens of kilometres wide, not a continent.
        assert north - south < 1.0, f"{key} box is too tall"
        assert east - west < 1.0, f"{key} box is too wide"


def test_singapore_box_excludes_johor_bahru() -> None:
    south, west, north, east = CITIES["singapore"].bbox

    # Johor Bahru city centre is north of the Causeway at 1.4927, 103.7414.
    assert not (south <= 1.4927 <= north and west <= 103.7414 <= east)


def test_unknown_city_lists_the_options() -> None:
    with pytest.raises(ValueError, match="yangon"):
        cities_for("atlantis")


def test_preset_all_returns_every_country() -> None:
    countries = countries_for("all")

    assert len(countries) == len(COUNTRIES)
    assert {country.iso for country in countries} == {"MM", "TH", "SG"}


def test_preset_lookup_is_case_insensitive() -> None:
    assert countries_for("THAILAND")[0].iso == "TH"
    assert countries_for(" Thailand ")[0].name == "Thailand"


def test_single_preset_returns_one_country() -> None:
    assert [country.iso for country in countries_for("singapore")] == ["SG"]


def test_unknown_preset_lists_the_options() -> None:
    with pytest.raises(ValueError, match="myanmar"):
        countries_for("atlantis")


def test_country_names_and_iso_codes_are_populated() -> None:
    for key, country in COUNTRIES.items():
        assert country.name, f"{key} needs a display name"
        assert len(country.iso) == 2, f"{key} needs a 2-letter ISO code"
