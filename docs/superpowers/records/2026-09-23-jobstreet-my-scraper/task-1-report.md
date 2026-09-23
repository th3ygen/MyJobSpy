# Task 1 Report: Register the board (JobStreet MY)

## Status: DONE

## Summary

Registered JobStreet Malaysia as a ninth board: `Site.JOBSTREET`, `JobStreetException`,
a minimal `jobspy/jobstreet/` package (`__init__.py` with a `JobStreet(Scraper)` stub
whose `scrape()` raises `NotImplementedError`, and `constant.py` with endpoints/headers/
vocab maps for later tasks), and wiring into `SCRAPER_MAPPING` + `DEFAULT_SITES` in
`jobspy/__init__.py`. `scrape()` itself is out of scope for this task (Task 4).

## Files changed

- `jobspy/model.py` — added `JOBSTREET = "jobstreet"` to `Site` enum.
- `jobspy/exception.py` — appended `JobStreetException`.
- `jobspy/__init__.py` — added `from jobspy.jobstreet import JobStreet` (alphabetical,
  beside `Indeed`/`LinkedIn`), added `Site.JOBSTREET` to `DEFAULT_SITES` and
  `SCRAPER_MAPPING`.
- `jobspy/jobstreet/__init__.py` (new) — `JobStreet(Scraper)`, forwards `proxies`,
  `ca_cert`, `user_agent` to `super().__init__` and sets a plain `requests` session
  (`is_tls=False`) since JobStreet's JSON API doesn't fingerprint TLS.
- `jobspy/jobstreet/constant.py` (new) — `BASE_URL`, `SEARCH_URL`, `GRAPHQL_URL`,
  `SITE_KEY`, `SOURCE_SYSTEM`, `JOBS_PER_PAGE`, `DESCRIPTION_WORKERS`, `headers`,
  `REMOTE_ARRANGEMENT`, `WORK_TYPE_MAP`, `WORK_TYPE_IDS`, `JOB_DETAILS_QUERY` —
  transcribed verbatim from the brief for use by later tasks.
- `tests/test_scrape_jobs_integration.py` — updated
  `test_default_sites_are_malaysia_relevant` to expect
  `{"indeed", "linkedin", "google", "jobstreet"}`. This test asserted on the
  pre-JobStreet `DEFAULT_SITES` set; per the ambiguity resolution in my task
  instructions (spec decision 10: JobStreet joins the defaults by design), I
  updated the test rather than reverting the `DEFAULT_SITES` change.

## TDD evidence

**Step 1 — baseline before any change** (`tests/test_scraper_contract.py -q`):

```
52 passed, 7 xfailed in 2.54s
```

**Step 3 — after adding `Site.JOBSTREET` but before registering the board**,
watching the guard fail (`tests/test_scraper_contract.py::test_every_site_has_a_scraper -q`):

```
FAILED tests/test_scraper_contract.py::test_every_site_has_a_scraper - AssertionError: Site members with no SCRAPER_MAPPING entry: ['jobstreet']
1 failed in 0.15s
```

This matches the brief's expected failure exactly.

**Step 8 — after full registration** (`tests/test_scraper_contract.py -q`):

```
59 passed, 7 xfailed in 2.43s
```

Seven more passing checks (one board x seven per-board contract tests), xfail
count unchanged at 7 — confirms `user_agent` reaches `super().__init__`
correctly and JobStreet was **not** added to `USER_AGENT_NOT_FORWARDED`.

**Step 9 — full suite** (`pytest -q`):

First run surfaced the anticipated `DEFAULT_SITES`-count assertion:

```
FAILED tests/test_scrape_jobs_integration.py::test_default_sites_are_malaysia_relevant
1 failed, 265 passed, 7 xfailed in 3.26s
```

After updating that test's expected set to include `"jobstreet"`:

```
266 passed, 7 xfailed in 2.37s
```

(259 baseline + 7 new contract checks = 266, consistent with the plan.)

## Formatting

`poetry run black jobspy/jobstreet` — "2 files left unchanged" (already
88-column compliant, transcribed verbatim from the brief). Did not run
`black jobspy tests` repo-wide, per the global constraint.

## Test file touched (per ambiguity resolution)

`tests/test_scrape_jobs_integration.py::test_default_sites_are_malaysia_relevant`
— updated the expected `DEFAULT_SITES` set to add `"jobstreet"`, since the
default genuinely changed by design and the test was asserting the old default.
`DEFAULT_SITES` itself was left as specified in the brief (unchanged, not reverted).

## Self-review notes

- Diff is minimal: 4 files modified (22 insertions, 4 deletions) + 2 new files,
  matching brief scope exactly. No unrelated reformatting.
- `git diff` confirms the pre-existing "No newline at end of file" warning on
  `jobspy/exception.py` predates this change (BDJobsException already lacked a
  trailing newline); my new `JobStreetException` block is appended correctly
  and picks up the same trailing-newline characteristic — not a regression I
  introduced, matches file's existing state.
- Import placed alphabetically among the other per-site imports in
  `jobspy/__init__.py`, consistent with existing style.
- No new `JobPost` fields added, so no `desired_order` change needed (matches
  Global Constraints).
- Verified `self.user_agent` non-None path is honoured (`if user_agent: self.session.headers["user-agent"] = user_agent`), matching the pattern the contract test checks for non-grandfathered boards.

## Commit

`d1bd9dd` — "feat: register JobStreet MY as a board"
(6 files changed, 128 insertions(+), 4 deletions(-))
