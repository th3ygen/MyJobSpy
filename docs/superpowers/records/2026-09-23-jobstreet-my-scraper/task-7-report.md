# Task 7 Report: Prove the pipeline normalizes JobStreet output

## Summary

Created `tests/test_jobstreet_pipeline.py`, running real parsed JobStreet
records (`tests/fixtures/jobstreet/search_page.json`, 8 records) through
`jobspy.malaysia.normalize()` and `jobspy.frame.build_jobs_dataframe()`, with
no per-board wiring in either. All 5 tests pass. No changes were made under
`jobspy/jobstreet/`.

The location gazetteer needed **no changes** — `test_state_survives_normalization`
passed on the first run. All of JobStreet's suburb-level labels in the fixture
("Kepong, Kuala Lumpur", "Bukit Bintang, Kuala Lumpur", "Cheras, Kuala Lumpur",
"Kuala Lumpur City Centre, Kuala Lumpur") already resolve: the KL-locality
entries already exist in `jobspy/malaysia/location.py` for the ones with a
recognised city (Kepong, Bukit Bintang, Cheras), and the ones that don't
("Kuala Lumpur City Centre") still resolve because `normalize_location` falls
back from a city miss to a state match, and the record's state field is
literally "Kuala Lumpur", which is already a gazetteer key.

## Finding: the brief's `test_remote_scope_is_assigned` had an incorrect premise

The brief's literal test body was:

```python
def test_remote_scope_is_assigned(jobs):
    for job in normalize(list(jobs)):
        assert job.remote_scope is not None
```

This failed on the first run. Root cause: `classify_remote_scope` in
`jobspy/malaysia/remote.py` has a documented, intentional contract —
"Returns None for non-remote jobs" — and returns `None` whenever
`job.is_remote` is falsy. The fixture is realistic data: only 1 of the 8
records (`js-94462128`, work arrangement "Remote") is actually remote; the
other 7 are On-site/Hybrid, so `parse_is_remote` in
`jobspy/jobstreet/util.py` correctly returns `False` for them
(`REMOTE_ARRANGEMENT = "Remote"` only — Hybrid is deliberately not folded
in). This is not a scraper bug and not a gazetteer-style pipeline gap; it's
the pipeline behaving exactly as documented and exactly as every existing
call site in `tests/malaysia/test_pipeline.py` already assumes.

This repo has direct precedent for this exact situation: `tests/malaysia/test_pipeline.py::test_normalizes_location_salary_and_remote`
carries a "Ruling F1" comment where a brief's original assertion was found to
be wrong given the pipeline's actual (correct) behavior, and the test was
corrected in place rather than production code being bent to fit a mistaken
assertion. I applied the same resolution here rather than touching
`jobspy/malaysia/remote.py` (out of this task's authorized scope, which only
covers `jobspy/malaysia/location.py`) or `jobspy/jobstreet/` (explicitly
off-limits).

Corrected assertion (see the in-file comment for full reasoning):

```python
def test_remote_scope_is_assigned(jobs):
    normalized = normalize(list(jobs))
    remote_jobs = [job for job in normalized if job.is_remote]
    assert remote_jobs, "fixture should contain at least one remote record"
    for job in remote_jobs:
        assert job.remote_scope is not None
    for job in normalized:
        if not job.is_remote:
            assert job.remote_scope is None
```

This still proves the real claim (remote_scope normalization runs and
produces a value for JobStreet's remote postings, with zero JobStreet-side
wiring) without asserting something the pipeline never promised.

No other lines of the brief's test code were changed.

## Test command and output

```
$ poetry run pytest tests/test_jobstreet_pipeline.py -v
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-8.4.2, pluggy-1.6.0
collected 5 items

tests/test_jobstreet_pipeline.py::test_normalize_accepts_jobstreet_jobs_without_wiring PASSED [ 20%]
tests/test_jobstreet_pipeline.py::test_board_salary_is_not_overwritten_by_the_description_parser PASSED [ 40%]
tests/test_jobstreet_pipeline.py::test_remote_scope_is_assigned PASSED   [ 60%]
tests/test_jobstreet_pipeline.py::test_rows_reach_the_dataframe_with_salary_marked_direct PASSED [ 80%]
tests/test_jobstreet_pipeline.py::test_state_survives_normalization PASSED [100%]

============================== 5 passed in 0.03s ==============================
```

Full suite (unaffected, run after this change):

```
$ poetry run pytest -q
........................................................................ [ 22%]
........................................................................ [ 45%]
........................................................................ [ 67%]
........................................................................ [ 90%]
xx.xx.xxx.....................                                           [100%]
311 passed, 7 xfailed in 4.64s
```

Contract test + pipeline test together, after `black`:

```
$ poetry run pytest tests/test_jobstreet_pipeline.py tests/test_scraper_contract.py -q
...........................................xx.xx.xxx...................  [100%]
64 passed, 7 xfailed in 1.32s
```

## Files touched

- Created: `tests/test_jobstreet_pipeline.py`
- No changes to `jobspy/malaysia/location.py` (gazetteer already sufficient)
- No changes anywhere under `jobspy/jobstreet/`

## Diagnostic evidence (not committed, ad hoc check during debugging)

Per-job `is_remote` / `remote_scope` after `normalize()`, confirming the
7-of-8-non-remote distribution behind the finding above:

```
js-94462128 is_remote=True  remote_scope=my
js-94689504 is_remote=False remote_scope=None
js-94234551 is_remote=False remote_scope=None
js-94830903 is_remote=False remote_scope=None
js-94831259 is_remote=False remote_scope=None
js-94586568 is_remote=False remote_scope=None
js-94333139 is_remote=False remote_scope=None
js-94553263 is_remote=False remote_scope=None
```
