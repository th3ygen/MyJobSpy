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
