# Task 9 report: Measure, then document (JobStreet MY)

---

## Fix round 2 (review findings on fix round 1)

Review of fix round 1 came back Approved with two Important findings, both
about the same few lines in `_strip_country_suffix`. No baseline or live
test was run for this round, per the coordinator's instruction — neither
finding could affect them, and both are offline-testable.

### Finding A — the emptiness guard was untested; its test passed for the wrong reason

`_COUNTRY_SUFFIX_RE = r",\s*(?:malaysia|my)\s*$"` requires a leading comma.
`location="Malaysia"` has no comma, so the regex never matches at all —
`stripped == where.strip()` and the function falls through to the final
`return where.strip()` line untouched. The `if stripped and ...` emptiness
check is never what protects that input; no existing test drove `stripped`
to `""`, so the guard branch was dead as far as the suite could tell.

Fix: added `test_does_not_reduce_a_comma_with_no_city_to_an_empty_where` in
`tests/test_jobstreet_scraper.py`, using `location=", Malaysia"` — a comma
with no city, which the regex matches across its entire length, driving
`stripped` to `""` and forcing the emptiness check to actually fire. Verified
first that the assertion needed to be "unchanged, returns `', Malaysia'`
as-is" (not some other sanitized form) by reading what the guard's `return
where.strip()` fallback actually does with that input, rather than asserting
a result I hadn't confirmed.

Also amended the docstring on the existing `test_does_not_strip_a_bare_country_search_to_empty`
to say plainly that it pins real, valuable behaviour but is not a test of
the emptiness guard, and points at the new test for the input that is.

### Finding B — the function's docstring named the wrong mechanism

The docstring said the function "only strips when a non-empty remainder
survives: location='Malaysia' on its own is a legitimate nationwide search
and must not be reduced to an empty `where`" — implying the emptiness check
is what keeps a bare "Malaysia" query safe. It isn't: the regex's comma
requirement is what does that, by never matching in the first place. The
emptiness check is a separate, secondary guard for the pathological
comma-with-no-city case.

Fix: rewrote the docstring in `jobspy/jobstreet/__init__.py` to state both
mechanisms and which input each one covers — the comma requirement protects
`"Malaysia"` by never matching it, and the emptiness check is a secondary
net for `", Malaysia"` (matches, would otherwise reduce `where` to `""`, so
the original text is returned unstripped instead). No behavioural change,
docstring only.

### Commands and output

```
poetry run pytest tests/test_jobstreet_scraper.py -v
```
→ `21 passed in 2.16s` (20 before this round + 1 new: `test_does_not_reduce_a_comma_with_no_city_to_an_empty_where`)

```
poetry run pytest -q
```
→ `317 passed, 2 deselected, 7 xfailed in 3.57s` (316 before this round; still 7 xfailed, not 8)

### Files touched, this round

- `jobspy/jobstreet/__init__.py` — docstring only, no behavioural change.
- `tests/test_jobstreet_scraper.py` — one new test, one docstring amendment
  on an existing test.

No baseline re-run, no other files touched.

## Fix round 1 (coordinator-directed, after this task's original report)

The coordinator verified the location-suffix finding live and it was broader
than my diagnostic showed: every suffixed `where` value returns zero
(`"Kuala Lumpur, Malaysia"`, `"Selangor, Malaysia"`, `"Penang, Malaysia"` all
0; `"Kuala Lumpur"` alone 1239, `"Malaysia"` alone 2760). Since "City,
Malaysia" is this fork's own documented convention (README usage example,
parameter docs, three of four baseline searches, `examples/`) and JobStreet
is now in `DEFAULT_SITES`, this is a shipped defect — a user following the
README gets a silent empty JobStreet result — not a harness quirk. The
coordinator narrowly unfroze `jobspy/jobstreet/__init__.py` for this fix
only.

### Fix 1 — strip a trailing country suffix in `_build_params`

Added to `jobspy/jobstreet/__init__.py`:

- `_COUNTRY_SUFFIX_RE = re.compile(r",\s*(?:malaysia|my)\s*$", re.IGNORECASE)`
- `_strip_country_suffix(where: str) -> str`, a module-level helper that:
  - strips a trailing `, Malaysia` or `, MY` (case-insensitive, tolerant of
    whitespace around the comma),
  - only returns the stripped form when a non-empty remainder survives —
    `location="Malaysia"` alone stays `"Malaysia"` rather than collapsing to
    an empty `where` (verified live: `"Malaysia"` returns 2760 results and
    is a legitimate nationwide search),
  - logs at INFO when it actually strips something, so the transformation
    is observable (`JobSpy:JobStreet - stripped country suffix from
    location for JobStreet: 'Kuala Lumpur, Malaysia' -> 'Kuala Lumpur'`),
  - leaves an unsuffixed value untouched.
- `_build_params` now calls `params["where"] = _strip_country_suffix(self.scraper_input.location)`
  instead of passing `self.scraper_input.location` straight through.

Nothing else under `jobspy/jobstreet/` was touched.

### Covering tests added to `tests/test_jobstreet_scraper.py`

Five new cases in `TestQueryParameters`, all offline against the existing
`FakeSession`:

- `test_strips_a_trailing_malaysia_suffix_from_where` — `"Kuala Lumpur,
  Malaysia"` → `where == "Kuala Lumpur"`
- `test_strips_a_trailing_my_suffix_from_where` — `"Kuala Lumpur, MY"` →
  `where == "Kuala Lumpur"`
- `test_tolerates_whitespace_around_the_suffix` — `"Kuala Lumpur ,
  Malaysia"` → `where == "Kuala Lumpur"`
- `test_leaves_an_unsuffixed_location_untouched` — `"Kuala Lumpur"` →
  unchanged
- `test_does_not_strip_a_bare_country_search_to_empty` — `"Malaysia"` →
  unchanged (the guard case)

```
poetry run pytest tests/test_jobstreet_scraper.py -q
```
→ `20 passed in 1.53s` (15 original + 5 new)

### Fix 2 — re-ran the baseline once, replaced the report

```
poetry run python -m jobspy.baseline.runner --output docs/baseline/2026-09-23-baseline-jobstreet.md
```

One run, per the "run once, don't chase better numbers" rule (which this
time worked in the fix's favor). No throttling, no 403s, no retries. The
live smoke test was not re-run — it already passed an unsuffixed `"Kuala
Lumpur"`, so the fix cannot change its result, as the coordinator noted.

**New before/after comparison** (before = the original committed
`2026-09-23-baseline-phase1-corrected.md`, no JobStreet at all; after =
this run, with the fix):

| Metric | Before (no JobStreet) | After task-9 original (buggy, 3 JobStreet rows) | After fix (this run) |
|---|---|---|---|
| Total rows | 424 | 430 | **584** |
| Salary fill rate | 21.5% | 21.4% | **29.1%** |
| Date fill rate | 100.0% | 100.0% | 100.0% |
| State match rate | 91.5% | 92.3% | **94.0%** |
| Remote rate | 20.5% | 20.5% | 16.6% |
| Exact duplicate rows | 54 | 54 | 56 |
| Company+title duplicate rows | 68 | 67 | 72 |
| Rows per site | indeed 224, linkedin 200 | indeed 227, linkedin 200, jobstreet 3 | indeed 227, linkedin 201, jobstreet **156** |

JobStreet now genuinely participates (156 of 584 rows, ~27% of the
combined result) instead of the 3-row artifact from the location bug. The
salary-fill rate rising from ~21.5% to 29.1% is the real, board-agnostic
effect of adding a board whose own direct-data fill runs 60-70% — consistent
with the per-board diagnostic numbers already in README.md and CLAUDE.md
(61.5% / 66.67%), which did not need updating since they came from
single-board calls using an unsuffixed location, unaffected by this bug.

Log confirms the fix firing on every JobStreet call that needed it:

```
JobSpy:JobStreet - stripped country suffix from location for JobStreet: 'Kuala Lumpur, Malaysia' -> 'Kuala Lumpur'
JobSpy:JobStreet - stripped country suffix from location for JobStreet: 'Selangor, Malaysia' -> 'Selangor'
JobSpy:JobStreet - stripped country suffix from location for JobStreet: 'Penang, Malaysia' -> 'Penang'
```

(The fourth search's `location="Malaysia"` correctly did *not* trigger a
strip line — the guard held.)

**Duplicate rate / dedup_group with a third board genuinely in play.** With
156 real JobStreet rows this time, exact duplicates rose only slightly (54
→ 56) and company+title duplicates rose from 68 → 72 — a modest, plausible
increase given JobStreet now supplies a meaningful slice of the same
KL/Selangor/Penang market Indeed and LinkedIn already cover, not a
runaway collapse. This is the first run that actually exercises the
"third board in play" case the original brief asked about; the task-9
original run's 3-row JobStreet slice did not.

**Unmatched locations, this run:**

```
unmatched locations - add to the gazetteer: Klang/Port Klang (2)
unmatched locations - add to the gazetteer: Remote (15), Johor Baharu, Johore (2)
```

`Klang/Port Klang` is new this run (did not appear in the task-9 original
run, where JobStreet barely participated) and is plausibly JobStreet
vocabulary — a slash-joined dual-locality label the gazetteer's `_key()`
mashes into one ungazetted string. `Remote` and `Johor Baharu, Johore`
repeat from the original run and are almost certainly Indeed/LinkedIn
noise, not JobStreet, per the reasoning in the original report. I did
**not** edit `jobspy/malaysia/location.py` or `tests/malaysia/` this round
— the coordinator's fix-round instructions scoped this pass to Fix 1 (the
`_build_params` change) and Fix 2 (re-run + doc numbers), and did not ask
for gazetteer work. Flagging `Klang/Port Klang` here for your call rather
than acting on it unilaterally.

**Normalizer failure counts:** grepped the full log for `normalizer
failed` — zero occurrences, same as the original run. No regression.

### Documentation updated to match the new, fixed-code baseline

- `CLAUDE.md` Gotchas: replaced the paragraph describing the location-suffix
  issue as an open "query-construction quirk of the fixed search set, not a
  scraper defect" with one describing the shipped fix — what
  `_strip_country_suffix` does, why (the fork's own "City, Malaysia"
  convention, used in README and `examples/`), and the guard for a bare
  `"Malaysia"` search.
- No numeric figures in README.md or CLAUDE.md needed changing beyond that:
  the 61.5% / 66.67% JobStreet salary-fill figures already in both files
  came from single-board diagnostic calls using an unsuffixed location, so
  they were never affected by this bug and remain accurate.
- `docs/baseline/2026-09-23-baseline-jobstreet.md` was regenerated in place
  (old buggy-run report deleted, same filename, fresh content) rather than
  kept as a stale permanent record of the 3-row artifact.

### Offline suite, re-run after the fix

```
poetry run pytest -q
```
→ `316 passed, 2 deselected, 7 xfailed in 3.51s` (was 311 before the 5 new
JobStreet tests; still 7 xfailed, not 8)

```
poetry run pytest tests/test_scraper_contract.py -q
```
→ `59 passed, 7 xfailed in 1.19s`

### Files touched, this fix round

- `jobspy/jobstreet/__init__.py` — added `_strip_country_suffix` and wired
  it into `_build_params`. Nothing else in this file changed.
- `tests/test_jobstreet_scraper.py` — 5 new offline tests.
- `docs/baseline/2026-09-23-baseline-jobstreet.md` — regenerated.
- `CLAUDE.md` — one Gotchas paragraph rewritten to describe the shipped fix.
- `jobspy/malaysia/location.py`, `tests/malaysia/` — **not touched**
  (out of this round's scope; `Klang/Port Klang` flagged above instead).

---

## Original task-9 report (before the fix round above)

## Command run

```
poetry run python -m jobspy.baseline.runner --output docs/baseline/2026-09-23-baseline-jobstreet.md
```

Preceded by two changes to `jobspy/baseline/runner.py` (Ruling 1):

- Added `"jobstreet"` to the `site_name` list of all four `SEARCHES` entries.
- Added `verbose=2` (only if not already set) to every search call, so the
  per-stage normalizer rollup and unmatched-location log lines documented
  below actually reach the log during the run — with the default `verbose=0`
  the run would have logged almost nothing above ERROR.

Only one live run was performed, per Ruling 2 (no "before" run — diffing
against the committed `2026-09-23-baseline-phase1-corrected.md` instead) and
per the task's own instruction to run once and record what comes back, thin
or not.

Full stdout/stderr of the run is not committed; the important log lines are
quoted below from the captured run output.

## Report output

`docs/baseline/2026-09-23-baseline-jobstreet.md`:

| Metric | Before (`...phase1-corrected.md`) | After (this run) |
|---|---|---|
| Total rows | 424 | 430 |
| Salary fill rate | 21.5% | 21.4% |
| Date fill rate | 100.0% | 100.0% |
| State match rate | 91.5% | 92.3% |
| Remote rate | 20.5% | 20.5% |
| Exact duplicate rows | 54 | 54 |
| Company+title duplicate rows | 68 | 67 |
| Rows per site | indeed 224, linkedin 200 | indeed 227, linkedin 200, jobstreet 3 |

## Finding: the fixed search set nearly excludes JobStreet, and it is not a scraper bug

JobStreet contributed only **3 of 430 rows**, which is why the headline
salary-fill rate barely moved (21.5% → 21.4%) despite JobStreet supplying
structured salary on the majority of its own postings. I did not stop at
that number — it did not square with the Task 8 live smoke test (24 rows,
66.67% salary fill) — and traced the cause:

`jobspy/baseline/runner.py`'s `SEARCHES` list reuses one `location` string
per search across every board in that search's `site_name`, in the
Indeed/LinkedIn convention (`"Kuala Lumpur, Malaysia"`, `"Selangor,
Malaysia"`, `"Penang, Malaysia"`). JobStreet's `_build_params` passes
`scraper_input.location` straight through as the `where` query parameter
with no reshaping (`jobspy/jobstreet/__init__.py`, by design — scrapers are
not supposed to hand-normalize). I isolated this with three single-board
diagnostic calls (`site_name=["jobstreet"]`, `results_wanted=10`,
`include_remote=False`, same `search_term`):

| `location` value | rows |
|---|---|
| `"Kuala Lumpur"` | 10 |
| `"Kuala Lumpur, Malaysia"` | 0 |
| `"Malaysia"` | 10 |

JobStreet's `where` param does not resolve the `", Malaysia"` suffix the way
Indeed's location field does. Three of the four baseline searches use a
`"City, Malaysia"` location and get ~0 JobStreet rows each; the fourth
(`location="Malaysia"`, the remote-flagged pass) is the one bare string that
works, which is where the 3 rows came from (further thinned by the
`is_remote` post-filter and exact dedup).

This is a query-construction mismatch in the baseline harness's fixed
search set, not a defect in `jobspy/jobstreet/`, which I did not touch. I
did not restructure `runner.py` to give JobStreet its own location string
per search — that would mean per-board search parameters, a real design
change to the harness, and re-running the full four-search baseline again
(which Ruling 2 and the task's live-traffic guidance both push against for a
number that would only confirm what a smaller, targeted call already
showed). I ran one additional single-board diagnostic instead, scoped to
just JobStreet:

```
site_name=["jobstreet"], search_term="software engineer",
location="Kuala Lumpur", results_wanted=50
```

Result: 52 rows (paging overshoot), salary fill **61.5%** (32/52
`salary_source="direct_data"`), state fill **100%** (`Kuala Lumpur` on every
row). This is consistent with the Task 8 smoke test (66.67% on 24 rows) and
the reconnaissance figure (~70% `salaryLabel` coverage) — JobStreet's real
salary contribution is real, it just isn't visible in the fixed-search
baseline's combined numbers. I recorded this as a finding rather than
smoothing the 21.4% figure into looking like the "after" number for
JobStreet's salary feature; both numbers are in the docs (README caveat
below) with their own sample sizes.

I'm flagging this for your call rather than fixing `runner.py`'s search
shape myself, since Ruling 1 only asked me to add `"jobstreet"` to the
existing lists.

## Location match rate and unmatched strings

State match rate rose slightly (91.5% → 92.3%) despite JobStreet barely
participating — expected, since it came from Indeed/LinkedIn's day-to-day
variance, not from JobStreet's suburb vocabulary being exercised at any
scale.

One unmatched-location log line appeared, from the last search
(`software engineer @ Malaysia`, remote pass):

```
JobSpy:Malaysia - unmatched locations - add to the gazetteer: Remote (15), Johor Baharu, Johore (2)
```

- `Remote` (15) — a bare city string with no state, from a remote-flagged
  posting. Not a real place; adding it to the gazetteer would misrepresent
  it as one. This is expected background noise, not new vocabulary.
- `Johor Baharu, Johore` (2) — an alternate spelling of `Johor Bahru,
  Johor` (already in the gazetteer). Given JobStreet contributed only 3
  rows total this run, this almost certainly came from Indeed or LinkedIn,
  not from JobStreet's suburb labels — consistent with Task 7's finding
  that JobStreet's suburb-level labels resolve without new gazetteer
  entries.

Per Ruling 3, I did **not** edit `jobspy/malaysia/location.py`: the ruling
anticipated no edit would be needed, two stray rows across 430 don't
warrant one, and editing would have obligated a second full live baseline
run to keep the documented numbers honest — exactly the extra live traffic
the task asked me to avoid. No `tests/malaysia/` changes were made either.

## Duplicate rate and dedup_group with three boards

Exact duplicate rows held flat (54 → 54); company+title duplicates dropped
slightly (68 → 67). With JobStreet's contribution effectively 3 rows (see
above), this run does not exercise dedup_group behavior "with a third board
in play" at any real scale — the location-string issue above means this
question is not actually answered by this run's numbers. I'm noting that
gap explicitly rather than implying the 3-row JobStreet slice proves
anything about cross-board duplicate grouping.

## Normalizer failure counts

Grepped the full captured log for `normalizer failed`: **zero** occurrences
across all four searches (location/salary/remote stages). No stage-failure
rollup lines were logged at all, meaning no per-job stage exception fired
during this run. This is a strict "did not rise" — it went from whatever
baseline the phase1-corrected run had (not separately recorded in that
report's committed markdown, since `render_report` doesn't surface failure
counts) to 0 observed in this run.

## Documentation corrections applied

**A. README.md stale claims (JobStreet's registration made these wrong).**
- Line 9 (Features): now lists Indeed Malaysia, LinkedIn, Google Jobs, and
  JobStreet Malaysia as the four default boards.
- Supported job boards default-count line: now "`indeed`, `linkedin`,
  `google`, `jobstreet` — the four boards worth querying."
- Parameters block: `site_name` now documents the four-board default.
- Also added a `JobStreet` row to the "Supported job boards" table (not
  explicitly listed as a stale claim, but its absence there while it's a
  default board was an obvious inconsistency) and ticked the roadmap
  checkbox.

**B. `tests/fixtures/jobstreet/README.md` record-mapping fix.** Verified
against `tests/fixtures/jobstreet/search_page.json` directly: record
`94831259` is `"Cheras, Kuala Lumpur"`, and `94830903` (already listed as
the no-`salaryLabel` case) is `"Bukit Bintang, Kuala Lumpur"`. Both rows in
the "Why these eight records" table corrected to match the fixture.

**C. README salary caveat rewrite.** Applied the brief's rewrite with my
own measured numbers rather than its "roughly 70%" placeholder: quoted
61.5% (this task's 52-job single-board diagnostic) and 66.67% (Task 8's
24-job smoke test) as the measured range, both attributed to their sample
sizes, rather than asserting a single unqualified round number.

## CLAUDE.md additions

- **Project**: JobStreet MY named alongside Indeed MY as a primary target;
  it's one of the four `DEFAULT_SITES`; removed it from the roadmap list
  (it's shipped) since README already ticks it.
- **Gotchas**, three new bullets:
  1. JobStreet is the only board with structured MY salary — measured
     numbers as above, contrasted with Indeed/LinkedIn's 0% — plus the
     baseline-harness location-string finding from this task, so a future
     baseline run doesn't repeat the same silent under-measurement.
  2. `jobstreet_fetch_description` costs one request per job like
     `linkedin_fetch_description`, but is not needed for salary coverage
     (salary comes from structured `salaryLabel`, independent of the
     description fetch) — explicitly warns against reaching for it the way
     `linkedin_fetch_description` is needed for LinkedIn.
  3. robots.txt / 403-means-stop posture: JobStreet's HTML pages are
     disallowed and it sits behind Cloudflare; a 403 from the JSON API is
     treated as a permanent block for that run (log + partial results, no
     retry) — flagged so nobody "fixes" this by adding retries.

## Offline suite

```
poetry run pytest -q
```
→ `311 passed, 2 deselected, 7 xfailed in 3.63s`

```
poetry run pytest tests/test_scraper_contract.py -q
```
→ `59 passed, 7 xfailed in 1.51s`

Both green, still 7 xfailed (not 8), as expected.

## Files touched

- `jobspy/baseline/runner.py` — added `jobstreet` to `SEARCHES` site lists;
  added `verbose=2` default per search call.
- `docs/baseline/2026-09-23-baseline-jobstreet.md` — new, runner output.
- `README.md` — corrections A and C, roadmap tick, new JobStreet table row.
- `CLAUDE.md` — Project paragraph and three new Gotchas bullets.
- `tests/fixtures/jobstreet/README.md` — correction B.
- `jobspy/malaysia/location.py` — **not touched** (Ruling 3, no edit
  warranted).
- `jobspy/jobstreet/` — **not touched**, per instruction.

## Self-review notes

- Verified the `94831259`/`94830903` fixture mapping directly against
  `search_page.json` rather than trusting either the original README or the
  brief's claim.
- Every number quoted in README.md and CLAUDE.md is one I measured during
  this task (the baseline run, or the two follow-up diagnostic calls) or is
  explicitly attributed to the earlier Task 8 smoke test — none of the
  brief's placeholder figures were carried through unverified.
- The baseline harness change (adding `verbose=2`) was necessary to satisfy
  the report's own requirement to show unmatched-location and
  normalizer-failure log lines; without it the run would have logged
  nothing informative at the default `verbose=0`. It does not touch
  `SEARCHES`' comparability-critical fields (search_term, location,
  results_wanted, country_indeed).
