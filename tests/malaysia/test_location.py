from __future__ import annotations

import pytest

from jobspy.malaysia.location import MalaysianState, normalize_location
from jobspy.model import Country, Location


@pytest.mark.parametrize(
    "raw_city,expected_city,expected_state",
    [
        ("Kuala Lumpur", "Kuala Lumpur", "Kuala Lumpur"),
        ("WP Kuala Lumpur", "Kuala Lumpur", "Kuala Lumpur"),
        ("Federal Territory of Kuala Lumpur", "Kuala Lumpur", "Kuala Lumpur"),
        ("Cyberjaya", "Cyberjaya", "Selangor"),
        ("Putrajaya", "Putrajaya", "Putrajaya"),
        ("Petaling Jaya", "Petaling Jaya", "Selangor"),
        ("George Town", "George Town", "Pulau Pinang"),
        ("Butterworth", "Butterworth", "Pulau Pinang"),
        ("Johor Bahru", "Johor Bahru", "Johor"),
        ("Kota Kinabalu", "Kota Kinabalu", "Sabah"),
        ("Taman Pulau Pinang", "Taman Pulau Pinang", "Pulau Pinang"),
        ("Simpang Ampat", "Simpang Ampat", "Pulau Pinang"),
        ("Bangsar South", "Bangsar South", "Kuala Lumpur"),
    ],
)
def test_resolves_known_places(raw_city, expected_city, expected_state):
    normalized, unmatched = normalize_location(
        Location(city=raw_city, country=Country.MALAYSIA)
    )

    assert normalized.city == expected_city
    assert normalized.state == expected_state
    assert normalized.country == Country.MALAYSIA
    assert unmatched is None


def test_kuala_lumpur_gets_a_state_not_none():
    normalized, _ = normalize_location(Location(city="Kuala Lumpur"))

    assert normalized.state == MalaysianState.KUALA_LUMPUR.value


def test_resolves_a_bare_state():
    normalized, unmatched = normalize_location(Location(state="Selangor"))

    assert normalized.state == "Selangor"
    assert normalized.city is None
    assert unmatched is None


def test_uses_state_field_when_city_is_unknown():
    # "Bandar Seri Putra" is deliberately absent from the gazetteer so this
    # test exercises the state-fallback path, not a city-hit.
    normalized, unmatched = normalize_location(
        Location(city="Bandar Seri Putra", state="Selangor")
    )

    assert normalized.state == "Selangor"
    assert normalized.city == "Bandar Seri Putra"
    assert unmatched is None


def test_unknown_location_passes_through_and_reports():
    original = Location(city="Atlantis", state="Nowhere")

    normalized, unmatched = normalize_location(original)

    assert normalized.city == "Atlantis"
    assert normalized.state == "Nowhere"
    assert unmatched == "Atlantis, Nowhere"


def test_none_location_is_safe():
    assert normalize_location(None) == (None, None)


# --- Instruction 1: Indeed emits ISO 3166-2:MY state codes ---------------


@pytest.mark.parametrize(
    "code,expected_state",
    [
        ("M01", "Johor"),
        ("M02", "Kedah"),
        ("M03", "Kelantan"),
        ("M04", "Melaka"),
        ("M05", "Negeri Sembilan"),
        ("M06", "Pahang"),
        ("M07", "Pulau Pinang"),
        ("M08", "Perak"),
        ("M09", "Perlis"),
        ("M10", "Selangor"),
        ("M11", "Terengganu"),
        ("M12", "Sabah"),
        ("M13", "Sarawak"),
        ("M14", "Kuala Lumpur"),
        ("M15", "Labuan"),
        ("M16", "Putrajaya"),
    ],
)
def test_resolves_iso_state_codes(code, expected_state):
    normalized, unmatched = normalize_location(Location(state=code))

    assert normalized.state == expected_state
    assert unmatched is None


def test_iso_state_code_matches_case_insensitively():
    normalized, unmatched = normalize_location(Location(state="m14"))

    assert normalized.state == "Kuala Lumpur"
    assert unmatched is None


def test_city_and_iso_code_together_resolve():
    normalized, unmatched = normalize_location(
        Location(city="Bayan Lepas", state="M07", country=Country.MALAYSIA)
    )

    assert normalized.city == "Bayan Lepas"
    assert normalized.state == "Pulau Pinang"
    assert unmatched is None


# --- Instruction 3: edge cases seen in live baseline data -----------------


def test_country_name_in_state_field_does_not_resolve():
    """'Malaysia' (a country) sometimes lands in the state slot; it must not
    resolve to any MalaysianState."""
    original = Location(city="Atlantis", state="Malaysia")

    normalized, unmatched = normalize_location(original)

    assert normalized.state == "Malaysia"
    assert normalized.state not in {state.value for state in MalaysianState}
    assert unmatched == "Atlantis, Malaysia"


def test_remote_in_city_field_does_not_resolve_to_a_place():
    normalized, unmatched = normalize_location(
        Location(city="Remote", country=Country.MALAYSIA)
    )

    assert normalized.city == "Remote"
    assert normalized.state is None
    assert unmatched == "Remote"


def test_empty_string_location_is_handled_like_a_miss():
    normalized, unmatched = normalize_location(Location(city="", state=""))

    assert normalized.city == ""
    assert normalized.state == ""
    assert unmatched is None
