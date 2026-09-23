# SDD ledger — plan: docs/superpowers/plans/2026-09-23-jobstreet-my-scraper.md

**Spec:** docs/superpowers/specs/2026-09-23-jobstreet-my-scraper-design.md (read — binding authority)
**Branch:** feat/jobstreet-my (created from main @ 2ce699c)
**Baseline before Task 1:** 259 passed, 7 xfailed

## Pre-flight scan

### Cross-task pairs sharing a file or interface

| Pair | Produces → consumes | Finding |
|---|---|---|
| T1 → T4 | `jobstreet/__init__.py` stub `scrape` raising NotImplementedError → T4 replaces it | Clean. Stub still passes `test_scrape_takes_a_scraper_input_and_is_implemented` (it checks `__isabstractmethod__`, not callability). |
| T1 → T5 | `__init__` body → T5 adds `self.fetch_description = False` | Clean |
| T1 → T6 | `jobspy/__init__.py` imports + registry → T6 adds signature param + `scrape_site` branch | Clean, disjoint regions |
| T1 → T2 | `constant.py`: `WORK_TYPE_MAP`, `REMOTE_ARRANGEMENT`, `BASE_URL` | Clean, all three defined in T1 Step 5 |
| T1 → T4 | `constant.py`: `SEARCH_URL`, `SITE_KEY`, `SOURCE_SYSTEM`, `JOBS_PER_PAGE`, `WORK_TYPE_IDS` | Clean |
| T1 → T5 | `constant.py`: `GRAPHQL_URL`, `JOB_DETAILS_QUERY`, `DESCRIPTION_WORKERS` | Clean |
| T2 → T3 | `test_jobstreet_util.py` module-level `load`, `records` fixture → T3 appends classes using both | Clean, module-scope fixture is visible to classes |
| T2 → T4 | `parse_job(record) -> JobPost \| None` | Clean, signature matches consumption |
| T2 → T7 | same | Clean |
| T4 → T5 | `test_jobstreet_scraper.py` `FakeSession`, `make_scraper`, `an_input`, `load` → T5 appends `TestDescriptions` | Clean, all module-level in T4 |
| T5 → T6 | `JobStreet.fetch_description` attribute | Clean |

### Per-task self-consistency

| Task | Finding |
|---|---|
| T1 | Clean. Expected counts check out: 7 parameterized contract tests × 9 boards + 3 suite-wide = 66; 59 passed + 7 xfailed. |
| T2 | Minor: test file imports `JobType` which only T3 uses. Harmless — Black is the only linter, no flake8. |
| T3 | Clean |
| T4 | **F1 — defective test** (below). Also imports are specified in two places (a block, then a trailing sentence) — sloppy but unambiguous. |
| T5 | **F2 — flaky test** (below) |
| T6 | Clean. `isinstance(scraper, JobStreet)` works on the monkeypatched subclass; construction does no I/O. |
| T7 | Clean. `build_jobs_dataframe` is keyword-only after arg 1; the test passes keywords. |
| T8 | Clean |
| T9 | **F3 — ordering** (below) |

### Findings and rulings

**F1 — `test_does_not_return_the_same_job_twice` (Task 4) cannot fail.**
It queues two identical 8-record pages, but `scrape` breaks on a short page
(`len(records) < jobs_per_page`, 8 < 100) after page 1, so the second page is
never fetched and the dedup path never runs. The assertion passes trivially.

`Ruling: Task 4's implementer must set scraper.jobs_per_page = 8 in that test so the 8-record fixture is a full page and paging continues to page 2, actually exercising seen_ids. — A test that cannot fail is worse than no test: it reports safety that was never checked, and dedup is load-bearing for this board (the spec's whole identity story keys on it). — If wrong, the test is merely redundant with test_applies_offset; cost is one wasted test.`

**F2 — `test_fetches_and_converts_descriptions_when_on` (Task 5) is order-dependent.**
It asserts `graphql[0]["json"]["variables"]["jobId"] == jobs[0].id...`, but
`_add_descriptions` uses `ThreadPoolExecutor.map` with 5 workers, so the order
calls land in `FakeSession.calls` is nondeterministic.

`Ruling: assert on the set of requested jobIds, not on call order — {c["json"]["variables"]["jobId"] for c in graphql} == {j.id.removeprefix("js-") for j in jobs}. — Concurrency makes the index assertion a coin flip that will pass locally and fail in CI; the set assertion tests what actually matters (every selected job was requested, exactly once). — If wrong, we lose an ordering guarantee nothing depends on.`

**F3 — Task 9 orders documentation before the gazetteer work it depends on.**
Step 3 adds gazetteer entries the baseline reveals, but Steps 4-5 write the
docs, and Step 2's measured numbers change once Step 3 lands.

`Ruling: Task 9 runs Step 1-3 (measure, then fix the gazetteer), then re-runs the baseline before writing docs in Steps 4-5, so the numbers documented are post-fix. — Documenting a location match rate that the same task then improves publishes a figure that was never true of the shipped code. — If wrong, cost is one extra baseline run (~minutes).`

**Scan verdict:** 3 findings, all ruled, none blocking. Proceeding to Task 1.

## Progress

Task 1: dispatched (sonnet, BASE 2ce699c) — register the board
Task 1: implementer DONE, commit d1bd9dd "feat: register JobStreet MY as a board" (6 files, +128/-4)
  - suite 259->266 passed, 7 xfailed (unchanged); contract test 52->59 passed, 7 xfailed
  - xfail held at 7, so user_agent forwarding works and the board did not join USER_AGENT_NOT_FORWARDED
  - authorized change applied: tests/test_scrape_jobs_integration.py::test_default_sites_are_malaysia_relevant
    now expects {indeed, linkedin, google, jobstreet}
Task 1: task review dispatched (sonnet, 2ce699c..d1bd9dd)
Task 1: review Spec OK / quality Approved — 0 Critical, 0 Important
Task 1: minor (deferred): jobspy/exception.py has no trailing newline; black was run only on jobspy/jobstreet, not all touched files. No formatting defect introduced.
Task 1: minor (deferred): jobstreet/__init__.py ships inert fields (scraper_input, jobs_per_page, seen_ids) unread until Task 4. Plan-mandated scaffolding.
Task 1: resolved the reviewer's WARN item myself — grepped for stale DEFAULT_SITES claims. Confirmed REAL: README.md:9, :74, :104 all still say the default is indeed/linkedin/google (now four boards). jobspy/__init__.py:30 comment is generic and stays accurate.
  Ruling: carry the README staleness to Task 9 Step 4 (which already owns README updates) rather than opening a Task 1 fix loop — README.md is not in Task 1's file list, so this is scheduled work, not a Task 1 requirement gap. The three line numbers go into Task 9's dispatch so it cannot be forgotten. — Cost if wrong: README is briefly stale on an unmerged branch; Task 9 is the last task, so it never ships stale.
Task 1: complete (commits 2ce699c..d1bd9dd, review clean)
Task 2: dispatched (sonnet, BASE d1bd9dd) — parse one search record into a JobPost
Task 2: implementer DONE, commit 02ddcfe "feat: parse JobStreet search records into JobPost" — suite 266->269 passed, 7 xfailed
Task 2: task review dispatched (sonnet, d1bd9dd..02ddcfe)
Task 2: review Spec OK / quality Approved — 0 Critical, 0 Important
Task 2: resolved the reviewer's WARN + 2 minors myself. It flagged 4 parser branches as untested (3-part location rejoin, advertiser fallback 94462128, multi-worktype 94586568, "labels present but not Remote" -> False). Verified all four ARE in Task 3's brief: test_three_part_location_label (record 90000006), test_falls_back_to_advertiser, test_multiple_work_types, test_remote_is_true_only_for_remote. The reviewer read only search_page.json and could not see that search_malformed.json carries "Bayan Lepas, Bayan Baru, Penang". No gap; no fix loop.
Task 2: complete (commits d1bd9dd..02ddcfe, review clean)
Task 3: dispatched (haiku — brief is complete test code, pure transcription; BASE 02ddcfe) — cover every parser branch
Task 3: implementer DONE, commit 7ebb07f "test: cover every JobStreet parser branch" — 23 tests in file (3 existing + 20 new)
Task 3: implementer raised a concern that was CORRECT and my error. Verified the fixture myself:
  94831259 is "Cheras, Kuala Lumpur"; "Bukit Bintang, Kuala Lumpur" is 94830903.
  My plan's test_suburb_and_state asserted "Bukit Bintang" for 94831259, and tests/fixtures/jobstreet/README.md
  documents the same wrong mapping. The implementer corrected the test to match the fixture and touched nothing else.
  Ruling: the implementer's deviation from the brief stands — the fixture is the source of truth, and a test
  rewritten to match real captured data is the correct resolution of a brief that contradicted its own fixture.
  The README.md correction is deferred to Task 9 with the other docs work. — Cost if wrong: none to the code;
  a stale line in fixture docs until Task 9, which is the last task.
Task 3: carried to Task 9 (docs) — (a) tests/fixtures/jobstreet/README.md record table: 94831259 = Cheras, 94830903 = Bukit Bintang; (b) README.md:9,:74,:104 stale "three default boards" claims
Task 3: task review dispatched (sonnet, 02ddcfe..7ebb07f)
Task 3: review Spec OK / quality Approved — 0 Critical, 0 Important. Reviewer independently verified the Cheras
  correction against search_page.json:252-278 and confirmed it was a single expected-value change: fixture untouched,
  test not weakened or deleted. Also grepped the fixtures for literal nbsp/en-dash and confirmed they are really present.
Task 3: minor (deferred): test_empty_locations_list (90000002) and test_missing_locations_key (90000003) hit the same
  code path — `record.get("locations") or []` collapses both. Harmless, no incremental branch coverage. My brief specified both.
Task 3: minor (deferred): parse_is_remote's "no workArrangements -> None" branch (util.py:85-86) is never asserted.
  Record 90000005 was seeded for it but no test checks is_remote on it. Real branch gap, authored by me in the brief.
  -> FLAG BOTH TO THE FINAL WHOLE-BRANCH REVIEW for triage; the second is a genuine one-line coverage gap.
Task 3: complete (commits 02ddcfe..7ebb07f, review clean)
Task 4: dispatched (sonnet, BASE 7ebb07f) — search, page, return a JobResponse; carries pre-flight ruling F1
Task 4: implementer DONE, commit a2e50f0 "feat: page the JobStreet search API and return a JobResponse"
  — 10/10 new tests (RED confirmed: all 10 failed with NotImplementedError); suite 289->299 passed, 7 xfailed; contract still 59/7
Task 4: F1 ruling applied AND refined by the implementer. With jobs_per_page=8 and two full 8-record pages, the loop
  probes a 3rd page (served empty), so total calls are 3, not 2. It fixed the ASSERTION (pages[:2] == [1,2], len>=2)
  rather than the scraper — correct: the scraper's behaviour is right, my expected call count was wrong.
  Ruling: accepted. The test now genuinely exercises seen_ids and cannot regress to the vacuous version. — Cost if wrong: none; the assertion is strictly stronger than the brief's.
Task 4: task review dispatched (sonnet, 7ebb07f..a2e50f0)
Task 4: review Spec OK / quality Approved — 0 Critical, 0 Important. Reviewer independently hand-traced the F1
  correction against fixture data and confirmed 3 calls is genuinely correct (page1 8 new -> page2 8 duplicates all
  skipped -> page3 empty -> break), so the implementer's reasoning was real, not a rationalization. Also traced all
  6 paging exits (exception / 403 / non-200 / empty / short page / wanted reached) and the offset slice arithmetic by hand.
Task 4: minor (deferred): tests/test_jobstreet_scraper.py:12 `import pytest` is unused. Verbatim from my brief.
Task 4: minor (deferred): jobspy/jobstreet/__init__.py _build_params — the sortmode comment claims "Newest-first lets
  paging stop as soon as it crosses the cutoff", but scrape() implements no early date-based break; it relies on
  short/empty-page detection plus the server-side daterange bound. The COMMENT overclaims, the behaviour is correct
  and low-risk. Verbatim from my brief, so plan-mandated. -> FLAG TO FINAL REVIEW: worth correcting the comment,
  since this file is the template the next four boards get copied from.
Task 4: complete (commits 7ebb07f..a2e50f0, review clean)
Task 5: dispatched (sonnet, BASE a2e50f0) — optional description fetching; carries pre-flight ruling F2
Task 5: implementer DONE, commit 027ff40 "feat: optional JobStreet description fetching via GraphQL"
  — test_jobstreet_scraper.py 10->14 passed; suite 299->303 passed, 7 xfailed
Task 5: F2 ruling applied as specified — order-dependent graphql[0] assertion replaced with a set comparison plus
  the len(graphql)==2 count check retained. Implementer also confirmed Task 6 scope boundary by reading task-6-brief
  and left jobspy/__init__.py untouched.
Task 5: task review dispatched (sonnet, a2e50f0..027ff40)
Task 5: review Spec OK but quality NEEDS FIXES — 1 Important.
  IMPORTANT: jobspy/jobstreet/__init__.py:117-118 — the GraphQL envelope traversal sits OUTSIDE the try/except.
  `payload = response.json() or {}` only normalizes FALSY results to {}; a truthy non-dict root (bare list/string/number)
  makes payload.get("data") raise AttributeError, which propagates fill -> executor.map -> list() -> scrape().
  That violates the task's explicit invariant "nothing may raise out of scrape()". No test covers this shape.
  Reviewer also audited the F2 correction on all three requested points and confirmed it is right: no assertion depends
  on scheduling, the set+count pair still pins one-request-per-job (a duplicate collapses the set and fails), and the
  pool was not serialized to dodge the problem.
Task 5: minor (deferred): jobspy/util.py:76-88 RequestsRotating.request mutates self.proxies from next(self.proxy_cycle)
  with no lock. _add_descriptions is the FIRST concurrent call site in this scraper, so this task newly activates a
  pre-existing race when a proxy list is configured. Out of diff scope, affects proxy selection only, not job data.
  -> FLAG TO FINAL REVIEW: real, newly-activated, and will affect the next four boards that copy this pattern.
Task 5: minor (deferred): no test covers the PLAIN or HTML branches of the description_format switch (only MARKDOWN).
Task 5: minor (deferred): _fetch_description returns None silently when content is empty, while the exception path logs.
Task 5: fix round 1/5 dispatched — resuming the original implementer with the Important finding verbatim
Task 5: fix round 1/5 (1 addressed, 0 open — envelope traversal now inside try/except at jobspy/jobstreet/__init__.py:124-133; commits 027ff40..d74b7ad)
  Re-reviewer confirmed the new test is a genuine DIFFERENTIAL test: NonDictPayload.post returns FakeResponse([1,2,3]),
  which stays truthy through `or {}`, so payload.get("data") raises AttributeError pre-fix for the right reason and
  passes post-fix. Also confirmed the try was widened by exactly the two lines needed — the description_format
  converter branch stays OUTSIDE it, so the fix does not newly swallow converter errors.
Task 5: minor (deferred): markdown_converter/plain_converter calls at jobspy/jobstreet/__init__.py:140-143 sit outside
  the try/except — same invariant-violation class as the fixed finding, but pre-existing and using shared hardened
  utilities. -> FLAG TO FINAL REVIEW alongside the other minors.
Task 5: complete (commits a2e50f0..d74b7ad, review clean after 1 fix round)
Task 6: dispatched (sonnet, BASE d74b7ad) — wire jobstreet_fetch_description through scrape_jobs
Task 6: implementer DONE, commit b86eead "feat: expose jobstreet_fetch_description on scrape_jobs"
  — suite 304->306 passed, 7 xfailed. RED was 1 of 2 new tests failing (the defaults_to_false case passes without
  the wiring, since both the attribute default and the kwarg default are False). Noted as a named risk for the reviewer.
Task 6: task review dispatched (sonnet, d74b7ad..b86eead)
Task 6: review Spec OK / quality Approved — 0 Critical, 0 Important. Reviewer verified the docstring's factual claim
  ("leaving this off costs little salary coverage") against jobspy/jobstreet/util.py:101-109 rather than accepting it,
  and confirmed the isinstance/globals() interaction concretely for both the real class and a monkeypatched subclass.
Task 6: minor (deferred): test_jobstreet_fetch_description_defaults_to_false is weak — it passed at RED by coincidence.
  Reviewer's judgement: KEEP it; post-GREEN it does guard against default-value drift between the kwarg and the class
  default. But only test_..._reaches_the_scraper actually proves the wiring exists.
Task 6: minor (deferred): KWARG SPRAWL. jobstreet_fetch_description is the second board-specific boolean in the shared
  scrape_jobs signature (after the two linkedin ones), each needing its own `if isinstance(scraper, X)` block in
  scrape_site. Readable now; by a fifth such kwarg the signature and scrape_site become a flat stack of near-identical
  isinstance blocks with no abstraction tying a kwarg to its board. The roadmap adds FOUR more boards.
  -> FLAG TO FINAL REVIEW, and surface to the user: this is an architectural decision worth making before Hiredly/Glints/Maukerja/Ricebowl repeat it.
Task 6: complete (commits d74b7ad..b86eead, review clean)
Task 7: dispatched (sonnet, BASE b86eead) — prove the pipeline normalizes JobStreet output
Task 7: implementer DONE, commit 35eaf0c "test: JobStreet output through the Malaysian pipeline" — 5 new tests; suite 306->311 passed, 7 xfailed
Task 7: gazetteer needed NO change — JobStreet's suburb labels already resolve via existing KL-locality entries or the
  city-miss/state-match fallback in jobspy/malaysia/location.py. The spec's "new board inherits normalization free" claim holds.
Task 7: THIRD defect of mine caught. My brief's test_remote_scope_is_assigned asserted remote_scope is not None for
  EVERY job. Verified against source myself: jobspy/malaysia/remote.py:66-67 returns None when `not job.is_remote`, and
  its docstring says "Returns None for non-remote jobs". tests/test_baseline_metrics.py:165 independently documents the
  same. 7 of the 8 fixture records are On-site/Hybrid.
  Ruling: the implementer's correction stands. It asserts BOTH directions (remote -> not None, non-remote -> None),
  which is strictly stronger than my blanket assertion, and it changed the test rather than remote.py — correct, since
  production behaviour is documented and intentional. — Cost if wrong: none; the test is stronger than briefed.
Task 7: task review dispatched (sonnet, b86eead..35eaf0c)
Task 7: review Spec OK / quality Approved — 0 Critical, 0 Important.
  Reviewer verified the "no gazetteer change needed" claim was NOT a degenerate pass: traced both resolution paths
  (city-level KL locality entries at location.py:66-85, and the federal-territory state alias at location.py:48-56),
  and confirmed location.py:290-300's canonical-or-nothing miss path means `state` is never copied from unrecognized
  raw text. Also confirmed my remote_scope correction is two-directional and strictly stronger, and that remote.py is
  untouched. Verified the fixture's salaried/remote splits against the file rather than the report (4 parseable RM
  labels, 1 rejected $ label, 1 of 8 genuinely remote).
Task 7: minor (deferred): test_state_survives_normalization is satisfied redundantly by two independent gazetteer
  paths, so it would keep passing if one silently broke. Splitting into two assertions would pin both mechanisms.
Task 7: complete (commits b86eead..35eaf0c, review clean)
Task 8: dispatched (sonnet, BASE 35eaf0c) — live smoke test. NOTE: this task makes real network requests to
  my.jobstreet.com. Authorized: the user approved a plan whose Task 8 explicitly says "Run it once against the live
  board", and extensive live reconnaissance was already run with the user present. Bounded to ~23 requests.
Task 8: implementer DONE, commit 7218264 "test: live smoke test for JobStreet MY"
  — plain suite 311 passed, 2 deselected, 7 xfailed. Live run: 2 passed, NO 403s, no rate limiting.
  *** FIRST PRODUCTION NUMBERS (live my.jobstreet.com, 2026-09-23, KL "software engineer"): ***
    row_count = 24
    salary fill = 66.67%   (floor 25%; the fork's recorded direct-board-data fill was 0%)
    state fill  = 100%
    description lengths: min 905 / max 2983 / mean 2078 chars
  These closely match the 2026-09-23 reconnaissance estimate of ~70% salaryLabel coverage.
  Implementer disclosed temporarily instrumenting the test with print()s to capture these numbers, then reverting to
  the brief's exact text before committing. Reviewer asked to verify the committed file matches the brief.
Task 8: task review dispatched (sonnet, 35eaf0c..7218264)
Task 8: review Spec NOT COMPLIANT / quality NEEDS FIXES — 1 Important.
  IMPORTANT: tests/test_jobstreet_live.py docstring dropped the brief's closing rationale ("A fixture test passing
  means the parser handles a shape captured in the past. This is what tells you the board still serves that shape
  today."). I verified the omission directly. Compounded by a self-report inaccuracy: the report's summary claimed
  "transcribed verbatim" while a later section admitted the trim.
  Everything substantive passed: all four thresholds byte-identical and unweakened, module-level pytestmark deselects
  both tests, no production/pyproject changes, print() instrumentation fully reverted with no residue, and the
  reviewer judged the threshold calibration sound against the measured numbers.
Task 8: fix round 1/5 dispatched — resumed original implementer; instructed NOT to re-run live tests (docstring change
  cannot affect behaviour and re-running loads a third-party board), verify by --collect-only plus the offline suite.
Task 8: fix applied, commit f14324e "fix: restore dropped rationale paragraph in live test docstring"
  — collect-only shows both tests collected; pytest -q 311 passed, 2 deselected, 7 xfailed. No live calls made.
  Implementer also corrected the inaccurate claim in its own report.
Task 8: scoped re-review dispatched (haiku — docstring-only fix diff, 7218264..f14324e)
Task 8: fix round 1/5 (1 addressed, 0 open — docstring restored character-for-character at tests/test_jobstreet_live.py:21-23,
  report's inaccurate claim corrected; commits 7218264..f14324e). Re-reviewer confirmed both parts and no breakage.
Task 8: complete (commits 35eaf0c..f14324e, review clean after 1 fix round)

PRE-DISPATCH FINDING ON TASK 9 — the plan's measurement step would have measured nothing.
  jobspy/baseline/runner.py's SEARCHES list hardcodes site_name to ["indeed","linkedin","google"] in all four searches.
  Running the baseline as the plan's Task 9 Step 1 literally says would therefore produce a report with ZERO JobStreet
  rows, and the "compare before/after" step would show no change attributable to this branch.
  The spec's Measurement section explicitly expects the opposite — it asks for "duplicate rate and dedup_group
  behavior WITH A THIRD BOARD IN PLAY", i.e. JobStreet participating.
  Ruling: Task 9 must add "jobstreet" to the SEARCHES site_name lists in jobspy/baseline/runner.py before measuring.
    That is a small production change squarely inside this task's purpose — without it the task's entire deliverable
    is vacuous. — Cost if wrong: a one-line revert; the baseline harness is dev tooling, not shipped scraper code.
  Ruling (refines pre-flight F3): re-run the baseline after gazetteer edits ONLY IF the gazetteer actually changes.
    Task 7 established it needs no changes for this board, so a second full live baseline run is most likely
    unnecessary. — Cost if wrong: documented numbers lag a gazetteer edit; the implementer is instructed to re-run
    if it touches location.py.
  Ruling: do NOT run a "before" baseline. docs/baseline/ already holds committed phase-1 reports to diff against,
    and a second full run would double live traffic across Indeed/LinkedIn/Google for no new information.
Task 9: dispatched (sonnet, BASE f14324e) — measure, then document; carries the two README corrections
Task 9: implementer DONE_WITH_CONCERNS, commit 1884249 "docs: record the JobStreet baseline and document the board"
  — suite 311 passed, 2 deselected, 7 xfailed; contract 59/7. Both README corrections + fixture README mapping applied.
  Baseline salary fill 21.5% -> 21.4% (flat), but JobStreet contributed only 3/430 rows. Isolated single-board
  diagnostic: 61.5% direct_data fill over 52 rows, consistent with Task 8's 66.67% and recon's ~70%.
Task 9: CONCERN IS A REAL SHIPPED DEFECT — I verified it live myself, and it is worse than reported:
    where="Kuala Lumpur"           -> totalCount 1239
    where="Kuala Lumpur, Malaysia" -> totalCount 0
    where="Selangor, Malaysia"     -> totalCount 0
    where="Penang, Malaysia"       -> totalCount 0
    where="Malaysia"               -> totalCount 2760
  JobStreet's `where` does not resolve the "City, Country" form. That form is THE fork's documented convention:
  README.md:34 (main usage example), README.md:115 (parameter docs), 3 of 4 baseline searches, and
  examples/scrape_fullstack_kl.py. JobStreet is now in DEFAULT_SITES, so every one of those silently returns ZERO
  JobStreet rows — a silent empty result, which reads as "no jobs found" rather than "malformed query".
  Ruling: this is load-bearing and must be fixed before the branch finishes. Dispatching Task 9 fix round 1 to strip a
    trailing country suffix from `where` in _build_params, with offline tests. I am explicitly unfreezing
    jobspy/jobstreet/__init__.py for this narrow change only. — Cost if wrong: a small, well-tested string
    normalization in one board's query builder; the alternative is shipping a board that returns nothing for the
    fork's own documented location format.
  Ruling: re-run the baseline once after the fix and replace the report. The committed report would otherwise stand as
    a permanent record saying JobStreet contributes 3/430 rows, which we now know is an artifact we fixed. The fork's
    stated discipline is that numbers decide, so the recorded number must reflect shipped behaviour. — Cost if wrong:
    one extra live baseline run.
Task 9: fix round 1/5 dispatched
Task 9: fix round 1 applied — commit 29343ae "fix: strip trailing country suffix from JobStreet location queries"
  _strip_country_suffix() added to jobspy/jobstreet/__init__.py, wired into _build_params; case-insensitive,
  whitespace-tolerant, logs when it fires, guards location="Malaysia" against collapsing to an empty where.
  +5 offline tests. Nothing else under jobspy/jobstreet/ touched.
  *** IMPACT OF THE FIX (re-run baseline) ***
    JobStreet rows in baseline:  3/430  ->  156/584
    combined salary fill:        21.4%  ->  29.1%   (pre-JobStreet baseline was 21.5%)
  So the board's real contribution was entirely masked by the bug. Suite 311 -> 316 passed, 2 deselected, 7 xfailed.
  Implementer confirmed the 61.5%/66.67% JobStreet figures already in README/CLAUDE.md came from unsuffixed
  single-board diagnostics and were never affected, so no published number needed restating.
Task 9: minor (deferred): new unmatched location "Klang/Port Klang" (2 rows), surfaced only once JobStreet genuinely
  participates. Real JobStreet vocabulary — a slash-joined dual locality that the gazetteer's _key() mashes into one
  ungazetted string. NOT a one-line dict addition; handling slash-joined localities is a small design question.
  Ruling: defer to the final whole-branch review rather than opening another round now. Gazetteer misses null `state`
  by design and are logged for exactly this purpose, so 2 rows of unset state is a coverage gap, not data corruption.
  -> FLAG TO FINAL REVIEW. — Cost if wrong: 2 baseline rows carry no state until a follow-up.
Task 9: task review dispatched (sonnet, f14324e..29343ae — covers both the docs commit and the fix commit)
Task 9: review Spec OK / quality Approved, but 2 Important findings -> fix loop (verdict said "doesn't block approval";
  the process is that Important findings enter the loop regardless, and I agree they should here).
  IMPORTANT A: the emptiness guard in _strip_country_suffix is untested dead code. I confirmed by reading the source:
    _COUNTRY_SUFFIX_RE = r",\s*(?:malaysia|my)\s*$" REQUIRES a comma, so location="Malaysia" never matches it and
    falls straight through. test_does_not_strip_a_bare_country_search_to_empty therefore passes for a reason
    unrelated to the guard it claims to exercise. Same defect class as pre-flight F1 (a test that cannot fail).
  IMPORTANT B: the docstring (jobspy/jobstreet/__init__.py:57-59) states the emptiness guard is what keeps
    location="Malaysia" safe. It is not — the regex's comma requirement is. The guard actually protects a different,
    pathological input (", Malaysia": comma with no city). A future reader would carry a false mental model, and this
    file is the template the next four boards get copied from.
  Reviewer independently re-ran both suites (316/2/7 and 59/7, plus 20 in test_jobstreet_scraper.py) and verified every
  documentation claim against shipped code: 403-terminal at __init__.py:220-227, salary independent of
  fetch_description at util.py:101-146, DEFAULT_SITES four boards, fixture record mapping against search_page.json,
  and confirmed the 61.5%/66.67% figures used unsuffixed locations so were never bug-affected.
Task 9: minor (deferred): runner.py has no automated guard against a future board silently contributing near-zero rows
  because its query dialect differs — mitigation is a prose note in CLAUDE.md only. -> FLAG TO FINAL REVIEW.
Task 9: minor (deferred): verbose=2 injected into baseline searches (beyond Ruling 1's literal text, but disclosed and
  a prerequisite for reading the unmatched-location lines the brief's own steps require). Accepted.
Task 9: minor (deferred): stray blank line mid-sentence in two new test docstrings. Cosmetic.
Task 9: fix round 2/5 dispatched
Task 9: fix round 2 applied — commit 79875e1 "fix: test the emptiness guard with the input that actually reaches it"
  Added test_does_not_reduce_a_comma_with_no_city_to_an_empty_where using location=", Malaysia" — the input that
  matches _COUNTRY_SUFFIX_RE across its whole length and drives `stripped` to "", so the guard actually fires.
  Amended the bare-"Malaysia" test's docstring to say it pins real behaviour but does not test the guard.
  Rewrote _strip_country_suffix's docstring to attribute correctly: the regex's comma requirement is why "Malaysia"
  is untouched; the emptiness check is a secondary net for the ", Malaysia" degenerate case. Docstring + tests only.
  Suite 316 -> 317 passed, 2 deselected, 7 xfailed (still 7, not 8). No baseline or live run.
Task 9: scoped re-review dispatched (haiku — docstring + one test, 29343ae..79875e1)
Task 9: fix round 2/5 (2 addressed, 0 open — commits 29343ae..79875e1). Re-reviewer traced that ", Malaysia" really
  does match _COUNTRY_SUFFIX_RE across its full length and drives `stripped` to "", so the guard genuinely fires;
  confirmed the docstring now matches the code and that the function logic is byte-identical (no behaviour change).
Task 9: complete (commits f14324e..79875e1, review clean after 2 fix rounds)

ALL 9 TASKS COMPLETE. Final suite: 317 passed, 2 deselected (live), 7 xfailed. Contract test 59 passed, 7 xfailed.

FINAL WHOLE-BRANCH REVIEW (opus, 2ce699c..79875e1): "Ready with follow-ups". 0 Critical, 7 Important, 8 Minor.
  Reviewer independently re-ran the suite (317/2/7), confirmed xfail still 7, no new JobPost fields, tree untouched.
  Confirmed the ARCHITECTURAL CLAIM HELD: jobspy/malaysia/ has zero JobStreet-aware code, jobspy/jobstreet/
  hand-normalizes nothing, and state match rate went UP 91.5% -> 94.0% with the new board added.
  Also verified _strip_country_suffix cannot mangle a legitimate location, and that the fixture README correction
  is accurate (diffed against the fixtures).
  BEST CATCH — C1: _fetch_description never inspects status_code, so on a 403 the body fails .json(), is swallowed
  as a warning, and the next of 5 concurrent workers fires again: ONE 403 PER JOB, FIVE AT A TIME, against a
  Cloudflare-fronted endpoint. The search loop stops on 403; the GraphQL path does not. CLAUDE.md:86 claims the
  scraper "only ever calls the JSON search API" (false) and that 403s are terminal (true only of search).
  Fix wave composed at .superpowers/sdd/2026-09-23-jobstreet-my-scraper/final-findings.md (F1-F9).
  Ruling: include F1-F9 (safety, doc-truth, one behavioural bug, a shared-code root cause, one vacuous test, trivia).
    EXCLUDE the kwarg-sprawl refactor, the proxy race, hour-precise _within_age, the runner under-contribution guard,
    the converter try/except, MAX_PAGES, and the salary-band ceiling — each is a separate change needing its own
    review, and bundling them would make this wave unreviewable. — Cost if wrong: the excluded items ship as
    documented follow-ups on a branch that is already "ready with follow-ups".
  Ruling: F6 fixes the _key() slash bug at root (map [/&-] to space) rather than adding a "Klang/Port Klang" alias.
    Both "Klang" and "Port Klang" are ALREADY gazetted — the alias would paper over a defect that hits every
    slash-joined locality the next four boards emit. — Cost if wrong: a shared-code change with its own tests;
    the full suite gates it.
Final fix wave: dispatched (sonnet, ONE agent, BASE 79875e1)
Final fix wave: agent hit the session rate limit mid-run and died at the last verification step, having written
  final-fix-report.md and modified 14 files but committed NOTHING. Recovered by inspection rather than re-dispatch:
  all of F1-F9 are marked FIXED in its report, suite 317 -> 328 passed / 2 deselected / 7 xfailed (still 7),
  contract 59/7, black clean on all 10 touched python files, fixture edit is a single surgical teaser append,
  no unrelated upstream scrapers touched. Committed as fcffcdb (14 files, +366/-31).
  Ruling: commit the dead agent's completed work rather than re-dispatching it. The work was finished and self-reported
    in full; re-running would have redone ~40 minutes of correct work and risked a different, unreviewed result.
    Committing is bookkeeping, not fixing — the scoped re-review below is still the gate. — Cost if wrong: the
    re-review catches it, same as any other wave.
Final fix wave: F6 OUTCOME CORRECTS MY OWN RULING. I ruled the _key() slash fix would resolve "Klang/Port Klang"
  because both "Klang" and "Port Klang" are gazetted. The agent verified empirically that it does NOT: _lookup() is a
  single exact dict.get() with no per-segment fallback, so "klang port klang" is simply not a registered key. It
  implemented the authorized root-cause fix (which genuinely fixes the class: "Petaling-Jaya"/"Petaling/Jaya"/
  "Petaling&Jaya" now resolve) and pinned the REMAINING limitation in an honest test rather than claiming a false win.
  -> Carry forward: segment-splitting lookup is a real follow-up, larger than a delimiter fix.
Final fix wave: F7 verified differentially — the agent temporarily removed the guard in malaysia/__init__.py and
  confirmed the test now fails, then reverted. Also added a fixture-drift guard assertion so it cannot silently go
  vacuous again.
Final fix wave: scoped re-review dispatched (sonnet, 79875e1..fcffcdb)
