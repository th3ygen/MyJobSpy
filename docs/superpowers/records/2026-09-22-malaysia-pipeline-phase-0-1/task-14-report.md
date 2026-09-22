# Task 14 Report: Quarantine non-MY boards, fix `__all__`, update README

Scope covered: Steps 1-4, 6, 7. **Step 5 (live "after" baseline capture) was deliberately skipped**, per the controller's instruction — that step requires multi-minute live network calls and its interpretation gates what gets reported to the user, which is the controller's job, not mine.

## What was implemented

### `jobspy/__init__.py`
- Added `DEFAULT_SITES: list[Site] = [Site.INDEED, Site.LINKEDIN, Site.GOOGLE]` right after the imports/logger setup, with the comment specified in the brief.
- Changed `get_site_type()`'s no-argument branch from `list(Site)` to `list(DEFAULT_SITES)`, so a bare `scrape_jobs()` (no `site_name`) now queries only Indeed, LinkedIn, and Google. Explicit `site_name` (str, `Site`, or list) is untouched — quarantined boards still resolve via `map_str_to_site` exactly as before.
- Replaced the stale `__all__ = ["BDJobs"]` (leftover from an upstream PR, which meant `from jobspy import *` didn't even export `scrape_jobs`) with `__all__ = ["scrape_jobs", "DEFAULT_SITES"]`.

### `tests/test_scrape_jobs_integration.py`
Appended the two tests specified in the brief's Step 1, verbatim:
- `test_default_sites_are_malaysia_relevant` — asserts `{site.value for site in DEFAULT_SITES} == {"indeed", "linkedin", "google"}`.
- `test_unsupported_board_still_works_when_named_explicitly` — monkeypatches `BaytScraper` and calls `scrape_jobs(site_name=["bayt"], ...)`, asserting the quarantined board still produces results when named explicitly.

Ran `poetry run black` on both changed files (only these two, not the whole tree, per constraint); Black reformatted one long line in the new Bayt test into a multi-line call.

### `README.md`
- **Features**: noted the five non-MY boards are quarantined out of the default set but still work by name.
- **Supported job boards table**: Indeed/LinkedIn/Google now marked `✅ Default`; the five others marked `⚠️/❌ Quarantined` with a note that each still works via explicit `site_name`. Added a paragraph directly under the table spelling out the default-vs-explicit distinction. Also added accurate per-board notes: Indeed/LinkedIn have no structured salary data; LinkedIn has no description text unless `linkedin_fetch_description=True`; Google returned zero rows across every search tried during this project's measurements.
- **Malaysia-specific caveats**: rewrote the stale salary-parsing paragraph (it previously said description-parsing "runs only when `country_indeed='usa'`", which is no longer true — Tasks 1-13 built a Malaysia-specific description parser). New text states: 0% structured salary fill measured on Indeed/LinkedIn; salary for `country_indeed="malaysia"` comes from parsing MYR amounts out of description text; structured data still wins when present; LinkedIn doesn't fetch descriptions by default, so description-parsed salary is effectively Indeed-only unless that flag is turned on; `salary_source` reports which path was used. Added a new short caveat explaining Indeed's ISO 3166-2 state codes (`M14`, `M10`, `M07`, …) and that the pipeline normalizes them to canonical state names.
- **Parameters block**: `site_name` now documents the default-3 + quarantined-5 split; `country_indeed` now says it defaults to `"malaysia"` (previously said `"usa"`) and names which pipeline stages are gated on it; added `include_remote` (Malaysia-only second pass, no-op + logged elsewhere) and `group_duplicates` (fuzzy dedup_group labeling, never removes rows, Malaysia-only) as new parameter entries, matching the existing bullet style.
- **Output section**: added a paragraph after the sample table describing the four new columns (`city`, `state`, `dedup_group`, `remote_scope`) with accurate semantics — including the explicit statement that `remote_scope` is a sorting aid, not a guarantee, since most postings never state remote eligibility.
- **JobPost schema**: added `dedup_group` and `remote_scope` (with its five possible values) to the top-level field list, labeled as coming from the Malaysia normalization pipeline.
- **Roadmap and Credits sections**: left untouched, per instruction, even though the roadmap's "MYR salary parsing from job descriptions" bullet is now stale (it's implemented) — flagged below as a known discrepancy I did not touch since the brief explicitly said keep roadmap intact.

## TDD evidence

**RED** — ran the two new tests in isolation before touching `jobspy/__init__.py`:

```
poetry run pytest tests/test_scrape_jobs_integration.py -v -k "test_default_sites_are_malaysia_relevant or test_unsupported_board_still_works_when_named_explicitly"
```

Result:
```
tests/test_scrape_jobs_integration.py::test_default_sites_are_malaysia_relevant FAILED
tests/test_scrape_jobs_integration.py::test_unsupported_board_still_works_when_named_explicitly PASSED
1 failed, 1 passed, 14 deselected in 0.12s

FAILED test_default_sites_are_malaysia_relevant - ImportError: cannot import name 'DEFAULT_SITES' from 'jobspy'
```
This is exactly the failure the brief predicted (Step 2: "Expected: FAIL — cannot import name 'DEFAULT_SITES'"). The second test passed even before the change because, pre-quarantine, `site_name=["bayt"]` already worked (explicit naming was never broken) — that test exists to guard against regressing that specific behavior, not to fail first.

**GREEN** — after adding `DEFAULT_SITES`, repointing `get_site_type()`, and fixing `__all__`:

```
poetry run pytest tests/ -v
```
Result: `181 passed in 0.22s` (0 warnings). Re-ran after Black reformatted the test file:
```
poetry run pytest tests/ -q
181 passed in 0.22s
```

## Self-review findings

- **Completeness**: `DEFAULT_SITES` added exactly as specified; `__all__` fixed exactly as specified; both brief tests present and passing; all README sections in scope (boards table, parameters, output columns, `country_indeed` default) updated.
- **Correctness**: Confirmed by reading the diff — `get_site_type()`'s no-arg branch is the only place `list(Site)` was replaced; the `isinstance(site_name, str/Site/list)` branches (which handle explicit naming) are untouched, so a quarantined board named explicitly still resolves through `map_str_to_site` unchanged. Verified via the passing `test_unsupported_board_still_works_when_named_explicitly` and via `test_default_sites_are_malaysia_relevant`.
- **Accuracy**: Every factual README claim was checked against either the measured facts given in the task instructions or the actual code:
  - Salary fill / Google zero-rows / LinkedIn no description-by-default / Indeed ISO state codes: taken directly from the supplied measured facts.
  - `group_duplicates` / `include_remote` gating on `country_indeed == Country.MALAYSIA`, and "never removes a row": verified by reading `jobspy/__init__.py` (the `if country_enum == Country.MALAYSIA` block) and `jobspy/malaysia/__init__.py` (`assign_groups`/`dedupe_exact` docstring and logic).
  - `remote_scope` values (`my, apac, global, other_country, unknown`) and their precedence: verified by reading `jobspy/malaysia/remote.py`.
  - `dedup_group` and `remote_scope` field presence on `JobPost`, and column ordering (`dedup_group` after `site`, `city`/`state` after `location`, `remote_scope` after `is_remote`): verified against `jobspy/model.py` and `jobspy/util.py`'s `desired_order`.
  - `salary_source` values (`direct_data`, `description`) and that structured board data always wins: verified against `jobspy/malaysia/__init__.py::_apply_salary` and `jobspy/frame.py`.
- **Discipline**: Step 5 not run — no `poetry run python -m jobspy.baseline.runner` invocation anywhere in this session, and no `docs/baseline/*-baseline-phase1.md` file was created or staged. No test added touches the network (both new tests monkeypatch scraper classes exactly like the existing suite's pattern). Nothing under `jobspy/malaysia/` was modified (only read, for accuracy-checking). Black was run only on `jobspy/__init__.py` and `tests/test_scrape_jobs_integration.py`, not the whole tree.
- **Testing**: `181 passed in 0.22s`, no warnings, no errors, both before and after the Black reformatting pass.

## Files changed

- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\jobspy\__init__.py`
- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\tests\test_scrape_jobs_integration.py`
- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\README.md`

Commit: `bded8c2` on branch `feat/malaysia-pipeline-phase-0-1` — "feat: default to MY-relevant boards, fix __all__, document new params". Only the three files above were staged and committed; `docs/baseline/` was intentionally left for the controller (Step 5 not run, so no second baseline report exists yet).

## Concerns / things I was unsure about

1. **Unrelated untracked file `CLAUDE.md`** exists in the repo root (not created by me, timestamped before this session's work began). I did not stage or commit it, and did not modify it — flagging it in case the controller wants to handle it separately.
2. **Roadmap section staleness**: the "Deferred/Roadmap" bullet "MYR salary parsing from job descriptions (see caveat below)" is now inaccurate — that feature is implemented (Tasks 1-13 shipped it, and I documented it in the caveats section). I left the roadmap section untouched per the explicit instruction to keep it intact, but this is a known, unresolved inconsistency between the roadmap and the caveats section it points to.
3. **Commit message wording differs slightly from the brief's suggested one-liner** (`"feat: default to MY-relevant boards and capture phase 1 baseline"`) since I did not capture a phase 1 baseline (Step 5 skipped) — I wrote a message describing only what this commit actually contains, to avoid claiming a baseline capture that didn't happen. The controller's later baseline-capture step may want its own commit or may want to fold into this one; I left that decision to it.
4. **`Site` import unused status**: `Site` was already imported before my change (`from jobspy.model import ScraperInput, Site`); no import changes were needed since `DEFAULT_SITES` uses the same `Site` enum already in scope.

## Done-criteria status (from the brief, scoped to what I covered)

- `scrape_jobs()` with no `site_name` queries only Indeed, LinkedIn, Google, against `country_indeed="malaysia"` — verified by test and by code inspection.
- A board that raises produces a logged error and partial result, never an exception out of `scrape_jobs` — pre-existing behavior (Task 5-era), unaffected by this task's changes, still covered by `test_one_failing_board_does_not_kill_the_run`.
- No row is ever removed by fuzzy grouping; `dedup_group` populated for cross-board matches — pre-existing behavior from `jobspy/malaysia/grouping.py`, documented accurately in this task's README update but not itself modified here.
- "Two baseline reports exist in `docs/baseline/`" — **not satisfied**, by design: that's Step 5, explicitly out of my scope for this dispatch.

---

# Fix report: post-review corrections (2026-09-23)

Review came back **Approved** with four follow-up items. All four addressed below. Commit: `99a8881` — "fix: address task 14 review — README self-consistency, null remote_scope bucket" (on top of `bded8c2` and the coordinator's own `805203c` baseline-capture commit).

## 1. Stale roadmap entry (Important)

Removed the `- [ ] MYR salary parsing from job descriptions (see caveat below)` bullet from the roadmap. Chose removal over checking it off `[x]` because the roadmap's intro line reads "None of the following are implemented yet" — a checked item under that header would read oddly, and the feature is already documented in full in the "Malaysia-specific caveats" section two headers down, so nothing is lost by dropping the pointer.

**Answer on other roadmap bullets**: checked all five remaining items against the codebase.
- JobStreet MY, Hiredly, Maukerja, Ricebowl, Glints Malaysia: `grep -ril "jobstreet\|hiredly\|maukerja\|ricebowl\|glints" jobspy/` returned nothing — none implemented, all still genuinely future work.
- "Bahasa Malaysia search-term handling": `jobspy/malaysia/language.py` ships a `to_bm_query` function, but `grep -rn "to_bm_query" jobspy/` (excluding its own definition) returned nothing — it is defined but called from nowhere, so search terms are never actually translated. This bullet is also still accurate and was left untouched, matching the task-14-brief's own "Deferred from spec" note that this wiring belongs to phase 3 (Maukerja/Ricebowl), not phases 0-1.

No other roadmap bullet needed changing.

## 2. `country_indeed` self-contradiction (Minor)

Changed the Usage example's inline comment from `# required for Indeed — routes to malaysia.indeed.com` to `# already the default; shown for clarity — routes to malaysia.indeed.com`, so it no longer implies the argument is mandatory when the Parameters block (correctly) says it now defaults to `"malaysia"`.

## 3. Dropped Naukri schema block (Minor)

Restored the "Naukri specific" field list (`skills`, `experience_range`, `company_rating`, `company_reviews_count`, `vacancy_count`, `work_from_home_type`) to the JobPost schema section, in the same form it existed upstream (verified against `git show fda080a:README.md`), with an added parenthetical `(quarantined by default — see Supported job boards)` so a reader understands why a board's fields are documented even though it's not in `DEFAULT_SITES`.

## 4. `remote_scope` null-bucket defect (Important)

### Root cause
`jobspy/baseline/metrics.py::compute_metrics` built `remote_scope_counts` via `df["remote_scope"].value_counts(dropna=False)`. In an object-dtype column, pandas' `value_counts` treats a literal Python `None` and a literal `float("nan")` as two distinct keys even though both are null. A live run's column apparently mixed both representations (e.g. from concatenating frames where some rows carry `None` and others get reindexed to `NaN`), producing the reported three-bucket table (`None: 102`, `my: 2`, `nan: 100`) where only two buckets (`my`, "not remote") actually exist in the data.

### Fix
In `jobspy/baseline/metrics.py`, replaced the single `value_counts(dropna=False)` call with: count nulls via `.isna().sum()` (which is True for both `None` and `NaN` regardless of dtype), build the non-null counts via `.dropna().value_counts()`, then add one combined bucket keyed `"(not remote)"` if there were any nulls. Comment explains why, referencing that `remote_scope` is `None` by design for every non-remote job.

### Test — TDD evidence

Added `test_remote_scope_collapses_null_like_values_into_one_bucket` to `tests/test_baseline_metrics.py`: builds a `remote_scope` column via `pd.array(["my", None, float("nan"), "my", None], dtype="object")` (mixing both null representations deliberately, mirroring the live-run column) and asserts `compute_metrics(df).remote_scope_counts == {"my": 2, "(not remote)": 3}`.

**RED** — ran before applying the fix:
```
poetry run pytest tests/test_baseline_metrics.py -v -k "test_remote_scope_collapses_null_like_values_into_one_bucket"
```
```
FAILED tests/test_baseline_metrics.py::test_remote_scope_collapses_null_like_values_into_one_bucket
AssertionError: assert {'None': 2, 'my': 2, 'nan': 1} == {'(not remote)': 3, 'my': 2}
1 failed, 8 deselected in 0.12s
```
This reproduces the reported defect exactly — `None` and `nan` land in separate buckets (`'None': 2, 'nan': 1`) instead of one combined `(not remote): 3` bucket.

**GREEN** — after the fix:
```
poetry run pytest tests/test_baseline_metrics.py -v
```
```
9 passed in 0.03s
```

### Full suite
```
poetry run pytest tests/ -v
```
```
182 passed in 0.22s
```
Zero warnings, zero errors, no network access (the new test builds its DataFrame in-memory).

### Baseline report not regenerated
Per instruction, the already-committed live baseline report (`805203c`, captured by the coordinator) was left untouched — it remains the historical record of that specific run, three-bucket artifact and all. The fix applies only to future `compute_metrics` calls / baseline runs.

## Black / formatting

```
poetry run black jobspy/baseline/metrics.py tests/test_baseline_metrics.py --diff
```
```
All done! (2 files would be left unchanged.)
```
No reformatting needed — the fix and test were already Black-compliant as written. Black was not run against `README.md` (not a Python file) or against any file outside this fix's scope.

## Files changed in this fix

- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\README.md`
- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\jobspy\baseline\metrics.py`
- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\tests\test_baseline_metrics.py`

Commit: `99a8881` on branch `feat/malaysia-pipeline-phase-0-1`.

## Remaining concerns

- The untracked `CLAUDE.md` in the repo root (not created by me, flagged in the original report) is still present and still untouched/uncommitted.
- No new concerns introduced by these four fixes.
