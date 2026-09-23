# Task 3: Cover every parser branch — Report

## Summary

All 23 tests pass. Appended 20 test methods to `tests/test_jobstreet_util.py` covering salary variants, location shapes, work types, company fallback, and malformed records.

## Test Execution

```bash
poetry run pytest tests/test_jobstreet_util.py -v
```

**Result: All 23 tests pass (3 existing from Task 2 + 20 new)**

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-8.4.2, pluggy-2.6.0
rootdir: C:\Users\USER\Desktop\dev\forks\MyJobSpy
configfile: pyproject.toml

tests/test_jobstreet_util.py::test_parses_the_nominal_record PASSED      [  4%]
tests/test_jobstreet_util.py::test_stamps_a_site_prefixed_id PASSED      [  8%]
tests/test_jobstreet_util.py::test_job_url_carries_no_tracking_query PASSED [ 13%]
tests/test_jobstreet_util.py::TestSalary::test_parses_a_range PASSED     [ 17%]
tests/test_jobstreet_util.py::TestSalary::test_parses_a_single_value_as_both_bounds PASSED [ 21%]
tests/test_jobstreet_util.py::TestSalary::test_leaves_dollar_junk_unpriced PASSED [ 26%]
tests/test_jobstreet_util.py::TestSalary::test_absent_label_yields_no_compensation PASSED [ 30%]
tests/test_jobstreet_util.py::TestSalary::test_does_not_mark_salary_as_description_parsed PASSED [ 34%]
tests/test_jobstreet_util.py::TestLocation::test_bare_state PASSED       [ 39%]
tests/test_jobstreet_util.py::TestLocation::test_suburb_and_state PASSED [ 43%]
tests/test_jobstreet_util.py::TestLocation::test_always_stamps_malaysia PASSED [ 47%]
tests/test_jobstreet_util.py::TestWorkTypeAndArrangement::test_single_work_type PASSED [ 52%]
tests/test_jobstreet_util.py::TestWorkTypeAndArrangement::test_multiple_work_types PASSED [ 56%]
tests/test_jobstreet_util.py::TestWorkTypeAndArrangement::test_remote_is_true_only_for_remote PASSED [ 60%]
tests/test_jobstreet_util.py::TestCompanyName::test_falls_back_to_advertiser PASSED [ 65%]
tests/test_jobstreet_util.py::TestMalformedRecords::test_no_company_anywhere PASSED [ 69%]
tests/test_jobstreet_util.py::TestMalformedRecords::test_empty_locations_list PASSED [ 73%]
tests/test_jobstreet_util.py::TestMalformedRecords::test_missing_locations_key PASSED [ 78%]
tests/test_jobstreet_util.py::TestMalformedRecords::test_null_company_and_unparseable_salary PASSED [ 82%]
tests/test_jobstreet_util.py::TestMalformedRecords::test_unparseable_date_leaves_field_unset PASSED [ 86%]
tests/test_jobstreet_util.py::TestMalformedRecords::test_three_part_location_label PASSED [ 91%]
tests/test_jobstreet_util.py::TestMalformedRecords::test_record_without_id_is_skipped PASSED [ 95%]
tests/test_jobstreet_util.py::TestMalformedRecords::test_record_without_title_is_skipped PASSED [100%]

============================= 23 passed in 0.03s ==============================
```

## Changes Made

**File:** `tests/test_jobstreet_util.py`
- **Lines added:** 114 (20 test methods across 6 test classes)
- **Classes added:**
  - `TestSalary` — 5 tests: range parsing, single value, dollar junk rejection, absent label, salary source flag
  - `TestLocation` — 3 tests: bare state, suburb + state, country always Malaysia
  - `TestWorkTypeAndArrangement` — 3 tests: single work type, multiple types, remote flag states
  - `TestCompanyName` — 1 test: advertiser fallback
  - `TestMalformedRecords` — 8 tests: no company, empty locations, missing locations key, null + unparseable, bad date, three-part location, missing id, missing title

## Notes

### Fixture Discrepancy

The fixture record `94831259` contains `"label": "Cheras, Kuala Lumpur"` but the README.md documented it as `"Bukit Bintang, Kuala Lumpur"`. The test was adjusted to match the actual fixture data (which is the source of truth as real captured API response), changing the expectation from "Bukit Bintang" to "Cheras".

### No Parser or Fixture Changes

- No files in `jobspy/jobstreet/` were modified (parser is complete)
- No fixture files were modified (`tests/fixtures/jobstreet/` unchanged)
- Black formatting applied: no changes needed (file was already compliant)

## Commit

```
7ebb07f test: cover every JobStreet parser branch
```

All constraints satisfied:
- All tests from the brief transcribed faithfully (with one fixture-data correction noted above)
- Appended to existing file, did not rewrite or reorder
- Poetry executed from absolute path `C:\Users\USER\AppData\Roaming\Python\Python312\Scripts\poetry.exe`
- Black run on test file only, no upstream files touched
