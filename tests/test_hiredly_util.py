"""Hiredly record parsing, against real captured records.

Every value asserted here was read out of tests/fixtures/hiredly/ rather than
remembered - see the README beside the fixtures for what each record covers.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from jobspy.hiredly.util import (
    parse_active_at,
    parse_company_name,
    parse_compensation,
    parse_description,
    parse_experience_range,
    parse_is_remote,
    parse_job,
    parse_job_types,
    parse_location,
)
from jobspy.model import (
    CompensationInterval,
    Country,
    DescriptionFormat,
    JobType,
)

FIXTURES = Path(__file__).parent / "fixtures" / "hiredly"


def nodes(name: str) -> list[dict]:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return payload["data"]["jobListsSearchResults"]["nodes"]


RECORDS = {node["id"]: node for node in nodes("search_page.json")}
MALFORMED = nodes("search_malformed.json")

SALARIED = RECORDS["a37fed3c-75e4-47f7-9a3b-c21c5044f7bf"]  # "5000 - 7000"
SINGLE_VALUE = RECORDS["8f5ec12d-adfd-4e87-9d00-badbf5484bef"]  # "400"
UNDISCLOSED = RECORDS["a13f6d67-e5b8-44c3-86b9-926c1451773f"]
AGGREGATED = RECORDS["8c138a21-ce0d-4fdf-a802-427bbfbb9f1a"]  # category=scraped
REMOTE_REGION = RECORDS["3279048b-d016-41a9-a260-eb3b211b4ebf"]  # stateRegion=Remote
INTERNSHIP = RECORDS["ae1b3068-0265-4aa8-a132-dfe3fc58a4ec"]
JUNK_SALARY = RECORDS["c2cc7a2a-817f-45b4-b99e-81eda389924c"]  # "1700 - 5002500"
REMOTE_PREF = RECORDS["8fd5baae-3fb2-45ae-bd2f-ab48ad19a89b"]  # ghp remote True
PENANG = RECORDS["7abd77e0-ed5d-4796-9eb7-464a9693073b"]
SINGAPORE = RECORDS["46843029-4cf3-46ea-8400-e6000365fdb5"]  # stateRegion=North-East


class TestCompanyName:
    def test_reads_the_company_object(self):
        assert parse_company_name(SALARIED) == "Syno Medical Sdn Bhd"

    def test_falls_back_to_the_aggregated_name(self):
        assert parse_company_name(MALFORMED[6]) == "Aggregated Co"

    def test_none_when_neither_is_present(self):
        assert parse_company_name(MALFORMED[2]) is None


class TestLocation:
    def test_keeps_the_free_text_as_city_and_the_region_as_state(self):
        location = parse_location(SALARIED)
        assert location.city == (
            "D2-01-01, Pusat Perdagangan Dana 1, Jalan 1A/46, Petaling Jaya"
        )
        assert location.state == "Selangor"
        assert location.country == Country.MALAYSIA

    def test_board_spelling_is_left_for_the_gazetteer(self):
        """ "Penang" is not rewritten to "Pulau Pinang" here."""
        assert parse_location(PENANG).state == "Penang"

    def test_remote_region_is_not_a_state(self):
        location = parse_location(REMOTE_REGION)
        assert location.state is None
        assert location.city == "Petaling Jaya"

    def test_all_null(self):
        location = parse_location(MALFORMED[2])
        assert location.city is None and location.state is None


class TestIsRemote:
    def test_remote_region(self):
        assert parse_is_remote(REMOTE_REGION) is True

    def test_remote_working_preference(self):
        assert parse_is_remote(REMOTE_PREF) is True

    def test_explicit_not_remote_preference(self):
        assert parse_is_remote(JUNK_SALARY) is False

    def test_silent_is_none_not_false(self):
        """The board saying nothing is different from it saying on-site."""
        assert parse_is_remote(SALARIED) is None


class TestJobTypes:
    @pytest.mark.parametrize(
        "record,expected",
        [
            (SALARIED, [JobType.FULL_TIME]),
            (INTERNSHIP, [JobType.INTERNSHIP]),
        ],
    )
    def test_known_types(self, record, expected):
        assert parse_job_types(record) == expected

    def test_unknown_type_is_dropped_not_guessed(self):
        assert parse_job_types(MALFORMED[3]) is None


class TestActiveAt:
    def test_keeps_the_timestamp_and_offset(self):
        assert parse_active_at(SALARIED) == datetime(
            2026, 9, 22, 15, 26, 11, tzinfo=timezone(timedelta(hours=8))
        )

    def test_unparseable_is_none(self):
        assert parse_active_at(MALFORMED[4]) is None

    def test_missing_is_none(self):
        assert parse_active_at(MALFORMED[2]) is None


class TestCompensation:
    def test_range(self):
        pay = parse_compensation(SALARIED)
        assert (pay.min_amount, pay.max_amount) == (5000, 7000)
        assert pay.interval == CompensationInterval.MONTHLY
        assert pay.currency == "MYR"

    def test_single_value(self):
        pay = parse_compensation(SINGLE_VALUE)
        assert (pay.min_amount, pay.max_amount) == (400, 400)

    def test_undisclosed_is_none(self):
        assert parse_compensation(UNDISCLOSED) is None

    def test_junk_is_rejected_by_the_shared_sanity_bands(self):
        """ "1700 - 5002500" is an advertiser typo. Reusing parse_myr_salary
        is what rejects it - a local number parser would have kept it."""
        assert parse_compensation(JUNK_SALARY) is None

    def test_non_numeric_is_none(self):
        assert parse_compensation(MALFORMED[5]) is None

    def test_senior_pay_above_the_prose_ceiling_is_kept(self):
        """The salary field is a board field, so the board ceiling applies."""
        pay = parse_compensation({"salary": "40000 - 55000"})
        assert (pay.min_amount, pay.max_amount) == (40_000, 55_000)

    def test_a_typo_above_the_board_ceiling_is_still_rejected(self):
        """Measured on the live board, 2026-09-24."""
        assert parse_compensation({"salary": "50 - 100000"}) is None

    def test_missing_is_none(self):
        assert parse_compensation(MALFORMED[2]) is None


class TestDescription:
    def test_joins_description_and_requirements(self):
        html = parse_description(SALARIED, DescriptionFormat.HTML)
        assert SALARIED["description"] in html
        assert SALARIED["requirements"] in html
        assert html.index(SALARIED["description"]) < html.index(
            SALARIED["requirements"]
        )

    def test_markdown_is_converted(self):
        text = parse_description(SALARIED, DescriptionFormat.MARKDOWN)
        assert "<p>" not in text
        assert "Requirements" in text

    def test_plain_is_converted(self):
        text = parse_description(SALARIED, DescriptionFormat.PLAIN)
        assert "<" not in text

    def test_neither_present_is_none(self):
        assert parse_description(MALFORMED[2], DescriptionFormat.MARKDOWN) is None


class TestExperienceRange:
    def test_range(self):
        assert parse_experience_range(SALARIED) == "4-7 years"

    def test_negative_sentinel_means_zero(self):
        """Internships carry minYearsExperience=-1, the board's 'none needed'."""
        assert parse_experience_range(INTERNSHIP) == "0 years"

    def test_missing_is_none(self):
        assert parse_experience_range(MALFORMED[2]) is None


class TestParseJob:
    def test_maps_a_full_record(self):
        job = parse_job(SALARIED)
        assert job.id == "hd-a37fed3c-75e4-47f7-9a3b-c21c5044f7bf"
        assert job.title == "Product Manager - Surgical Equipments"
        assert job.company_name == "Syno Medical Sdn Bhd"
        assert job.job_url == (
            "https://my.hiredly.com/jobs/"
            "jobs-malaysia-syno-medical-sdn-bhd-job-product-manager-surgical-equipments"
        )
        assert job.job_url_direct is None
        assert job.date_posted == date(2026, 9, 22)
        assert job.job_level == "Manager / Team Lead"
        assert job.skills == [
            "Leadership",
            "Sales Strategy",
            "Marketing Analytics",
            "Data Collection",
        ]
        assert job.experience_range == "4-7 years"
        assert job.company_logo.startswith("https://s3.ap-southeast-1.amazonaws.com/")
        assert job.compensation.min_amount == 5000
        assert job.description

    def test_title_whitespace_is_stripped(self):
        assert parse_job(UNDISCLOSED).title == "HR Executive"

    def test_aggregated_listing_links_to_the_employer(self):
        job = parse_job(AGGREGATED)
        assert job.job_url_direct.startswith("https://swarovski.wd3.myworkdayjobs.com/")
        assert job.job_url.startswith("https://my.hiredly.com/jobs/")

    def test_missing_logo_stays_none(self):
        assert parse_job(SINGLE_VALUE).company_logo is None

    @pytest.mark.parametrize("index", [0, 1])
    def test_no_id_or_no_title_is_skipped(self, index):
        assert parse_job(MALFORMED[index]) is None

    def test_every_optional_field_null_still_parses(self):
        job = parse_job(MALFORMED[2])
        assert job is not None
        assert job.title == "Every optional field null"
        assert job.company_name is None
        assert job.compensation is None
        assert job.date_posted is None
        assert job.skills is None
        assert job.job_type is None

    def test_respects_description_format(self):
        html = parse_job(SALARIED, DescriptionFormat.HTML).description
        markdown = parse_job(SALARIED, DescriptionFormat.MARKDOWN).description
        assert "<p>" in html
        assert "<p>" not in markdown
