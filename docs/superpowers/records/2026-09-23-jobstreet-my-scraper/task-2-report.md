# Task 2 Report: Parse one search record into a JobPost (JobStreet MY)

## Summary

Created `jobspy/jobstreet/util.py` with pure JSON-parsing functions
(`parse_job`, `parse_location`, `parse_job_types`, `parse_is_remote`,
`parse_company_name`, `parse_date_posted`, `parse_compensation`) and
`tests/test_jobstreet_util.py`, transcribed verbatim from the task brief.
Consumed `BASE_URL`, `REMOTE_ARRANGEMENT`, `WORK_TYPE_MAP` from
`jobspy/jobstreet/constant.py` (Task 1) and `parse_myr_salary` from
`jobspy/malaysia/salary.py` unmodified, as instructed.

## TDD evidence

### RED — Step 2

Command:

```bash
poetry run pytest tests/test_jobstreet_util.py -q
```

Output:

```
=================================== ERRORS ====================================
________________ ERROR collecting tests/test_jobstreet_util.py ________________
ImportError while importing test module 'C:\Users\USER\Desktop\dev\forks\MyJobSpy\tests\test_jobstreet_util.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
..\..\..\..\AppData\Local\Programs\Python\Python312\Lib\importlib\__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests\test_jobstreet_util.py:16: in <module>
    from jobspy.jobstreet.util import parse_job
E   ModuleNotFoundError: No module named 'jobspy.jobstreet.util'
=========================== short test summary info ===========================
ERROR tests/test_jobstreet_util.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.24s
```

Expected failure: `jobspy/jobstreet/util.py` did not exist yet, so the test
module couldn't even be collected. This matches the brief's expected output
exactly (`ModuleNotFoundError: No module named 'jobspy.jobstreet.util'`).

### GREEN — Step 4

Command:

```bash
poetry run pytest tests/test_jobstreet_util.py -q
```

Output:

```
...                                                                      [100%]
3 passed in 0.02s
```

All three tests pass: the nominal record (`94689504`) parses with a
`js-`-prefixed id, a title, a company name, the exact
`job_url = "https://my.jobstreet.com/job/94689504"`, and
`location.country == Country.MALAYSIA`; every one of the 8 fixture records
gets a `js-<id>`-prefixed id; and no `parse_job` result's `job_url` contains
a `?` (tracking-token check).

## Verification beyond the task's own tests

- `poetry run black jobspy/jobstreet tests/test_jobstreet_util.py` -> "4 files
  left unchanged" (both new files were already 88-col compliant, transcribed
  verbatim from the brief).
- Full suite: `poetry run pytest -q` -> `269 passed, 7 xfailed` (the 7 xfails
  are the pre-existing, grandfathered `USER_AGENT_NOT_FORWARDED` contract
  cases from `tests/test_scraper_contract.py`, unrelated to this task).

## Notes / decisions

- Left the `JobType` import in `tests/test_jobstreet_util.py` unused by
  Task 2's own three tests, per the brief's pre-resolved ambiguity: it is
  staged for Task 3, which appends to the same file.
- No new `JobPost` fields were added; no `desired_order` changes needed.
- No hand-normalization was added inside the scraper: `parse_location`
  emits JobStreet's raw comma-separated label as city/state without any
  gazetteer lookup, and salary parsing is delegated entirely to the shared
  `parse_myr_salary`.
- `parse_job` returns `None` only when a record has no `id` or no `title`;
  none of the 8 nominal fixture records trigger that path (that is
  `search_malformed.json`'s job, covered by a later task per the fixture
  README).

## Files changed

- Created: `jobspy/jobstreet/util.py`
- Created: `tests/test_jobstreet_util.py`

## Commit

`02ddcfe` — `feat: parse JobStreet search records into JobPost`
