# Task 5: Baseline Runner — Implementation Report

## Summary

Successfully implemented the baseline harness runner that executes a fixed set of Malaysian job searches and generates markdown reports. The runner is designed for measurement comparability across runs by using a fixed search set (SEARCHES constant). All three test cases pass, and the test suite maintains 21 passing tests with zero warnings.

**Step 5 (live baseline capture) was skipped per instruction** — the controller will execute that step as it requires multi-minute live network calls and is a stop condition for the project phase.

## Implementation Details

### Files Created

1. **jobspy/baseline/runner.py** (87 lines)
   - `SEARCHES: list[dict]` — Fixed set of 4 Malaysian job searches for KL, Selangor, Penang, and Malaysia-wide remote
   - `run_baseline(output_path: Path, *, scrape=scrape_jobs) -> Path` — Main runner function
   - `main()` — CLI entry point with `--output` argument
   - Per-search error handling: exceptions are logged and skipped, not fatal
   - Uses `compute_metrics()` and `render_report()` from Task 4
   - Uses `create_logger()` from `jobspy.util`

2. **tests/test_baseline_runner.py** (40 lines)
   - Three test functions with injectable `scrape` parameter
   - Tests verify: searches are Malaysian, runner writes reports, graceful failure handling

3. **docs/baseline/.gitkeep**
   - Directory placeholder for baseline output (used by Step 5 and controller)

### Design Decisions

- **SEARCHES immutability**: The searches are intentionally hard-coded as a fixed set to ensure comparability across runs. The comment in the code warns against casual changes.
- **Error handling**: The `try/except` in the search loop catches all exceptions and logs them as warnings, allowing partial results when one search or board fails.
- **Test injection**: Tests use a fake `scrape` function to avoid network calls; the real `scrape_jobs` is the default parameter.
- **Empty DataFrame handling**: Runner safely handles searches that return None or empty results via `pd.concat()` with `ignore_index=True`.

## TDD Evidence

### Step 1: Failing Test (RED)

```bash
$ poetry run pytest tests/test_baseline_runner.py -v
```

**Result**: FAILED with `ModuleNotFoundError: No module named 'jobspy.baseline.runner'`

```
ERROR collecting tests/test_baseline_runner.py
Hint: make sure your test modules/packages have valid Python names.
Traceback:
...
tests\test_baseline_runner.py:5: in <module>
    from jobspy.baseline.runner import SEARCHES, run_baseline
E   ModuleNotFoundError: No module named 'jobspy.baseline.runner'
=========================== Interrupted: 1 error during collection ===========================
```

**Expected failure**: Module doesn't exist yet. ✓

### Step 4: Implementation Tests (GREEN)

```bash
$ poetry run pytest tests/test_baseline_runner.py -v
```

**Result**: PASSED (3/3 tests)

```
tests/test_baseline_runner.py::test_searches_are_malaysian PASSED        [ 33%]
tests/test_baseline_runner.py::test_run_baseline_writes_a_report PASSED  [ 66%]
tests/test_baseline_runner.py::test_run_baseline_survives_a_failing_search PASSED [100%]

============================== 3 passed in 0.04s ==============================
```

### Full Suite Verification (POST-COMMIT)

```bash
$ poetry run pytest tests/ -v
```

**Result**: 21 PASSED (18 existing + 3 new), 0 warnings

```
tests/test_baseline_metrics.py::test_counts_rows_per_site PASSED         [  4%]
tests/test_baseline_metrics.py::test_salary_fill_rate PASSED             [  9%]
tests/test_baseline_metrics.py::test_counts_exact_duplicate_urls PASSED  [ 14%]
tests/test_baseline_metrics.py::test_top_locations_are_ranked PASSED     [ 19%]
tests/test_baseline_metrics.py::test_state_match_rate_is_zero_when_unpopulated PASSED [ 23%]
tests/test_baseline_metrics.py::test_empty_frame_is_safe PASSED          [ 28%]
tests/test_baseline_metrics.py::test_render_report_contains_headline_numbers PASSED [ 33%]
tests/test_baseline_runner.py::test_searches_are_malaysian PASSED        [ 38%]
tests/test_baseline_runner.py::test_run_baseline_writes_a_report PASSED  [ 42%]
tests/test_baseline_runner.py::test_run_baseline_survives_a_failing_search PASSED [ 47%]
tests/test_frame.py::test_builds_one_row_per_job PASSED                  [ 52%]
... [11 more tests] ...

============================== 21 passed in 0.11s ==============================
```

## Code Quality Verification

### Black Formatting

Applied Black formatter to changed files only (per project guidelines):

```bash
$ poetry run black jobspy/baseline/runner.py tests/test_baseline_runner.py
```

Result: `jobspy/baseline/runner.py` reformatted (line wrapping for `render_report()` call), `tests/test_baseline_runner.py` unchanged.

All tests pass after Black formatting.

### Commit

```
Commit: c6e8f19
Message: feat: add baseline harness runner and test infrastructure

Implement run_baseline function that executes a fixed set of Malaysian
job searches and generates a markdown report. Includes 4 fixed searches
for comparability across runs, per-search error handling, and test suite
with fake scraper injection.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

## Self-Review Findings

✅ **Completeness**
- All 3 tests present and passing
- SEARCHES constant contains exactly 4 searches (≥3 required), all with `country_indeed: "malaysia"`
- All searches have required `search_term` field
- docs/baseline/.gitkeep created
- No network calls in tests (fake scraper used)

✅ **Accuracy**
- Code transcribed verbatim from brief
- Per-search try/except with logging is present and load-bearing
- Error handling allows one bad board to be skipped: `except Exception as exc: ... continue`
- Empty frame handling correct: `pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()`

✅ **Discipline**
- No overbuilding (only runner module and tests as specified)
- Step 5 (live baseline) properly skipped per instruction
- No imports beyond what's needed
- No modifications to Task 4 code

✅ **Testing**
- Test output pristine: 21 passed, 0 warnings
- Test suite grew from 18 to 21 (3 new runner tests)
- All tests isolated: use fixture tmp_path, inject fake scraper
- Tests verify the three critical behaviors:
  1. Searches are configured for Malaysia
  2. Report is written with correct title and content
  3. Graceful failure when a search raises an exception

## Concerns

None. The implementation is complete, tested, and ready. The controller will execute Step 5 (live baseline capture) in a separate phase.

## What Was NOT Done (Per Instruction)

- **Step 5: Live Baseline Capture** — Skipped per task instructions
  - This step requires `poetry run python -m jobspy.baseline.runner` to hit real job boards
  - Takes several minutes of live network I/O
  - Controller will execute this as a stop condition for Phase 0.1
  - No output file was created by this step (infrastructure in place for controller to do so)

## Files Changed

- **Created**: jobspy/baseline/runner.py (87 lines)
- **Created**: tests/test_baseline_runner.py (40 lines)
- **Created**: docs/baseline/.gitkeep (empty, directory marker)
- **Total**: 130 lines of new code and tests

All changes conform to Python 3.10+, Black line-length 88, and project patterns.
