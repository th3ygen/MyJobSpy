from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class BaselineMetrics:
    total_rows: int = 0
    rows_per_site: dict[str, int] = field(default_factory=dict)
    salary_fill_rate: float = 0.0
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
        remote_scope_counts = {
            str(k): int(v)
            for k, v in df["remote_scope"].value_counts(dropna=False).items()
        }

    top_locations: list[tuple[str, int]] = []
    if "location" in df.columns:
        counter = Counter(df["location"].dropna().astype(str))
        top_locations = counter.most_common(top_n)

    return BaselineMetrics(
        total_rows=total,
        rows_per_site=rows_per_site,
        salary_fill_rate=_fill_rate(df, "min_amount"),
        date_fill_rate=_fill_rate(df, "date_posted"),
        state_match_rate=_fill_rate(df, "state"),
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
