from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from jobspy import scrape_jobs
from jobspy.baseline.metrics import compute_metrics, render_report
from jobspy.util import create_logger

log = create_logger("Baseline")

# A fixed search set. Do not change these casually — comparability across
# runs is the entire point of the harness.
SEARCHES: list[dict] = [
    {
        "site_name": ["indeed", "linkedin", "google", "jobstreet", "hiredly"],
        "search_term": "software engineer",
        "google_search_term": "software engineer jobs in Kuala Lumpur Malaysia",
        "location": "Kuala Lumpur, Malaysia",
        "country_indeed": "malaysia",
        "results_wanted": 50,
    },
    {
        "site_name": ["indeed", "linkedin", "google", "jobstreet", "hiredly"],
        "search_term": "data analyst",
        "google_search_term": "data analyst jobs in Selangor Malaysia",
        "location": "Selangor, Malaysia",
        "country_indeed": "malaysia",
        "results_wanted": 50,
    },
    {
        "site_name": ["indeed", "linkedin", "jobstreet", "hiredly"],
        "search_term": "admin assistant",
        "location": "Penang, Malaysia",
        "country_indeed": "malaysia",
        "results_wanted": 50,
    },
    {
        "site_name": ["indeed", "linkedin", "jobstreet", "hiredly"],
        "search_term": "software engineer",
        "location": "Malaysia",
        "country_indeed": "malaysia",
        "is_remote": True,
        "results_wanted": 50,
    },
]


def run_baseline(output_path: Path, *, scrape=scrape_jobs) -> Path:
    """Runs every search in SEARCHES and writes a markdown report.

    A failing search is logged and skipped — a single dead board must not
    cost the whole measurement.
    """
    frames: list[pd.DataFrame] = []

    for search in SEARCHES:
        label = f"{search['search_term']} @ {search.get('location', 'anywhere')}"
        # verbose=2 so per-stage normalizer rollups and unmatched-location
        # lines actually reach the log during a measurement run; the fixed
        # search parameters above are untouched.
        search = {**search, "verbose": search.get("verbose", 2)}
        try:
            df = scrape(**search)
        except Exception as exc:  # noqa: BLE001 - one bad search must not abort the run
            log.warning(f"baseline search failed ({label}): {exc}")
            continue
        if df is not None and not df.empty:
            frames.append(df)
        log.info(f"baseline search done ({label}): {0 if df is None else len(df)} rows")

    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    metrics = compute_metrics(combined)
    report = render_report(
        metrics, title=f"MyJobSpy Baseline — {date.today().isoformat()}"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MyJobSpy baseline harness")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/baseline") / f"{date.today().isoformat()}-baseline.md",
    )
    args = parser.parse_args()
    path = run_baseline(args.output)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
