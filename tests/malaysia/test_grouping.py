from __future__ import annotations

import pytest
from rapidfuzz import fuzz

from jobspy.malaysia.grouping import (
    assign_groups,
    dedupe_exact,
    normalize_company,
    seniority_markers,
)
from jobspy.model import Country, Location


def _my(city="Kuala Lumpur"):
    return Location(city=city, state="Kuala Lumpur", country=Country.MALAYSIA)


def test_normalizes_company_suffixes():
    assert normalize_company("Grab Malaysia Sdn Bhd") == "grab"
    assert normalize_company("GrabTaxi Holdings Pte Ltd") == "grabtaxi holdings"
    assert normalize_company(None) == ""


def test_detects_seniority_markers():
    assert seniority_markers("Senior Software Engineer") == frozenset({"senior"})
    assert seniority_markers("Software Engineer") == frozenset()
    assert seniority_markers("Engineering Manager") == frozenset({"manager"})


def test_exact_dedup_drops_repeated_urls(make_job):
    jobs = [
        make_job(job_url="https://x/1"),
        make_job(job_url="https://x/1?utm_source=email"),
        make_job(job_url="https://x/2"),
    ]

    assert len(dedupe_exact(jobs)) == 2


def test_exact_dedup_keeps_the_most_complete_record(make_job):
    sparse = make_job(job_url="https://x/1", description=None)
    rich = make_job(job_url="https://x/1", description="Full description here")

    kept = dedupe_exact([sparse, rich])

    assert len(kept) == 1
    assert kept[0].description == "Full description here"


def test_groups_same_job_across_boards(make_job):
    jobs = [
        make_job(job_url="https://a/1", title="Software Engineer", location=_my()),
        make_job(job_url="https://b/1", title="Software  Engineer", location=_my()),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group is not None
    assert grouped[0].dedup_group == grouped[1].dedup_group


def test_never_groups_across_seniority(make_job):
    jobs = [
        make_job(
            job_url="https://a/1", title="Senior Software Engineer", location=_my()
        ),
        make_job(job_url="https://b/1", title="Software Engineer", location=_my()),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group != grouped[1].dedup_group


def test_does_not_group_different_states(make_job):
    jobs = [
        make_job(job_url="https://a/1", title="Software Engineer", location=_my()),
        make_job(
            job_url="https://b/1",
            title="Software Engineer",
            location=Location(
                city="Penang", state="Pulau Pinang", country=Country.MALAYSIA
            ),
        ),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group != grouped[1].dedup_group


def test_groups_a_remote_listing_with_a_located_one(make_job):
    jobs = [
        make_job(job_url="https://a/1", title="Software Engineer", location=_my()),
        make_job(
            job_url="https://b/1",
            title="Software Engineer",
            location=None,
            is_remote=True,
        ),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group == grouped[1].dedup_group


def test_does_not_group_different_companies(make_job):
    jobs = [
        make_job(job_url="https://a/1", company_name="Grab", location=_my()),
        make_job(job_url="https://b/1", company_name="Shopee", location=_my()),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group != grouped[1].dedup_group


def test_group_ids_are_stable_across_runs(make_job):
    def build():
        return [
            make_job(job_url="https://a/1", title="Software Engineer", location=_my()),
            make_job(job_url="https://b/1", title="Software Engineer", location=_my()),
        ]

    first = assign_groups(build())[0].dedup_group
    second = assign_groups(build())[0].dedup_group

    assert first == second


def test_grouping_never_removes_rows(make_job):
    jobs = [make_job(job_url=f"https://a/{i}") for i in range(5)]

    assert len(assign_groups(jobs)) == 5


def test_two_jobs_with_unresolved_state_are_not_grouped(make_job):
    """normalize_location (Task 7) sets state=None when it cannot resolve a
    location. Two jobs both carrying state=None, neither remote, must not be
    treated as location-compatible - "both unknown" is not evidence of "same
    place."."""
    unresolved = Location(city="Somewhere Weird", state=None, country=Country.MALAYSIA)
    jobs = [
        make_job(job_url="https://a/1", title="Software Engineer", location=unresolved),
        make_job(job_url="https://b/1", title="Software Engineer", location=unresolved),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group is None
    assert grouped[1].dedup_group is None


# --- Real-data regression tests -------------------------------------------
#
# Sampled from 120 real listings. Two companies each posted the same role at
# two seniority levels - the exact false-grouping this module must prevent.
# These are messier than the synthetic "Senior Software Engineer" case:
# punctuation, parentheses, dotted tech names.


def test_never_groups_aveva_seniority_pair(make_job):
    jobs = [
        make_job(
            job_url="https://a/1",
            company_name="AVEVA",
            title="Full-Stack Engineer (.NET + Angular)",
            location=_my(),
        ),
        make_job(
            job_url="https://b/1",
            company_name="AVEVA",
            title="Senior Full-Stack Engineer (.NET + Angular)",
            location=_my(),
        ),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group != grouped[1].dedup_group


def test_never_groups_applify_seniority_pair(make_job):
    jobs = [
        make_job(
            job_url="https://a/1",
            company_name="Applify Technologies Sdn Bhd",
            title="MES System Developer",
            location=_my(),
        ),
        make_job(
            job_url="https://b/1",
            company_name="Applify Technologies Sdn Bhd",
            title="Senior MES System Developer",
            location=_my(),
        ),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group != grouped[1].dedup_group


def test_aveva_pair_token_sort_ratio_is_on_record():
    """Pins the actual score for this real pair so the margin relative to
    threshold=90 is on record. Measured at 89.86: close to, but just under,
    the threshold on title text alone. The seniority guard is what makes the
    non-grouping outcome unconditional rather than a threshold coincidence -
    see test_never_groups_aveva_seniority_pair."""
    score = fuzz.token_sort_ratio(
        "full stack engineer net angular", "senior full stack engineer net angular"
    )
    assert score == pytest.approx(89.855, abs=0.01)


def test_applify_pair_token_sort_ratio_is_on_record():
    """Measured at 85.11 - comfortably under threshold=90 on title text
    alone. See test_never_groups_applify_seniority_pair for the guard that
    makes the non-grouping outcome absolute rather than threshold-dependent."""
    score = fuzz.token_sort_ratio("mes system developer", "senior mes system developer")
    assert score == pytest.approx(85.106, abs=0.01)


def test_normalize_company_real_world_shapes():
    assert normalize_company("Applify Technologies Sdn Bhd") == "applify technologies"
    assert (
        normalize_company("ASIAN BIOSCIENCE CORPORATION SDN BHD")
        == "asian bioscience corporation"
    )
    # "(M)" is a Malaysia marker in parentheses; stripping punctuation leaves
    # a stray "m" token after the "sdn bhd" suffix is removed. See report for
    # the decision on this residue.
    assert normalize_company("ARRK Engineering GmbH") == "arrk engineering"
    assert normalize_company("Gen Digital Inc.") == "gen digital"
    assert (
        normalize_company("Skill Quotient Technologies Inc")
        == "skill quotient technologies"
    )
    assert normalize_company("Beyondsoft Singapore") == "beyondsoft singapore"
    assert normalize_company("Experian Asia Pacific") == "experian asia pacific"


def test_normalize_company_conspec_parenthesised_malaysia_marker():
    result = normalize_company("Conspec Builders (M) Sdn Bhd")
    # Whatever residue policy is chosen, the company's identity must survive.
    assert "conspec builders" in result
