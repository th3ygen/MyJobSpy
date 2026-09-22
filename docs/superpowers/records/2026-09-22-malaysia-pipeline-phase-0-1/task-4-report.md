# Task 4: Baseline Metrics — Report

## Implementation Summary

Successfully implemented a measurement harness for Malaysian job search baseline metrics. The implementation consists of pure functions over a pandas DataFrame with no network or scraping dependencies.

### Files Created

1. **jobspy/baseline/__init__.py** — Module docstring: "Measurement harness for Malaysian job searches."

2. **jobspy/baseline/metrics.py** — Core implementation containing:
   - `BaselineMetrics` dataclass with 10 fields capturing all metrics
   - `_fill_rate(df, column)` helper for robust null/column handling
   - `compute_metrics(df, *, top_n=25)` main function
   - `render_report(metrics, *, title)` markdown renderer

3. **tests/test_baseline_metrics.py** — 7 comprehensive test cases covering:
   - Row counts and site distribution
   - Salary fill rate calculation
   - Duplicate URL detection
   - Location ranking
   - State match rate edge cases (empty column)
   - Empty frame safety
   - Report markdown generation

### Key Features

- **Defensive implementation**: Handles missing columns and empty DataFrames gracefully
- **Rounding**: Fill rates rounded to 4 decimal places (via `_fill_rate` helper)
- **Location seeds**: `top_locations` uses Counter to rank raw location strings for gazetteer seeding (Task 7)
- **Markdown output**: Table-based report with sections for metrics, sites, remote_scope distribution, and top locations

## TDD Evidence

### RED Phase (Tests Fail Before Implementation)
```
$ poetry run pytest tests/test_baseline_metrics.py -v
ERROR collecting tests/test_baseline_metrics.py
ModuleNotFoundError: No module named 'jobspy.baseline'
```
**Expected failure reason**: Module didn't exist yet.

### GREEN Phase (Tests Pass After Implementation)
```
$ poetry run pytest tests/test_baseline_metrics.py -v
tests/test_baseline_metrics.py::test_counts_rows_per_site PASSED         [ 14%]
tests/test_baseline_metrics.py::test_salary_fill_rate PASSED             [ 28%]
tests/test_baseline_metrics.py::test_counts_exact_duplicate_urls PASSED  [ 42%]
tests/test_baseline_metrics.py::test_top_locations_are_ranked PASSED     [ 57%]
tests/test_baseline_metrics.py::test_state_match_rate_is_zero_when_unpopulated PASSED [ 71%]
tests/test_baseline_metrics.py::test_empty_frame_is_safe PASSED          [ 85%]
tests/test_baseline_metrics.py::test_render_report_contains_headline_numbers PASSED [100%]

============================== 7 passed in 0.02s ==============================
```

### Full Suite Verification
```
$ poetry run pytest tests/ -v
============================== 18 passed in 0.07s ==============================
```
✓ All 7 new tests + 11 existing tests pass (zero warnings)

## Compliance Checklist

- [x] All 7 tests present and passing
- [x] Test renamed per Ruling F2: `test_state_match_rate_is_none_when_unpopulated` → `test_state_match_rate_is_zero_when_unpopulated`
- [x] Both source files created in correct locations
- [x] Code transcribed accurately from brief (no dropped guards, all column checks present)
- [x] Handles missing columns (`if column not in df.columns`)
- [x] Handles empty DataFrames (`if df is None or df.empty`)
- [x] YAGNI discipline — only what was requested, no overbuilding
- [x] Black formatting applied (88 character line length)
- [x] Test output pristine — zero warnings
- [x] Full test suite passes (18/18)
- [x] Committed with proper message

## Self-Review Findings

### Correctness
- ✓ `_fill_rate` correctly returns 0.0 for missing columns or empty DataFrames
- ✓ `compute_metrics` safely handles partial DataFrames (columns may be absent)
- ✓ `rows_per_site` uses `value_counts()` for correct counting
- ✓ `exact_duplicate_rows` counts duplicated URLs across all sites (correct behavior)
- ✓ `company_title_duplicates` uses subset parameter correctly
- ✓ `remote_rate` converts to bool and uses `.fillna(False)` for safety
- ✓ `remote_scope_counts` preserves `None` values via `dropna=False`
- ✓ `top_locations` uses Counter for frequency ranking (correct order)
- ✓ `render_report` formats all metrics with correct column order

### Quality
- ✓ Black formatting applied — lines properly split at 88 chars
- ✓ Imports organized (`from __future__` first, then stdlib, then third-party)
- ✓ Type hints present (dataclass fields and function signatures)
- ✓ Docstrings present on key functions
- ✓ No unnecessary complexity — straightforward DataFrame operations
- ✓ Column existence guards use appropriate idioms (`in df.columns`, `issubset`)

### Testing
- ✓ Tests exercise happy paths (counted rows, fill rates)
- ✓ Tests exercise edge cases (empty frame, unpopulated columns)
- ✓ Tests verify markdown output format
- ✓ All assertions match expected behavior from brief
- ✓ `_frame` helper provides consistent test DataFrame

### Architecture
- ✓ Pure functions (no side effects, no network)
- ✓ Correct contract from brief: `compute_metrics(df) -> BaselineMetrics`
- ✓ Markdown renderer as separate function (composable)
- ✓ Module organization follows project structure

## No Concerns

All requirements met. All tests passing. Code is defensive, readable, and properly formatted.

---

**Commit:** `581f22b` — feat: add baseline metrics computation and markdown report

**Test Results:** 18 passed (7 new + 11 existing), 0.07s, zero warnings

**Files Changed:**
- `jobspy/baseline/__init__.py` (created)
- `jobspy/baseline/metrics.py` (created)
- `tests/test_baseline_metrics.py` (created)
