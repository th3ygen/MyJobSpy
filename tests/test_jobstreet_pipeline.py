"""JobStreet output through the Malaysian pipeline and into the DataFrame.

The spec claims a new board inherits normalization at zero marginal cost.
These tests are what make that claim falsifiable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobspy.frame import build_jobs_dataframe
from jobspy.jobstreet.util import parse_job
from jobspy.malaysia import normalize
from jobspy.model import Country, JobResponse

FIXTURES = Path(__file__).parent / "fixtures" / "jobstreet"


@pytest.fixture(scope="module")
def jobs():
    records = json.loads((FIXTURES / "search_page.json").read_text(encoding="utf-8"))[
        "data"
    ]
    return [job for job in (parse_job(r) for r in records) if job]


def test_normalize_accepts_jobstreet_jobs_without_wiring(jobs):
    normalized = normalize(list(jobs), group_duplicates=True)
    assert len(normalized) == len(jobs)


def test_board_salary_is_not_overwritten_by_the_description_parser(jobs):
    """The board's own figure must win, and must not be relabelled."""
    priced = [job for job in jobs if job.compensation is not None]
    assert priced, "fixture should contain salaried records"

    before = {job.id: job.compensation.min_amount for job in priced}
    for job in normalize(list(jobs)):
        if job.id in before:
            assert job.compensation.min_amount == before[job.id]
            assert job.salary_parsed_from_description is False


def test_remote_scope_is_assigned(jobs):
    # Note (Ruling, matching test_pipeline.py's F1 precedent): the brief's
    # original version asserted remote_scope is not None for every job.
    # That's wrong given classify_remote_scope's documented contract -
    # "Returns None for non-remote jobs" - and this fixture is realistic:
    # only 1 of 8 records (js-94462128) carries a "Remote" work arrangement,
    # the rest are on-site/hybrid. Asserting the literal brief text would
    # require either mislabeling on-site jobs as having a remote scope or
    # changing classify_remote_scope's contract for every board, neither of
    # which is warranted by this fixture. The assertion is corrected to the
    # documented contract: a scope is assigned for remote jobs, and withheld
    # for non-remote ones.
    normalized = normalize(list(jobs))
    remote_jobs = [job for job in normalized if job.is_remote]
    assert remote_jobs, "fixture should contain at least one remote record"
    for job in remote_jobs:
        assert job.remote_scope is not None
    for job in normalized:
        if not job.is_remote:
            assert job.remote_scope is None


def test_rows_reach_the_dataframe_with_salary_marked_direct(jobs):
    normalized = normalize(list(jobs))
    df = build_jobs_dataframe(
        {"jobstreet": JobResponse(jobs=normalized)},
        country_enum=Country.MALAYSIA,
        enforce_annual_salary=False,
    )

    assert len(df) == len(normalized)
    assert set(df["site"]) == {"jobstreet"}

    priced = df[df["min_amount"].notna()]
    assert not priced.empty
    assert set(priced["salary_source"]) == {"direct_data"}


def test_state_survives_normalization(jobs):
    """Gazetteer misses null the state; KL must not be one of them."""
    normalized = normalize(list(jobs))
    states = {job.location.state for job in normalized if job.location}
    assert "Kuala Lumpur" in states
