# Malaysia Pipeline (Phases 0–1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a baseline measurement harness for Malaysian job searches, then a `jobspy/malaysia/` normalization pipeline (location, MYR salary, BM parsing, remote scope, duplicate grouping) that runs on the existing Indeed/LinkedIn/Google scrapers.

**Architecture:** Scrapers stay unchanged and return raw `JobPost`s. A new `jobspy/malaysia/` package normalizes `list[JobPost]` *before* DataFrame flattening — three per-job stages (location, salary, remote) then one batch-wide stage (grouping). `language.py` is a shared helper, not a stage. DataFrame assembly is extracted out of `scrape_jobs` first so the output schema becomes unit-testable.

**Tech Stack:** Python ≥3.10, Poetry, pydantic v2, pandas, rapidfuzz (new), pytest (new), Black (line-length 88).

**Spec:** `docs/superpowers/specs/2026-09-22-malaysia-specialization-design.md`

## Global Constraints

- Python `^3.10`; Black line-length **88**, enforced by pre-commit.
- Salary sanity bands (verbatim from spec): monthly **RM1,000 – RM30,000**; annual **RM20,000 – RM500,000**; hourly **RM8 – RM150**.
- `remote_scope` values are exactly: `my`, `apac`, `global`, `other_country`, `unknown`.
- Structured board data always wins — the MYR parser only fills when `compensation` is absent.
- Seniority mismatch is a **hard block** on grouping, checked before similarity scoring.
- Fuzzy grouping uses `token_sort_ratio` (never `token_set_ratio`) at threshold **90**.
- Grouping is **non-destructive**; only exact-duplicate dedup removes rows.
- Any new field on `JobPost` MUST also be added to `desired_order` in `jobspy/util.py` or it is silently dropped from the DataFrame.
- Normalizer failures log at WARNING with the offending input and leave the field unset — never raise, never silently pass.

## Spec Amendment (decided during planning)

The spec says location normalization produces structured `(city, state)`, and justifies `state="Kuala Lumpur"` by "filtering by state must work uniformly." But `scrape_jobs` flattens `Location` to a display string, so **state never reaches the DataFrame** and that filtering is impossible as specced. This plan therefore adds `city` and `state` as output columns (Task 3). Fold this back into the spec when the plan lands.

---

## Task 1: Development environment and test infrastructure

**No Python is installed on this machine.** `python` / `python3` / `py` resolve to Microsoft Store alias stubs; there is no Poetry, conda, uv, or repo venv. This task is a hard prerequisite for every task after it.

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing
- Produces: a working `poetry run pytest`; the `live` marker; `rapidfuzz` importable

- [ ] **Step 1: Install Python 3.12**

Download and install from python.org (check "Add python.exe to PATH"), or:

```powershell
winget install --id Python.Python.3.12 -e
```

Then open a **new** shell and verify:

```powershell
python --version
```

Expected: `Python 3.12.x`. If it still prints the Store prompt, disable the aliases in Settings → Apps → Advanced app settings → App execution aliases.

- [ ] **Step 2: Install Poetry and project dependencies**

```powershell
python -m pip install --user poetry
poetry install
```

Expected: `poetry install` completes and creates a virtualenv.

- [ ] **Step 3: Add rapidfuzz and pytest to pyproject.toml**

In `[tool.poetry.dependencies]`, after the `regex` line:

```toml
rapidfuzz = "^3.9.0"
```

In `[tool.poetry.group.dev.dependencies]`, after `pre-commit = "*"`:

```toml
pytest = "^8.0.0"
```

Append a new section at the end of the file:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "live: hits real job boards over the network (deselected by default)",
]
addopts = "-m 'not live'"
```

- [ ] **Step 4: Install the new dependencies**

```powershell
poetry lock
poetry install
```

Expected: rapidfuzz and pytest appear in the install output.

- [ ] **Step 5: Create the test scaffolding**

`tests/conftest.py`:

```python
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
```

`tests/test_smoke.py`:

```python
def test_package_imports():
    from jobspy import scrape_jobs

    assert callable(scrape_jobs)


def test_rapidfuzz_available():
    from rapidfuzz import fuzz

    assert fuzz.token_sort_ratio("abc", "abc") == 100
```

- [ ] **Step 6: Run the smoke tests**

```powershell
poetry run pytest tests/test_smoke.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml poetry.lock tests/conftest.py tests/test_smoke.py
git commit -m "chore: add pytest and rapidfuzz, scaffold test suite"
```

---

## Task 2: Extract DataFrame assembly into a testable function

Behavior-preserving refactor. `scrape_jobs` currently builds the DataFrame inline (`jobspy/__init__.py:129-221`), so the output schema cannot be tested without hitting the network. Everything after this task depends on being able to test columns.

**Files:**
- Create: `jobspy/frame.py`
- Modify: `jobspy/__init__.py:129-221`
- Test: `tests/test_frame.py`

**Interfaces:**
- Consumes: `JobResponse`, `JobPost`, `Country` from `jobspy.model`; `desired_order`, `convert_to_annual`, `extract_salary` from `jobspy.util`
- Produces: `build_jobs_dataframe(site_to_jobs: dict[str, JobResponse], *, country_enum: Country, enforce_annual_salary: bool = False) -> pd.DataFrame`

- [ ] **Step 1: Write the failing test**

`tests/test_frame.py`:

```python
from __future__ import annotations

from jobspy.frame import build_jobs_dataframe
from jobspy.model import (
    Compensation,
    CompensationInterval,
    Country,
    JobResponse,
    Location,
)
from jobspy.util import desired_order


def test_builds_one_row_per_job(make_job):
    response = JobResponse(jobs=[make_job(), make_job(job_url="https://x/2")])

    df = build_jobs_dataframe({"indeed": response}, country_enum=Country.MALAYSIA)

    assert len(df) == 2
    assert set(df["site"]) == {"indeed"}


def test_columns_match_desired_order(make_job):
    response = JobResponse(jobs=[make_job()])

    df = build_jobs_dataframe({"indeed": response}, country_enum=Country.MALAYSIA)

    assert list(df.columns) == desired_order


def test_flattens_compensation_and_location(make_job):
    job = make_job(
        location=Location(city="Cyberjaya", state="Selangor", country=Country.MALAYSIA),
        compensation=Compensation(
            interval=CompensationInterval.MONTHLY,
            min_amount=5000,
            max_amount=7000,
            currency="MYR",
        ),
    )

    df = build_jobs_dataframe({"indeed": JobResponse(jobs=[job])}, country_enum=Country.MALAYSIA)

    row = df.iloc[0]
    assert row["location"] == "Cyberjaya, Selangor, Malaysia"
    assert row["interval"] == "monthly"
    assert row["min_amount"] == 5000
    assert row["currency"] == "MYR"
    assert row["salary_source"] == "direct_data"


def test_empty_input_returns_empty_frame():
    df = build_jobs_dataframe({}, country_enum=Country.MALAYSIA)

    assert df.empty
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
poetry run pytest tests/test_frame.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'jobspy.frame'`

- [ ] **Step 3: Create `jobspy/frame.py`**

Move the body of the row loop out of `scrape_jobs` verbatim. The only change is that it now takes parameters instead of closing over them:

```python
from __future__ import annotations

import pandas as pd

from jobspy.model import Country, JobResponse, Location, SalarySource
from jobspy.util import convert_to_annual, desired_order, extract_salary


def build_jobs_dataframe(
    site_to_jobs: dict[str, JobResponse],
    *,
    country_enum: Country,
    enforce_annual_salary: bool = False,
) -> pd.DataFrame:
    """Flattens scraped JobPosts into the canonical output DataFrame."""
    jobs_dfs: list[pd.DataFrame] = []

    for site, job_response in site_to_jobs.items():
        for job in job_response.jobs:
            job_data = job.dict()
            job_data["site"] = site
            job_data["company"] = job_data["company_name"]
            job_data["job_type"] = (
                ", ".join(job_type.value[0] for job_type in job_data["job_type"])
                if job_data["job_type"]
                else None
            )
            job_data["emails"] = (
                ", ".join(job_data["emails"]) if job_data["emails"] else None
            )
            if job_data["location"]:
                job_data["location"] = Location(
                    **job_data["location"]
                ).display_location()

            compensation_obj = job_data.get("compensation")
            if compensation_obj and isinstance(compensation_obj, dict):
                job_data["interval"] = (
                    compensation_obj.get("interval").value
                    if compensation_obj.get("interval")
                    else None
                )
                job_data["min_amount"] = compensation_obj.get("min_amount")
                job_data["max_amount"] = compensation_obj.get("max_amount")
                job_data["currency"] = compensation_obj.get("currency", "USD")
                job_data["salary_source"] = SalarySource.DIRECT_DATA.value
                if enforce_annual_salary and (
                    job_data["interval"]
                    and job_data["interval"] != "yearly"
                    and job_data["min_amount"]
                    and job_data["max_amount"]
                ):
                    convert_to_annual(job_data)
            elif country_enum == Country.USA:
                (
                    job_data["interval"],
                    job_data["min_amount"],
                    job_data["max_amount"],
                    job_data["currency"],
                ) = extract_salary(
                    job_data["description"],
                    enforce_annual_salary=enforce_annual_salary,
                )
                job_data["salary_source"] = SalarySource.DESCRIPTION.value

            job_data["salary_source"] = (
                job_data.get("salary_source")
                if job_data.get("min_amount")
                else None
            )

            job_data["skills"] = (
                ", ".join(job_data["skills"]) if job_data["skills"] else None
            )

            jobs_dfs.append(pd.DataFrame([job_data]))

    if not jobs_dfs:
        return pd.DataFrame()

    filtered_dfs = [df.dropna(axis=1, how="all") for df in jobs_dfs]
    jobs_df = pd.concat(filtered_dfs, ignore_index=True)

    for column in desired_order:
        if column not in jobs_df.columns:
            jobs_df[column] = None

    jobs_df = jobs_df[desired_order]
    return jobs_df.sort_values(
        by=["site", "date_posted"], ascending=[True, False]
    ).reset_index(drop=True)
```

Note: the naukri passthrough assignments in the original (`experience_range`, `company_rating`, etc.) were no-ops — `job_data.get(k)` assigned back to `job_data[k]` — and are dropped. The fields still reach the frame via `job.dict()`.

- [ ] **Step 4: Replace the inline block in `scrape_jobs`**

In `jobspy/__init__.py`, delete lines 129–221 (everything from `jobs_dfs: list[pd.DataFrame] = []` through the final `return pd.DataFrame()`) and replace with:

```python
    return build_jobs_dataframe(
        site_to_jobs_dict,
        country_enum=country_enum,
        enforce_annual_salary=enforce_annual_salary,
    )
```

Add the import at the top:

```python
from jobspy.frame import build_jobs_dataframe
```

Remove now-unused imports from `jobspy/__init__.py`: `SalarySource`, `extract_salary`, `convert_to_annual`, `desired_order`.

- [ ] **Step 5: Run the tests**

```powershell
poetry run pytest tests/ -v
```

Expected: all pass (4 new + 2 smoke).

- [ ] **Step 6: Format and commit**

```bash
poetry run black jobspy tests
git add jobspy/frame.py jobspy/__init__.py tests/test_frame.py
git commit -m "refactor: extract DataFrame assembly into jobspy/frame.py"
```

---

## Task 3: Add the new output columns

**Files:**
- Modify: `jobspy/model.py` (JobPost)
- Modify: `jobspy/util.py` (`desired_order`)
- Modify: `jobspy/frame.py`
- Test: `tests/test_frame.py`

**Interfaces:**
- Consumes: `build_jobs_dataframe` from Task 2
- Produces: `JobPost.dedup_group: str | None`, `JobPost.remote_scope: str | None`; DataFrame columns `dedup_group`, `remote_scope`, `city`, `state`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_frame.py`:

```python
def test_emits_city_and_state_columns(make_job):
    job = make_job(
        location=Location(city="Cyberjaya", state="Selangor", country=Country.MALAYSIA)
    )

    df = build_jobs_dataframe({"indeed": JobResponse(jobs=[job])}, country_enum=Country.MALAYSIA)

    assert df.iloc[0]["city"] == "Cyberjaya"
    assert df.iloc[0]["state"] == "Selangor"
    assert df.iloc[0]["location"] == "Cyberjaya, Selangor, Malaysia"


def test_emits_pipeline_columns(make_job):
    job = make_job(dedup_group="abc123", remote_scope="my")

    df = build_jobs_dataframe({"indeed": JobResponse(jobs=[job])}, country_enum=Country.MALAYSIA)

    assert df.iloc[0]["dedup_group"] == "abc123"
    assert df.iloc[0]["remote_scope"] == "my"


def test_new_columns_are_in_desired_order():
    for column in ("dedup_group", "remote_scope", "city", "state"):
        assert column in desired_order
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
poetry run pytest tests/test_frame.py -v
```

Expected: FAIL — `JobPost` has no field `dedup_group`.

- [ ] **Step 3: Add the JobPost fields**

In `jobspy/model.py`, inside `class JobPost`, after the `work_from_home_type` line:

```python
    # Malaysia normalization pipeline (jobspy/malaysia/)
    dedup_group: str | None = None  # shared by likely-duplicate listings
    remote_scope: str | None = None  # my | apac | global | other_country | unknown
```

- [ ] **Step 4: Add the columns to `desired_order`**

In `jobspy/util.py`, change the head of the `desired_order` list so it reads:

```python
desired_order = [
    "id",
    "site",
    "dedup_group",
    "job_url",
    "job_url_direct",
    "title",
    "company",
    "location",
    "city",
    "state",
    "date_posted",
```

and change the `is_remote` entry so it reads:

```python
    "is_remote",
    "remote_scope",
```

- [ ] **Step 5: Emit city and state in `frame.py`**

Replace the location block in `build_jobs_dataframe`:

```python
            if job_data["location"]:
                location = Location(**job_data["location"])
                job_data["city"] = location.city
                job_data["state"] = location.state
                job_data["location"] = location.display_location()
```

- [ ] **Step 6: Run the tests**

```powershell
poetry run pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 7: Format and commit**

```bash
poetry run black jobspy tests
git add jobspy/model.py jobspy/util.py jobspy/frame.py tests/test_frame.py
git commit -m "feat: add dedup_group, remote_scope, city and state output columns"
```

---

## Task 4: Baseline metrics

Pure functions over a DataFrame. No network. `top_locations` is the output that seeds the gazetteer in Task 7.

**Files:**
- Create: `jobspy/baseline/__init__.py`
- Create: `jobspy/baseline/metrics.py`
- Test: `tests/test_baseline_metrics.py`

**Interfaces:**
- Consumes: the DataFrame from `build_jobs_dataframe`
- Produces: `BaselineMetrics` dataclass; `compute_metrics(df: pd.DataFrame) -> BaselineMetrics`; `render_report(metrics: BaselineMetrics, *, title: str) -> str`

- [ ] **Step 1: Write the failing test**

`tests/test_baseline_metrics.py`:

```python
from __future__ import annotations

import pandas as pd

from jobspy.baseline.metrics import compute_metrics, render_report


def _frame(rows):
    columns = [
        "site", "job_url", "title", "company", "location", "city", "state",
        "date_posted", "min_amount", "is_remote", "remote_scope",
    ]
    return pd.DataFrame(rows, columns=columns)


def test_counts_rows_per_site():
    df = _frame([
        ["indeed", "u1", "Engineer", "Acme", "KL", None, None, "2026-09-01", None, False, None],
        ["indeed", "u2", "Analyst", "Acme", "KL", None, None, "2026-09-01", None, False, None],
        ["linkedin", "u3", "Engineer", "Acme", "KL", None, None, "2026-09-01", None, False, None],
    ])

    m = compute_metrics(df)

    assert m.total_rows == 3
    assert m.rows_per_site == {"indeed": 2, "linkedin": 1}


def test_salary_fill_rate():
    df = _frame([
        ["indeed", "u1", "A", "X", "KL", None, None, None, 5000, False, None],
        ["indeed", "u2", "B", "X", "KL", None, None, None, None, False, None],
    ])

    assert compute_metrics(df).salary_fill_rate == 0.5


def test_counts_exact_duplicate_urls():
    df = _frame([
        ["indeed", "u1", "A", "X", "KL", None, None, None, None, False, None],
        ["linkedin", "u1", "A", "X", "KL", None, None, None, None, False, None],
        ["google", "u2", "B", "X", "KL", None, None, None, None, False, None],
    ])

    assert compute_metrics(df).exact_duplicate_rows == 1


def test_top_locations_are_ranked():
    df = _frame([
        ["indeed", "u1", "A", "X", "Kuala Lumpur", None, None, None, None, False, None],
        ["indeed", "u2", "B", "X", "Kuala Lumpur", None, None, None, None, False, None],
        ["indeed", "u3", "C", "X", "Penang", None, None, None, None, False, None],
    ])

    assert compute_metrics(df).top_locations[0] == ("Kuala Lumpur", 2)


def test_state_match_rate_is_none_when_unpopulated():
    df = _frame([
        ["indeed", "u1", "A", "X", "KL", None, None, None, None, False, None],
    ])

    assert compute_metrics(df).state_match_rate == 0.0


def test_empty_frame_is_safe():
    m = compute_metrics(pd.DataFrame())

    assert m.total_rows == 0
    assert m.salary_fill_rate == 0.0


def test_render_report_contains_headline_numbers():
    df = _frame([
        ["indeed", "u1", "A", "X", "KL", None, "Selangor", None, 5000, False, None],
    ])

    report = render_report(compute_metrics(df), title="Baseline")

    assert "# Baseline" in report
    assert "Total rows | 1" in report
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
poetry run pytest tests/test_baseline_metrics.py -v
```

Expected: FAIL — `No module named 'jobspy.baseline'`

- [ ] **Step 3: Implement the metrics module**

`jobspy/baseline/__init__.py`:

```python
"""Measurement harness for Malaysian job searches."""
```

`jobspy/baseline/metrics.py`:

```python
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
        remote_rate = round(float(df["is_remote"].fillna(False).astype(bool).sum()) / total, 4)

    remote_scope_counts: dict[str, int] = {}
    if "remote_scope" in df.columns:
        remote_scope_counts = {
            str(k): int(v) for k, v in df["remote_scope"].value_counts(dropna=False).items()
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
```

- [ ] **Step 4: Run the tests**

```powershell
poetry run pytest tests/test_baseline_metrics.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Format and commit**

```bash
poetry run black jobspy tests
git add jobspy/baseline tests/test_baseline_metrics.py
git commit -m "feat: add baseline metrics computation and markdown report"
```

---

## Task 5: Baseline runner

**Files:**
- Create: `jobspy/baseline/runner.py`
- Create: `docs/baseline/.gitkeep`
- Test: `tests/test_baseline_runner.py`

**Interfaces:**
- Consumes: `compute_metrics`, `render_report` (Task 4); `scrape_jobs`
- Produces: `SEARCHES: list[dict]`; `run_baseline(output_path: Path, *, scrape=scrape_jobs) -> Path`

- [ ] **Step 1: Write the failing test**

`tests/test_baseline_runner.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
poetry run pytest tests/test_baseline_runner.py -v
```

Expected: FAIL — `No module named 'jobspy.baseline.runner'`

- [ ] **Step 3: Implement the runner**

`jobspy/baseline/runner.py`:

```python
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
        "site_name": ["indeed", "linkedin", "google"],
        "search_term": "software engineer",
        "google_search_term": "software engineer jobs in Kuala Lumpur Malaysia",
        "location": "Kuala Lumpur, Malaysia",
        "country_indeed": "malaysia",
        "results_wanted": 50,
    },
    {
        "site_name": ["indeed", "linkedin", "google"],
        "search_term": "data analyst",
        "google_search_term": "data analyst jobs in Selangor Malaysia",
        "location": "Selangor, Malaysia",
        "country_indeed": "malaysia",
        "results_wanted": 50,
    },
    {
        "site_name": ["indeed", "linkedin"],
        "search_term": "admin assistant",
        "location": "Penang, Malaysia",
        "country_indeed": "malaysia",
        "results_wanted": 50,
    },
    {
        "site_name": ["indeed", "linkedin"],
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
    report = render_report(metrics, title=f"MyJobSpy Baseline — {date.today().isoformat()}")

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
```

- [ ] **Step 4: Run the tests**

```powershell
poetry run pytest tests/test_baseline_runner.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Capture the "before" baseline**

This hits real job boards and takes several minutes.

```powershell
New-Item -ItemType Directory -Force docs/baseline
poetry run python -m jobspy.baseline.runner
```

Expected: a report at `docs/baseline/<today>-baseline.md`. **Read it.** The `Top location strings` table is the input to Task 7's gazetteer; the salary fill rate is the number Phase 1 must improve.

If every search returns zero rows, stop and investigate before continuing — the rest of the plan assumes the existing scrapers work.

- [ ] **Step 6: Format and commit**

```bash
poetry run black jobspy tests
git add jobspy/baseline/runner.py tests/test_baseline_runner.py docs/baseline
git commit -m "feat: add baseline harness runner and capture pre-pipeline baseline"
```

---

## Task 6: `language.py` — Bahasa Malaysia parsing

**Files:**
- Create: `jobspy/malaysia/__init__.py`
- Create: `jobspy/malaysia/language.py`
- Modify: `jobspy/model.py` (JobType tuples)
- Test: `tests/malaysia/test_language.py`

**Interfaces:**
- Consumes: nothing
- Produces: `parse_bm_relative_date(text: str, *, today: date | None = None) -> date | None`; `BM_INTERVAL_WORDS: dict[str, str]`; `detect_interval(text: str) -> str | None`; `to_bm_query(term: str) -> str | None`

- [ ] **Step 1: Write the failing test**

`tests/malaysia/test_language.py`:

```python
from __future__ import annotations

from datetime import date

import pytest

from jobspy.malaysia.language import (
    detect_interval,
    parse_bm_relative_date,
    to_bm_query,
)
from jobspy.util import get_enum_from_job_type
from jobspy.model import JobType

TODAY = date(2026, 9, 22)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("hari ini", date(2026, 9, 22)),
        ("Baru sahaja", date(2026, 9, 22)),
        ("semalam", date(2026, 9, 21)),
        ("3 hari lepas", date(2026, 9, 19)),
        ("2 minggu lepas", date(2026, 9, 8)),
        ("1 bulan lepas", date(2026, 8, 23)),
        ("5 jam lepas", date(2026, 9, 22)),
        ("30 minit yang lepas", date(2026, 9, 22)),
    ],
)
def test_parses_bm_relative_dates(text, expected):
    assert parse_bm_relative_date(text, today=TODAY) == expected


@pytest.mark.parametrize("text", ["3 days ago", "", "gibberish", None])
def test_returns_none_for_non_bm_dates(text):
    assert parse_bm_relative_date(text, today=TODAY) is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("RM3,000 sebulan", "monthly"),
        ("RM50 sejam", "hourly"),
        ("RM90,000 setahun", "yearly"),
        ("RM3,000 per month", "monthly"),
        ("RM3,000", None),
    ],
)
def test_detects_interval(text, expected):
    assert detect_interval(text) == expected


@pytest.mark.parametrize(
    "term,expected",
    [
        ("driver", "pemandu"),
        ("Security Guard", "pengawal keselamatan"),
        ("admin clerk", "pentadbir kerani"),
        ("software engineer", "software jurutera"),
        ("blockchain wizard", None),
    ],
)
def test_translates_query_terms(term, expected):
    assert to_bm_query(term) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("sepenuhmasa", JobType.FULL_TIME),
        ("separuhmasa", JobType.PART_TIME),
        ("kontrak", JobType.CONTRACT),
        ("latihanindustri", JobType.INTERNSHIP),
    ],
)
def test_bm_job_types_resolve(value, expected):
    assert get_enum_from_job_type(value) == expected
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
poetry run pytest tests/malaysia/test_language.py -v
```

Expected: FAIL — `No module named 'jobspy.malaysia'`

- [ ] **Step 3: Add BM values to the JobType enum**

`JobType` already matches space-stripped lowercase across many languages, so BM needs new tuple entries only. In `jobspy/model.py`:

- `FULL_TIME`: add `"sepenuhmasa"` after `"toànthờigian"`.
- `PART_TIME`: change to `("parttime", "teilzeit", "částečnýúvazek", "deltid", "separuhmasa")`.
- `CONTRACT`: change to `("contract", "contractor", "kontrak")`.
- `TEMPORARY`: change to `("temporary", "sementara")`.
- `INTERNSHIP`: add `"latihanindustri"` and `"praktikal"` after `"praktik"`.

- [ ] **Step 4: Implement `language.py`**

`jobspy/malaysia/__init__.py`:

```python
"""Malaysia-specific normalization for scraped job posts."""
```

`jobspy/malaysia/language.py`:

```python
from __future__ import annotations

import re
from datetime import date, timedelta

# Relative-date phrases with a fixed day offset.
_FIXED_OFFSET_DAYS: dict[str, int] = {
    "hari ini": 0,
    "baru sahaja": 0,
    "baru saja": 0,
    "sebentar tadi": 0,
    "semalam": 1,
    "kelmarin": 2,
}

# "<n> <unit> lepas" — approximate month as 30 days, matching how boards round.
_UNIT_DAYS: dict[str, float] = {
    "minit": 0.0,
    "saat": 0.0,
    "jam": 0.0,
    "hari": 1.0,
    "minggu": 7.0,
    "bulan": 30.0,
    "tahun": 365.0,
}

_RELATIVE_RE = re.compile(
    r"(\d+)\s*(minit|saat|jam|hari|minggu|bulan|tahun)\s*(?:yang\s+)?lepas",
    re.IGNORECASE,
)

BM_INTERVAL_WORDS: dict[str, str] = {
    "sejam": "hourly",
    "per jam": "hourly",
    "sehari": "daily",
    "per hari": "daily",
    "seminggu": "weekly",
    "per minggu": "weekly",
    "sebulan": "monthly",
    "per bulan": "monthly",
    "/bulan": "monthly",
    "setahun": "yearly",
    "per tahun": "yearly",
}

_EN_INTERVAL_WORDS: dict[str, str] = {
    "per hour": "hourly",
    "hourly": "hourly",
    "per day": "daily",
    "daily": "daily",
    "per week": "weekly",
    "weekly": "weekly",
    "per month": "monthly",
    "monthly": "monthly",
    "a month": "monthly",
    "/month": "monthly",
    "p.m.": "monthly",
    "per annum": "yearly",
    "per year": "yearly",
    "yearly": "yearly",
    "annually": "yearly",
}

# Deliberately weighted toward blue-collar and administrative roles: Malaysian
# tech and white-collar postings are written in English even on BM-heavy boards.
EN_TO_BM_QUERY_TERMS: dict[str, str] = {
    "security guard": "pengawal keselamatan",
    "general worker": "pekerja am",
    "production operator": "operator pengeluaran",
    "accountant": "akauntan",
    "administrator": "pentadbir",
    "admin": "pentadbir",
    "assistant": "pembantu",
    "cashier": "juruwang",
    "chef": "tukang masak",
    "cleaner": "pencuci",
    "clerk": "kerani",
    "cook": "tukang masak",
    "driver": "pemandu",
    "engineer": "jurutera",
    "guard": "pengawal",
    "manager": "pengurus",
    "mechanic": "mekanik",
    "nurse": "jururawat",
    "operator": "pengendali",
    "receptionist": "penyambut tetamu",
    "sales": "jualan",
    "supervisor": "penyelia",
    "tailor": "tukang jahit",
    "teacher": "guru",
    "technician": "juruteknik",
    "waiter": "pelayan",
    "warehouse": "gudang",
}


def parse_bm_relative_date(text: str | None, *, today: date | None = None) -> date | None:
    """Parses Malay relative dates ('3 hari lepas') into an absolute date.

    Returns None for anything that is not a recognised Malay phrase.
    """
    if not text:
        return None

    today = today or date.today()
    normalized = re.sub(r"\s+", " ", text.strip().lower())

    for phrase, days in _FIXED_OFFSET_DAYS.items():
        if phrase in normalized:
            return today - timedelta(days=days)

    match = _RELATIVE_RE.search(normalized)
    if not match:
        return None

    quantity = int(match.group(1))
    unit_days = _UNIT_DAYS[match.group(2).lower()]
    return today - timedelta(days=round(quantity * unit_days))


def detect_interval(text: str | None) -> str | None:
    """Finds a compensation interval word in Malay or English. None if absent."""
    if not text:
        return None

    normalized = re.sub(r"\s+", " ", text.lower())
    # Longest phrases first so 'per month' wins over a bare 'month' substring.
    for phrase, interval in sorted(
        {**BM_INTERVAL_WORDS, **_EN_INTERVAL_WORDS}.items(),
        key=lambda item: -len(item[0]),
    ):
        if phrase in normalized:
            return interval
    return None


def to_bm_query(term: str | None) -> str | None:
    """Translates known role words in a query to Malay.

    Returns None when nothing in the term is translatable, so callers can skip
    issuing a redundant second query.
    """
    if not term:
        return None

    normalized = re.sub(r"\s+", " ", term.strip().lower())

    # Multi-word entries first, so 'security guard' is not split into 'guard'.
    for phrase, translation in sorted(
        EN_TO_BM_QUERY_TERMS.items(), key=lambda item: -len(item[0])
    ):
        if " " in phrase and phrase in normalized:
            normalized = normalized.replace(phrase, translation)

    tokens = [EN_TO_BM_QUERY_TERMS.get(token, token) for token in normalized.split(" ")]
    translated = " ".join(tokens)
    return translated if translated != re.sub(r"\s+", " ", term.strip().lower()) else None
```

- [ ] **Step 5: Run the tests**

```powershell
poetry run pytest tests/malaysia/test_language.py -v
```

Expected: all pass.

- [ ] **Step 6: Format and commit**

```bash
poetry run black jobspy tests
git add jobspy/malaysia tests/malaysia/test_language.py jobspy/model.py
git commit -m "feat(malaysia): add Bahasa Malaysia date, interval and query parsing"
```

---

## Task 7: `location.py` — Malaysian location normalization

Seed the gazetteer from the `Top location strings` table in the Task 5 baseline report, not from imagination. The entries below are the starting set.

**Files:**
- Create: `jobspy/malaysia/location.py`
- Test: `tests/malaysia/test_location.py`

**Interfaces:**
- Consumes: `Location`, `Country` from `jobspy.model`
- Produces: `MalaysianState` (str Enum); `normalize_location(location: Location | None) -> tuple[Location | None, str | None]` returning `(normalized, unmatched_text)`

- [ ] **Step 1: Write the failing test**

`tests/malaysia/test_location.py`:

```python
from __future__ import annotations

import pytest

from jobspy.malaysia.location import MalaysianState, normalize_location
from jobspy.model import Country, Location


@pytest.mark.parametrize(
    "raw_city,expected_city,expected_state",
    [
        ("Kuala Lumpur", "Kuala Lumpur", "Kuala Lumpur"),
        ("WP Kuala Lumpur", "Kuala Lumpur", "Kuala Lumpur"),
        ("Federal Territory of Kuala Lumpur", "Kuala Lumpur", "Kuala Lumpur"),
        ("Cyberjaya", "Cyberjaya", "Selangor"),
        ("Putrajaya", "Putrajaya", "Putrajaya"),
        ("Petaling Jaya", "Petaling Jaya", "Selangor"),
        ("George Town", "George Town", "Pulau Pinang"),
        ("Butterworth", "Butterworth", "Pulau Pinang"),
        ("Johor Bahru", "Johor Bahru", "Johor"),
        ("Kota Kinabalu", "Kota Kinabalu", "Sabah"),
    ],
)
def test_resolves_known_places(raw_city, expected_city, expected_state):
    normalized, unmatched = normalize_location(
        Location(city=raw_city, country=Country.MALAYSIA)
    )

    assert normalized.city == expected_city
    assert normalized.state == expected_state
    assert normalized.country == Country.MALAYSIA
    assert unmatched is None


def test_kuala_lumpur_gets_a_state_not_none():
    normalized, _ = normalize_location(Location(city="Kuala Lumpur"))

    assert normalized.state == MalaysianState.KUALA_LUMPUR.value


def test_resolves_a_bare_state():
    normalized, unmatched = normalize_location(Location(state="Selangor"))

    assert normalized.state == "Selangor"
    assert normalized.city is None
    assert unmatched is None


def test_uses_state_field_when_city_is_unknown():
    normalized, unmatched = normalize_location(
        Location(city="Bandar Baru Bangi", state="Selangor")
    )

    assert normalized.state == "Selangor"
    assert normalized.city == "Bandar Baru Bangi"
    assert unmatched is None


def test_unknown_location_passes_through_and_reports():
    original = Location(city="Atlantis", state="Nowhere")

    normalized, unmatched = normalize_location(original)

    assert normalized.city == "Atlantis"
    assert normalized.state == "Nowhere"
    assert unmatched == "Atlantis, Nowhere"


def test_none_location_is_safe():
    assert normalize_location(None) == (None, None)
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
poetry run pytest tests/malaysia/test_location.py -v
```

Expected: FAIL — `No module named 'jobspy.malaysia.location'`

- [ ] **Step 3: Implement `location.py`**

```python
from __future__ import annotations

import re
from enum import Enum

from jobspy.model import Country, Location


class MalaysianState(str, Enum):
    """The 13 states and 3 federal territories."""

    JOHOR = "Johor"
    KEDAH = "Kedah"
    KELANTAN = "Kelantan"
    MELAKA = "Melaka"
    NEGERI_SEMBILAN = "Negeri Sembilan"
    PAHANG = "Pahang"
    PERAK = "Perak"
    PERLIS = "Perlis"
    PULAU_PINANG = "Pulau Pinang"
    SABAH = "Sabah"
    SARAWAK = "Sarawak"
    SELANGOR = "Selangor"
    TERENGGANU = "Terengganu"
    KUALA_LUMPUR = "Kuala Lumpur"
    LABUAN = "Labuan"
    PUTRAJAYA = "Putrajaya"


# alias -> (canonical city or None, state)
_GAZETTEER: dict[str, tuple[str | None, MalaysianState]] = {}


def _key(text: str) -> str:
    """Lowercases and strips punctuation so alias lookup is forgiving."""
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


def _add(city: str | None, state: MalaysianState, *aliases: str) -> None:
    names = [city] if city else []
    names += [state.value] if city is None else []
    for name in [*names, *aliases]:
        if name:
            _GAZETTEER[_key(name)] = (city, state)


# --- Federal territories -------------------------------------------------
_add(
    "Kuala Lumpur",
    MalaysianState.KUALA_LUMPUR,
    "KL",
    "WP Kuala Lumpur",
    "W.P. Kuala Lumpur",
    "Wilayah Persekutuan Kuala Lumpur",
    "Federal Territory of Kuala Lumpur",
)
_add("Putrajaya", MalaysianState.PUTRAJAYA, "WP Putrajaya", "Wilayah Persekutuan Putrajaya")
_add("Labuan", MalaysianState.LABUAN, "WP Labuan", "Wilayah Persekutuan Labuan")

# KL localities
for _locality in (
    "Bukit Bintang", "Bangsar", "Mont Kiara", "Cheras", "Setapak", "Sentul",
    "Wangsa Maju", "Bukit Jalil", "Sri Petaling", "Kepong", "Segambut",
    "KL Sentral", "Mid Valley", "Damansara Heights", "Taman Tun Dr Ismail", "TTDI",
):
    _add(_locality, MalaysianState.KUALA_LUMPUR)

# --- Selangor ------------------------------------------------------------
_add(None, MalaysianState.SELANGOR, "Selangor", "Selangor Darul Ehsan")
for _city in (
    "Petaling Jaya", "Shah Alam", "Subang Jaya", "Cyberjaya", "Puchong",
    "Klang", "Kajang", "Bangi", "Bandar Baru Bangi", "Seri Kembangan",
    "Rawang", "Sepang", "Semenyih", "Ampang", "Damansara", "Sunway",
    "Kota Damansara", "Bandar Utama", "Cheras Selatan", "Port Klang",
    "Batu Caves", "Selayang", "Gombak", "Hulu Langat", "Kuala Selangor",
):
    _add(_city, MalaysianState.SELANGOR)
_add("Petaling Jaya", MalaysianState.SELANGOR, "PJ")
_add("Subang Jaya", MalaysianState.SELANGOR, "USJ")

# --- Pulau Pinang --------------------------------------------------------
_add(None, MalaysianState.PULAU_PINANG, "Penang", "Pulau Pinang")
for _city in (
    "George Town", "Bayan Lepas", "Butterworth", "Bukit Mertajam",
    "Seberang Perai", "Gelugor", "Tanjung Tokong", "Batu Kawan", "Perai",
):
    _add(_city, MalaysianState.PULAU_PINANG)
_add("George Town", MalaysianState.PULAU_PINANG, "Georgetown")

# --- Johor ---------------------------------------------------------------
_add(None, MalaysianState.JOHOR, "Johor", "Johor Darul Takzim")
for _city in (
    "Johor Bahru", "Iskandar Puteri", "Nusajaya", "Skudai", "Pasir Gudang",
    "Kulai", "Batu Pahat", "Muar", "Kluang", "Senai", "Pontian", "Segamat",
):
    _add(_city, MalaysianState.JOHOR)
_add("Johor Bahru", MalaysianState.JOHOR, "JB")

# --- Remaining states ----------------------------------------------------
_add(None, MalaysianState.PERAK, "Perak")
for _city in ("Ipoh", "Taiping", "Teluk Intan", "Sitiawan", "Lumut", "Kampar", "Batu Gajah"):
    _add(_city, MalaysianState.PERAK)

_add(None, MalaysianState.KEDAH, "Kedah")
for _city in ("Alor Setar", "Sungai Petani", "Kulim", "Langkawi", "Jitra"):
    _add(_city, MalaysianState.KEDAH)

_add(None, MalaysianState.PERLIS, "Perlis")
_add("Kangar", MalaysianState.PERLIS)

_add(None, MalaysianState.KELANTAN, "Kelantan")
for _city in ("Kota Bharu", "Pasir Mas", "Tanah Merah"):
    _add(_city, MalaysianState.KELANTAN)

_add(None, MalaysianState.TERENGGANU, "Terengganu")
for _city in ("Kuala Terengganu", "Kemaman", "Dungun", "Kerteh"):
    _add(_city, MalaysianState.TERENGGANU)

_add(None, MalaysianState.PAHANG, "Pahang")
for _city in ("Kuantan", "Temerloh", "Bentong", "Genting Highlands", "Cameron Highlands", "Gambang"):
    _add(_city, MalaysianState.PAHANG)

_add(None, MalaysianState.MELAKA, "Melaka", "Malacca")
for _city in ("Melaka City", "Ayer Keroh", "Alor Gajah", "Jasin"):
    _add(_city, MalaysianState.MELAKA)

_add(None, MalaysianState.NEGERI_SEMBILAN, "Negeri Sembilan", "Negri Sembilan")
for _city in ("Seremban", "Nilai", "Port Dickson", "Bahau", "Senawang"):
    _add(_city, MalaysianState.NEGERI_SEMBILAN)

_add(None, MalaysianState.SABAH, "Sabah")
for _city in ("Kota Kinabalu", "Sandakan", "Tawau", "Lahad Datu", "Keningau", "Papar"):
    _add(_city, MalaysianState.SABAH)

_add(None, MalaysianState.SARAWAK, "Sarawak")
for _city in ("Kuching", "Miri", "Sibu", "Bintulu", "Samarahan", "Sri Aman"):
    _add(_city, MalaysianState.SARAWAK)


def _lookup(text: str | None) -> tuple[str | None, MalaysianState] | None:
    if not text:
        return None
    return _GAZETTEER.get(_key(text))


def normalize_location(
    location: Location | None,
) -> tuple[Location | None, str | None]:
    """Resolves a scraped Location to a canonical Malaysian city and state.

    Returns (normalized_location, unmatched_text). unmatched_text is non-None
    only when nothing could be resolved; the caller logs it so the gazetteer
    can grow from measured misses rather than guesses.
    """
    if location is None:
        return None, None

    city_hit = _lookup(location.city)
    state_hit = _lookup(location.state)

    if city_hit:
        canonical_city, state = city_hit
        return (
            Location(
                city=canonical_city or location.city,
                state=state.value,
                country=Country.MALAYSIA,
            ),
            None,
        )

    if state_hit:
        _, state = state_hit
        return (
            Location(city=location.city, state=state.value, country=Country.MALAYSIA),
            None,
        )

    unmatched = ", ".join(part for part in (location.city, location.state) if part)
    return location, (unmatched or None)
```

- [ ] **Step 4: Run the tests**

```powershell
poetry run pytest tests/malaysia/test_location.py -v
```

Expected: all pass.

- [ ] **Step 5: Extend the gazetteer from real data**

Open the baseline report from Task 5. For each entry in `Top location strings` that the gazetteer does not resolve, add an alias. Add a test case for any non-obvious one.

- [ ] **Step 6: Format and commit**

```bash
poetry run black jobspy tests
git add jobspy/malaysia/location.py tests/malaysia/test_location.py
git commit -m "feat(malaysia): add location gazetteer and state normalization"
```

---

## Task 8: `salary.py` — MYR salary parsing

**Files:**
- Create: `jobspy/malaysia/salary.py`
- Test: `tests/malaysia/test_salary.py`

**Interfaces:**
- Consumes: `detect_interval` from `jobspy.malaysia.language`; `Compensation`, `CompensationInterval` from `jobspy.model`
- Produces: `parse_myr_salary(text: str | None) -> Compensation | None`

- [ ] **Step 1: Write the failing test**

`tests/malaysia/test_salary.py`:

```python
from __future__ import annotations

import pytest

from jobspy.malaysia.salary import parse_myr_salary


@pytest.mark.parametrize(
    "text,interval,low,high",
    [
        ("Salary: RM3,000 - RM5,000", "monthly", 3000, 5000),
        ("RM 3,000 - RM 5,000 per month", "monthly", 3000, 5000),
        ("MYR 3000-5000", "monthly", 3000, 5000),
        ("3,000 - 5,000 MYR", "monthly", 3000, 5000),
        ("RM3k-5k", "monthly", 3000, 5000),
        ("Gaji RM2,500 sebulan", "monthly", 2500, 2500),
        ("RM3,000 hingga RM4,500", "monthly", 3000, 4500),
        ("RM90,000 setahun", "yearly", 90000, 90000),
        ("RM 25 sejam", "hourly", 25, 25),
        ("Up to RM12,000", "monthly", 12000, 12000),
    ],
)
def test_parses_myr_salaries(text, interval, low, high):
    compensation = parse_myr_salary(text)

    assert compensation is not None
    assert compensation.interval.value == interval
    assert compensation.min_amount == low
    assert compensation.max_amount == high
    assert compensation.currency == "MYR"


def test_bare_amount_defaults_to_monthly():
    # MY postings quote monthly by default - the inverse of the US assumption.
    assert parse_myr_salary("RM5,000").interval.value == "monthly"


@pytest.mark.parametrize(
    "text",
    [
        "RM800",          # below the monthly floor; likelier hourly or daily
        "RM2,000,000",    # above the monthly ceiling and not marked annual
        "$3,000 - $5,000",  # USD, not ours to parse
        "Competitive salary",
        "",
        None,
    ],
)
def test_rejects_implausible_or_absent_salaries(text):
    assert parse_myr_salary(text) is None


def test_annual_band_is_wider_than_monthly():
    assert parse_myr_salary("RM120,000 per annum") is not None


def test_inverted_range_is_rejected():
    assert parse_myr_salary("RM5,000 - RM3,000") is None
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
poetry run pytest tests/malaysia/test_salary.py -v
```

Expected: FAIL — `No module named 'jobspy.malaysia.salary'`

- [ ] **Step 3: Implement `salary.py`**

```python
from __future__ import annotations

import re

from jobspy.malaysia.language import detect_interval
from jobspy.model import Compensation, CompensationInterval

# Sanity bands from the design spec. These filter nonsense; they are not
# claims about Malaysian pay policy. The monthly floor sits below the
# statutory minimum wage (RM1,700/month as of 2025) on purpose, to allow
# part-time and internship rates through.
_BANDS: dict[str, tuple[float, float]] = {
    "hourly": (8, 150),
    "daily": (30, 1_000),
    "weekly": (200, 8_000),
    "monthly": (1_000, 30_000),
    "yearly": (20_000, 500_000),
}

_AMOUNT = r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*([kK])?"
_SEPARATOR = r"\s*(?:-|–|—|to|hingga|sehingga|until)\s*"

# RM3,000 - RM5,000  /  MYR 3000-5000
_PREFIXED_RANGE = re.compile(
    rf"(?:RM|MYR)\s*{_AMOUNT}{_SEPARATOR}(?:RM|MYR)?\s*{_AMOUNT}", re.IGNORECASE
)
# 3,000 - 5,000 MYR
_SUFFIXED_RANGE = re.compile(
    rf"{_AMOUNT}{_SEPARATOR}{_AMOUNT}\s*(?:RM|MYR)", re.IGNORECASE
)
_PREFIXED_SINGLE = re.compile(rf"(?:RM|MYR)\s*{_AMOUNT}", re.IGNORECASE)
_SUFFIXED_SINGLE = re.compile(rf"{_AMOUNT}\s*(?:RM|MYR)", re.IGNORECASE)


def _to_number(digits: str, k_suffix: str | None) -> float:
    value = float(digits.replace(",", ""))
    return value * 1000 if k_suffix else value


def _extract_pair(text: str) -> tuple[float, float] | None:
    for pattern in (_PREFIXED_RANGE, _SUFFIXED_RANGE):
        match = pattern.search(text)
        if match:
            low = _to_number(match.group(1), match.group(2))
            high = _to_number(match.group(3), match.group(4))
            return low, high

    for pattern in (_PREFIXED_SINGLE, _SUFFIXED_SINGLE):
        match = pattern.search(text)
        if match:
            value = _to_number(match.group(1), match.group(2))
            return value, value

    return None


def parse_myr_salary(text: str | None) -> Compensation | None:
    """Extracts a MYR salary from free text.

    Malaysian postings quote monthly pay by default, so an amount with no
    stated interval is treated as monthly. Returns None when nothing
    plausible is found - callers must not guess on its behalf.
    """
    if not text:
        return None

    pair = _extract_pair(text)
    if pair is None:
        return None

    low, high = pair
    if low > high:
        return None

    interval = detect_interval(text) or "monthly"
    floor, ceiling = _BANDS.get(interval, _BANDS["monthly"])
    if not (floor <= low <= ceiling and floor <= high <= ceiling):
        return None

    return Compensation(
        interval=CompensationInterval(interval),
        min_amount=low,
        max_amount=high,
        currency="MYR",
    )
```

- [ ] **Step 4: Run the tests**

```powershell
poetry run pytest tests/malaysia/test_salary.py -v
```

Expected: all pass.

- [ ] **Step 5: Format and commit**

```bash
poetry run black jobspy tests
git add jobspy/malaysia/salary.py tests/malaysia/test_salary.py
git commit -m "feat(malaysia): parse MYR salaries from description text"
```

---

## Task 9: `remote.py` — remote eligibility tagging

**Files:**
- Create: `jobspy/malaysia/remote.py`
- Test: `tests/malaysia/test_remote.py`

**Interfaces:**
- Consumes: `JobPost` from `jobspy.model`
- Produces: `classify_remote_scope(job: JobPost) -> str | None`

- [ ] **Step 1: Write the failing test**

`tests/malaysia/test_remote.py`:

```python
from __future__ import annotations

import pytest

from jobspy.malaysia.remote import classify_remote_scope
from jobspy.model import Country, Location


def test_non_remote_job_has_no_scope(make_job):
    assert classify_remote_scope(make_job(is_remote=False)) is None


@pytest.mark.parametrize(
    "description,expected",
    [
        ("Candidates must be based in Malaysia.", "my"),
        ("Open to candidates across APAC.", "apac"),
        ("Work from anywhere in the world.", "global"),
        ("Must have US work authorization.", "other_country"),
        ("We are a fast-growing startup.", "unknown"),
        ("You will work GMT+8 hours.", "apac"),
        ("Core hours are EST.", "other_country"),
    ],
)
def test_classifies_from_description(make_job, description, expected):
    job = make_job(is_remote=True, description=description)

    assert classify_remote_scope(job) == expected


def test_explicit_exclusion_beats_generic_remote(make_job):
    job = make_job(
        is_remote=True,
        description="Fully remote role. Applicants must be authorized to work in the US.",
    )

    assert classify_remote_scope(job) == "other_country"


def test_malaysian_location_implies_my(make_job):
    job = make_job(
        is_remote=True,
        description="Remote role.",
        location=Location(city="Kuala Lumpur", country=Country.MALAYSIA),
    )

    assert classify_remote_scope(job) == "my"


def test_missing_description_is_unknown(make_job):
    assert classify_remote_scope(make_job(is_remote=True, description=None, location=None)) == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
poetry run pytest tests/malaysia/test_remote.py -v
```

Expected: FAIL — `No module named 'jobspy.malaysia.remote'`

- [ ] **Step 3: Implement `remote.py`**

```python
from __future__ import annotations

import re

from jobspy.model import Country, JobPost

# Checked in order. An explicit exclusion must beat a generic remote claim,
# so other_country is evaluated before everything else.
_OTHER_COUNTRY_PATTERNS = (
    r"\bus work authoriz",
    r"\bauthoriz\w* to work in the (?:us|united states|uk|eu)\b",
    r"\bmust (?:be|reside) (?:located |based )?in the (?:us|usa|united states|uk)\b",
    r"\bus[- ]only\b",
    r"\bus[- ]based only\b",
    r"\b(?:est|pst|cst|pdt|edt)\b",
    r"\bgmt[+-](?:4|5|6|7|8)?\b(?=.*\b(?:us|america)\b)",
)

_MY_PATTERNS = (
    r"\bmalaysia\b",
    r"\bmalaysian\b",
    r"\bkuala lumpur\b",
    r"\bmyt\b",
)

_APAC_PATTERNS = (
    r"\bapac\b",
    r"\basia[- ]pacific\b",
    r"\bsoutheast asia\b",
    r"\bsea region\b",
    r"\bsingapore\b",
    r"\bgmt\+8\b",
    r"\bsgt\b",
)

_GLOBAL_PATTERNS = (
    r"\banywhere in the world\b",
    r"\bwork from anywhere\b",
    r"\bfully distributed\b",
    r"\bglobally remote\b",
    r"\bworldwide\b",
)


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def classify_remote_scope(job: JobPost) -> str | None:
    """Tags where a remote job can plausibly be worked from.

    Returns None for non-remote jobs. 'unknown' is expected to dominate -
    most postings never state eligibility. This is a sorting aid, never a
    filter: callers must not drop rows based on it.
    """
    if not job.is_remote:
        return None

    haystack_parts = [job.description or "", job.title or ""]
    if job.location is not None:
        haystack_parts.append(job.location.city or "")
        haystack_parts.append(job.location.state or "")
        if isinstance(job.location.country, str):
            haystack_parts.append(job.location.country)
        elif job.location.country is Country.MALAYSIA:
            haystack_parts.append("malaysia")

    text = re.sub(r"\s+", " ", " ".join(haystack_parts).lower())
    if not text.strip():
        return "unknown"

    if _matches(text, _OTHER_COUNTRY_PATTERNS):
        return "other_country"
    if _matches(text, _MY_PATTERNS):
        return "my"
    if _matches(text, _APAC_PATTERNS):
        return "apac"
    if _matches(text, _GLOBAL_PATTERNS):
        return "global"
    return "unknown"
```

- [ ] **Step 4: Run the tests**

```powershell
poetry run pytest tests/malaysia/test_remote.py -v
```

Expected: all pass.

- [ ] **Step 5: Format and commit**

```bash
poetry run black jobspy tests
git add jobspy/malaysia/remote.py tests/malaysia/test_remote.py
git commit -m "feat(malaysia): tag remote listings with eligibility scope"
```

---

## Task 10: `grouping.py` — exact dedup and fuzzy grouping

Two mechanisms, deliberately separate. Exact dedup removes rows; fuzzy grouping never does.

**Files:**
- Create: `jobspy/malaysia/grouping.py`
- Test: `tests/malaysia/test_grouping.py`

**Interfaces:**
- Consumes: `JobPost` from `jobspy.model`; `rapidfuzz.fuzz.token_sort_ratio`
- Produces: `normalize_company(name: str | None) -> str`; `seniority_markers(title: str | None) -> frozenset[str]`; `dedupe_exact(jobs: list[JobPost]) -> list[JobPost]`; `assign_groups(jobs: list[JobPost], *, threshold: int = 90) -> list[JobPost]`

- [ ] **Step 1: Write the failing test**

`tests/malaysia/test_grouping.py`:

```python
from __future__ import annotations

from jobspy.malaysia.grouping import (
    assign_groups,
    dedupe_exact,
    normalize_company,
    seniority_markers,
)
from jobspy.model import Country, Location


def _my(city="Kuala Lumpur"):
    return Location(city=city, state="Kuala Lumpur", country=Country.MALAYSIA)


def test_normalizes_company_suffixes():
    assert normalize_company("Grab Malaysia Sdn Bhd") == "grab"
    assert normalize_company("GrabTaxi Holdings Pte Ltd") == "grabtaxi holdings"
    assert normalize_company(None) == ""


def test_detects_seniority_markers():
    assert seniority_markers("Senior Software Engineer") == frozenset({"senior"})
    assert seniority_markers("Software Engineer") == frozenset()
    assert seniority_markers("Engineering Manager") == frozenset({"manager"})


def test_exact_dedup_drops_repeated_urls(make_job):
    jobs = [
        make_job(job_url="https://x/1"),
        make_job(job_url="https://x/1?utm_source=email"),
        make_job(job_url="https://x/2"),
    ]

    assert len(dedupe_exact(jobs)) == 2


def test_exact_dedup_keeps_the_most_complete_record(make_job):
    sparse = make_job(job_url="https://x/1", description=None)
    rich = make_job(job_url="https://x/1", description="Full description here")

    kept = dedupe_exact([sparse, rich])

    assert len(kept) == 1
    assert kept[0].description == "Full description here"


def test_groups_same_job_across_boards(make_job):
    jobs = [
        make_job(job_url="https://a/1", title="Software Engineer", location=_my()),
        make_job(job_url="https://b/1", title="Software  Engineer", location=_my()),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group is not None
    assert grouped[0].dedup_group == grouped[1].dedup_group


def test_never_groups_across_seniority(make_job):
    jobs = [
        make_job(job_url="https://a/1", title="Senior Software Engineer", location=_my()),
        make_job(job_url="https://b/1", title="Software Engineer", location=_my()),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group != grouped[1].dedup_group


def test_does_not_group_different_states(make_job):
    jobs = [
        make_job(job_url="https://a/1", title="Software Engineer", location=_my()),
        make_job(
            job_url="https://b/1",
            title="Software Engineer",
            location=Location(city="Penang", state="Pulau Pinang", country=Country.MALAYSIA),
        ),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group != grouped[1].dedup_group


def test_groups_a_remote_listing_with_a_located_one(make_job):
    jobs = [
        make_job(job_url="https://a/1", title="Software Engineer", location=_my()),
        make_job(job_url="https://b/1", title="Software Engineer", location=None, is_remote=True),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group == grouped[1].dedup_group


def test_does_not_group_different_companies(make_job):
    jobs = [
        make_job(job_url="https://a/1", company_name="Grab", location=_my()),
        make_job(job_url="https://b/1", company_name="Shopee", location=_my()),
    ]

    grouped = assign_groups(jobs)

    assert grouped[0].dedup_group != grouped[1].dedup_group


def test_group_ids_are_stable_across_runs(make_job):
    def build():
        return [
            make_job(job_url="https://a/1", title="Software Engineer", location=_my()),
            make_job(job_url="https://b/1", title="Software Engineer", location=_my()),
        ]

    first = assign_groups(build())[0].dedup_group
    second = assign_groups(build())[0].dedup_group

    assert first == second


def test_grouping_never_removes_rows(make_job):
    jobs = [make_job(job_url=f"https://a/{i}") for i in range(5)]

    assert len(assign_groups(jobs)) == 5
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
poetry run pytest tests/malaysia/test_grouping.py -v
```

Expected: FAIL — `No module named 'jobspy.malaysia.grouping'`

- [ ] **Step 3: Implement `grouping.py`**

```python
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

from rapidfuzz import fuzz

from jobspy.model import JobPost

_COMPANY_SUFFIXES = (
    "sdn bhd", "sdn. bhd.", "bhd", "berhad", "pte ltd", "pte. ltd.",
    "pvt ltd", "ltd", "llc", "inc", "plc", "gmbh", "co",
)

# Words that mark a rank rather than a role. Two titles carrying different
# markers are different jobs and must never share a group - this is checked
# before similarity scoring, because set-based similarity gets it backwards:
# token_set_ratio("senior software engineer", "software engineer") == 100.
_SENIORITY_MARKERS = (
    "intern", "internship", "trainee", "graduate", "junior", "jr",
    "senior", "snr", "sr", "lead", "principal", "staff", "head",
    "manager", "director", "vp", "chief",
)


def normalize_company(name: str | None) -> str:
    """Strips corporate suffixes and country tags so one company forms one block."""
    if not name:
        return ""

    text = re.sub(r"[^a-z0-9 ]+", " ", name.lower())
    text = re.sub(r"\s+", " ", text).strip()

    changed = True
    while changed:
        changed = False
        for suffix in _COMPANY_SUFFIXES:
            if text.endswith(" " + suffix) or text == suffix:
                text = text[: -len(suffix)].strip()
                changed = True
        if text.endswith(" malaysia"):
            text = text[: -len(" malaysia")].strip()
            changed = True

    return text


def seniority_markers(title: str | None) -> frozenset[str]:
    """Returns the rank words present in a title."""
    if not title:
        return frozenset()

    tokens = set(re.findall(r"[a-z]+", title.lower()))
    return frozenset(marker for marker in _SENIORITY_MARKERS if marker in tokens)


def _normalize_title(title: str | None) -> str:
    if not title:
        return ""
    text = re.sub(r"[^a-z0-9 ]+", " ", title.lower())
    return re.sub(r"\s+", " ", text).strip()


def _canonical_url(url: str | None) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _completeness(job: JobPost) -> int:
    """Higher is richer. Used to pick a winner among exact duplicates."""
    score = 0
    if job.description:
        score += 2
    if job.compensation:
        score += 2
    if job.date_posted:
        score += 1
    if job.job_url_direct:
        score += 1
    return score


def dedupe_exact(jobs: list[JobPost]) -> list[JobPost]:
    """Removes listings that are literally the same posting seen twice.

    This is the only destructive step in the pipeline. It exists because the
    location and remote query passes overlap heavily.
    """
    best: dict[str, JobPost] = {}
    order: list[str] = []

    for job in jobs:
        # Never fall back to a shared constant - a batch of jobs with no url
        # and no id would otherwise collapse into a single row.
        key = (
            _canonical_url(job.job_url)
            or (f"id:{job.id}" if job.id else "")
            or f"obj:{id(job)}"
        )
        if key not in best:
            best[key] = job
            order.append(key)
        elif _completeness(job) > _completeness(best[key]):
            best[key] = job

    return [best[key] for key in order]


def _state_of(job: JobPost) -> str | None:
    if job.location is None:
        return None
    return job.location.state


def _compatible_location(left: JobPost, right: JobPost) -> bool:
    left_state, right_state = _state_of(left), _state_of(right)
    if left.is_remote or right.is_remote:
        return True
    if left_state is None or right_state is None:
        return False
    return left_state == right_state


def _group_id(company: str, title: str, state: str | None) -> str:
    canonical = f"{company}|{title}|{state or 'remote'}"
    return hashlib.blake2s(canonical.encode("utf-8"), digest_size=6).hexdigest()


def assign_groups(jobs: list[JobPost], *, threshold: int = 90) -> list[JobPost]:
    """Stamps likely-duplicate listings with a shared dedup_group id.

    Non-destructive: every input job is returned. Tuned conservative - a
    missed group costs one duplicate row, a wrong group asserts that two
    distinct openings are the same job.
    """
    blocks: dict[str, list[JobPost]] = {}
    for job in jobs:
        blocks.setdefault(normalize_company(job.company_name), []).append(job)

    for company, members in blocks.items():
        if not company:
            continue

        clusters: list[list[JobPost]] = []
        for job in sorted(members, key=lambda j: (_normalize_title(j.title), j.job_url or "")):
            title = _normalize_title(job.title)
            markers = seniority_markers(job.title)

            placed = False
            for cluster in clusters:
                leader = cluster[0]
                if markers != seniority_markers(leader.title):
                    continue
                if not _compatible_location(job, leader):
                    continue
                if fuzz.token_sort_ratio(title, _normalize_title(leader.title)) >= threshold:
                    cluster.append(job)
                    placed = True
                    break
            if not placed:
                clusters.append([job])

        for cluster in clusters:
            if len(cluster) < 2:
                continue
            leader = cluster[0]
            group = _group_id(company, _normalize_title(leader.title), _state_of(leader))
            for job in cluster:
                job.dedup_group = group

    return jobs
```

- [ ] **Step 4: Run the tests**

```powershell
poetry run pytest tests/malaysia/test_grouping.py -v
```

Expected: all pass.

- [ ] **Step 5: Format and commit**

```bash
poetry run black jobspy tests
git add jobspy/malaysia/grouping.py tests/malaysia/test_grouping.py
git commit -m "feat(malaysia): add exact dedup and conservative fuzzy grouping"
```

---

## Task 11: The `normalize()` pipeline

**Files:**
- Modify: `jobspy/malaysia/__init__.py`
- Test: `tests/malaysia/test_pipeline.py`

**Interfaces:**
- Consumes: `normalize_location` (Task 7), `parse_myr_salary` (Task 8), `classify_remote_scope` (Task 9), `dedupe_exact` / `assign_groups` (Task 10)
- Produces: `normalize(jobs: list[JobPost], *, group_duplicates: bool = True) -> list[JobPost]`

- [ ] **Step 1: Write the failing test**

`tests/malaysia/test_pipeline.py`:

```python
from __future__ import annotations

from jobspy.malaysia import normalize
from jobspy.model import Country, Location


def test_normalizes_location_salary_and_remote(make_job):
    job = make_job(
        location=Location(city="Cyberjaya", country=Country.MALAYSIA),
        description="We offer RM6,000 - RM8,000 per month. Open to APAC candidates.",
        is_remote=True,
    )

    result = normalize([job])[0]

    assert result.location.state == "Selangor"
    assert result.compensation.min_amount == 6000
    assert result.compensation.currency == "MYR"
    assert result.remote_scope == "apac"


def test_does_not_overwrite_structured_compensation(make_job):
    from jobspy.model import Compensation, CompensationInterval

    job = make_job(
        description="RM9,000 per month",
        compensation=Compensation(
            interval=CompensationInterval.MONTHLY,
            min_amount=4000,
            max_amount=4000,
            currency="MYR",
        ),
    )

    assert normalize([job])[0].compensation.min_amount == 4000


def test_removes_exact_duplicates(make_job):
    jobs = [make_job(job_url="https://x/1"), make_job(job_url="https://x/1")]

    assert len(normalize(jobs)) == 1


def test_group_duplicates_false_skips_grouping(make_job):
    jobs = [
        make_job(job_url="https://a/1", title="Software Engineer"),
        make_job(job_url="https://b/1", title="Software Engineer"),
    ]

    result = normalize(jobs, group_duplicates=False)

    assert len(result) == 2
    assert all(job.dedup_group is None for job in result)


def test_exact_dedup_runs_even_when_grouping_is_off(make_job):
    jobs = [make_job(job_url="https://x/1"), make_job(job_url="https://x/1")]

    assert len(normalize(jobs, group_duplicates=False)) == 1


def test_a_failing_normalizer_does_not_abort_the_batch(make_job, monkeypatch):
    import jobspy.malaysia as pipeline

    def boom(_):
        raise ValueError("bad input")

    monkeypatch.setattr(pipeline, "parse_myr_salary", boom)

    jobs = [make_job(job_url="https://x/1", description="RM5,000")]
    result = normalize(jobs)

    assert len(result) == 1
    assert result[0].compensation is None


def test_empty_input_is_safe():
    assert normalize([]) == []
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
poetry run pytest tests/malaysia/test_pipeline.py -v
```

Expected: FAIL — `cannot import name 'normalize'`

- [ ] **Step 3: Implement the pipeline**

Replace the contents of `jobspy/malaysia/__init__.py`:

```python
"""Malaysia-specific normalization for scraped job posts.

Three per-job stages (location, salary, remote) then one batch-wide stage
(grouping). Runs on list[JobPost] before DataFrame flattening so normalizers
read and write structured fields.
"""

from __future__ import annotations

from collections import Counter

from jobspy.malaysia.grouping import assign_groups, dedupe_exact
from jobspy.malaysia.location import normalize_location
from jobspy.malaysia.remote import classify_remote_scope
from jobspy.malaysia.salary import parse_myr_salary
from jobspy.model import JobPost
from jobspy.util import create_logger

log = create_logger("Malaysia")

__all__ = ["normalize"]


def _apply_location(job: JobPost, unmatched: Counter) -> None:
    normalized, miss = normalize_location(job.location)
    job.location = normalized
    if miss:
        unmatched[miss] += 1


def _apply_salary(job: JobPost) -> None:
    # Structured board data always wins.
    if job.compensation is not None:
        return
    parsed = parse_myr_salary(job.description)
    if parsed is not None:
        job.compensation = parsed


def _apply_remote(job: JobPost) -> None:
    job.remote_scope = classify_remote_scope(job)


_PER_JOB_STAGES = (
    ("location", _apply_location),
    ("salary", _apply_salary),
    ("remote", _apply_remote),
)


def normalize(
    jobs: list[JobPost], *, group_duplicates: bool = True
) -> list[JobPost]:
    """Runs the Malaysian normalization pipeline over a batch of jobs.

    A stage that raises on one job is logged and skipped for that job only -
    it must never take the batch down. Exact dedup always runs;
    group_duplicates=False disables fuzzy grouping only.
    """
    if not jobs:
        return []

    unmatched_locations: Counter = Counter()
    failures: Counter = Counter()

    for job in jobs:
        for stage_name, stage in _PER_JOB_STAGES:
            try:
                if stage_name == "location":
                    stage(job, unmatched_locations)
                else:
                    stage(job)
            except Exception as exc:  # noqa: BLE001 - one bad job must not abort the batch
                failures[stage_name] += 1
                log.warning(
                    f"{stage_name} normalizer failed for {job.job_url!r}: {exc}"
                )

    deduped = dedupe_exact(jobs)
    removed = len(jobs) - len(deduped)
    if removed:
        log.info(f"exact dedup removed {removed} duplicate listing(s)")

    if group_duplicates:
        try:
            deduped = assign_groups(deduped)
        except Exception as exc:  # noqa: BLE001 - grouping is optional, never fatal
            log.warning(f"grouping failed, continuing ungrouped: {exc}")

    if unmatched_locations:
        top = ", ".join(
            f"{name} ({count})" for name, count in unmatched_locations.most_common(10)
        )
        log.info(f"unmatched locations - add to the gazetteer: {top}")

    for stage_name, count in failures.items():
        log.warning(f"{stage_name} normalizer failed on {count} job(s)")

    return deduped
```

Note: `_apply_salary` is referenced through the module-global `parse_myr_salary`, which is what makes the monkeypatch test work.

- [ ] **Step 4: Run the tests**

```powershell
poetry run pytest tests/malaysia/ -v
```

Expected: all pass.

- [ ] **Step 5: Format and commit**

```bash
poetry run black jobspy tests
git add jobspy/malaysia/__init__.py tests/malaysia/test_pipeline.py
git commit -m "feat(malaysia): add normalization pipeline with per-stage error isolation"
```

---

## Task 12: Wire the pipeline into `scrape_jobs` and fix the fatal-board bug

**Files:**
- Modify: `jobspy/__init__.py`
- Test: `tests/test_scrape_jobs_integration.py`

**Interfaces:**
- Consumes: `normalize` (Task 11), `build_jobs_dataframe` (Task 2)
- Produces: `scrape_jobs(..., country_indeed="malaysia", group_duplicates=True)`

- [ ] **Step 1: Write the failing test**

`tests/test_scrape_jobs_integration.py`:

```python
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

    df = jobspy.scrape_jobs(site_name=["indeed"], search_term="engineer", results_wanted=1)

    assert df.iloc[0]["state"] == "Selangor"
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
poetry run pytest tests/test_scrape_jobs_integration.py -v
```

Expected: FAIL — `country_indeed` default is `"usa"`.

- [ ] **Step 3: Make `SCRAPER_MAPPING` monkeypatchable**

The mapping currently reads the imported classes at call time inside `scrape_jobs`, which is what the tests patch. Confirm `SCRAPER_MAPPING` is built inside the function body (it is, at `jobspy/__init__.py:58`) and change it to reference module globals so `monkeypatch.setattr(jobspy, "Indeed", ...)` takes effect:

```python
    SCRAPER_MAPPING = {
        Site.LINKEDIN: globals()["LinkedIn"],
        Site.INDEED: globals()["Indeed"],
        Site.ZIP_RECRUITER: globals()["ZipRecruiter"],
        Site.GLASSDOOR: globals()["Glassdoor"],
        Site.GOOGLE: globals()["Google"],
        Site.BAYT: globals()["BaytScraper"],
        Site.NAUKRI: globals()["Naukri"],
        Site.BDJOBS: globals()["BDJobs"],
    }
```

- [ ] **Step 4: Change the signature**

In `jobspy/__init__.py`, change `country_indeed: str = "usa"` to:

```python
    country_indeed: str = "malaysia",
```

and add after `enforce_annual_salary: bool = False,`:

```python
    group_duplicates: bool = True,
```

- [ ] **Step 5: Guard `future.result()` and run the pipeline**

Replace the `as_completed` loop and the return (currently `jobspy/__init__.py:125-127` plus the `build_jobs_dataframe` call from Task 2):

```python
        for future in as_completed(future_to_site):
            site = future_to_site[future]
            try:
                site_value, scraped_data = future.result()
            except Exception as exc:  # noqa: BLE001 - one board must not kill the run
                create_logger(site.value.capitalize()).error(
                    f"scrape failed, continuing without it: {exc}"
                )
                site_to_jobs_dict[site.value] = JobResponse(jobs=[])
                continue
            site_to_jobs_dict[site_value] = scraped_data

    if country_enum == Country.MALAYSIA:
        # Site attribution lives in the dict key, not on JobPost, so remember
        # which site each job came from before flattening for the pipeline.
        site_by_job = {
            id(job): site
            for site, response in site_to_jobs_dict.items()
            for job in response.jobs
        }
        all_jobs = [job for r in site_to_jobs_dict.values() for job in r.jobs]
        normalized = malaysia_normalize(all_jobs, group_duplicates=group_duplicates)

        regrouped = {site: JobResponse(jobs=[]) for site in site_to_jobs_dict}
        for job in normalized:
            regrouped[site_by_job[id(job)]].jobs.append(job)
        site_to_jobs_dict = regrouped

    return build_jobs_dataframe(
        site_to_jobs_dict,
        country_enum=country_enum,
        enforce_annual_salary=enforce_annual_salary,
    )
```

Add the import at the top:

```python
from jobspy.malaysia import normalize as malaysia_normalize
```

- [ ] **Step 6: Run the tests**

```powershell
poetry run pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 7: Format and commit**

```bash
poetry run black jobspy tests
git add jobspy/__init__.py tests/test_scrape_jobs_integration.py
git commit -m "feat: run the Malaysia pipeline in scrape_jobs and survive board failures"
```

---

## Task 13: `include_remote` two-pass querying

**Files:**
- Modify: `jobspy/__init__.py`
- Test: `tests/test_scrape_jobs_integration.py`

**Interfaces:**
- Consumes: `scrape_jobs` (Task 12)
- Produces: `scrape_jobs(..., include_remote=True)`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scrape_jobs_integration.py`:

```python
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
        site_name=["indeed"], search_term="engineer", include_remote=True, results_wanted=1
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
        site_name=["indeed"], search_term="engineer", include_remote=False, results_wanted=1
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
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
poetry run pytest tests/test_scrape_jobs_integration.py -v
```

Expected: FAIL — `scrape_jobs() got an unexpected keyword argument 'include_remote'`

- [ ] **Step 3: Add the parameter**

In `jobspy/__init__.py`, after `group_duplicates: bool = True,`:

```python
    include_remote: bool = True,
```

- [ ] **Step 4: Run both passes**

Replace `scrape_site`, `worker` and the executor block:

```python
    def scrape_site(site: Site, site_input: ScraperInput) -> Tuple[str, JobResponse]:
        scraper_class = SCRAPER_MAPPING[site]
        scraper = scraper_class(proxies=proxies, ca_cert=ca_cert, user_agent=user_agent)
        scraped_data: JobResponse = scraper.scrape(site_input)
        cap_name = site.value.capitalize()
        site_display = "ZipRecruiter" if cap_name == "Zip_recruiter" else cap_name
        site_display = "LinkedIn" if cap_name == "Linkedin" else site_display
        create_logger(site_display).info("finished scraping")
        return site.value, scraped_data

    site_to_jobs_dict: dict[str, JobResponse] = {}

    # The located pass and the remote pass overlap heavily; exact dedup in the
    # Malaysia pipeline absorbs the duplicates.
    passes: list[ScraperInput] = [scraper_input]
    if include_remote and not is_remote:
        remote_input = scraper_input.model_copy(deep=True)
        remote_input.is_remote = True
        passes.append(remote_input)

    jobs_to_run = [(site, site_input) for site in scraper_input.site_type for site_input in passes]

    with ThreadPoolExecutor() as executor:
        future_to_site = {
            executor.submit(scrape_site, site, site_input): site
            for site, site_input in jobs_to_run
        }

        for future in as_completed(future_to_site):
            site = future_to_site[future]
            try:
                site_value, scraped_data = future.result()
            except Exception as exc:  # noqa: BLE001 - one board must not kill the run
                create_logger(site.value.capitalize()).error(
                    f"scrape failed, continuing without it: {exc}"
                )
                site_to_jobs_dict.setdefault(site.value, JobResponse(jobs=[]))
                continue
            existing = site_to_jobs_dict.setdefault(site_value, JobResponse(jobs=[]))
            existing.jobs.extend(scraped_data.jobs)
```

- [ ] **Step 5: Run the tests**

```powershell
poetry run pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 6: Format and commit**

```bash
poetry run black jobspy tests
git add jobspy/__init__.py tests/test_scrape_jobs_integration.py
git commit -m "feat: add include_remote two-pass querying"
```

---

## Task 14: Quarantine the non-MY boards and re-measure

**Files:**
- Modify: `jobspy/__init__.py`
- Modify: `README.md`
- Create: `docs/baseline/<today>-baseline-phase1.md`
- Test: `tests/test_scrape_jobs_integration.py`

**Interfaces:**
- Consumes: everything above
- Produces: `DEFAULT_SITES: list[Site]`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scrape_jobs_integration.py`:

```python
def test_default_sites_are_malaysia_relevant():
    from jobspy import DEFAULT_SITES

    assert {site.value for site in DEFAULT_SITES} == {"indeed", "linkedin", "google"}


def test_unsupported_board_still_works_when_named_explicitly(monkeypatch, make_job):
    class OkScraper:
        def __init__(self, **kwargs):
            pass

        def scrape(self, scraper_input):
            return JobResponse(jobs=[make_job(job_url="https://bayt/1")])

    monkeypatch.setattr(jobspy, "BaytScraper", OkScraper, raising=False)

    df = jobspy.scrape_jobs(site_name=["bayt"], search_term="engineer", results_wanted=1)

    assert len(df) == 1
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
poetry run pytest tests/test_scrape_jobs_integration.py -v
```

Expected: FAIL — `cannot import name 'DEFAULT_SITES'`

- [ ] **Step 3: Add the default site list**

In `jobspy/__init__.py`, after the imports:

```python
# Boards worth querying for a Malaysian search. The rest are inherited from
# upstream and stay importable, but are not queried unless asked for by name.
DEFAULT_SITES: list[Site] = [Site.INDEED, Site.LINKEDIN, Site.GOOGLE]
```

Change `get_site_type()` so the no-argument case uses it:

```python
    def get_site_type():
        site_types = list(DEFAULT_SITES)
        if isinstance(site_name, str):
            site_types = [map_str_to_site(site_name)]
        elif isinstance(site_name, Site):
            site_types = [site_name]
        elif isinstance(site_name, list):
            site_types = [
                map_str_to_site(site) if isinstance(site, str) else site
                for site in site_name
            ]
        return site_types
```

Replace the trailing `__all__` (currently `["BDJobs"]`, a leftover that does not export `scrape_jobs`):

```python
__all__ = ["scrape_jobs", "DEFAULT_SITES"]
```

- [ ] **Step 4: Run the tests**

```powershell
poetry run pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 5: Capture the "after" baseline**

```powershell
poetry run python -m jobspy.baseline.runner --output docs/baseline/2026-09-22-baseline-phase1.md
```

Compare against the Task 5 report. Expected direction:

- **Salary fill rate: up.** This is the headline number for Phase 1.
- **State match rate: up from 0%.** Any large residue of blanks is gazetteer backlog — the log line `unmatched locations - add to the gazetteer` names them.
- **Total rows: up**, because of the remote pass.
- **Exact duplicate rows: down**, because dedup now runs.

If salary fill rate did not move, stop and investigate before declaring Phase 1 done — that is the phase's entire justification.

- [ ] **Step 6: Update the README**

In the "Supported job boards" table, mark Indeed/LinkedIn/Google as the default set and note that the others must be named explicitly. In the parameters block, add `include_remote`, `group_duplicates`, and the new `dedup_group` / `remote_scope` / `city` / `state` output columns. Change `country_indeed` to note the new `"malaysia"` default.

- [ ] **Step 7: Commit**

```bash
poetry run black jobspy tests
git add jobspy/__init__.py README.md docs/baseline tests/test_scrape_jobs_integration.py
git commit -m "feat: default to MY-relevant boards and capture phase 1 baseline"
```

---

## Deferred from the spec (with reasons)

Checked against the spec section by section. Four spec items have no task here, all deliberately:

- **Fixture-based scraper tests.** The spec's second testing tier records an HTTP response per board. Phases 0–1 change no scraper parsing logic, so fixtures here would test code this plan does not touch. Build them in phase 2 alongside the JobStreet scraper, where they are genuinely load-bearing.
- **A `live`-marked test.** The marker is configured in Task 1, but the actual live check for phases 0–1 is the baseline runner (Tasks 5 and 14), which exercises all three boards end to end. A redundant `@pytest.mark.live` test would add nothing.
- **`query_language` on scraper classes and EN→BM query expansion.** `to_bm_query` ships in Task 6, but nothing calls it — every phase 0–1 board is English-dominant. The wiring belongs with Maukerja/Ricebowl in phase 3, per the spec's own phasing.
- **Playwright as an optional extra.** No phase 0–1 board needs a browser. Add the extra when the first board that requires it arrives.

## Done criteria

- `poetry run pytest` is green, and `poetry run pytest -m live` is a separate, deliberate action.
- Two baseline reports exist in `docs/baseline/` and the second shows a higher salary fill rate and a non-zero state match rate.
- `scrape_jobs()` with no `site_name` queries only Indeed, LinkedIn and Google, against `country_indeed="malaysia"`.
- A board that raises produces a logged error and a partial result, never an exception out of `scrape_jobs`.
- No row is ever removed by fuzzy grouping; `dedup_group` is populated for cross-board matches.
