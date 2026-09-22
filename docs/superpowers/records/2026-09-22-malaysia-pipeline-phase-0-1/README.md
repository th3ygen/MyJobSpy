# Execution record — Malaysia pipeline, Phases 0–1

Process artifacts from the implementation of
[`../../plans/2026-09-22-malaysia-pipeline-phase-0-1.md`](../../plans/2026-09-22-malaysia-pipeline-phase-0-1.md),
which implements
[`../../specs/2026-09-22-malaysia-specialization-design.md`](../../specs/2026-09-22-malaysia-specialization-design.md).

Kept because these contain reasoning that the commit history does not: why particular
decisions were made, what was measured, and which of those decisions turned out to be
wrong. Review diffs were discarded — they are regenerable with `git diff`.

## Files

- **`ledger.md`** — the controller's running record: 27 numbered rulings (each with its
  reasoning and stated cost-if-wrong), every review finding, and the controller's own
  corrections when its analysis turned out to be mistaken.
- **`task-N-report.md`** — per-task implementer reports with TDD evidence. Two
  (`task-11`, and the level-suffix section of `task-10`) are partly controller-authored
  because those agents were killed mid-task by infrastructure failures; that is disclosed
  in the files themselves.
- **`final-fix-report.md`** — the fix wave following the whole-branch review, including
  the investigation of how all eight scrapers construct `job_url`.

## The things worth knowing

**A Critical defect survived 182 tests and six task reviews.** `_canonical_url` stripped
the entire query string, but Indeed encodes job identity as `?jk=<key>` — so exact dedup
collapsed the whole board to one row. It escaped because every test fixture URL was
path-distinguished and every integration fake returned exactly one job. Only the
whole-branch review caught it, by checking a normalizer's assumption against the URL
format the scrapers actually emit. See `ledger.md` finding C1.

**The first Phase 1 measurement was invalid and was retracted.** The controller
attributed Indeed's collapse from 200 rows to 4 to rate limiting, and reported that
confidently. It was the dedup bug: four searches × one surviving row. The baseline was
re-run after the fix; `docs/baseline/2026-09-23-baseline-phase1-corrected.md` is the
valid one, and `2026-09-23-baseline-phase1.md` is retained only as the record of the
broken run.

**Measuring before building changed the design repeatedly.** Live sampling found that
Indeed emits ISO 3166-2 state codes rather than names (the planned gazetteer would have
missed every Indeed row), that a regex in the plan under-reported comma-less salaries by
10×, that real postings state wages below the planned sanity floor, and that Naukri's URL
carries a per-request session id. None of these were visible from the plan alone.

**Most defects were in the plan, not in its implementation.** Transcription from a
detailed spec proved reliable; the specification is where the errors lived, and they
surfaced when something adversarial ran the code against real inputs.
