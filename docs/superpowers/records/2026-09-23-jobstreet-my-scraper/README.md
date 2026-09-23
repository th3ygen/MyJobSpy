# Execution record — JobStreet MY scraper (Phase 2)

Process artifacts from the implementation of
[`../../plans/2026-09-23-jobstreet-my-scraper.md`](../../plans/2026-09-23-jobstreet-my-scraper.md),
which implements
[`../../specs/2026-09-23-jobstreet-my-scraper-design.md`](../../specs/2026-09-23-jobstreet-my-scraper-design.md).

Kept for the same reason as the phase 0–1 record: these contain reasoning the commit
history does not — why particular decisions were made, what was measured, and which of
those decisions turned out to be wrong. Review diffs and task briefs were discarded; the
first are regenerable with `git diff`, the second with the plan.

## Files

- **`ledger.md`** — the controller's running record: the pre-flight conflict scan, 15
  numbered rulings (each with its reasoning and stated cost-if-wrong), every review
  finding, and the controller's own corrections when its analysis proved mistaken.
- **`task-N-report.md`** — per-task implementer reports with TDD evidence.
- **`final-findings.md`** — the whole-branch review's findings, triaged into the one
  fix wave (F1–F9) versus explicit follow-ups.
- **`final-fix-report.md`** — the fix wave, per finding.

## The things worth knowing

**The architectural bet held, and was tested rather than assumed.** The fork's central
claim is that `jobspy/malaysia/` normalizes board-agnostically, so a new board inherits
location, salary, remote and grouping handling with no per-board wiring. JobStreet was
built across nine tasks without a line of normalization code. `tests/test_jobstreet_pipeline.py`
exists to make that falsifiable, and the gazetteer needed no new entries — the state
match rate went *up*, 91.5% → 94.0%, with a new board added.

**A silent zero-result bug survived eight offline tasks and their reviews.** JobStreet's
`where` parameter returns `totalCount: 0` for the `"City, Country"` form — which is this
fork's documented convention (`README.md`, three of four baseline searches,
`examples/scrape_fullstack_kl.py`). Every JobStreet query following the README returned
nothing, with no error. Fixture tests could not have caught it: fixtures do not know what
the board does with a query. It surfaced only because the baseline measurement showed
JobStreet contributing 3 of 430 rows and someone asked why. Fixing it moved the board
from 3/430 to 156/584 rows and lifted combined salary fill 21.4% → 29.1%. See
`ledger.md` under Task 9.

**Five tests passed for reasons unrelated to what they claimed to check.** Four were
caught during the branch (a duplicate-page test that never reached page two, an
order-dependent concurrency assertion, a `remote_scope` assertion contradicting the
documented contract, a guard test whose input never reached the guard); the fifth — the
pipeline test nominated as proof of the architectural claim — was caught by the
whole-branch review and fixed by giving a fixture teaser a salary that disagrees with the
board's. This is the branch's most repeated defect class, and worth watching for on the
next board.

**Three plan defects were found before execution, and three more during it.** The
pre-flight scan caught a test that could not fail, a test that would flake under
concurrency, and a documentation step ordered before the work it documented. Execution
then found the plan's fixture README mapped a record to the wrong location, its
`remote_scope` assertion contradicted `remote.py`'s documented contract, and its
measurement step would have measured nothing because the baseline runner did not query
the new board. Transcription from a detailed plan was reliable; the plan is where the
errors lived.

**A 403 was being retried five workers at a time.** The search loop treated 403 as
terminal from the start. `_fetch_description` did not — it never inspected
`status_code`, so a 403 body failed `.json()`, was swallowed as a warning, and the next
of five concurrent workers fired again: one 403 per job. Against a Cloudflare-fronted
host whose robots.txt disallows the endpoint. Found only by the whole-branch review, and
`CLAUDE.md` simultaneously claimed the scraper "only ever calls the JSON search API".
