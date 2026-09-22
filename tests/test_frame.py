from __future__ import annotations

from jobspy.frame import build_jobs_dataframe
from jobspy.model import (
    Compensation,
    CompensationInterval,
    Country,
    JobResponse,
    Location,
)
from jobspy.util import desired_order


def test_builds_one_row_per_job(make_job):
    response = JobResponse(jobs=[make_job(), make_job(job_url="https://x/2")])

    df = build_jobs_dataframe({"indeed": response}, country_enum=Country.MALAYSIA)

    assert len(df) == 2
    assert set(df["site"]) == {"indeed"}


def test_columns_match_desired_order(make_job):
    response = JobResponse(jobs=[make_job()])

    df = build_jobs_dataframe({"indeed": response}, country_enum=Country.MALAYSIA)

    assert list(df.columns) == desired_order


def test_flattens_compensation_and_location(make_job):
    job = make_job(
        location=Location(city="Cyberjaya", state="Selangor", country=Country.MALAYSIA),
        compensation=Compensation(
            interval=CompensationInterval.MONTHLY,
            min_amount=5000,
            max_amount=7000,
            currency="MYR",
        ),
    )

    df = build_jobs_dataframe(
        {"indeed": JobResponse(jobs=[job])}, country_enum=Country.MALAYSIA
    )

    row = df.iloc[0]
    assert row["location"] == "Cyberjaya, Selangor, Malaysia"
    assert row["interval"] == "monthly"
    assert row["min_amount"] == 5000
    assert row["currency"] == "MYR"
    assert row["salary_source"] == "direct_data"


def test_empty_input_returns_empty_frame():
    df = build_jobs_dataframe({}, country_enum=Country.MALAYSIA)

    assert df.empty


def test_emits_city_and_state_columns(make_job):
    job = make_job(
        location=Location(city="Cyberjaya", state="Selangor", country=Country.MALAYSIA)
    )

    df = build_jobs_dataframe(
        {"indeed": JobResponse(jobs=[job])}, country_enum=Country.MALAYSIA
    )

    assert df.iloc[0]["city"] == "Cyberjaya"
    assert df.iloc[0]["state"] == "Selangor"
    assert df.iloc[0]["location"] == "Cyberjaya, Selangor, Malaysia"


def test_emits_pipeline_columns(make_job):
    job = make_job(dedup_group="abc123", remote_scope="my")

    df = build_jobs_dataframe(
        {"indeed": JobResponse(jobs=[job])}, country_enum=Country.MALAYSIA
    )

    assert df.iloc[0]["dedup_group"] == "abc123"
    assert df.iloc[0]["remote_scope"] == "my"


def test_new_columns_are_in_desired_order():
    for column in ("dedup_group", "remote_scope", "city", "state"):
        assert column in desired_order


def test_enforce_annual_salary_converts_monthly_to_yearly(make_job):
    job = make_job(
        compensation=Compensation(
            interval=CompensationInterval.MONTHLY,
            min_amount=5000,
            max_amount=7000,
            currency="MYR",
        ),
    )

    df = build_jobs_dataframe(
        {"indeed": JobResponse(jobs=[job])},
        country_enum=Country.MALAYSIA,
        enforce_annual_salary=True,
    )

    row = df.iloc[0]
    assert row["interval"] == "yearly"
    assert row["min_amount"] == 60000
    assert row["max_amount"] == 84000
    assert row["currency"] == "MYR"


def test_usa_extracts_salary_from_description_when_no_compensation(make_job):
    job = make_job(
        compensation=None,
        description="We offer a salary of $80,000 - $100,000 per year",
    )

    df = build_jobs_dataframe(
        {"indeed": JobResponse(jobs=[job])}, country_enum=Country.USA
    )

    row = df.iloc[0]
    assert row["interval"] == "yearly"
    assert row["min_amount"] == 80000
    assert row["max_amount"] == 100000
    assert row["currency"] == "USD"
    assert row["salary_source"] == "description"
