# Final review fix wave — findings to fix

Whole-branch review of `feat/jobstreet-my` (2ce699c..79875e1) returned
**Ready with follow-ups**: no Criticals, 7 Important, 8 Minor, plus triage of 9
deferred items.

This is the **one** fix wave. Items not listed here are deliberately deferred to
follow-up work and must not be touched.

Ordering below is by priority. F1 is the only one with a real safety
consequence; do it first and do it carefully.

---

## F1 — `_fetch_description` hammers a 403 five workers at a time (Important)

**Files:** `jobspy/jobstreet/__init__.py`, `CLAUDE.md:86`, `README.md:68`

The search loop treats a 403 as terminal and stops (`__init__.py:228-233`). The
GraphQL description path does not: `_fetch_description` never inspects
`response.status_code`. On a 403 the body fails `.json()`, the exception is
swallowed as a warning, and the next of up to 5 concurrent workers immediately
issues another request — **one 403 per selected job, five at a time.**

That is exactly the ban-earning pattern this branch's own documentation claims
to avoid, against a Cloudflare-fronted endpoint that robots.txt disallows.

**Fix:** check for `403` in `_fetch_description` and set a run-level stop flag
that `_add_descriptions` honours, so the first 403 ends description fetching for
that run and remaining jobs keep their teaser. Do not retry, do not back off and
continue — stop. Add an offline test with a fake session returning 403 that
asserts only one GraphQL request is made and all jobs survive with teasers.

**Two documentation claims are false and must be corrected in the same change:**
- `CLAUDE.md:86` says *"The scraper only ever calls the JSON search API"* — it
  does not; `_fetch_description` POSTs to `my.jobstreet.com/graphql`.
- `CLAUDE.md:86` says the 403 rule covers the scraper; it covered only the
  search loop. After your fix it will be true of both — say "search API and
  GraphQL" explicitly.
- `README.md:68` says *"Its HTML job pages return 403 … the scraper treats a 403
  as a block"*. The scraper never requests an HTML job page. Reword so the
  statement is about the endpoints actually used.

## F2 — No `user-agent` header (Important)

**File:** `jobspy/jobstreet/constant.py:29-33`

All eight sibling scrapers set a browser user-agent in their headers constant.
JobStreet sends `python-requests/x.y` to a Cloudflare-fronted endpoint. It works
today, and it is the single most likely cause of the 403 the docs are braced
for — and this file is the template four more boards get copied from.

**Fix:** add a browser `user-agent` to the `headers` dict, matching the
convention the sibling scrapers use. Note that `JobStreet.__init__` already
overrides it when the caller passes `user_agent`; keep that behaviour.

## F3 — `is_remote` starves `results_wanted` on every default scrape (Important)

**File:** `jobspy/jobstreet/__init__.py:217, 257-258`

The client-side remote filter runs *after* paging, while the paging loop counts
unfiltered jobs. So `results_wanted=50, is_remote=True` stops after one
100-record page and then filters down to whatever fraction happens to be remote
— typically a handful — while hundreds more sit deeper in the result set.

This is not an edge case: `scrape_jobs` appends an `is_remote=True` pass for
every Malaysian run because `include_remote` defaults to True, so it fires on
every default scrape, and it is baseline search #4.

**Fix:** page until enough *post-filter* jobs are collected, with a page cap so
a search with no remote jobs cannot page forever. Add offline tests: one
asserting a remote-filtered search keeps paging past the first page, and one
asserting the cap terminates when nothing matches.

## F4 — Published salary figure is not reproduced by the committed measurement (Important)

**Files:** `README.md:92`, `CLAUDE.md:85`, and optionally `jobspy/baseline/metrics.py`

Both cite "61.5% over a 52-job sample, 66.67% on a 24-job smoke test". Neither
is a committed artifact. The committed baseline is, and it implies roughly half
that: 424 rows @ 21.5% → 584 rows @ 29.1% means ~78 of JobStreet's 156 rows
carried salary, i.e. **≈50%** — on the largest sample taken.

The report cannot show this directly because `metrics.py` computes no per-site
salary fill.

**Fix (preferred):** add per-site salary fill to the metrics and
`render_report`, then cite the committed baseline's own number. This also gives
the under-contribution guard something to key on later.

**Fix (minimum, if the above proves large):** widen the quoted range so it
honestly spans the baseline result, and say which sample each figure came from.

Do not quote a number you cannot point at in a committed file.

## F5 — Two comments assert behaviour that does not exist (Important)

**File:** `jobspy/jobstreet/__init__.py:128, 137-144`

Comment-only fixes. Do not change behaviour.

- `:128` — *"Newest-first lets paging stop as soon as it crosses the cutoff"*.
  The loop has no cutoff break; it exits on `len(jobs) >= wanted`, a short page,
  an empty page, or a non-200. Say what sorting by date actually buys.
- `:137-144` — `_within_age`'s docstring claims it "applies the exact
  `hours_old` cutoff the day-granular filter cannot". It cannot: it recomputes
  the *same* `ceil(hours_old/24)` already sent as `daterange`, and
  `parse_date_posted` discards the timestamp via `.date()` anyway. Net effect is
  that `hours_old=6` returns postings up to ~48h old.

  Correct the docstring to describe the real behaviour, and add a short note
  that hour-level precision would require keeping the timestamp. **Leave the
  code alone** — that is a follow-up.

## F6 — `_key()` deletes `/` instead of splitting on it (Important)

**File:** `jobspy/malaysia/location.py:34-36`

`re.sub(r"[^a-z0-9 ]+", "", …)` deletes the slash, so `"Klang/Port Klang"`
becomes `"klangport klang"` and matches nothing — even though **both** `"Klang"`
and `"Port Klang"` are already in the gazetteer (`location.py:95,109`).

Fix the root cause, not the symptom: map `[/&-]` to a space before the strip, so
slash-joined dual localities resolve. Do **not** add a `"Klang/Port Klang"`
alias — that papers over a defect that will hit every slash-joined locality the
next four boards emit.

Add covering tests under `tests/malaysia/`, following the patterns already
there. This is shared code every board uses, so run the full suite and confirm
no existing gazetteer test regresses.

## F7 — A test that cannot fail (Important)

**File:** `tests/test_jobstreet_pipeline.py:35-45`

`test_board_salary_is_not_overwritten_by_the_description_parser` is the test the
file's own docstring nominates as what makes the architectural claim
falsifiable. It cannot fail: none of the 17 teasers across the fixtures contains
a parseable MYR figure, so deleting the `if job.compensation is not None:
return` guard in `jobspy/malaysia/__init__.py:33` changes neither assertion.

This is the fourth instance on this branch of a test passing for a reason
unrelated to what it claims to check.

**Fix:** make the test genuinely discriminating — give one fixture record's
`teaser` an RM figure that differs from its `salaryLabel`, so removing the guard
would visibly change the parsed amount. If you modify a fixture, note it in
`tests/fixtures/jobstreet/README.md` so the file stays an accurate record of
what each fixture is for and why it deviates from raw capture.

The invariant *is* covered non-vacuously elsewhere
(`tests/malaysia/test_pipeline.py:84-96`), so this is a mislabelled redundant
test rather than a coverage hole — but it should either discriminate or stop
claiming to.

## F8 — `parse_is_remote`'s None branch is never asserted (Minor, one line)

**File:** `tests/test_jobstreet_util.py`

Fixture `90000005` has `workArrangements: {"data": []}` and `90000001-4/6` omit
the key, so the branch executes six times per run and is asserted zero times.
Add an assertion in `TestMalformedRecords` that `is_remote is None` there.

## F9 — Small cleanups (Minor)

- `jobspy/exception.py` — no trailing newline. The branch moved the
  `\ No newline at end of file` marker rather than fixing it. Add the newline.
- `tests/test_jobstreet_scraper.py:12` — unused `import pytest`. Remove.
- `tests/test_jobstreet_scraper.py:169,181,199,216` — stray blank line splitting
  a docstring summary mid-sentence. Close them up.
- `README.md` — `jobstreet_fetch_description` is missing from the parameter
  reference, though `linkedin_fetch_description` is documented at `:167`. A user
  reading that block cannot discover the new kwarg. Add it.
- `jobspy/jobstreet/__init__.py` — `easy_apply` is dropped silently, while
  `distance` logs and a non-MY `country` warns. Log it too, for consistency with
  the board's own stated convention of making ignored filters observable.
- `tests/test_jobstreet_scraper.py` — `test_does_not_return_the_same_job_twice`
  spends a measured 1.22s in real `time.sleep` (two `random.uniform(0.5, 1.5)`
  waits), over a third of the suite runtime CLAUDE.md advertises as "~2s".
  Monkeypatch `time.sleep` in that test.

---

## Explicitly NOT in this wave — do not touch

These were triaged as follow-ups. Changing them here would make this wave
unreviewable:

- The `isinstance` kwarg-sprawl refactor in `scrape_jobs` / `scrape_site`, and
  the related `site_display` capitalize-fixup that gives JobStreet an
  inconsistent logger name. This is the next task, done properly, before board #2
  copies the pattern.
- The proxy-rotation race in `jobspy/util.py` — shared code, needs its own
  change and its own test.
- Making `_within_age` genuinely hour-precise (keeping the timestamp through
  `parse_date_posted`). F5 fixes only the false docstring.
- An under-contribution guard in `jobspy/baseline/runner.py` / `metrics.py`
  beyond the per-site salary fill that F4 may add.
- Moving the description converters inside the try/except.
- `test_state_survives_normalization`'s dual-path redundancy.
- `parse_myr_salary`'s RM30,000 monthly ceiling silently dropping legitimate
  high board-vouched salaries.
- A `MAX_PAGES` ceiling on the main paging loop.
- Adding assertions for `company_url` / `company_logo` / `job_function`.
- Stamping the queried board list into the baseline report header.
