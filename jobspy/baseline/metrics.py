from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from jobspy.malaysia.location import MalaysianState


@dataclass
class BaselineMetrics:
    total_rows: int = 0
    rows_per_site: dict[str, int] = field(default_factory=dict)
    salary_fill_rate: float = 0.0
    salary_fill_rate_by_site: dict[str, float] = field(default_factory=dict)
    date_fill_rate: float = 0.0
    state_match_rate: float = 0.0
    remote_rate: float = 0.0
    remote_scope_counts: dict[str, int] = field(default_factory=dict)
    exact_duplicate_rows: int = 0
    company_title_duplicate_rows: int = 0
    top_locations: list[tuple[str, int]] = field(default_factory=list)


def _fill_rate(df: pd.DataFrame, column: str) -> float:
    if column not in df.columns or len(df) == 0:
        return 0.0
    return round(float(df[column].notna().sum()) / len(df), 4)


def _fill_rate_by_site(df: pd.DataFrame, column: str) -> dict[str, float]:
    """Per-site fill rate for `column`.

    The overall fill rate blends boards with very different coverage into
    one number - e.g. JobStreet publishes a structured salary field on
    roughly half its postings while Indeed and LinkedIn direct-supply
    essentially none, so a blended "salary fill rate" understates what
    JobStreet actually contributes and cannot be cited as if it were
    JobStreet's own number (see docs/baseline and the F4 fix-wave note).
    """
    if column not in df.columns or "site" not in df.columns or len(df) == 0:
        return {}
    rates = df.groupby("site")[column].apply(lambda s: float(s.notna().sum()) / len(s))
    return {str(site): round(float(rate), 4) for site, rate in rates.items()}


def _canonical_state_rate(df: pd.DataFrame) -> float:
    """Fraction of rows whose state is a canonical MalaysianState.

    Deliberately NOT a plain fill-rate: scrapers emit raw state values
    (ISO codes, country names) that must not count as normalized.
    """
    if "state" not in df.columns or len(df) == 0:
        return 0.0
    valid = {state.value for state in MalaysianState}
    return round(float(df["state"].isin(valid).sum()) / len(df), 4)


def compute_metrics(df: pd.DataFrame, *, top_n: int = 25) -> BaselineMetrics:
    """Summarises a scrape result. Safe on an empty or partial frame."""
    if df is None or df.empty:
        return BaselineMetrics()

    total = len(df)

    rows_per_site: dict[str, int] = {}
    if "site" in df.columns:
        rows_per_site = {str(k): int(v) for k, v in df["site"].value_counts().items()}

    exact_duplicates = 0
    if "job_url" in df.columns:
        exact_duplicates = int(df["job_url"].duplicated().sum())

    company_title_duplicates = 0
    if {"company", "title"}.issubset(df.columns):
        company_title_duplicates = int(df.duplicated(subset=["company", "title"]).sum())

    remote_rate = 0.0
    if "is_remote" in df.columns:
        remote_rate = round(
            float(df["is_remote"].fillna(False).astype(bool).sum()) / total, 4
        )

    remote_scope_counts: dict[str, int] = {}
    if "remote_scope" in df.columns:
        scope_series = df["remote_scope"]
        # value_counts(dropna=False) treats Python None and float("nan") as
        # distinct keys in an object-dtype column, which invents a false
        # split the data doesn't have. remote_scope is None by design for
        # every non-remote job, so collapse all null-like values into one
        # clearly-labeled bucket instead.
        null_count = int(scope_series.isna().sum())
        remote_scope_counts = {
            str(k): int(v) for k, v in scope_series.dropna().value_counts().items()
        }
        if null_count:
            remote_scope_counts["(not remote)"] = null_count

    top_locations: list[tuple[str, int]] = []
    if "location" in df.columns:
        counter = Counter(df["location"].dropna().astype(str))
        top_locations = counter.most_common(top_n)

    return BaselineMetrics(
        total_rows=total,
        rows_per_site=rows_per_site,
        salary_fill_rate=_fill_rate(df, "min_amount"),
        salary_fill_rate_by_site=_fill_rate_by_site(df, "min_amount"),
        date_fill_rate=_fill_rate(df, "date_posted"),
        state_match_rate=_canonical_state_rate(df),
        remote_rate=remote_rate,
        remote_scope_counts=remote_scope_counts,
        exact_duplicate_rows=exact_duplicates,
        company_title_duplicate_rows=company_title_duplicates,
        top_locations=top_locations,
    )


def render_report(metrics: BaselineMetrics, *, title: str) -> str:
    """Renders metrics as committable markdown."""
    lines = [f"# {title}", ""]
    lines += [
        "| Metric | Value |",
        "|---|---|",
        f"| Total rows | {metrics.total_rows} |",
        f"| Salary fill rate | {metrics.salary_fill_rate:.1%} |",
        f"| Date fill rate | {metrics.date_fill_rate:.1%} |",
        f"| State match rate | {metrics.state_match_rate:.1%} |",
        f"| Remote rate | {metrics.remote_rate:.1%} |",
        f"| Exact duplicate rows | {metrics.exact_duplicate_rows} |",
        f"| Company+title duplicate rows | {metrics.company_title_duplicate_rows} |",
        "",
        "## Rows per site",
        "",
        "| Site | Rows |",
        "|---|---|",
    ]
    for site, count in sorted(metrics.rows_per_site.items()):
        lines.append(f"| {site} | {count} |")

    lines += [
        "",
        "## Salary fill rate by site",
        "",
        "The headline salary fill rate above blends every board into one",
        "number; boards with structured salary data (e.g. JobStreet) and",
        "boards without it (Indeed, LinkedIn) read very differently site by",
        "site.",
        "",
        "| Site | Fill rate |",
        "|---|---|",
    ]
    for site, rate in sorted(metrics.salary_fill_rate_by_site.items()):
        lines.append(f"| {site} | {rate:.1%} |")

    lines += ["", "## remote_scope distribution", "", "| Scope | Rows |", "|---|---|"]
    for scope, count in sorted(metrics.remote_scope_counts.items()):
        lines.append(f"| {scope} | {count} |")

    lines += [
        "",
        "## Top location strings",
        "",
        "Seeds the `jobspy/malaysia/location.py` gazetteer — unmatched entries here are the backlog.",
        "",
        "| Location | Rows |",
        "|---|---|",
    ]
    for location, count in metrics.top_locations:
        lines.append(f"| {location} | {count} |")

    return "\n".join(lines) + "\n"
