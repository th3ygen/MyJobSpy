"""Live smoke test against the real Hiredly board.

Deselected by default (pyproject sets addopts = "-m 'not live'"). Run with:

    poetry run pytest tests/test_hiredly_live.py -m live -v

A fixture test passing means the parser handles a shape captured in the
past. This is what tells you the board still serves that shape today.
"""

from __future__ import annotations

import pytest

from jobspy import scrape_jobs

pytestmark = pytest.mark.live


def test_returns_real_kl_jobs_with_salary_and_descriptions():
    df = scrape_jobs(
        site_name=["hiredly"],
        search_term="software engineer",
        location="Kuala Lumpur, Malaysia",
        country_indeed="malaysia",
        results_wanted=30,
    )

    assert len(df) >= 10, "board returned suspiciously few results"
    assert set(df["site"]) == {"hiredly"}
    assert df["title"].notna().all()

    # 18/30 "software engineer" results carried a salary on 2026-09-24,
    # aggregated listings included. A 25% floor catches the field
    # disappearing without failing on normal variation.
    fill = df["min_amount"].notna().mean()
    assert fill > 0.25, f"salary fill collapsed to {fill:.0%}"
    assert set(df[df["min_amount"].notna()]["salary_source"]) == {"direct_data"}

    # The filter sends stateRegions=["Kuala Lumpur"], so nearly every row is
    # KL. Not all: an employer can file under KL but type "Petaling Jaya" as
    # the address, and the shared normalizer rightly prefers the more
    # specific city (Selangor). Measured 29/30 on 2026-09-24.
    assert df["state"].notna().mean() > 0.9, "location matching collapsed"
    assert (df["state"] == "Kuala Lumpur").mean() > 0.8, "state filter ignored"

    # Descriptions arrive inline with the search, no extra request.
    assert df["description"].str.len().median() > 300
