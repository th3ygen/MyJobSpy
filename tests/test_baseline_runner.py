from __future__ import annotations

import pandas as pd

from jobspy.baseline.runner import SEARCHES, run_baseline


def test_searches_are_malaysian():
    assert len(SEARCHES) >= 3
    for search in SEARCHES:
        assert search["country_indeed"] == "malaysia"
        assert "search_term" in search


def test_run_baseline_writes_a_report(tmp_path):
    calls = []

    def fake_scrape(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame(
            [["indeed", "u1", "Engineer", "Acme", "Kuala Lumpur", 5000]],
            columns=["site", "job_url", "title", "company", "location", "min_amount"],
        )

    output = run_baseline(tmp_path / "report.md", scrape=fake_scrape)

    assert output.exists()
    assert "# MyJobSpy Baseline" in output.read_text(encoding="utf-8")
    assert len(calls) == len(SEARCHES)


def test_run_baseline_survives_a_failing_search(tmp_path):
    def fake_scrape(**kwargs):
        raise RuntimeError("board is down")

    output = run_baseline(tmp_path / "report.md", scrape=fake_scrape)

    assert output.exists()
    assert "Total rows | 0" in output.read_text(encoding="utf-8")
