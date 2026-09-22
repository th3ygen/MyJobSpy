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


# Real job_url shapes, copied from how each scraper in this repo actually
# builds them. Half of the boards put the listing id in the *query string*,
# which a canonicalizer that drops the query collapses onto one key. Every
# other fixture in this file is path-distinguished, which is exactly why the
# collapse went unnoticed.
_REAL_BOARD_URLS = {
    # jobspy/indeed/__init__.py: f'{self.base_url}/viewjob?jk={job["key"]}'
    "indeed": (
        "https://malaysia.indeed.com/viewjob?jk=a1b2c3d4e5f60001",
        "https://malaysia.indeed.com/viewjob?jk=a1b2c3d4e5f60002",
    ),
    # jobspy/glassdoor/__init__.py: f"{self.base_url}job-listing/j?jl={job_id}"
    "glassdoor": (
        "https://www.glassdoor.com/job-listing/j?jl=1009412345",
        "https://www.glassdoor.com/job-listing/j?jl=1009498765",
    ),
    # jobspy/ziprecruiter/__init__.py: f"{self.base_url}/jobs//j?lvk={listing_key}"
    "ziprecruiter": (
        "https://www.ziprecruiter.com/jobs//j?lvk=9f1c2a7b0001",
        "https://www.ziprecruiter.com/jobs//j?lvk=9f1c2a7b0002",
    ),
    # jobspy/bdjobs/__init__.py: an href carrying ?jobid=
    "bdjobs": (
        "https://jobs.bdjobs.com/jobdetails.asp?id=1301234&ln=1",
        "https://jobs.bdjobs.com/jobdetails.asp?id=1309876&ln=1",
    ),
    # jobspy/linkedin/__init__.py: f"{self.base_url}/jobs/view/{job_id}"
    # (path-distinguished - the shape that always worked)
    "linkedin": (
        "https://www.linkedin.com/jobs/view/4012345678",
        "https://www.linkedin.com/jobs/view/4087654321",
    ),
}


@pytest.mark.parametrize("board", sorted(_REAL_BOARD_URLS))
def test_exact_dedup_keeps_distinct_listings_on_every_board_shape(make_job, board):
    """Two different listings must never collapse into one row, whatever
    part of the URL the board encodes identity in."""
    first, second = _REAL_BOARD_URLS[board]

    jobs = [make_job(job_url=first), make_job(job_url=second)]

    assert len(dedupe_exact(jobs)) == 2


def test_exact_dedup_survives_tracking_params_on_a_query_id_url(make_job):
    """Stripping tracking noise must not require stripping the whole query:
    the same Indeed listing with a campaign tag is still one listing."""
    jobs = [
        make_job(job_url="https://malaysia.indeed.com/viewjob?jk=a1b2c3d4e5f60001"),
        make_job(
            job_url=(
                "https://malaysia.indeed.com/viewjob"
                "?jk=a1b2c3d4e5f60001&utm_source=email&utm_campaign=weekly"
            )
        ),
        make_job(
            job_url=(
                "https://malaysia.indeed.com/viewjob"
                "?jk=a1b2c3d4e5f60001&gclid=Cj0KCQiA&fbclid=IwAR1"
            )
        ),
    ]

    assert len(dedupe_exact(jobs)) == 1


def test_exact_dedup_prefers_the_board_assigned_id(make_job):
    """Every scraper stamps a site-prefixed board id on JobPost.id. When it
    is present it is the identity - the same listing reached by two
    different URLs is still one listing."""
    jobs = [
        make_job(
            id="in-a1b2c3d4e5f60001",
            job_url="https://malaysia.indeed.com/viewjob?jk=a1b2c3d4e5f60001",
        ),
        make_job(
            id="in-a1b2c3d4e5f60001",
            job_url="https://malaysia.indeed.com/viewjob?jk=a1b2c3d4e5f60001&from=serp",
        ),
    ]

    assert len(dedupe_exact(jobs)) == 1


def test_exact_dedup_never_merges_distinct_board_ids(make_job):
    jobs = [
        make_job(
            id="in-a1b2c3d4e5f60001", job_url="https://malaysia.indeed.com/viewjob"
        ),
        make_job(
            id="in-a1b2c3d4e5f60002", job_url="https://malaysia.indeed.com/viewjob"
        ),
        make_job(id="li-4012345678", job_url="https://malaysia.indeed.com/viewjob"),
    ]

    assert len(dedupe_exact(jobs)) == 3


def test_a_batch_of_query_id_listings_is_not_collapsed(make_job):
    """The reported failure in miniature: a page of Indeed results is 25
    listings distinguished only by ?jk=."""
    jobs = [
        make_job(job_url=f"https://malaysia.indeed.com/viewjob?jk=deadbeef{n:04d}")
        for n in range(25)
    ]

    assert len(dedupe_exact(jobs)) == 25


def test_unresolved_fallback_ids_differ_for_two_unrelated_listings(make_job):
    """F17: 'unresolved' is not evidence two postings are the same. Two
    query-id listings that cannot be resolved must not share a
    dedup_group."""
    unresolved = Location(city="Somewhere Weird", state=None, country=Country.MALAYSIA)
    jobs = [
        make_job(
            job_url="https://malaysia.indeed.com/viewjob?jk=a1b2c3d4e5f60001",
            company_name=None,
            title="Software Engineer",
            location=unresolved,
        ),
        make_job(
            job_url="https://malaysia.indeed.com/viewjob?jk=a1b2c3d4e5f60002",
            company_name=None,
            title="Data Analyst",
            location=unresolved,
        ),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group is not None
    assert grouped[1].dedup_group is not None
    assert grouped[0].dedup_group != grouped[1].dedup_group


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
    place." Each still gets its own stable, per-row dedup_group (derived
    from its canonical url) rather than a shared None sentinel: dedup_group
    must be uniform across every row so "is this a duplicate?" is always
    answered by group size, and a shared None would compare equal under
    ==, which is indistinguishable from an actual match to any consumer
    that isn't specifically routing through pandas.groupby(dropna=True)."""
    unresolved = Location(city="Somewhere Weird", state=None, country=Country.MALAYSIA)
    jobs = [
        make_job(job_url="https://a/1", title="Software Engineer", location=unresolved),
        make_job(job_url="https://b/1", title="Software Engineer", location=unresolved),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group is not None
    assert grouped[1].dedup_group is not None
    assert grouped[0].dedup_group != grouped[1].dedup_group


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


def test_detects_trailing_level_markers():
    """ "II" and "2" are the same real-world level convention written two
    ways, so they normalize to the same marker. A letter-number code like
    "L3" is kept in its own namespace - see _level_marker."""
    assert seniority_markers("Software Engineer II") == frozenset({"level:2"})
    assert seniority_markers("Software Engineer 2") == frozenset({"level:2"})
    assert seniority_markers("Backend Engineer L3") == frozenset({"code:l3"})
    # A trailing level word is a real level, wherever in the title it sits.
    assert seniority_markers("Business Intelligence I") == frozenset({"level:1"})
    # A bare roman-numeral-shaped word NOT in trailing position is not a
    # level - anchoring on the last token avoids a false trigger here.
    assert seniority_markers("Engineer V Team") == frozenset()


def test_roman_numeral_levels_do_not_group(make_job):
    # Real false positive from a live scrape: Experian Asia Pacific posted
    # both "Software Engineer I" and "Software Engineer II" as distinct
    # openings, and they grouped as one posting before this fix - neither
    # title carries a word marker, and token_sort_ratio scores the pair
    # around 97, comfortably over threshold.
    jobs = [
        make_job(
            job_url="https://a/1",
            company_name="Experian Asia Pacific",
            title="Software Engineer I",
            location=_my(),
        ),
        make_job(
            job_url="https://b/1",
            company_name="Experian Asia Pacific",
            title="Software Engineer II",
            location=_my(),
        ),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group != grouped[1].dedup_group


def test_numeric_levels_do_not_group(make_job):
    jobs = [
        make_job(
            job_url="https://a/1",
            company_name="Acme Sdn Bhd",
            title="Data Engineer 1",
            location=_my(),
        ),
        make_job(
            job_url="https://b/1",
            company_name="Acme Sdn Bhd",
            title="Data Engineer 2",
            location=_my(),
        ),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group != grouped[1].dedup_group


def test_letter_number_level_codes_do_not_group(make_job):
    jobs = [
        make_job(
            job_url="https://a/1",
            company_name="Acme Sdn Bhd",
            title="Backend Engineer L3",
            location=_my(),
        ),
        make_job(
            job_url="https://b/1",
            company_name="Acme Sdn Bhd",
            title="Backend Engineer L4",
            location=_my(),
        ),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group != grouped[1].dedup_group


def test_same_level_still_groups(make_job):
    jobs = [
        make_job(
            job_url="https://a/1",
            company_name="Experian Asia Pacific",
            title="Software Engineer II",
            location=_my(),
        ),
        make_job(
            job_url="https://b/1",
            company_name="Experian Asia Pacific",
            title="Software Engineer II",
            location=_my(),
        ),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group is not None
    assert grouped[0].dedup_group == grouped[1].dedup_group


def test_unlevelled_titles_still_group(make_job):
    jobs = [
        make_job(
            job_url="https://a/1",
            company_name="Experian Asia Pacific",
            title="Software Engineer",
            location=_my(),
        ),
        make_job(
            job_url="https://b/1",
            company_name="Experian Asia Pacific",
            title="Software Engineer",
            location=_my(),
        ),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group is not None
    assert grouped[0].dedup_group == grouped[1].dedup_group


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
    assert normalize_company("ARRK Engineering GmbH") == "arrk engineering"
    assert normalize_company("Gen Digital Inc.") == "gen digital"
    assert (
        normalize_company("Skill Quotient Technologies Inc")
        == "skill quotient technologies"
    )
    assert normalize_company("Beyondsoft Singapore") == "beyondsoft singapore"
    assert normalize_company("Experian Asia Pacific") == "experian asia pacific"


def test_normalize_company_conspec_parenthesised_malaysia_marker():
    # "(M)" is a Malaysia marker in parentheses; stripping punctuation leaves
    # a stray "m" token after the "sdn bhd" suffix is removed. See report for
    # the decision on this residue.
    result = normalize_company("Conspec Builders (M) Sdn Bhd")
    # Whatever residue policy is chosen, the company's identity must survive.
    assert "conspec builders" in result


def test_unresolved_fallback_group_id_is_stable_across_runs(make_job):
    """The per-row fallback id for unresolvable rows (see
    test_two_jobs_with_unresolved_state_are_not_grouped) must be derived
    from something stable, not e.g. object identity or a per-batch counter -
    otherwise the same listing scraped again tomorrow gets a different id
    and can never be recognized as already seen."""

    def build():
        unresolved = Location(
            city="Somewhere Weird", state=None, country=Country.MALAYSIA
        )
        return [
            make_job(
                job_url="https://a/1", title="Software Engineer", location=unresolved
            )
        ]

    first = assign_groups(build())[0].dedup_group
    second = assign_groups(build())[0].dedup_group

    assert first is not None
    assert first == second
