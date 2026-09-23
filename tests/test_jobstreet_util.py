"""Parser tests for JobStreet MY, against real captured responses.

The fixtures are trimmed live payloads - see tests/fixtures/jobstreet/README.md
for why each record is in there. Assertions quote the board's real strings,
non-breaking spaces and all.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from jobspy.jobstreet.util import parse_job
from jobspy.model import Country, JobType

FIXTURES = Path(__file__).parent / "fixtures" / "jobstreet"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def records() -> dict[str, dict]:
    """Search-page records keyed by board id, for addressing one at a time."""
    return {r["id"]: r for r in load("search_page.json")["data"]}


def test_parses_the_nominal_record(records):
    job = parse_job(records["94689504"])

    assert job.id == "js-94689504"
    assert job.title
    assert job.company_name
    assert job.job_url == "https://my.jobstreet.com/job/94689504"
    assert job.location.country == Country.MALAYSIA


def test_stamps_a_site_prefixed_id(records):
    """Exact dedup keys on this; an unprefixed id collides across boards."""
    for record in records.values():
        assert parse_job(record).id == f"js-{record['id']}"


def test_job_url_carries_no_tracking_query(records):
    """A tracking token in the URL would defeat URL-based dedup."""
    for record in records.values():
        assert "?" not in parse_job(record).job_url
