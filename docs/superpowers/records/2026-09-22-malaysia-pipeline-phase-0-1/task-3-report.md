# Task 3 Report: Add the new output columns

## What was implemented

1. **`jobspy/model.py`** — Added two new `JobPost` fields after `work_from_home_type`:
   ```python
   # Malaysia normalization pipeline (jobspy/malaysia/)
   dedup_group: str | None = None  # shared by likely-duplicate listings
   remote_scope: str | None = None  # my | apac | global | other_country | unknown
   ```

2. **`jobspy/util.py`** — Inserted `"dedup_group"` after `"site"`, `"city"`/`"state"` after `"location"`, and `"remote_scope"` after `"is_remote"` in `desired_order`, verbatim per the brief.

3. **`jobspy/frame.py`** — Two changes:
   - Replaced the location-flattening block to also emit `city` and `state` from the `Location` object (verbatim per brief Step 5).
   - **Ruling F5**: replaced `job.dict()` with `job.model_dump()` to eliminate the `PydanticDeprecatedSince20` warning. Verified behavior-identical via the four pre-existing `test_frame.py` tests (see GREEN evidence below) — all four still pass unchanged.

4. **`tests/test_frame.py`** — Appended 5 tests:
   - `test_emits_city_and_state_columns` (brief Step 1)
   - `test_emits_pipeline_columns` (brief Step 1)
   - `test_new_columns_are_in_desired_order` (brief Step 1)
   - `test_enforce_annual_salary_converts_monthly_to_yearly` — new, covers the `enforce_annual_salary=True` conversion branch in `build_jobs_dataframe` (monthly Compensation → yearly, amounts ×12). Asserts `interval == "yearly"`, `min_amount == 60000`, `max_amount == 84000`, `currency == "MYR"` from a monthly $5000-$7000 input.
   - `test_usa_extracts_salary_from_description_when_no_compensation` — new, covers the `Country.USA` description-salary-extraction branch (`compensation=None`, `country_enum=Country.USA`, salary parsed from `description` via `extract_salary`). Asserts `interval == "yearly"`, `min_amount == 80000`, `max_amount == 100000`, `currency == "USD"`, `salary_source == "description"` from description text `"We offer a salary of $80,000 - $100,000 per year"`.

## TDD evidence

**RED** — `poetry run pytest tests/test_frame.py -v` (before implementing Steps 3-5, after appending the new tests):
```
tests/test_frame.py::test_builds_one_row_per_job PASSED
tests/test_frame.py::test_columns_match_desired_order PASSED
tests/test_frame.py::test_flattens_compensation_and_location PASSED
tests/test_frame.py::test_empty_input_returns_empty_frame PASSED
tests/test_frame.py::test_emits_city_and_state_columns FAILED   -- KeyError: 'city'
tests/test_frame.py::test_emits_pipeline_columns FAILED         -- KeyError: 'dedup_group'
tests/test_frame.py::test_new_columns_are_in_desired_order FAILED -- AssertionError: 'dedup_group' not in desired_order
tests/test_frame.py::test_enforce_annual_salary_converts_monthly_to_yearly PASSED
tests/test_frame.py::test_usa_extracts_salary_from_description_when_no_compensation PASSED
3 failed, 6 passed
```
The 3 failures are exactly the ones expected (new columns don't exist yet). The two new coverage-gap tests already pass against pre-existing behavior — expected, since they pin behavior that already exists in `build_jobs_dataframe`/`util.py`, not new behavior. The warnings summary at this point also showed 8x `PydanticDeprecatedSince20` warnings from `.dict()`.

**GREEN** — after implementing Steps 3-5 and the F5 change, `poetry run pytest tests/test_frame.py -v`:
```
9 passed in 0.04s
```
Full suite with warnings visible, `poetry run pytest tests/ -q -W "default"`:
```
11 passed in 0.06s
```
Zero `PydanticDeprecatedSince20` warnings (or any other warnings) in the output — pristine.

**Confirming the four pre-existing `test_frame.py` tests (Task 2) are unaffected by the `model_dump()` switch**: `test_builds_one_row_per_job`, `test_columns_match_desired_order`, `test_flattens_compensation_and_location`, `test_empty_input_returns_empty_frame` all pass unchanged in both the RED and GREEN runs above. No behavior change observed — column set, column order, sorting, location display string, and salary precedence are all identical to before.

## Files changed (committed)

- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\jobspy\model.py`
- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\jobspy\util.py`
- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\jobspy\frame.py`
- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\tests\test_frame.py`

Commit: `9a5c89d` — "feat: add dedup_group, remote_scope, city and state output columns"

## Note on `black jobspy tests`

Running `poetry run black jobspy tests` (as instructed) reformatted a large number of unrelated pre-existing files across the repo (bayt, bdjobs, exception.py, glassdoor, google, indeed, linkedin, naukri, ziprecruiter, README.md) — this appears to be repo-wide style debt predating this plan, not something introduced by this task. Per the brief's Step 7 (`git add jobspy/model.py jobspy/util.py jobspy/frame.py tests/test_frame.py`), I staged and committed only the four files in scope for this task, leaving the rest of the black reformatting unstaged in the working tree. This keeps the commit focused but means those other files remain modified-but-uncommitted locally; flagging this so it isn't mistaken for stray/lost work in a later task.

## Self-review

- **Completeness**: all four columns (`dedup_group`, `remote_scope`, `city`, `state`) added in the exact positions specified in the brief. Both controller instructions (F5 `model_dump()` switch, and the two coverage-gap tests) completed.
- **Quality**: changes are minimal and match existing patterns (field placement, comment style, test style using `make_job` fixture).
- **Discipline**: no scope creep — only the four brief files touched (plus the report file). Did not restructure anything else. Did not commit unrelated black reformatting.
- **Testing**: all new tests assert real values (not smoke tests) — the two coverage-gap tests assert exact converted salary numbers and currency/interval/source fields, not just "did not raise."
- **Output pristine**: confirmed 11 passed, zero warnings with `-W "default"`.

## Concerns

None. The `.dict()` → `.model_dump()` swap was verified behavior-identical against all four pre-existing pinning tests, and no other test in the suite was affected.
