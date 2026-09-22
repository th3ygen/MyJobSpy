from __future__ import annotations

import inspect

import pytest

import jobspy
from jobspy.model import JobResponse, Site


def test_country_indeed_defaults_to_malaysia():
    signature = inspect.signature(jobspy.scrape_jobs)

    assert signature.parameters["country_indeed"].default == "malaysia"


def test_group_duplicates_parameter_exists():
    signature = inspect.signature(jobspy.scrape_jobs)

    assert signature.parameters["group_duplicates"].default is True


def test_one_failing_board_does_not_kill_the_run(monkeypatch, make_job):
    class OkScraper:
        def __init__(self, **kwargs):
            pass

        def scrape(self, scraper_input):
            return JobResponse(jobs=[make_job(job_url="https://ok/1")])

    class BrokenScraper:
        def __init__(self, **kwargs):
            pass

        def scrape(self, scraper_input):
            raise RuntimeError("board is on fire")

    monkeypatch.setattr(jobspy, "Indeed", OkScraper, raising=False)
    monkeypatch.setattr(jobspy, "LinkedIn", BrokenScraper, raising=False)

    df = jobspy.scrape_jobs(
        site_name=["indeed", "linkedin"],
        search_term="engineer",
        location="Kuala Lumpur, Malaysia",
        results_wanted=1,
    )

    assert len(df) == 1
    assert df.iloc[0]["site"] == "indeed"


def test_pipeline_populates_state_column(monkeypatch, make_job):
    from jobspy.model import Country, Location

    class OkScraper:
        def __init__(self, **kwargs):
            pass

        def scrape(self, scraper_input):
            return JobResponse(
                jobs=[
                    make_job(
                        job_url="https://ok/1",
                        location=Location(city="Cyberjaya", country=Country.MALAYSIA),
                    )
                ]
            )

    monkeypatch.setattr(jobspy, "Indeed", OkScraper, raising=False)

    df = jobspy.scrape_jobs(
        site_name=["indeed"], search_term="engineer", results_wanted=1
    )

    assert df.iloc[0]["state"] == "Selangor"
