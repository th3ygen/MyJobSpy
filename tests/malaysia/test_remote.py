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
        # "Core hours are EST." now returns unknown to avoid false exclusions like
        # "est. 1998". A missed EST timezone hint costs less than falsely excluding
        # established dates, since this field sorts rather than filters.
        ("Core hours are EST.", "unknown"),
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


def test_established_abbreviation_is_not_a_us_timezone(make_job):
    job = make_job(
        is_remote=True,
        description="TechCorp, est. 1998, is hiring for a fully remote role based in Malaysia.",
    )
    assert classify_remote_scope(job) == "my"


def test_contact_us_boilerplate_is_not_the_united_states(make_job):
    job = make_job(
        is_remote=True,
        description="Work hours: GMT+8. Contact us for more info about this Kuala Lumpur based role.",
    )
    assert classify_remote_scope(job) == "my"


def test_asia_pacific_time_is_not_a_us_timezone(make_job):
    """The US-timezone pattern matched the "pacific time" inside "Asia
    Pacific time zones", classifying an APAC-eligible job as other_country
    on the highest-precedence branch - the exact false-exclusion class the
    pattern was introduced to eliminate."""
    job = make_job(
        is_remote=True,
        description="Remote role covering Asia Pacific time zones.",
        location=None,
    )

    assert classify_remote_scope(job) != "other_country"


def test_hyphenated_asia_pacific_time_is_not_a_us_timezone(make_job):
    job = make_job(
        is_remote=True,
        description="Support customers across Asia-Pacific time zones.",
        location=None,
    )

    assert classify_remote_scope(job) != "other_country"


def test_genuine_pacific_standard_time_is_still_other_country(make_job):
    job = make_job(
        is_remote=True,
        description="Core hours are 9am-5pm Pacific Standard Time.",
        location=None,
    )

    assert classify_remote_scope(job) == "other_country"


def test_genuine_eastern_time_is_still_other_country(make_job):
    job = make_job(
        is_remote=True,
        description="You must overlap with Eastern Time for standups.",
        location=None,
    )

    assert classify_remote_scope(job) == "other_country"


def test_sergeant_abbreviation_is_not_singapore_time(make_job):
    job = make_job(
        is_remote=True,
        title="Security Sgt - Overnight Remote Monitoring",
        description="Remote monitoring role.",
        location=None,
    )
    assert classify_remote_scope(job) == "unknown"
