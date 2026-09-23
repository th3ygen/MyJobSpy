# Task 6 Report: Wire the flag through scrape_jobs (JobStreet MY)

## Summary

Added `jobstreet_fetch_description: bool = False` to the `scrape_jobs` signature
(beside `linkedin_fetch_description` / `linkedin_company_ids`), documented it in
the docstring, and in `scrape_site` set it onto the constructed scraper via
`isinstance(scraper, JobStreet)` after construction — `ScraperInput` itself is
untouched, per the brief's constraint. Appended the two prescribed tests to
`tests/test_scrape_jobs_integration.py`.

## Files changed

- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\jobspy\__init__.py`
  - New kwarg `jobstreet_fetch_description: bool = False` in `scrape_jobs()` signature.
  - New docstring `:param jobstreet_fetch_description:` entry.
  - In `scrape_site()`, after `scraper = scraper_class(...)`:
    ```python
    if isinstance(scraper, JobStreet):
        scraper.fetch_description = jobstreet_fetch_description
    ```
- `C:\Users\USER\Desktop\dev\forks\MyJobSpy\tests\test_scrape_jobs_integration.py`
  - Appended `test_jobstreet_fetch_description_reaches_the_scraper`
  - Appended `test_jobstreet_fetch_description_defaults_to_false`

No other file was modified. `jobspy/jobstreet/` was not touched. No other
scraper's behavior was changed (the `isinstance` branch is additive and only
fires for `JobStreet` instances).

## TDD evidence

### RED

Command:
```
poetry run pytest tests/test_scrape_jobs_integration.py -k jobstreet -q
```

Output (before implementation, tests appended only):
```
F.                                                                       [100%]
================================== FAILURES ===================================
____________ test_jobstreet_fetch_description_reaches_the_scraper _____________
...
    jobspy.scrape_jobs(
        site_name=["jobstreet"],
        search_term="engineer",
        jobstreet_fetch_description=True,
    )
>       assert seen["fetch_description"] is True
E       assert False is True

tests\test_scrape_jobs_integration.py:470: AssertionError
---------------------------- Captured stderr call -----------------------------
2026-09-23 21:52:52,532 - INFO - JobSpy:Jobstreet - finished scraping
2026-09-23 21:52:52,533 - INFO - JobSpy:Jobstreet - finished scraping
=========================== short test summary info ===========================
FAILED tests/test_scrape_jobs_integration.py::test_jobstreet_fetch_description_reaches_the_scraper
1 failed, 1 passed, 18 deselected in 0.18s
```

Why this is the expected failure: `scrape_jobs` did not yet accept
`jobstreet_fetch_description` as a named parameter, so it silently landed in
`**kwargs` and was discarded — `JobStreet.fetch_description` stayed at its
Task-5 default of `False`, so the "reaches the scraper" test (which asserts
`True`) failed while the "defaults to False" test passed trivially (nothing
was wired yet, so the default held by coincidence, not by the new code path).

### GREEN

Command:
```
poetry run pytest tests/test_scrape_jobs_integration.py -q
```

Output (after implementation):
```
....................                                                     [100%]
20 passed in 0.16s
```

### Full suite

Command:
```
poetry run pytest -q
```

Output:
```
........................................................................ [ 23%]
........................................................................ [ 46%]
........................................................................ [ 69%]
...................................................................xx.xx [ 92%]
.xxx.....................                                                [100%]
306 passed, 7 xfailed in 4.14s
```

306 passed, 7 xfailed (the pre-existing `USER_AGENT_NOT_FORWARDED` grandfathered
xfails in the scraper contract test — unrelated to this change, unchanged in
count). No new failures, no new xfails, no skips. Confirms the shared
orchestration change did not regress any of the other eight boards.

## Formatting

```
poetry run black jobspy/__init__.py tests/test_scrape_jobs_integration.py
```
Output: `All done! ... 2 files left unchanged.` — both files already matched
Black's 88-column style after the edits, so no reformatting was applied (and no
other files were touched by the formatter).

## Self-review

- Diff reviewed with `git diff -- jobspy/__init__.py tests/test_scrape_jobs_integration.py`
  before committing: the change is exactly the three snippets from the brief,
  inserted in place, with nothing reordered or rewritten elsewhere in either
  file.
- `ScraperInput` was not touched — confirmed by diff (no changes near the
  `ScraperInput(...)` construction other than what already existed).
- `isinstance(scraper, JobStreet)` resolves `JobStreet` through the module
  global inside `scrape_site`, which a test's `monkeypatch.setattr(jobspy,
  "JobStreet", FakeJobStreet)` replaces before the closure runs — verified by
  the passing `FakeJobStreet(jobspy.JobStreet)` subclass test.
- No other scraper's construction/dispatch path changed; the new lines are a
  single additive `if` block.
- YAGNI: no ScraperInput field added, no new module-level helper, no changes
  beyond the three call sites named in the brief.

## Commit

```
b86eead feat: expose jobstreet_fetch_description on scrape_jobs
 2 files changed, 45 insertions(+)
```
