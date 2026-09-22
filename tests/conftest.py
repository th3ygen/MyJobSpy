"""Shared pytest fixtures for the MyJobSpy test suite."""

from __future__ import annotations

import pytest

from jobspy.model import Country, JobPost, Location


@pytest.fixture
def make_job():
    """Builds a JobPost with sane defaults; override any field via kwargs."""

    def _make(**kwargs):
        defaults = dict(
            title="Software Engineer",
            company_name="Acme Sdn Bhd",
            job_url="https://example.com/job/1",
            location=Location(city="Kuala Lumpur", country=Country.MALAYSIA),
        )
        defaults.update(kwargs)
        return JobPost(**defaults)

    return _make
