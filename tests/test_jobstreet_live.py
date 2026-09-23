"""Live smoke test against the real JobStreet board.

Deselected by default (pyproject sets addopts = "-m 'not live'"). Run with:

    poetry run pytest tests/test_jobstreet_live.py -m live -v
"""

from __future__ import annotations

import pytest

from jobspy import scrape_jobs

pytestmark = pytest.mark.live


def test_returns_real_kl_jobs_with_salary():
    df = scrape_jobs(
        site_name=["jobstreet"],
        search_term="software engineer",
        location="Kuala Lumpur",
        country_indeed="malaysia",
        results_wanted=20,
    )

    assert len(df) >= 10, "board returned suspiciously few results"
    assert df["title"].notna().all()
    assert set(df["site"]) == {"jobstreet"}

    # Roughly 70% of postings carried a salary label when measured on
    # 2026-09-23. A floor of 25% catches the label disappearing without
    # failing on normal variation between searches.
    fill = df["min_amount"].notna().mean()
    assert fill > 0.25, f"salary fill collapsed to {fill:.0%}"
    assert set(df[df["min_amount"].notna()]["salary_source"]) == {"direct_data"}

    assert df["state"].notna().mean() > 0.8, "location matching collapsed"


def test_descriptions_arrive_when_requested():
    df = scrape_jobs(
        site_name=["jobstreet"],
        search_term="software engineer",
        location="Kuala Lumpur",
        country_indeed="malaysia",
        results_wanted=3,
        jobstreet_fetch_description=True,
    )

    assert df["description"].notna().all()
    assert df["description"].str.len().min() > 200
