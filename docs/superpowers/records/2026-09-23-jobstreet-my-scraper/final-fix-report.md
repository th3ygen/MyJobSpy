# Final fix wave report — feat/jobstreet-my

Applied against `79875e1` (branch tip at the start of this wave). All nine
findings addressed; none skipped. Full offline suite: **328 passed, 2
deselected, 7 xfailed** (up from 317/2/7 — the delta is exactly the new
tests added below, confirmed by counting).

## F1 — 403 on GraphQL description fetch (Important, safety) — FIXED

**File:** `jobspy/jobstreet/__init__.py`

`_fetch_description` now takes a shared `threading.Event`. It checks the
event before doing anything; a 403 response sets the event and returns
`None` without raising or retrying. `_add_descriptions` creates one
`threading.Event()` per call and passes it to every worker via `fill()`, so
the first 403 seen by any of the (up to `DESCRIPTION_WORKERS`) concurrent
workers stops the rest — they check the event before issuing their own
request. No backoff, no retry, matching the search loop's existing 403
handling.

Also corrected the two false documentation claims named in the finding, plus
the `JobStreet` class docstring which made the same false claim:
- `CLAUDE.md`: "the scraper only ever calls the JSON search API" →
  now describes both the search API and the GraphQL endpoint, and how a 403
  on each is handled.
- `README.md`: "Its HTML job pages return 403 ... the scraper treats a 403
  as a block" → reworded to describe the two endpoints actually used
  (search API + GraphQL), both Cloudflare-fronted; the HTML-page mention is
  now parenthetical context, not the subject of the block-handling claim.
- `jobspy/jobstreet/__init__.py` class docstring: same correction.

**Test added:** `tests/test_jobstreet_scraper.py::TestDescriptions::test_a_403_stops_further_description_fetches`.
Monkeypatches `jobspy.jobstreet.DESCRIPTION_WORKERS` to 1 (so the
`ThreadPoolExecutor` processes jobs one at a time, making the outcome
deterministic instead of racy across 5 real threads) and a fake session that
always returns 403 on `POST /graphql`. Asserts exactly one GraphQL request
is made across 5 jobs, and all 5 keep their teaser as `description`.

**Command:** `poetry run pytest tests/test_jobstreet_scraper.py -q` → passed.

## F2 — No user-agent header (Important) — FIXED

**File:** `jobspy/jobstreet/constant.py`

Added a desktop Chrome `user-agent` to the `headers` dict, matching the
convention of every sibling scraper (`indeed`, `linkedin`, `google`, etc.).
`JobStreet.__init__`'s existing override (`if user_agent: self.session.headers["user-agent"] = user_agent`)
was left untouched, so a caller-supplied `user_agent` still wins — verified
by the existing (still-passing) contract test
`test_forwards_user_agent_to_super[jobstreet]`, which is not in
`USER_AGENT_NOT_FORWARDED` (confirmed: 7 xfailed, jobstreet not among them).

## F3 — is_remote starves results_wanted (Important) — FIXED

**File:** `jobspy/jobstreet/__init__.py`, `jobspy/jobstreet/constant.py`

Moved the `is_remote` filter inline into the per-record loop (was: filter
applied to the whole `jobs` list after the paging loop ended). The
while-loop's `len(jobs) < wanted` now counts *post-filter* jobs, so paging
continues past a full-but-mostly-non-remote page instead of stopping as
soon as enough unfiltered jobs exist.

Added `MAX_REMOTE_PAGES = 20` in `constant.py` and a matching check at the
top of the loop, **scoped to `scraper_input.is_remote`**: `if
scraper_input.is_remote and page > MAX_REMOTE_PAGES: break`. This does not
touch the do-not-touch item "a MAX_PAGES ceiling on the main paging loop" —
that item, read in context, is about an unconditional cap applied to every
search (non-remote included), which would be a broader change than this
finding asked for. The cap added here only ever fires when the caller is
actively filtering for remote jobs — the specific failure mode this finding
describes, since normal (non-remote) searches already terminate correctly
via the pre-existing short-page/empty-page/non-200 conditions and are
untouched by this change. **Flagging this reasoning explicitly** since it
sits right next to an item on the do-not-touch list — happy to be
overruled in review if the two were meant to be read as the same thing.

**Tests added** (`tests/test_jobstreet_scraper.py::TestIsRemoteFiltering`):
- `test_keeps_paging_past_a_full_first_page`: a full first page (8/8
  records, only 1 remote) must not stop paging; asserts >=2 requests were
  made and only the genuinely-remote job survives.
- `test_stops_at_the_page_cap_when_nothing_matches`: `MAX_REMOTE_PAGES + 5`
  full pages supplied, zero-or-near-zero remote matches; asserts the scraper
  stops at exactly `MAX_REMOTE_PAGES` requests rather than exhausting the
  supply or looping indefinitely.

**Command:** `poetry run pytest tests/test_jobstreet_scraper.py tests/test_scraper_contract.py -q`
→ passed, plus full suite run below.

## F4 — Unreproducible salary figure (Important) — FIXED (preferred option)

**Files:** `jobspy/baseline/metrics.py`, `README.md`, `CLAUDE.md`,
`tests/test_baseline_metrics.py`

Implemented the preferred fix: `BaselineMetrics.salary_fill_rate_by_site`
(new field) and `_fill_rate_by_site()` (new helper, mirrors `_fill_rate`
grouped by `site`), wired into `compute_metrics()` and rendered as a new
"## Salary fill rate by site" section in `render_report()`. Did **not**
regenerate any committed baseline report, per instructions — the next real
`poetry run python -m jobspy.baseline.runner` run will render the new
per-site column against live data.

Corrected the unreproducible "61.5% / 66.67%" figures in both `README.md`
and `CLAUDE.md`. Since no committed baseline report breaks salary fill out
by site (that's the whole gap F4 identifies), I could not cite an exact
JobStreet-only number from committed data. Instead I derived and clearly
labeled an approximation from the two committed reports that do exist:
`docs/baseline/2026-09-23-baseline-phase1-corrected.md` (424 rows, no
JobStreet, 21.5% fill) and `docs/baseline/2026-09-23-baseline-jobstreet.md`
(584 rows, 156 of them JobStreet, 29.1% fill). The jump in filled rows
between the two (≈+79) attributed to JobStreet's 156 rows works out to
**≈50%**, which is what both docs now say, explicitly flagged as an
approximation rather than a precise per-site measurement, with a pointer to
the new metric for the next real run. Verified no remaining "61.5%" /
"66.67%" / "62-67%" strings anywhere in the repo (`grep`, zero hits).

**Tests added** (`tests/test_baseline_metrics.py`, synthetic DataFrames,
fully offline):
- `test_salary_fill_rate_by_site`: two sites with different fill rates (100%
  and 0%) both come out correctly, and the blended rate (50%) is confirmed
  distinct from either site's own number.
- `test_salary_fill_rate_by_site_is_empty_without_a_site_column`.
- `test_render_report_includes_salary_fill_by_site`: checks the new section
  header and both site rows appear in rendered markdown.

**Command:** `poetry run pytest tests/test_baseline_metrics.py -q` →
passed. Baseline runner was **not** invoked (per explicit instruction).

## F5 — False behaviour comments (Important, comment-only) — FIXED

**File:** `jobspy/jobstreet/__init__.py`. No behaviour changed.

- The `sortmode` comment ("Newest-first lets paging stop as soon as it
  crosses the cutoff") was replaced with a comment describing the real
  effect: sorting makes the *set* of returned jobs consistent across
  repeated searches for a given `hours_old`; there is no early-exit on date
  anywhere in the loop.
- `_within_age`'s docstring was rewritten to state plainly that it
  recomputes the same day-granular `daterange` value already sent to the
  board, that `date_posted` has already lost its time-of-day, and that in
  practice `hours_old=6` behaves like `hours_old=24` (~48h of real slack).
  It also names what the method actually buys today (a defensive re-check),
  and notes that genuine hour precision is out of scope here (that's the
  do-not-touch item). Code unchanged.

## F6 — `_key()` deletes delimiters instead of splitting on them (Important) — FIXED, with an honest limitation

**File:** `jobspy/malaysia/location.py`

`_key()` now maps `/`, `&` and `-` to a space *before* the punctuation
strip, then collapses any resulting repeated whitespace. This fixes the
general class of bug: a board using a delimiter where the canonical name
has a space (`"Petaling-Jaya"`, `"Petaling/Jaya"`, `"Petaling&Jaya"`,
`"Petaling - Jaya"`) now resolves correctly to the registered two-word
gazetteer key, instead of fusing into an unmatchable single token
(`"petalingjaya"`).

**Important finding-vs-code discrepancy I want to surface explicitly:** I
verified empirically (`_GAZETTEER.get(_key("Klang/Port Klang"))`) that the
specific example named in the finding does **not** actually resolve under
this fix, before or after. `_lookup()` is a single exact `dict.get()` on the
whole normalized string — there is no per-word/segment fallback anywhere in
`location.py`. `"Klang/Port Klang"` normalizes to the three-token string
`"klang port klang"`, which is not itself a registered gazetteer key; only
`"klang"` and `"port klang"` are, separately, as two independently
registered places (Klang town and its port). The finding's fix
("map `[/&-]` to a space before the strip") does not bridge that gap — it
only helps when the delimiter stands in for the single missing space inside
one two-word name that *is* registered whole, which "Klang/Port Klang" is
not.

I implemented exactly the described fix (root-cause, in `_key()`, no new
alias for the specific string — consistent with the explicit "do not add a
Klang/Port Klang alias" instruction) and did **not** additionally build a
segment-splitting fallback lookup, since that's a materially larger design
change than "map a delimiter to a space" and isn't something the finding
authorized. I added a test
(`test_slash_joined_dual_locality_still_does_not_resolve`) that pins this
real, current behavior honestly (state stays `None`, `unmatched` is
recorded) rather than asserting something false. I did not write anywhere
that "Klang/Port Klang" now resolves.

**Tests added** (`tests/malaysia/test_location.py`):
- `test_delimiter_joined_two_word_city_resolves` (parametrized over `-`,
  `/`, `&`, and `" - "` with spaces): all four resolve to `Petaling Jaya` /
  `Selangor`.
- `test_slash_joined_dual_locality_still_does_not_resolve`: pins the
  limitation above.

**Command:** `poetry run pytest tests/malaysia -q` → all passed, including
every pre-existing gazetteer test (confirms no regression). Full suite run
below.

## F7 — Test that cannot fail (Important) — FIXED

**Files:** `tests/fixtures/jobstreet/search_page.json`,
`tests/fixtures/jobstreet/README.md`, `tests/test_jobstreet_pipeline.py`

Confirmed the finding's diagnosis: none of the 8 real teasers in
`search_page.json` contained a parseable MYR figure, so removing the
`if job.compensation is not None: return` guard in
`jobspy/malaysia/__init__.py` changed neither assertion in
`test_board_salary_is_not_overwritten_by_the_description_parser`.

Hand-edited record `94689504`'s `teaser` (via a small Python script, to
avoid corrupting the fixture's real non-breaking-space/en-dash characters)
to append: `" Entry-level hires may start from RM 3,000 per month."` This
gives that record two disagreeing salary signals: `salaryLabel` → RM
5,000–7,500/month (board), teaser → RM 3,000/month (parseable by
`parse_myr_salary`). With the guard in place, `compensation` stays at the
board's 5000; with the guard removed, it would flip to 3000 and
`salary_parsed_from_description` would flip to `True` — both assertions in
the test now actually discriminate.

Documented the deviation in `tests/fixtures/jobstreet/README.md` (a new
paragraph explaining what changed, why, and dated) per the finding's
instruction. Also strengthened the test's docstring and added a guard
assertion (`before["js-94689504"] == 5000`) that fails loudly with a clear
message if the fixture drifts again in a way that silently makes the test
vacuous.

**Command:** `poetry run pytest tests/test_jobstreet_pipeline.py -q` →
passed. Manually verified the "cannot fail" claim is now false by
temporarily commenting out the guard in `jobspy/malaysia/__init__.py` and
confirming `test_board_salary_is_not_overwritten_by_the_description_parser`
fails (then reverted — this was not committed).

## F8 — parse_is_remote's None branch never asserted (Minor) — FIXED

**File:** `tests/test_jobstreet_util.py`

Added `assert job.is_remote is None` to
`TestMalformedRecords::test_unparseable_date_leaves_field_unset` (fixture
`90000005`, which has `workArrangements: {"data": []}`), with a comment
explaining why this record specifically exercises the empty-list branch as
opposed to the missing-key branch every other malformed-record test
exercises incidentally.

## F9 — Small cleanups (Minor) — ALL FIXED

- `jobspy/exception.py`: added the missing trailing newline. (Left the rest
  of the file's pre-existing style — the missing space in
  `NaukriException.__init__(self,message=None)` and the missing blank line
  before that class — untouched: those predate this branch and are outside
  this file's one-line fix; reformatting them would be exactly the kind of
  unrelated churn the "black only on files you touch" rule is meant to
  avoid.)
- `tests/test_jobstreet_scraper.py`: removed the unused `import pytest`.
- `tests/test_jobstreet_scraper.py`: closed up the three stray blank lines
  splitting a docstring summary mid-sentence (the `test_strips_a_trailing_malaysia_suffix_from_where`,
  `test_does_not_strip_a_bare_country_search_to_empty`, and
  `test_does_not_reduce_a_comma_with_no_city_to_an_empty_where` docstrings).
- `README.md`: added `jobstreet_fetch_description` to the parameter
  reference block, matching the existing `linkedin_fetch_description` entry
  in shape and content.
- `jobspy/jobstreet/__init__.py`: `easy_apply` now logs
  `"JobStreet has no easy-apply filter; easy_apply is ignored"` (info level,
  matching `distance`'s existing convention) instead of being silently
  dropped.
- `tests/test_jobstreet_scraper.py::test_does_not_return_the_same_job_twice`:
  monkeypatches `jobspy.jobstreet.time.sleep` to a no-op. Full suite now
  runs in ~1.6s (was ~2.1s+ with the real sleep), matching CLAUDE.md's
  advertised "~2s".

## Do-not-touch list — verified untouched

Diffed against the explicit list: the `scrape_jobs`/`scrape_site` kwarg
refactor and `site_display` capitalize-fixup, the `jobspy/util.py`
proxy-rotation race, `_within_age` hour-precision (only its docstring
changed), an under-contribution guard beyond F4's per-site metric,
description-converter try/except placement, `test_state_survives_normalization`'s
dual-path redundancy, `parse_myr_salary`'s RM30,000 ceiling, a general
`MAX_PAGES` ceiling on the main loop (see the F3 note above for why
`MAX_REMOTE_PAGES` is scoped differently and not a violation), assertions
for `company_url`/`company_logo`/`job_function`, and stamping the queried
board list into the baseline report header — none of these were modified.

## Full verification

```
poetry run pytest -q
```
```
328 passed, 2 deselected, 7 xfailed in 1.61s
```

```
poetry run pytest tests/test_scraper_contract.py -q -rx
```
```
59 passed, 7 xfailed in 1.22s
```
(7 xfails are the same pre-existing `USER_AGENT_NOT_FORWARDED` set —
`bayt`, `bdjobs`, `google`, `indeed`, `linkedin`, `naukri`, `zip_recruiter`;
`jobstreet` is not among them.)

Black run only on files touched in this wave (never the whole `jobspy
tests` tree): `metrics.py`, `jobstreet/__init__.py`, `jobstreet/constant.py`,
`malaysia/location.py`, `test_location.py`, `test_baseline_metrics.py`,
`test_jobstreet_pipeline.py`, `test_jobstreet_scraper.py`,
`test_jobstreet_util.py` — all report "would be left unchanged" after
formatting fixes were applied to the two spots black flagged in my own new
code (a docstring's leading quote, one long line). `exception.py` was
**not** run through black beyond the manual one-line trailing-newline
addition, to avoid reformatting pre-existing, unrelated code in that file
(see F9 note above).

Live tests and the baseline runner were **not** run, per instructions —
nothing in this wave required it, and the two live-affecting layers
(`@pytest.mark.live`, `jobspy.baseline.runner`) remain untouched in
behavior beyond the metrics changes described in F4.
