# Task 5 Report: Fetch descriptions on request (JobStreet MY)

## Summary

Added optional, off-by-default description fetching to `JobStreet.scrape`. When
`fetch_description=True`, `_add_descriptions` fires one GraphQL request per
already-sliced job (bounded to `DESCRIPTION_WORKERS=5` via `ThreadPoolExecutor`)
and overwrites the search teaser only on success. `description_format` is
honoured with the same three-way branch every other scraper uses:
`MARKDOWN` -> `markdown_converter`, `PLAIN` -> `plain_converter`, `HTML` falls
through untouched. Any fetch failure (exception, empty payload, missing
content) is caught, logged, and leaves the teaser in place — nothing raises
out of `scrape()`.

## Files changed

- `jobspy/jobstreet/__init__.py` — added `self.fetch_description = False` to
  `__init__`; added `_fetch_description` and `_add_descriptions`; inserted the
  description step between the final slice and the `JobResponse` return.
- `tests/test_jobstreet_scraper.py` — appended `TestDescriptions` with 4 tests
  (transcribed from the brief, with the F2 correction below applied).

Neither `jobspy/jobstreet/util.py` nor any pre-existing test was touched.
`jobspy/__init__.py` (wiring `jobstreet_fetch_description` through
`scrape_jobs`) is explicitly out of scope — that's Task 6, confirmed by
reading `task-6-brief.md` before starting.

## F2 correction applied

The brief's `test_fetches_and_converts_descriptions_when_on` asserted
positional order:

```python
assert graphql[0]["json"]["variables"]["jobId"] == jobs[0].id.removeprefix("js-")
```

`_add_descriptions` dispatches through a `ThreadPoolExecutor(max_workers=5)`,
so the order calls land in `FakeSession.calls` is not guaranteed to match
input order. Replaced with a set comparison, plus a comment explaining why:

```python
graphql = [c for c in scraper.session.calls if c["url"].endswith("/graphql")]
assert len(graphql) == 2
# _add_descriptions runs on a ThreadPoolExecutor with 5 workers, so
# the order calls land in scraper.session.calls is nondeterministic.
# Compare the set of requested ids rather than positional order.
requested = {c["json"]["variables"]["jobId"] for c in graphql}
assert requested == {job.id.removeprefix("js-") for job in jobs}
```

The `len(graphql) == 2` count assertion (order-independent: exactly one
request per selected job) was kept as-is. No other test asserts on call
ordering; `FakeSession.calls` is only ever compared by length, membership, or
set in this file.

## TDD evidence

### RED

Isolated the pre-implementation state with `git stash push -- jobspy/jobstreet/__init__.py`
(keeping the new tests in place), then ran:

```
poetry run pytest tests/test_jobstreet_scraper.py -k Descriptions -q
```

Output:

```
..F.                                                                     [100%]
================================== FAILURES ===================================
_______ TestDescriptions.test_fetches_and_converts_descriptions_when_on _______

    def test_fetches_and_converts_descriptions_when_on(self):
        scraper = make_scraper([load("search_page.json")])
        scraper.fetch_description = True
        jobs = scraper.scrape(an_input(results_wanted=2)).jobs

        graphql = [c for c in scraper.session.calls if c["url"].endswith("/graphql")]
>       assert len(graphql) == 2
E       assert 0 == 2
E        +  where 0 = len([])

tests\test_jobstreet_scraper.py:194: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_jobstreet_scraper.py::TestDescriptions::test_fetches_and_converts_descriptions_when_on
1 failed, 3 passed, 10 deselected in 0.18s
```

Why expected: `fetch_description` was not yet a real switch inside `scrape()` —
setting `scraper.fetch_description = True` on the pre-implementation class
just creates a dynamic attribute that `scrape()` never reads, so no GraphQL
call is ever made and the assertion on request count fails. The other three
`TestDescriptions` tests pass vacuously at this stage (they only require the
teaser to survive and no GraphQL calls when the flag is off/unused), which is
expected and consistent with the brief.

Restored the implementation with `git stash pop`.

### GREEN

```
poetry run pytest tests/test_jobstreet_scraper.py -q
```

Output:

```
..............                                                           [100%]
14 passed in 2.08s
```

Full suite:

```
poetry run pytest -q
```

Output:

```
........................................................................ [ 23%]
........................................................................ [ 46%]
........................................................................ [ 69%]
................................................................xx.xx.xx [ 92%]
x.....................                                                   [100%]
303 passed, 7 xfailed in 3.44s
```

The 7 `xfailed` are the pre-existing, unrelated `USER_AGENT_NOT_FORWARDED`
contract xfails documented in `CLAUDE.md` — JobStreet is not among them.

### Formatting

```
poetry run black jobspy/jobstreet tests/test_jobstreet_scraper.py
```

Reformatted only `jobspy/jobstreet/__init__.py` (wrapped the new multi-name
imports to 88 columns). No formatting changes were needed in the test file.

## Self-review notes

- Diff matches the brief's code blocks verbatim except for the deliberate F2
  fix and the black-driven import wrapping.
- No test asserts on thread-scheduling order; `test_fetches_and_converts_descriptions_when_on`
  now uses a set comparison exactly per the correction instructions.
- `jobspy/jobstreet/util.py` and all pre-existing tests are untouched (verified
  via `git diff`).
- Did not touch `jobspy/__init__.py` / `scrape_jobs` — that wiring is Task 6.

## Fix: review finding (Important) — envelope traversal outside try/except

### Finding

Reviewer flagged `jobspy/jobstreet/__init__.py:117-118` (pre-fix numbering):
`payload = response.json() or {}` only normalizes falsy JSON roots (`None`,
`""`, `[]`, `0`) to `{}`. A truthy-but-non-dict root — the endpoint returning
a bare list, string, or number — stays as-is, so the next line,
`payload.get("data")`, raises `AttributeError` because lists/strings/numbers
have no `.get`. That line sat *after* the `try/except`, so the exception was
uncaught and propagated through `fill` → `executor.map` → `list(...)` in
`_add_descriptions` → out of `scrape()`, violating "nothing may raise out of
scrape()". No existing test exercised this shape — the failure test only
raised from `session.post` itself.

### Fix

Moved the envelope-traversal and `content` extraction inside the same `try`
block that wraps the request and `response.json()` call, so any JSON shape —
correctly-shaped dict, empty dict, or a non-dict root — is contained by the
one `except Exception` and degrades to `return None` (teaser survives).
Added a comment on the `payload.get("data")` line explaining why the
traversal must stay inside the try. No other behavior changed: the
`if not content: return None` check and the three-way `description_format`
branch stayed where they were, just after the try/except returns cleanly.

```python
        try:
            response = self.session.post(
                GRAPHQL_URL,
                json={
                    "operationName": "jobDetails",
                    "variables": {"jobId": job_id},
                    "query": JOB_DETAILS_QUERY,
                },
                timeout=self.scraper_input.request_timeout,
            )
            payload = response.json() or {}
            # payload is only guaranteed falsy-normalized above - a
            # truthy-but-non-dict JSON root (a bare list, string, number)
            # would make .get() raise below, so the traversal stays inside
            # this same try: any shape of payload must be contained here.
            job = ((payload.get("data") or {}).get("jobDetails") or {}).get("job") or {}
            content = job.get("content")
        except Exception as exc:  # noqa: BLE001 - one description is not the batch
            log.warning(f"description fetch failed for {job_id}: {exc}")
            return None

        if not content:
            return None
```

### New covering test

Added `test_a_malformed_graphql_payload_leaves_the_teaser` to
`TestDescriptions` in `tests/test_jobstreet_scraper.py`: a `FakeSession`
subclass (`NonDictPayload`) whose `post` returns a `FakeResponse` wrapping a
bare list (`[1, 2, 3]`) as the JSON root. Asserts `scrape()` returns normally
with the job present and its teaser description intact — pinning that a
non-dict-but-truthy payload cannot escape `_fetch_description`.

### TDD evidence for the fix

**RED** — isolated the pre-fix code with
`git stash push -- jobspy/jobstreet/__init__.py` (new test stayed in the
working tree), then ran:

```
poetry run pytest tests/test_jobstreet_scraper.py -k malformed -q
```

Output (trimmed to the relevant frames):

```
jobspy\jobstreet\__init__.py:150: in fill
    body = self._fetch_description(job.id.removeprefix("js-"))
...
>       job = ((payload.get("data") or {}).get("jobDetails") or {}).get("job") or {}
                ^^^^^^^^^^^
E       AttributeError: 'list' object has no attribute 'get'

jobspy\jobstreet\__init__.py:129: AttributeError
=========================== short test summary info ===========================
FAILED tests/test_jobstreet_scraper.py::TestDescriptions::test_a_malformed_graphql_payload_leaves_the_teaser
1 failed, 14 deselected in 0.21s
```

This is exactly the reviewer-predicted failure mode: the `AttributeError`
raised on the (then-unguarded) `.get("data")` call, uncaught, propagating out
of the worker thread and through `scrape()`. Restored the fix with
`git stash pop`.

**GREEN** — after restoring the fix and re-running `poetry run black
jobspy/jobstreet tests/test_jobstreet_scraper.py` (reformatted only
`jobspy/jobstreet/__init__.py`; the moved envelope line is exactly 88 columns
so it did not need wrapping):

```
poetry run pytest tests/test_jobstreet_scraper.py -v
```

Output:

```
collected 15 items

tests/test_jobstreet_scraper.py::test_returns_jobs_from_one_page PASSED  [  6%]
tests/test_jobstreet_scraper.py::test_stops_on_an_empty_page_instead_of_spinning PASSED [ 13%]
tests/test_jobstreet_scraper.py::test_stops_on_a_short_page PASSED       [ 20%]
tests/test_jobstreet_scraper.py::test_does_not_return_the_same_job_twice PASSED [ 26%]
tests/test_jobstreet_scraper.py::test_applies_offset PASSED              [ 33%]
tests/test_jobstreet_scraper.py::TestQueryParameters::test_sends_the_board_identifiers_and_query PASSED [ 40%]
tests/test_jobstreet_scraper.py::TestQueryParameters::test_maps_hours_old_to_whole_days PASSED [ 46%]
tests/test_jobstreet_scraper.py::TestQueryParameters::test_sorts_by_date_only_when_filtering_by_age PASSED [ 53%]
tests/test_jobstreet_scraper.py::TestQueryParameters::test_maps_job_type_to_the_worktype_id PASSED [ 60%]
tests/test_jobstreet_scraper.py::TestQueryParameters::test_omits_filters_that_were_not_requested PASSED [ 66%]
tests/test_jobstreet_scraper.py::TestDescriptions::test_teaser_is_used_when_descriptions_are_off PASSED [ 73%]
tests/test_jobstreet_scraper.py::TestDescriptions::test_no_graphql_calls_when_descriptions_are_off PASSED [ 80%]
tests/test_jobstreet_scraper.py::TestDescriptions::test_fetches_and_converts_descriptions_when_on PASSED [ 86%]
tests/test_jobstreet_scraper.py::TestDescriptions::test_a_failed_description_leaves_the_teaser PASSED [ 93%]
tests/test_jobstreet_scraper.py::TestDescriptions::test_a_malformed_graphql_payload_leaves_the_teaser PASSED [100%]

============================= 15 passed in 1.62s ==============================
```

### Scope discipline

Only the flagged Important finding was addressed. The three Minor findings
mentioned by the coordinator were deliberately left untouched, per
instruction, for the final whole-branch review.
