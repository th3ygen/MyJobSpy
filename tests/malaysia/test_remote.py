from __future__ import annotations

import pytest

from jobspy.malaysia.remote import classify_remote_scope
from jobspy.model import Country, Location


def test_non_remote_job_has_no_scope(make_job):
    assert classify_remote_scope(make_job(is_remote=False)) is None


@pytest.mark.parametrize(
    "description,expected",
    [
        ("Candidates must be based in Malaysia.", "my"),
        ("Open to candidates across APAC.", "apac"),
        ("Work from anywhere in the world.", "global"),
        ("Must have US work authorization.", "other_country"),
        ("We are a fast-growing startup.", "unknown"),
        ("You will work GMT+8 hours.", "apac"),
        ("Core hours are EST.", "other_country"),
    ],
)
def test_classifies_from_description(make_job, description, expected):
    job = make_job(is_remote=True, description=description, location=None)

    assert classify_remote_scope(job) == expected


def test_explicit_exclusion_beats_generic_remote(make_job):
    job = make_job(
        is_remote=True,
        description="Fully remote role. Applicants must be authorized to work in the US.",
    )

    assert classify_remote_scope(job) == "other_country"


def test_malaysian_location_implies_my(make_job):
    job = make_job(
        is_remote=True,
        description="Remote role.",
        location=Location(city="Kuala Lumpur", country=Country.MALAYSIA),
    )

    assert classify_remote_scope(job) == "my"


def test_missing_description_is_unknown(make_job):
    assert (
        classify_remote_scope(make_job(is_remote=True, description=None, location=None))
        == "unknown"
    )


def test_missing_description_with_malaysian_location_returns_my(make_job):
    """LinkedIn supplies no descriptions, but if location is Malaysia, infer MY eligibility."""
    job = make_job(
        is_remote=True,
        description=None,
        location=Location(city="Kuala Lumpur", country=Country.MALAYSIA),
    )

    assert classify_remote_scope(job) == "my"
