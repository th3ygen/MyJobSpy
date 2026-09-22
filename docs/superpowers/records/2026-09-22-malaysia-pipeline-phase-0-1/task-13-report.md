# Task 13 Report: `include_remote` two-pass querying

## Status: DONE

## Addendum: fix for Concern 2 (non-Malaysia row doubling)

The coordinator confirmed Concern 2 below as a live regression and directed
a fix before review: `include_remote` defaults to `True` and was gating the
second pass on `include_remote and not is_remote` only — with no country
check — while the exact-dedup that absorbs the two passes' overlap only
runs inside `if country_enum == Country.MALAYSIA:`. Any caller overriding
`country_indeed` to a non-Malaysia value (e.g. `"usa"`) while leaving
`include_remote` at its default got every listing back twice, undeduped.

### Fix

Gated the second pass on the same condition that gates the pipeline, in
`C:\Users\USER\Desktop\dev\forks\MyJobSpy\jobspy\__init__.py`:

```python
    # The located pass and the remote pass overlap heavily, and the exact-dedup
    # step that absorbs that overlap only runs for Malaysia. Tie the second pass
    # to the same condition so the two can never come apart: issuing two passes
    # without the dedup behind them returns every listing twice.
    passes: list[ScraperInput] = [scraper_input]
    if include_remote and not is_remote and country_enum == Country.MALAYSIA:
        remote_input = scraper_input.model_copy(deep=True)
        remote_input.is_remote = True
        passes.append(remote_input)
```

Non-Malaysia callers now get exactly their prior single-pass behavior; no
change to Malaysia behavior (the primary, default-country case).

### Regression test added

Appended to `tests/test_scrape_jobs_integration.py`:

```python
def test_non_malaysia_country_does_not_double_rows(monkeypatch, make_job):
    passes = []

    class RecordingScraper:
        def __init__(self, **kwargs):
            pass

        def scrape(self, scraper_input):
            passes.append(scraper_input.is_remote)
            return JobResponse(jobs=[make_job(job_url="https://ok/1")])

    monkeypatch.setattr(jobspy, "Indeed", RecordingScraper, raising=False)

    df = jobspy.scrape_jobs(
        site_name=["indeed"], search_term="engineer",
        country_indeed="usa", include_remote=True, results_wanted=1,
    )

    assert passes == [False]   # only the located pass ran
    assert len(df) == 1        # and therefore no doubling
```

### Before/after evidence (the actual pin)

**Before the fix** — ran only the new test against the pre-fix code:

```
$poetry run pytest tests/test_scrape_jobs_integration.py::test_non_malaysia_country_does_not_double_rows -v
```

```
>       assert passes == [False]  # only the located pass ran
E       assert [False, True] == [False]
E       Left contains one more item: True
1 failed in 0.11s
```

Confirms the regression exactly as predicted: both passes ran (`is_remote`
`False` then `True`) for a non-Malaysia country.

**After the fix** — same command:

```
$poetry run pytest tests/test_scrape_jobs_integration.py::test_non_malaysia_country_does_not_double_rows -v
```

```
tests/test_scrape_jobs_integration.py::test_non_malaysia_country_does_not_double_rows PASSED
1 passed in 0.01s
```

**Full integration file** (confirms the three earlier two-pass tests, which
use the default `country_indeed="malaysia"`, are unaffected):

```
$poetry run pytest tests/test_scrape_jobs_integration.py -v
```

```
10 passed in 0.05s
```
(all of: test_country_indeed_defaults_to_malaysia, test_group_duplicates_parameter_exists,
test_one_failing_board_does_not_kill_the_run, test_pipeline_populates_state_column,
test_pipeline_is_skipped_for_non_malaysia_country, test_pipeline_runs_for_malaysia,
test_include_remote_runs_a_second_pass, test_include_remote_false_runs_one_pass,
test_remote_pass_is_skipped_when_is_remote_already_set, test_non_malaysia_country_does_not_double_rows)

**Full suite:**

```
$poetry run pytest tests/ -v
```

```
175 passed in 0.20s
```

Zero warnings. `black --check --diff jobspy/__init__.py tests/test_scrape_jobs_integration.py`
reported both files already correctly formatted (no reformatting needed after
the Edit-tool changes).

### Commits

- `0fd1913` feat: add include_remote two-pass querying (original implementation)
- `2037a96` fix: gate the include_remote second pass on Malaysia (this fix)

Concern 1 (accepted, no action) stands as originally reported below.
Concern 2 is now resolved by this addendum, not merely flagged.

---

## Original report (Concern 2 below is now fixed — see addendum above)

## Summary

Added `include_remote: bool = True` to `scrape_jobs`. When enabled and the
caller has not already set `is_remote=True`, a second `ScraperInput` pass
(deep-copied via `model_copy(deep=True)`, with `is_remote` flipped to `True`)
is queued alongside the original "located" pass for every site. Both passes
run through the existing `ThreadPoolExecutor`, and their `JobResponse.jobs`
are accumulated (not overwritten) per site via `dict.setdefault(...).extend(...)`.
The heavy overlap between the two passes is absorbed downstream by the
Malaysia pipeline's unconditional exact-dedup (`dedupe_exact`, keyed on
`job_url`, in `jobspy/malaysia/__init__.py::normalize`), which was already
built to run regardless of `group_duplicates`.

## Files changed

- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\jobspy\__init__.py`
- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\tests\test_scrape_jobs_integration.py`

## TDD evidence

**RED** — appended the brief's three new tests, then ran:

```
$poetry run pytest tests/test_scrape_jobs_integration.py -v
```

Result: `test_include_remote_runs_a_second_pass` FAILED, the other two new
tests passed vacuously (nothing yet reads `include_remote`, so `scrape_jobs`'s
existing `**kwargs` silently swallows it and always runs one pass with
`is_remote=False`):

```
>       assert sorted(seen_is_remote) == [False, True]
E       assert [False] == [False, True]
1 failed, 8 passed in 0.15s
```

This failed for the expected reason (only one pass ran, `is_remote` never
flipped to `True`), though the literal failure text differs from the brief's
prediction ("unexpected keyword argument"): because `scrape_jobs` declares
`**kwargs`, an unknown keyword doesn't raise `TypeError` — it's absorbed
silently. The functional gap (no second pass) is identical either way.

**GREEN** — after adding the `include_remote` parameter and rewriting
`scrape_site` / the executor block per the brief:

```
$poetry run pytest tests/ -v
```

First result: 173 passed, 1 failed —
`tests/test_scrape_jobs_integration.py::test_pipeline_runs_for_malaysia`
(pre-existing test, not one of the brief's three). See "Conflict found and
resolved" below. After fixing that test:

```
$poetry run pytest tests/ -q
...
174 passed in 0.19s
```

Zero warnings in either run.

## Conflict found and resolved

`test_pipeline_runs_for_malaysia` (written in an earlier task, before
`include_remote` existed) replaces `malaysia_normalize` with a passthrough
spy that does **not** perform the real exact-dedup, then asserts the spy is
called with exactly 1 job. Its `OkScraper` ignores `scraper_input.is_remote`
and always returns a job with the same `job_url`. With `include_remote`
defaulting to `True` (mandated by this task) and `is_remote` defaulting to
`False`, `OkScraper` now legitimately runs twice (located pass + remote
pass), so the spy — which bypasses the real dedup that's supposed to absorb
that overlap — observed 2 raw jobs instead of 1. This is not a defect in the
implementation; it's the intended two-pass behavior colliding with a test
double that stands in for the very step meant to absorb it.

Resolution: added `include_remote=False` to that test's `scrape_jobs` call,
with an inline comment explaining why. This preserves the test's original
intent (verify the Malaysia pipeline runs at all) and its original
assertion (`calls == [1]`) without touching production code, since the test
was never meant to exercise two-pass unioning — the three new tests in this
task cover that. I judged this to be a stale-test-assumption fix within
scope (the region I was asked to pay particular attention to), not a "bend
the test to hide a bug" move — verified by tracing the exact accumulation
path and confirming no doubled row ever reaches a live caller (see
Correctness below).

## Self-review

- **Completeness**: `include_remote` parameter added, defaults `True`. Two
  passes are queued (`passes: list[ScraperInput]`) and both run through the
  same executor. Second pass is skipped via `if include_remote and not
  is_remote` — matches the brief's condition exactly.
- **Regression / board-failure guard**: verified present in the rewritten
  executor block — `future.result()` is still inside `try/except Exception`,
  logs at ERROR (`create_logger(...).error(...)`), records an empty
  `JobResponse` via `site_to_jobs_dict.setdefault(site.value, JobResponse(jobs=[]))`,
  and `continue`s the loop rather than propagating. Confirmed still working:
  `test_one_failing_board_does_not_kill_the_run` passes.
- **Regression / site vs site_value naming split**: verified intact. The
  executor loop keeps the `Site` enum in a variable named `site` throughout
  (`future_to_site[future]` yields the enum; `site.value.capitalize()` is
  used for logging on the failure path). The string key is `site_value`,
  returned from `scrape_site()` and used only for `site_to_jobs_dict`
  indexing. `scrape_site`'s internal local previously named `site_name`
  (shadowing the outer function parameter `site_name`) is now `site_display`
  per the brief — the exact collision the brief was renaming away from is
  not reintroduced.
- **Correctness — union and dedup trace**: for Malaysia-country runs (the
  default and primary use case for this fork), when both passes return the
  same listing, `site_to_jobs_dict[site_value].jobs` ends up with both
  copies (via `.extend`), `all_jobs` flattens to include both, and
  `malaysia_normalize`'s unconditional `dedupe_exact` (keyed on `job_url`)
  collapses them back to one before `build_jobs_dataframe` runs — confirmed
  empirically: `test_include_remote_runs_a_second_pass` uses *different*
  URLs per pass (`/onsite` vs `/remote`) and correctly sees 2 rows;
  `test_one_failing_board_does_not_kill_the_run` and
  `test_pipeline_populates_state_column` use the *same* URL across
  (implicit) passes and correctly collapse to 1 row via real dedup.
- **Discipline**: no changes under `jobspy/malaysia/`. No test hits the
  network — all scrapers are monkeypatched recording fakes per the brief.
  Black run only on the two changed files (`jobspy/__init__.py`,
  `tests/test_scrape_jobs_integration.py`), not the whole tree.
- **Testing**: 174 passed, 0 warnings, pristine output.

## Concern (not fixed, flagged for visibility)

Exact-dedup only runs inside the `if country_enum == Country.MALAYSIA:`
branch. For a caller who overrides `country_indeed` to a non-Malaysia value
(e.g. `"usa"`, as in `test_pipeline_is_skipped_for_non_malaysia_country`)
and leaves `include_remote` at its default `True`, the two passes' overlap
is **not** deduped anywhere — a job returned by both the located and remote
pass would appear as two identical rows in the final DataFrame. This is
consistent with the brief's own framing ("exact dedup in the *Malaysia*
pipeline absorbs the duplicates") and this fork's stated purpose (Malaysian
job seeker, `country_indeed` already defaults to `"malaysia"`), so I judged
it out of scope for a task whose file list is limited to `jobspy/__init__.py`
and the integration test — restructuring where dedup gating lives is a
bigger architectural change than this task describes. Flagging it in case
the plan wants non-Malaysia callers protected too in a later task.

## Test run commands for reviewer

```powershell
$poetry = "$env:APPDATA\Python\Python312\Scripts\poetry.exe"
& $poetry run pytest tests/ -v
```

## Addendum 2: Important finding — non-Malaysia no-op was invisible to callers

Task 13 review approved the country-gate fix (Addendum 1) but raised one
Important finding against the fix instruction itself: gating the second
pass on `country_enum == Country.MALAYSIA` correctly stopped the row
doubling, but it also made `include_remote` — a public, default-`True`
parameter — silently do nothing for any non-Malaysia `country_indeed`, with
no docstring note and no observable signal. Fixed on both axes as directed.

### 1. Documented

Added a `:param include_remote:` entry to `scrape_jobs`'s docstring in
`C:\Users\USER\Desktop\dev\forks\MyJobSpy\jobspy\__init__.py`, stating the
Malaysia-only scope and that it degrades to a no-op (not doubled rows) for
other countries.

### 2. Logged, only on the surprising combination

Added a module-level logger `log = create_logger("ScrapeJobs")` (mirrors
the `log = create_logger("X")` pattern used in every other `jobspy/*`
submodule). Restructured the pass-building block so the `else` arm — taken
only when `include_remote and not is_remote` is true and the country is
*not* Malaysia — emits one INFO line naming the ignored parameter and the
offending `country_indeed` value, with actionable guidance
(`include_remote=False` to silence it). The `is_remote=True` case (a
caller's deliberate single pass) and the Malaysia case never reach this
branch at all, so they can never log it; `include_remote=False` short-circuits
the outer `if` entirely.

### 3. Regression tests added (4)

Appended to `tests/test_scrape_jobs_integration.py`:
- `test_include_remote_noop_is_logged_for_non_malaysia` — fires for the
  surprising combination (`country_indeed="usa"`, `include_remote=True`,
  `is_remote` default `False`).
- `test_include_remote_noop_is_not_logged_for_malaysia` — silent for a
  Malaysia run (the parameter works as intended there).
- `test_include_remote_noop_is_not_logged_when_include_remote_false` —
  silent when the caller explicitly opted out.
- `test_include_remote_noop_is_not_logged_when_is_remote_already_set` —
  silent when `is_remote=True` was the caller's deliberate choice, even
  for a non-Malaysia country.

All four follow the `caplog` + re-enabled `propagate` pattern from
`tests/malaysia/test_pipeline.py::test_normalizer_failures_are_counted_and_reported`
(`create_logger` sets `propagate=False`, so `caplog` sees nothing unless a
test flips it back for its duration).

### A real trap found along the way, and how it was resolved

The first run of the new "fires" test failed even though the log line was
correctly in place:

```
$poetry run pytest tests/test_scrape_jobs_integration.py -v -k "noop"
```

```
assert any("include_remote=True has no effect" in m for m in messages)
E       assert False
```

Root cause: `scrape_jobs` calls `set_logger_level(verbose)` on every
invocation, and `verbose` defaults to `0`, which maps to `ERROR` and
resets **every** `JobSpy:*` logger's level — including the brand-new
`JobSpy:ScrapeJobs` — before the pass-building block runs. `logger.info()`
checks `isEnabledFor(INFO)` and short-circuits before a record is even
created, so `caplog`'s pre-set level (`caplog.set_level(logging.INFO, ...)`)
was silently overwritten. Confirmed by a standalone script
(`level: 40` = `ERROR` after calling `scrape_jobs` with default `verbose`).
This is existing, intentional project behavior — every other INFO log in
this file (e.g. "finished scraping") is equally invisible under the
default verbosity — so the fix was to pass `verbose=2` explicitly in all
four new tests, matching what a real caller must do to see any INFO-level
JobSpy log, not to change the logging default.

### RED/GREEN evidence for the "fires" test

To rule out the test passing for the wrong reason, the `log.info(...)` call
was temporarily replaced with `pass` and the four tests re-run:

```
$poetry run pytest tests/test_scrape_jobs_integration.py -v -k "noop"
```

```
tests/test_scrape_jobs_integration.py::test_include_remote_noop_is_logged_for_non_malaysia FAILED
tests/test_scrape_jobs_integration.py::test_include_remote_noop_is_not_logged_for_malaysia PASSED
tests/test_scrape_jobs_integration.py::test_include_remote_noop_is_not_logged_when_include_remote_false PASSED
tests/test_scrape_jobs_integration.py::test_include_remote_noop_is_not_logged_when_is_remote_already_set PASSED
1 failed, 3 passed
```

Only the positive assertion failed, exactly as expected (the three negative
assertions are vacuously satisfied whether or not the log line exists, so
seeing them stay green while the positive one alone breaks is the evidence
that the positive test is actually pinning the log line, not passing by
accident). The `log.info(...)` call was then restored verbatim (diffed
byte-for-byte against a pre-edit backup to confirm no other change leaked
in) and all four passed again:

```
$poetry run pytest tests/test_scrape_jobs_integration.py -v -k "noop"
```

```
4 passed in 0.04s
```

### Confirmation the log does NOT fire on the two non-surprising paths

Both explicitly covered by dedicated tests and passing:
- `include_remote=False` (explicit opt-out), non-Malaysia country: silent
  (`test_include_remote_noop_is_not_logged_when_include_remote_false`).
- `is_remote=True` (caller's deliberate single pass), non-Malaysia country:
  silent (`test_include_remote_noop_is_not_logged_when_is_remote_already_set`).

And, per the coordinator's explicit ask, silent for a Malaysia run too
(`test_include_remote_noop_is_not_logged_for_malaysia`), where the
parameter is not a no-op at all.

### Full verification

```
$poetry run pytest tests/test_scrape_jobs_integration.py -v
```
```
14 passed in 0.07s
```

```
$poetry run pytest tests/ -q
```
```
179 passed in 0.21s
```

Zero warnings in either run. `black jobspy/__init__.py tests/test_scrape_jobs_integration.py`
reported both files already correctly formatted — no reformatting needed.

### Commit

- `8ee66ea` fix: document and log the include_remote non-Malaysia no-op

### Status

DONE. The two Minors from the review (jobs_to_run cross-product concurrency
at current scale, and the pinned-test comment length) were explicitly out
of scope per the coordinator's instruction and were not touched.
