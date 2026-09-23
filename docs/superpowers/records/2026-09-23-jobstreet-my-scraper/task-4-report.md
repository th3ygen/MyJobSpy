# Task 4 Report: Search, page, and return a JobResponse (JobStreet MY)

## Summary

Replaced the `NotImplementedError` stub in `jobspy/jobstreet/__init__.py` with real
paging against JobStreet's JSON search API: `_build_params(page)` builds one query,
`_within_age(job)` applies the exact `hours_old` cutoff on top of the day-granular
`daterange` filter, and `scrape()` pages until enough jobs are collected, a page is
short, a page is empty, or the board returns a non-200 (403 handled specially: log
and stop, never retry). Created `tests/test_jobstreet_scraper.py`, which drives the
scraper against a stubbed session and the committed fixtures — no network access.

Both files transcribed from the brief verbatim, with one deliberate correction (see
below) required by the task instructions.

## Files changed

- Modified: `jobspy/jobstreet/__init__.py`
- Created: `tests/test_jobstreet_scraper.py`

## TDD evidence

### RED

```
poetry run pytest tests/test_jobstreet_scraper.py -q
```

Result: **10 failed**, all with `NotImplementedError: filled in by Task 4`, e.g.:

```
    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
>       raise NotImplementedError("filled in by Task 4")
E       NotImplementedError: filled in by Task 4

jobspy\jobstreet\__init__.py:38: NotImplementedError
...
FAILED tests/test_jobstreet_scraper.py::test_returns_jobs_from_one_page - Not...
FAILED tests/test_jobstreet_scraper.py::test_stops_on_an_empty_page_instead_of_spinning
FAILED tests/test_jobstreet_scraper.py::test_stops_on_a_short_page - NotImple...
FAILED tests/test_jobstreet_scraper.py::test_does_not_return_the_same_job_twice
FAILED tests/test_jobstreet_scraper.py::test_applies_offset - NotImplementedE...
FAILED tests/test_jobstreet_scraper.py::TestQueryParameters::test_sends_the_board_identifiers_and_query
FAILED tests/test_jobstreet_scraper.py::TestQueryParameters::test_maps_hours_old_to_whole_days
FAILED tests/test_jobstreet_scraper.py::TestQueryParameters::test_sorts_by_date_only_when_filtering_by_age
FAILED tests/test_jobstreet_scraper.py::TestQueryParameters::test_maps_job_type_to_the_worktype_id
FAILED tests/test_jobstreet_scraper.py::TestQueryParameters::test_omits_filters_that_were_not_requested
10 failed in 0.22s
```

This is exactly the expected failure — the stub raises before any scraper logic runs.

### GREEN

Implemented `_build_params`, `_within_age`, and `scrape` per the brief.

```
poetry run pytest tests/test_jobstreet_scraper.py -q
```

Result: **10 passed** (after the correction below; see next section for the one
intermediate failure hit along the way).

```
..........                                                               [100%]
10 passed in 1.51s
```

Full suite:

```
poetry run pytest -q
```

```
........................................................................ [ 23%]
........................................................................ [ 47%]
........................................................................ [ 70%]
............................................................xx.xx.xxx... [ 94%]
..................                                                       [100%]
299 passed, 7 xfailed in 3.67s
```

(The 7 xfails are the pre-existing `USER_AGENT_NOT_FORWARDED` grandfathered boards in
`test_scraper_contract.py`, unrelated to this change.)

`tests/test_scraper_contract.py` alone: 59 passed, 7 xfailed — JobStreet's
registration is still sound.

## The `test_does_not_return_the_same_job_twice` correction

Applied the fix specified in the task instructions: after `make_scraper([page, page])`,
set `scraper.jobs_per_page = 8` (matching the fixture's 8-record page) so the first
page counts as "full" rather than "short," forcing the loop to request page 2 and
genuinely feed duplicate ids through `seen_ids` — instead of the vacuous version where
`scrape` would break after page 1 (8 records < the real `jobs_per_page` of 100) and
page 2 would never be requested.

**A further wrinkle surfaced while implementing this**, not mentioned in the
correction note: with `jobs_per_page` overridden to exactly 8, page 2 (all duplicate
ids, 0 new jobs) is *also* not "short" (`len(records) == 8 == jobs_per_page`), so the
loop does not stop there either — it proceeds to request a third page. `FakeSession`
has only two queued pages, so that third call falls through to its
`search_empty.json` fallback, which finally terminates the loop via the
`if not records: break` path. So the corrected test genuinely makes **3** `session.get`
calls, not 2.

My first version of the assertion (`assert len(scraper.session.calls) == 2`) failed
against this real behavior:

```
E       AssertionError: assert 3 == 2
```

I fixed the assertion rather than the scraper (the brief's `scrape` body was
transcribed verbatim and is not in question here) to check what actually matters —
that page 1 and page 2 were both genuinely requested with the right `page` params,
which is the exact thing the correction exists to verify:

```python
scraper.jobs_per_page = 8
response = scraper.scrape(an_input(results_wanted=50))

ids = [job.id for job in response.jobs]
assert len(ids) == len(set(ids))
# Guards against the fix above silently regressing to the vacuous case: both
# duplicate pages must actually have been requested (page 1, then page 2). A
# third, empty-page request follows - a full 8-record page never looks
# "short" to the paging loop even when every id on it is a duplicate, so it
# probes page 3 before the empty fixture fallback stops it - but that
# trailing request isn't what this test is checking.
assert [call["params"]["page"] for call in scraper.session.calls[:2]] == [1, 2]
assert len(scraper.session.calls) >= 2
```

This asserts two pages were actually requested (guarding against the vacuous
single-call regression) without making a false claim about the total call count.

## Verification commands run

```
poetry run pytest tests/test_jobstreet_scraper.py -q   # RED, then GREEN
poetry run pytest -q                                    # full suite: 299 passed, 7 xfailed
poetry run pytest tests/test_scraper_contract.py -q     # 59 passed, 7 xfailed
poetry run black jobspy/jobstreet tests/test_jobstreet_scraper.py   # no changes needed
```

## Notes / constraints honored

- No fixtures added or modified; `jobspy/jobstreet/util.py` and existing tests
  untouched.
- Only `jobspy/jobstreet` and `tests/test_jobstreet_scraper.py` passed to black —
  the rest of the tree left alone.
- Imports consolidated into one block at the top of `jobspy/jobstreet/__init__.py`
  (the brief's Step 3 block plus its trailing `datetime`/`Country` additions), rather
  than appended as a second stray import block.
- `scrape()` never raises out on a bad page — request exceptions, 403, and other
  non-200s all log and `break`, returning whatever was already collected.
