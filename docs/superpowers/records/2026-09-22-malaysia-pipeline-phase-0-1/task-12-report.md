# Task 12 Report: Wire the pipeline into `scrape_jobs` and fix the fatal-board bug

## Summary

Implemented all three changes from the brief in `jobspy/__init__.py`:

1. `country_indeed` default flipped from `"usa"` to `"malaysia"`.
2. New `group_duplicates: bool = True` parameter added after `enforce_annual_salary`.
3. `future.result()` is now guarded per-site: a raising board is caught, logged at ERROR,
   recorded as an empty `JobResponse`, and the run continues with the other boards' results.
4. `SCRAPER_MAPPING` now reads scraper classes via `globals()[...]` so
   `monkeypatch.setattr(jobspy, "Indeed", Fake)` takes effect (required for the test to work
   without hitting the network).
5. When `country_enum == Country.MALAYSIA`, all scraped jobs are flattened, run through
   `jobspy.malaysia.normalize(all_jobs, group_duplicates=group_duplicates)`, and regrouped back
   by originating site before being handed to `build_jobs_dataframe`.

## Files changed

- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\jobspy\__init__.py`
- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\tests\test_scrape_jobs_integration.py` (new)

No changes to `jobspy/malaysia/` or `jobspy/frame.py`.

## TDD evidence

**RED** — wrote the brief's test file verbatim, ran:

```
$poetry = "$env:APPDATA\Python\Python312\Scripts\poetry.exe"
& $poetry run pytest tests/test_scrape_jobs_integration.py -v
```

Result: 4 failed, all for the expected reasons:
- `test_country_indeed_defaults_to_malaysia`: `AssertionError: assert 'usa' == 'malaysia'`
- `test_group_duplicates_parameter_exists`: `KeyError: 'group_duplicates'`
- `test_one_failing_board_does_not_kill_the_run`: `RuntimeError: board is on fire` propagated
  out of `future.result()` in `jobspy/__init__.py:125`, killing the whole `scrape_jobs` call.
- `test_pipeline_populates_state_column`: `AssertionError: assert None == 'Selangor'` (pipeline
  not wired, so `state` was never populated for a Cyberjaya listing).

**GREEN** — after implementing (signature changes, globals()-based `SCRAPER_MAPPING`, guarded
executor loop, Malaysia regrouping block, `from jobspy.malaysia import normalize as
malaysia_normalize` import):

```
& $poetry run pytest tests/test_scrape_jobs_integration.py -v
```
→ `4 passed in 0.02s`

Full suite:
```
& $poetry run pytest tests/ -v
```
→ `163 passed in 0.16s` (159 pre-existing + 4 new), zero warnings.

Ran again after Black formatting to confirm still pristine: `163 passed in 0.16s`.

## Black

Ran `poetry run black jobspy/__init__.py tests/test_scrape_jobs_integration.py` only (never
`black jobspy tests`, per the constraint). `jobspy/__init__.py` was already compliant with no
diff; the test file had one line wrapped (the `scrape_jobs(...)` call in
`test_pipeline_populates_state_column`) to fit line-length 88.

## Object-identity mapping — verified, then hardened anyway

Verified by reading `jobspy/malaysia/grouping.py`:

- `dedupe_exact` builds a `dict[str, JobPost]` of `best` and returns `[best[key] for key in
  order]` — it only ever selects among the **original** `JobPost` objects passed in, never
  copies or reconstructs one.
- `assign_groups` only mutates `job.dedup_group` in place on the objects it's given and returns
  the same list object unchanged in composition.

So `normalize()` today always returns the exact same `JobPost` objects (same `id()`) it was
given, in a possibly-shorter list (exact dedup can drop entries) and possibly reordered
(grouping sorts within company blocks). The brief's `site_by_job[id(job)]` identity lookup is
therefore safe today.

However, per the task's explicit invitation to consider fragility, I did not leave the lookup as
a raising `dict[...]` access. I changed it to `site_by_job.get(id(job))` with a fallback: if a
job's origin site is ever not found (i.e., the identity contract breaks in a future edit to
`jobspy/malaysia/`), the job is logged at WARNING via `create_logger("Malaysia")` and placed into
an `"unknown"` bucket in `regrouped` rather than raising `KeyError` and killing the whole scrape.
This directly serves the task's stated purpose (one bad thing must not kill the whole run) and
costs nothing when the identity assumption holds, which today it does. No job is ever silently
dropped — every job flows into `regrouped` and out through `build_jobs_dataframe`, just possibly
under an `"unknown"` site label instead of its real origin.

## Self-review

- **Completeness:** default flipped, `group_duplicates` parameter added, `future.result()`
  guarded, Malaysia pipeline wired into the return path. All confirmed by passing tests.
- **Correctness:**
  - Raising board: `test_one_failing_board_does_not_kill_the_run` confirms LinkedIn's
    `RuntimeError` is caught, LinkedIn is recorded as `JobResponse(jobs=[])`, and Indeed's single
    job still comes through (`len(df) == 1`, `site == "indeed"`).
  - USA path unchanged: `tests/test_frame.py::test_usa_extracts_salary_from_description_when_no_compensation`
    still passes; the Malaysia regrouping block is gated behind `if country_enum ==
    Country.MALAYSIA` and is a no-op otherwise, so `extract_salary` for USA is untouched.
  - Identity mapping: verified safe today (see above), hardened with a non-raising fallback for
    the future.
- **Discipline:** no edits to `jobspy/malaysia/` or `jobspy/frame.py`. No test reaches the
  network — both new scraper fakes (`OkScraper`, `BrokenScraper`) are pure Python classes
  monkeypatched onto `jobspy.Indeed`/`jobspy.LinkedIn`; `scrape_jobs` never imports a real network
  client for those sites in the test run since `globals()["Indeed"]` now resolves to the
  monkeypatched fake at call time.
- **Testing:** `163 passed`, zero warnings, confirmed both before and after Black formatting.

## Concerns

None blocking. One minor style note for future readers: the executor loop reuses the local name
`site` for a `Site` enum, while the Malaysia regrouping block below it reuses `site` again for a
string site-value key — they're in disjoint scopes timewise (sequential, not nested) so there's
no bug, but a future editor extending either block should watch for the shadowing. Left as-is
since it mirrors the brief's own code shape and Task 13 is expected to rewrite this region anyway
per the task note.

## Commit

`d6d70dc` — `feat: run the Malaysia pipeline in scrape_jobs and survive board failures`

---

## Fix report (post-review)

Review came back **Approved** with one Important finding and one Minor promoted to must-fix
before Task 13. Both addressed.

### 1. Important: no test proved the non-Malaysia gate actually skips the pipeline

The original suite only exercised the "pipeline runs for Malaysia" path indirectly (via
`test_pipeline_populates_state_column`, which never asserted the pipeline was the *cause* of the
`state` column). An implementation that always ran `normalize()` regardless of country would have
passed the whole suite. Added two new tests to `tests/test_scrape_jobs_integration.py`, both using
a `spy` monkeypatched onto `jobspy.malaysia_normalize` (this works because `scrape_jobs` calls the
module-level name `malaysia_normalize` at call time, so patching `jobspy.malaysia_normalize`
redirects it):

- `test_pipeline_is_skipped_for_non_malaysia_country` — scrapes one job with `country_indeed="usa"`,
  asserts `calls == []`.
- `test_pipeline_runs_for_malaysia` — same scraper setup with `country_indeed="malaysia"`,
  asserts `calls == [1]`.

**Meaningfulness check (as requested):** temporarily replaced `if country_enum ==
Country.MALAYSIA:` with `if True:` in `jobspy/__init__.py` and reran just the skip test:

```
$poetry = "$env:APPDATA\Python\Python312\Scripts\poetry.exe"
& $poetry run pytest tests/test_scrape_jobs_integration.py::test_pipeline_is_skipped_for_non_malaysia_country -v
```

Result: **FAILED** — `assert [1] == []` (`Left contains one more item: 1`). This confirms the
test actually depends on the gate being present and would catch a regression where the pipeline
runs unconditionally. Reverted the temporary change immediately after (via `git checkout --
jobspy/__init__.py`, then reapplied the rename fix below, since the checkout also reverted that
uncommitted edit — confirmed via `git diff` that the final diff contained only the intended
rename, no leftover `if True:`).

### 2. Rename shadowed `site` variable ahead of Task 13

Renamed the string site-key variable in the Malaysia regrouping block (both the `site_by_job`
dict comprehension and the `regrouped` loop) from `site` to `site_value`, so it's textually
distinct from the `Site` enum `site` used earlier in the executor's `for future in
as_completed(...)` loop. No behavior change — purely a rename for clarity, confirmed by diff
review before committing.

### Test evidence (post-fix)

```
& $poetry run pytest tests/test_scrape_jobs_integration.py -v
```
→ `6 passed in 0.03s` (4 original + 2 new).

```
& $poetry run pytest tests/ -q
```
→ `171 passed in 0.17s`, zero warnings. (Baseline had grown to 165 expected-plus-new by this
point because commit `5584e43` — `fix(malaysia): block grouping across trailing job-level
suffixes`, unrelated to this task — landed on the branch between my two commits and added its own
tests; confirmed via `git log` that this is a legitimate sibling commit, not an artifact of my
own changes.)

### Black

Ran `poetry run black jobspy/__init__.py tests/test_scrape_jobs_integration.py` only. Output:
"2 files left unchanged" — both were already compliant after manual editing.

### Files changed (this fix)

- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\jobspy\__init__.py` (rename only)
- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\tests\test_scrape_jobs_integration.py` (2 new tests)

### Commit

`c3c0882` — `fix(review): pin the Malaysia gate both ways, rename shadowed site var`

### Deferred (per coordinator instruction, not actioned)

- Failure-path logger naming inconsistency (`JobSpy:Linkedin` vs `JobSpy:LinkedIn`).
- Missing exception type / `exc_info` in the per-board ERROR log.
- The `"unknown"`-bucket fallback path itself remains untested.
