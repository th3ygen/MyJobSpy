from __future__ import annotations

import inspect
import logging

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


def test_pipeline_is_skipped_for_non_malaysia_country(monkeypatch, make_job):
    calls = []

    def spy(jobs, **kwargs):
        calls.append(len(jobs))
        return jobs

    monkeypatch.setattr(jobspy, "malaysia_normalize", spy)

    class OkScraper:
        def __init__(self, **kwargs):
            pass

        def scrape(self, scraper_input):
            return JobResponse(jobs=[make_job(job_url="https://ok/1")])

    monkeypatch.setattr(jobspy, "Indeed", OkScraper, raising=False)

    jobspy.scrape_jobs(
        site_name=["indeed"],
        search_term="engineer",
        country_indeed="usa",
        results_wanted=1,
    )

    assert calls == []  # the pipeline must never have run


def test_pipeline_runs_for_malaysia(monkeypatch, make_job):
    calls = []

    def spy(jobs, **kwargs):
        calls.append(len(jobs))
        return jobs

    monkeypatch.setattr(jobspy, "malaysia_normalize", spy)

    class OkScraper:
        def __init__(self, **kwargs):
            pass

        def scrape(self, scraper_input):
            return JobResponse(jobs=[make_job(job_url="https://ok/1")])

    monkeypatch.setattr(jobspy, "Indeed", OkScraper, raising=False)

    jobspy.scrape_jobs(
        site_name=["indeed"],
        search_term="engineer",
        country_indeed="malaysia",
        results_wanted=1,
        # This test predates include_remote (Task 13) and asserts on the raw
        # job count reaching normalize(), bypassed here by the spy. With the
        # include_remote default of True, the same OkScraper would otherwise
        # run twice (located + remote pass), doubling the count the spy sees
        # before the real exact-dedup - which this spy bypasses - would
        # normally absorb the overlap. Pin to one pass to keep this test
        # about "the pipeline runs", not about two-pass unioning.
        include_remote=False,
    )

    assert calls == [1]  # the pipeline ran, over the one scraped job


def test_include_remote_runs_a_second_pass(monkeypatch, make_job):
    seen_is_remote = []

    class RecordingScraper:
        def __init__(self, **kwargs):
            pass

        def scrape(self, scraper_input):
            seen_is_remote.append(scraper_input.is_remote)
            suffix = "remote" if scraper_input.is_remote else "onsite"
            return JobResponse(jobs=[make_job(job_url=f"https://ok/{suffix}")])

    monkeypatch.setattr(jobspy, "Indeed", RecordingScraper, raising=False)

    df = jobspy.scrape_jobs(
        site_name=["indeed"],
        search_term="engineer",
        include_remote=True,
        results_wanted=1,
    )

    assert sorted(seen_is_remote) == [False, True]
    assert len(df) == 2


def test_include_remote_false_runs_one_pass(monkeypatch, make_job):
    passes = []

    class RecordingScraper:
        def __init__(self, **kwargs):
            pass

        def scrape(self, scraper_input):
            passes.append(scraper_input.is_remote)
            return JobResponse(jobs=[make_job(job_url="https://ok/1")])

    monkeypatch.setattr(jobspy, "Indeed", RecordingScraper, raising=False)

    jobspy.scrape_jobs(
        site_name=["indeed"],
        search_term="engineer",
        include_remote=False,
        results_wanted=1,
    )

    assert passes == [False]


def test_remote_pass_is_skipped_when_is_remote_already_set(monkeypatch, make_job):
    passes = []

    class RecordingScraper:
        def __init__(self, **kwargs):
            pass

        def scrape(self, scraper_input):
            passes.append(scraper_input.is_remote)
            return JobResponse(jobs=[make_job(job_url="https://ok/1")])

    monkeypatch.setattr(jobspy, "Indeed", RecordingScraper, raising=False)

    jobspy.scrape_jobs(
        site_name=["indeed"],
        search_term="engineer",
        is_remote=True,
        include_remote=True,
        results_wanted=1,
    )

    assert passes == [True]


def test_non_malaysia_country_does_not_double_rows(monkeypatch, make_job):
    passes = []

    class RecordingScraper:
        def __init__(self, **kwargs):
            pass

        def scrape(self, scraper_input):
            passes.append(scraper_input.is_remote)
            return JobResponse(jobs=[make_job(job_url="https://ok/1")])

    monkeypatch.setattr(jobspy, "Indeed", RecordingScraper, raising=False)

    df = jobspy.scrape_jobs(
        site_name=["indeed"],
        search_term="engineer",
        country_indeed="usa",
        include_remote=True,
        results_wanted=1,
    )

    assert passes == [False]  # only the located pass ran
    assert len(df) == 1  # and therefore no doubling


def test_include_remote_noop_is_logged_for_non_malaysia(monkeypatch, make_job, caplog):
    class OkScraper:
        def __init__(self, **kwargs):
            pass

        def scrape(self, scraper_input):
            return JobResponse(jobs=[make_job(job_url="https://ok/1")])

    monkeypatch.setattr(jobspy, "Indeed", OkScraper, raising=False)
    # create_logger sets propagate=False, so caplog cannot see these records
    # unless propagation is re-enabled for the duration of this test.
    monkeypatch.setattr(jobspy.log, "propagate", True)
    caplog.set_level(logging.INFO, logger="JobSpy:ScrapeJobs")

    jobspy.scrape_jobs(
        site_name=["indeed"],
        search_term="engineer",
        country_indeed="usa",
        include_remote=True,
        results_wanted=1,
        # set_logger_level(verbose) gates all JobSpy:* loggers at ERROR by
        # default (verbose=0); raise it so the INFO no-op record is actually
        # emitted, mirroring what a caller must do to see it.
        verbose=2,
    )

    messages = [record.getMessage() for record in caplog.records]
    assert any("include_remote=True has no effect" in m for m in messages)


def test_include_remote_noop_is_not_logged_for_malaysia(monkeypatch, make_job, caplog):
    class OkScraper:
        def __init__(self, **kwargs):
            pass

        def scrape(self, scraper_input):
            return JobResponse(jobs=[make_job(job_url="https://ok/1")])

    monkeypatch.setattr(jobspy, "Indeed", OkScraper, raising=False)
    monkeypatch.setattr(jobspy.log, "propagate", True)
    caplog.set_level(logging.INFO, logger="JobSpy:ScrapeJobs")

    jobspy.scrape_jobs(
        site_name=["indeed"],
        search_term="engineer",
        country_indeed="malaysia",
        include_remote=True,
        results_wanted=1,
        verbose=2,  # visibility on; absence below is the actual behavior, not suppression
    )

    messages = [record.getMessage() for record in caplog.records]
    assert not any("include_remote=True has no effect" in m for m in messages)


def test_include_remote_noop_is_not_logged_when_include_remote_false(
    monkeypatch, make_job, caplog
):
    class OkScraper:
        def __init__(self, **kwargs):
            pass

        def scrape(self, scraper_input):
            return JobResponse(jobs=[make_job(job_url="https://ok/1")])

    monkeypatch.setattr(jobspy, "Indeed", OkScraper, raising=False)
    monkeypatch.setattr(jobspy.log, "propagate", True)
    caplog.set_level(logging.INFO, logger="JobSpy:ScrapeJobs")

    jobspy.scrape_jobs(
        site_name=["indeed"],
        search_term="engineer",
        country_indeed="usa",
        include_remote=False,
        results_wanted=1,
        verbose=2,  # visibility on; absence below is the actual behavior, not suppression
    )

    messages = [record.getMessage() for record in caplog.records]
    assert not any("include_remote=True has no effect" in m for m in messages)


def test_include_remote_noop_is_not_logged_when_is_remote_already_set(
    monkeypatch, make_job, caplog
):
    class OkScraper:
        def __init__(self, **kwargs):
            pass

        def scrape(self, scraper_input):
            return JobResponse(jobs=[make_job(job_url="https://ok/1")])

    monkeypatch.setattr(jobspy, "Indeed", OkScraper, raising=False)
    monkeypatch.setattr(jobspy.log, "propagate", True)
    caplog.set_level(logging.INFO, logger="JobSpy:ScrapeJobs")

    jobspy.scrape_jobs(
        site_name=["indeed"],
        search_term="engineer",
        country_indeed="usa",
        is_remote=True,
        include_remote=True,
        results_wanted=1,
        verbose=2,  # visibility on; absence below is the actual behavior, not suppression
    )

    messages = [record.getMessage() for record in caplog.records]
    assert not any("include_remote=True has no effect" in m for m in messages)
