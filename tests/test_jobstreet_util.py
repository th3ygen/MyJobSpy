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


class TestSalary:
    def test_parses_a_range(self, records):
        """The board sends non-breaking spaces and en-dashes. Both must work."""
        job = parse_job(records["94689504"])
        assert job.compensation.min_amount == 5000
        assert job.compensation.max_amount == 7500
        assert job.compensation.interval.value == "monthly"

    def test_parses_a_single_value_as_both_bounds(self, records):
        job = parse_job(records["94333139"])
        assert job.compensation.min_amount == 1000
        assert job.compensation.max_amount == 1000

    def test_leaves_dollar_junk_unpriced(self, records):
        """'$5,000 - $7,000' is an advertiser typo, not a USD salary.

        Guessing it is MYR would be indistinguishable downstream from a
        figure the board actually vouched for.
        """
        assert parse_job(records["94553263"]).compensation is None

    def test_absent_label_yields_no_compensation(self, records):
        assert parse_job(records["94830903"]).compensation is None

    def test_does_not_mark_salary_as_description_parsed(self, records):
        """This is what makes salary_source come out as direct_data.

        jobspy/malaysia/__init__.py skips its own salary stage when
        compensation is already set, and frame.py then defaults the source
        to direct_data. Setting this flag here would mislabel the board's
        own figure as scraped from prose.
        """
        job = parse_job(records["94689504"])
        assert job.salary_parsed_from_description is False


class TestLocation:
    def test_bare_state(self, records):
        job = parse_job(records["94462128"])
        assert job.location.state == "Kuala Lumpur"
        assert job.location.city is None

    def test_suburb_and_state(self, records):
        job = parse_job(records["94831259"])
        assert job.location.city == "Cheras"
        assert job.location.state == "Kuala Lumpur"

    def test_always_stamps_malaysia(self, records):
        for record in records.values():
            assert parse_job(record).location.country == Country.MALAYSIA


class TestWorkTypeAndArrangement:
    def test_single_work_type(self, records):
        assert parse_job(records["94689504"]).job_type == [JobType.FULL_TIME]

    def test_multiple_work_types(self, records):
        """One posting can be tagged both - it appears under both filters."""
        types = parse_job(records["94586568"]).job_type
        assert set(types) == {JobType.TEMPORARY, JobType.FULL_TIME}

    def test_remote_is_true_only_for_remote(self, records):
        assert parse_job(records["94462128"]).is_remote is True
        assert parse_job(records["94234551"]).is_remote is False  # Hybrid
        assert parse_job(records["94689504"]).is_remote is False  # On-site


class TestCompanyName:
    def test_falls_back_to_advertiser(self, records):
        """94462128 has no companyName key at all - only an advertiser."""
        assert parse_job(records["94462128"]).company_name == "Private Advertiser"


class TestMalformedRecords:
    """Every case here is a shape the live API emits. None may raise."""

    @pytest.fixture(scope="class")
    def bad(self) -> dict[str, dict]:
        return {r["id"]: r for r in load("search_malformed.json")["data"]}

    def test_no_company_anywhere(self, bad):
        assert parse_job(bad["90000001"]).company_name is None

    def test_empty_locations_list(self, bad):
        job = parse_job(bad["90000002"])
        assert job.location.city is None and job.location.state is None
        assert job.location.country == Country.MALAYSIA

    def test_missing_locations_key(self, bad):
        assert parse_job(bad["90000003"]).location.state is None

    def test_null_company_and_unparseable_salary(self, bad):
        job = parse_job(bad["90000004"])
        assert job.company_name is None
        assert job.compensation is None
        assert job.job_type is None  # "Permanent" is not a known work type

    def test_unparseable_date_leaves_field_unset(self, bad):
        job = parse_job(bad["90000005"])
        assert job.date_posted is None
        assert job.title == "Bad Date"  # the job survives

    def test_three_part_location_label(self, bad):
        job = parse_job(bad["90000006"])
        assert job.location.state == "Penang"
        assert job.location.city == "Bayan Lepas, Bayan Baru"

    def test_record_without_id_is_skipped(self):
        assert parse_job({"title": "No Id"}) is None

    def test_record_without_title_is_skipped(self):
        assert parse_job({"id": "123"}) is None
