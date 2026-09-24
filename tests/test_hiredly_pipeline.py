"""Hiredly output through the Malaysian pipeline and into the DataFrame.

The fork's claim is that a new board inherits normalization with no
board-specific code in jobspy/malaysia/. These tests are what make that claim
falsifiable for board #2.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobspy.frame import build_jobs_dataframe
from jobspy.hiredly.constant import MALAYSIAN_REGIONS
from jobspy.hiredly.util import parse_job
from jobspy.malaysia import normalize
from jobspy.model import Country, JobResponse

FIXTURES = Path(__file__).parent / "fixtures" / "hiredly"


@pytest.fixture(scope="module")
def jobs():
    nodes = json.loads((FIXTURES / "search_page.json").read_text(encoding="utf-8"))[
        "data"
    ]["jobListsSearchResults"]["nodes"]
    # The scraper drops non-Malaysian regions before parsing; mirror that.
    nodes = [n for n in nodes if n["stateRegion"] in MALAYSIAN_REGIONS]
    return [job for job in (parse_job(n) for n in nodes) if job]


def by_id(jobs, suffix):
    return next(job for job in jobs if job.id.startswith(f"hd-{suffix}"))


def test_normalize_accepts_hiredly_jobs_without_wiring(jobs):
    normalized = normalize(list(jobs), group_duplicates=True)
    assert len(normalized) == len(jobs) == 9


def test_every_job_gets_a_canonical_state(jobs):
    """The board's region names ("Penang") resolve through the shared
    gazetteer, and the "Remote" record gets its state from its city."""
    normalized = normalize(list(jobs))

    assert all(job.location.state for job in normalized)
    assert by_id(normalized, "7abd77e0").location.state == "Pulau Pinang"
    assert by_id(normalized, "3279048b").location.state == "Selangor"


def test_board_salary_is_not_overwritten_by_the_description_parser(jobs):
    """a37fed3c's description was hand-edited to say "RM 3,000 per month",
    which disagrees with its board figure of 5000 - 7000 (see the fixture
    README). Without that disagreement this test could not fail."""
    normalized = normalize(list(jobs))
    job = by_id(normalized, "a37fed3c")

    assert job.compensation.min_amount == 5000
    assert job.salary_parsed_from_description is False


def test_rows_reach_the_dataframe_with_board_fields(jobs):
    normalized = normalize(list(jobs))
    df = build_jobs_dataframe(
        {"hiredly": JobResponse(jobs=normalized)},
        country_enum=Country.MALAYSIA,
        enforce_annual_salary=False,
    )

    assert len(df) == len(normalized)
    assert set(df["site"]) == {"hiredly"}
    assert set(df[df["min_amount"].notna()]["salary_source"]) == {"direct_data"}
    # Board-specific fields that only exist because desired_order lists them.
    for column in ("skills", "job_level", "experience_range", "job_url_direct"):
        assert df[column].notna().any(), f"{column} was dropped from the frame"
