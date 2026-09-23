"""Scrape full stack developer/engineer postings in Kuala Lumpur.

    poetry run python examples/scrape_fullstack_kl.py

Writes a CSV next to this file and prints a summary. Edit the constants below
to point it at a different role or city.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from jobspy import scrape_jobs

SITES = ["indeed", "linkedin"]

# "developer/engineer" is two separate board queries — boards match the title
# fairly literally, so searching only one term misses the other's postings.
SEARCH_TERMS = ["full stack developer", "full stack engineer"]

LOCATION = "Kuala Lumpur, Malaysia"

# Per site, per term. Cross-term overlap and board throttling both cut into
# this, so ask for noticeably more than you need.
RESULTS_WANTED = 30

# LinkedIn returns descriptions only if you ask, at the cost of one extra
# request per job. Worth it here: MYR salary parsing reads the description,
# so turning this off drops most LinkedIn salary data. Set False if you are
# being rate limited or just want a fast look.
FETCH_LINKEDIN_DESCRIPTIONS = True

OUTPUT = Path(__file__).parent / f"fullstack-kl-{date.today().isoformat()}.csv"


def scrape() -> pd.DataFrame:
    """Runs every search term and returns one deduplicated frame."""
    frames = []

    for term in SEARCH_TERMS:
        print(f"searching {term!r} on {', '.join(SITES)} ...")
        df = scrape_jobs(
            site_name=SITES,
            search_term=term,
            location=LOCATION,
            country_indeed="malaysia",
            results_wanted=RESULTS_WANTED,
            linkedin_fetch_description=FETCH_LINKEDIN_DESCRIPTIONS,
            verbose=1,
        )
        print(f"  -> {len(df)} rows")
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)

    # Each scrape_jobs call deduplicates within itself; the overlap *between*
    # the two term queries is ours to collapse.
    before = len(combined)
    combined = combined.drop_duplicates(subset="job_url", ignore_index=True)
    print(f"\n{before} rows -> {len(combined)} after cross-term dedup")

    return combined


def summarize(df: pd.DataFrame) -> None:
    print(f"\n{'=' * 70}")
    print(f"{len(df)} postings")
    print(f"{'=' * 70}")

    print(f"\nby board:  {df['site'].value_counts().to_dict()}")
    print(f"by state:  {df['state'].value_counts(dropna=False).head(5).to_dict()}")

    remote = df[df["is_remote"] == True]  # noqa: E712 - pandas mask, not a bool
    print(f"remote:    {len(remote)} of {len(df)}", end="")
    if not remote.empty:
        print(f"  (scope: {remote['remote_scope'].value_counts().to_dict()})")
    else:
        print()

    paid = df[df["min_amount"].notna()]
    print(f"with pay:  {len(paid)} of {len(df)}", end="")
    if not paid.empty:
        print(f"  (sources: {paid['salary_source'].value_counts().to_dict()})")
    else:
        print()

    # dedup_group tags postings the pipeline believes are the same job on more
    # than one board. They are kept as separate rows on purpose, not merged.
    grouped = df[df["dedup_group"].notna()]
    if not grouped.empty:
        multi = grouped["dedup_group"].value_counts()
        multi = multi[multi > 1]
        if not multi.empty:
            print(f"\n{len(multi)} job(s) cross-posted to more than one board:")
            for group_id in multi.head(3).index:
                rows = grouped[grouped["dedup_group"] == group_id]
                title = rows.iloc[0]["title"]
                boards = ", ".join(rows["site"].tolist())
                print(f"  {title}  [{boards}]")

    print("\nsample:")
    columns = ["site", "title", "company", "city", "min_amount", "max_amount"]
    print(df[columns].head(10).to_string(index=False))


def main() -> None:
    df = scrape()

    if df.empty:
        print("\nNo results. Both boards may be throttling — try again shortly.")
        return

    summarize(df)

    df.to_csv(OUTPUT, index=False, encoding="utf-8")
    print(f"\nwrote {len(df)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
