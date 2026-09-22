# SDD ledger — plan: docs/superpowers/plans/2026-09-22-malaysia-pipeline-phase-0-1.md

Spec: docs/superpowers/specs/2026-09-22-malaysia-specialization-design.md (read)
Branch: feat/malaysia-pipeline-phase-0-1 (off docs/malaysia-specialization-design @ ea1b99a)

## Environment (controller-executed, Task 1 Steps 1-2)

No Python existed on this machine at session start. Installed:
- Python 3.12.10 via `winget install Python.Python.3.12 --scope user`
- Poetry 2.5.1 via `python -m pip install --user poetry`
- Venv created; `poetry lock` regenerated (lock was ALREADY stale vs pyproject before any edit of mine); `poetry install` succeeded.
- Verified: `poetry run python -c "import jobspy"` works, pydantic 2.9.2.

Ruling: tool shells inherit Claude Code's startup PATH, so `poetry`/`python` are NOT
resolvable by bare name in subagent shells until Claude Code restarts. All dispatches
must use the absolute poetry path:
  $env:APPDATA\Python\Python312\Scripts\poetry.exe
`poetry run <x>` activates the venv, so poetry is the only binary needing an absolute
path. Cost if wrong: subagents hit "command not found" and need a re-dispatch with the
path; no data loss.

## Preflight conflict scan

### Cross-task rows (shared file or interface)

| Tasks | Shared file / interface | Finding |
|---|---|---|
| T2 → T3 | `jobspy/frame.py`; `build_jobs_dataframe` | Clean. T2 creates, T3 extends location block. |
| T2 → T12 | `jobspy/__init__.py`; `build_jobs_dataframe` | Clean. T2 replaces row loop with a call; T12 wraps the executor above it. |
| T3 → T9 | `JobPost.remote_scope` | Clean. T3 adds field, T9 writes it. Ordered. |
| T3 → T10 | `JobPost.dedup_group` | Clean. T3 adds field, T10 writes it. Ordered. |
| T3 → T4 | `desired_order`, `state` column | Clean. T4's `state_match_rate` reads the column T3 adds. |
| T4 → T5 | `compute_metrics`, `render_report` | Clean. Signatures match call sites. |
| T6 → T7..T11 | `jobspy/malaysia/` package | Clean. T6 creates `__init__.py`; T11 replaces its contents (explicitly stated). |
| T6 → T8 | `detect_interval` | Clean. T8 imports it; signature matches. |
| T7..T10 → T11 | all four normalizers | Clean. Return types match pipeline call sites. |
| T11 → T12 | `normalize(jobs, *, group_duplicates)` | Clean. |
| T12 → T13 | `jobspy/__init__.py` executor block | Clean. T13's replacement carries T12's try/except forward; the normalize block sits below the `with` and survives. |
| T12 → T14 | `jobspy/__init__.py` `get_site_type`, `__all__` | Clean. Disjoint regions. |
| T13 → T12 tests | `tests/test_scrape_jobs_integration.py` | Clean. T12's two tests still pass under T13's two-pass (same job_url → exact dedup → 1 row). Verified both directions. |
| T5 → T14 | `docs/baseline/`, SEARCHES | Clean, with a caveat already stated in T14 Step 5: T13's second pass inflates row counts, so the two baselines are comparable on rates, not on volume. |
| T3 → T2 tests | `tests/test_frame.py` | Clean. T3 appends; T2's assertions stay true. |

### Per-task self-consistency rows

| Task | Self-consistent? |
|---|---|
| T1 | Yes (Steps 1-2 now already done by controller). |
| T2 | **F4** — drops `SalarySource`/`extract_salary`/`convert_to_annual`/`desired_order` imports but leaves `Location`, which also becomes unused. |
| T3 | Yes. |
| T4 | **F2** — `test_state_match_rate_is_none_when_unpopulated` asserts `== 0.0`, not None. Name contradicts assertion. |
| T5 | Yes. |
| T6 | Yes. Traced every date/query case by hand. |
| T7 | **F3** — `test_uses_state_field_when_city_is_unknown` uses "Bandar Baru Bangi", which IS in the gazetteer, so it never exercises the state-fallback path it claims to test. |
| T8 | Yes. Traced all 10 parse cases + 6 rejection cases against the regexes. |
| T9 | Yes. |
| T10 | Yes. Traced all 11 grouping cases. |
| T11 | **F1** — `test_normalizes_location_salary_and_remote` expects `remote_scope == "apac"`, but location runs before remote, so the normalized `country=MALAYSIA` makes `_MY_PATTERNS` match first and the result is `"my"`. Test contradicts the pipeline order the same task defines. |
| T12 | Yes. |
| T13 | Yes. |
| T14 | Yes. |

### Rulings (all made before Task 1 dispatch)

Ruling: F1 — T11's test will expect `remote_scope == "my"` and drop the "Open to APAC
candidates" sentence. The behavior is correct (a Cyberjaya-located remote job IS
MY-eligible) and T9 already covers APAC classification thoroughly; asserting "my" here
additionally pins the location-before-remote stage order, which is stronger. Cost if
wrong: this one test stops distinguishing APAC text, which T9 covers.

Ruling: F2 — rename to `test_state_match_rate_is_zero_when_unpopulated`. Assertion
stands. Cost if wrong: none, cosmetic.

Ruling: F3 — change the city to "Bandar Seri Putra" (absent from the gazetteer) so the
test exercises the state-fallback branch it names. Assertions unchanged. Cost if wrong:
the test keeps testing the city-hit path, which other cases already cover.

Ruling: F4 — the T2 implementer removes any import left unused, `Location` included,
rather than only the four the plan names. Cost if wrong: a lint-level unused import.

## Progress

Task 1: dispatched (sonnet, BASE ea1b99a) — brief task-1-brief.md, report task-1-report.md.
  Controller pre-did Steps 1-2 (env install); implementer starts at Step 3.
Task 1: implementer DONE (commit 471dd9b). Controller independently re-ran
  `poetry run pytest tests/ -q` -> 2 passed, output pristine. Review dispatched (sonnet).
Task 1: complete (commits ea1b99a..471dd9b, review clean — spec OK, quality Approved,
  0 Critical/Important). Reviewer's sole Minor (pristine output unverifiable from diff)
  already resolved by the controller's independent pytest run.
Task 2: dispatched (sonnet, BASE 471dd9b) — carries ruling F4.
Task 2: implementer DONE (commit 1475104). Review dispatched (sonnet).

Ruling: F5 (pydantic .dict() deprecation) — `jobspy/frame.py` calls `job.dict()`, moved
  verbatim from upstream. Emits PydanticDeprecatedSince20 on 3 tests; confirmed by
  controller running `pytest -W default`. It is genuinely pre-existing, but it was
  invisible until Task 2 gave it test coverage, and left alone it makes "test output is
  pristine" unenforceable for the remaining 12 tasks.
  Decision: change `.dict()` -> `.model_dump()`, but NOT as a mid-review scope change to
  Task 2. Carry it into Task 3, which already modifies that exact block in frame.py.
  Safe because in pydantic v2 `.dict()` is a pure alias for `.model_dump()`: same
  mode="python", nested models still become dicts (frame.py relies on this via
  `Location(**job_data["location"])` and the `isinstance(compensation_obj, dict)` check),
  and enum members are preserved (relied on by `.get("interval").value` and
  `job_type.value[0]`). Verified each of those call sites against the semantics.
  Cost if wrong: DataFrame values change shape subtly; caught immediately by Task 2's
  four behavior-preservation tests, which Task 3 re-runs.
Task 2: complete (commits 471dd9b..1475104, review clean — spec OK, quality Approved,
  0 Critical/Important, 2 Minor). Reviewer independently verified behavior preservation
  line-by-line and confirmed ruling F4 was applied correctly.

Reviewer DISSENT on ruling F5, recorded: the Task 2 reviewer argued leaving `.dict()`
  alone is correct and that switching to `.model_dump()` would be "an unrequested
  behavior/API change." Its scope-creep point is fair; its technical reason is not —
  in pydantic v2 `.dict()` is a pure alias that calls `model_dump()` and then warns,
  so there is no behavior or API delta. F5 STANDS, on the narrower ground that
  `frame.py` is a file THIS plan created and Task 3 edits that exact block, making it
  "improve the code you are working in" rather than unrelated refactoring.
  Cost if wrong: a one-word revert.

Task 2 Minor (actioned, not deferred): frame.py had no test for the
  `enforce_annual_salary=True` path or the `Country.USA` description-salary branch —
  a real gap in a function three later tasks depend on. Folded into Task 3, which
  already touches frame.py and its test file.
Task 3: dispatched (sonnet, BASE 1475104) — carries F5 + the Task 2 coverage Minor.
Task 3: implementer DONE (commit 9a5c89d). 11 passed, 0 warnings -> ruling F5 confirmed
  correct: the four Task 2 behavior-pinning tests still pass after .dict()->.model_dump().

Ruling: F6 (repo-wide Black churn) — the brief's `black jobspy tests` reformatted 14
  files no task in this plan owns (bayt, bdjobs, exception, glassdoor, google, indeed,
  linkedin, naukri, ziprecruiter), 266+/215- lines, left unstaged by the implementer.
  Inspected with `git diff -w` and read the largest hunk: pure Black line-splitting,
  zero semantic change. Decision: REVERTED all 14. The plan never asked to reformat the
  repo, most of these are boards this fork will quarantine in Task 14, and keeping them
  would bury the final whole-branch review in unrelated churn.
  Future dispatches instruct: run black ONLY on the files you changed.
  Cost if wrong: repo style debt persists in untouched files — which is the status quo.
Task 3: review dispatched (sonnet).
Task 3: complete (commits 1475104..9a5c89d, review clean — spec OK, quality Approved,
  0 Critical/Important, 1 cosmetic Minor). Reviewer verified desired_order positions
  line-by-line against the brief and grepped that no `.dict()` remains in jobspy/.
  Rulings F5 and the Task 2 coverage Minor both verified as correctly applied.
Task 4: dispatched (haiku — brief carries complete code, transcription+testing).
  BASE 9a5c89d. Carries ruling F2 and the scoped-black instruction (F6).
Task 4: complete (commits 9a5c89d..581f22b, review clean — spec OK, quality Approved,
  0 Critical/Important, 3 Minor). Reviewer empirically verified the all-null
  value_counts key, .duplicated() semantics, and render_report on empty metrics.
  Ruling F2 verified applied.
  Carry-forward from Task 4 Minor #3: `state_match_rate` is a plain fill-rate, so it
  only means "gazetteer match rate" if Task 7 populates `state` ONLY on a genuine match.
  The design already requires this (unmatched locations pass through untouched). Added
  to Task 7's dispatch as an explicit invariant to preserve.

Ruling: F7 (Task 5 live step) — Task 5 Step 5 runs the harness against real job boards
  and the plan makes it a STOP condition ("if every search returns zero rows, stop and
  investigate"). Splitting the task: the implementer does Steps 1-4 and 6 (runner code,
  unit tests with a fake scrape fn, commit); the CONTROLLER executes Step 5 and judges
  the result, because evaluating a plan-gating stop condition is not delegable, and a
  subagent waiting on multi-minute network calls burns turns for nothing.
  Cost if wrong: the live capture happens one dispatch later than the plan drew it.
Task 5: dispatched (haiku, BASE 581f22b) — Steps 1-4 and 6 only.
Task 5: complete (commits 581f22b..c6e8f19 code, b3b1fdd baseline report; review clean —
  spec OK, quality Approved, 0 Critical/Important). Reviewer verified SEARCHES field-by-
  field and confirmed no reachable network path from the tests.

## PHASE 0 BASELINE RESULT (controller-executed Step 5) — NOT a stop condition

400 rows: indeed 200, linkedin 200, **google 0**. Salary fill 0.0%. Date fill 100%.
Remote rate 15.8%. Exact dup rows 43 (10.8%). Company+title dup rows 53.
Stop condition NOT met (it required EVERY search returning zero); continuing.

Follow-up probe (controller, 30 rows, indeed+linkedin) established the facts below.

Ruling: F8 — `state_match_rate` is MISLEADING and must be redefined. It reported 91.2%
  BEFORE any normalization exists, because scrapers already emit a raw `Location.state`
  and Task 3 surfaced it. The probe shows those raw values are
  ['Federal Territory of Kuala Lumpur', 'M14', 'Malaysia', 'Selangor'] — a mix of ISO
  codes, full names, and 'Malaysia' (a COUNTRY sitting in the state field). As written
  the metric would show ~91% before and ~91% after, making Task 14's before/after
  comparison worthless. Decision: redefine it to count only rows whose `state` equals a
  canonical `MalaysianState` value; implement in Task 7, which creates that enum and owns
  the notion of canonical. Cost if wrong: one metric needs recomputing from saved data.

Ruling: F9 — Indeed Malaysia returns ISO 3166-2:MY state CODES, not names: M01=Johor,
  M07=Pulau Pinang, M10=Selangor, M14=Kuala Lumpur (confirmed against the city names
  co-occurring with each: Johor Bahru/M01, Bayan Lepas+Butterworth+George Town/M07,
  Petaling Jaya+Cyberjaya+Shah Alam/M10, Kuala Lumpur/M14). The planned gazetteer maps
  NAMES only and would miss every Indeed row. Decision: Task 7 must add the full M01-M16
  ISO code map, and must NOT treat the literal 'Malaysia' as a state. This requirement
  was measured, not anticipated by the plan. Cost if wrong: Indeed rows stay unnormalized,
  which is the current state anyway.

Ruling: F10 — Google returned 0 rows across both searches that requested it. Consistent
  with the fork README's own FAQ (Google Jobs needs very specific phrasing). NOT treated
  as a blocker: two of three boards returned full result sets. Decision: continue, and
  Task 14 must not claim Google coverage in the before/after comparison. Cost if wrong:
  we under-count available listings, which is visible in the report's per-site table.

Ruling: F11 — LinkedIn supplies NO descriptions (probe: description_filled=0/15), because
  `linkedin_fetch_description` defaults False and enabling it costs O(n) extra requests on
  the most rate-limited board. Indeed supplies descriptions for 15/15, of which 5/15 (33%)
  actually contain "RM". Consequence: the Task 8 MYR parser can only ever lift salary on
  Indeed rows, so the realistic ceiling for Phase 1 is roughly 33% of Indeed = ~16% of
  total rows, NOT a large fraction of 400. Decision: do NOT enable
  linkedin_fetch_description (it would break run-to-run comparability and invite 429s);
  instead record the bound now so Task 14's "salary fill rate went up" criterion is judged
  against ~16%, not against an implied 100%. Without this, Task 14 would have read a
  correct result as a failure. Cost if wrong: we under-collect LinkedIn salary data that
  was never available by default anyway.
Task 6: review = NEEDS FIXES. 2 Important (both plan-mandated), 3 Minor.

Ruling: F12 — `to_bm_query` re-processes its own output. The multi-word pass rewrites
  "production operator" -> "operator pengeluaran", then the single-token pass re-reads
  "operator" and rewrites it to "pengendali", yielding "pengendali pengeluaran".
  Reviewer verified by direct execution. The bug is in MY plan's prescribed code, not an
  implementer deviation. Finding UPHELD over the plan text: the spec requires BM query
  expansion to translate role words correctly, so the plan's code contradicts the spec it
  argues from, and the spec is the binding authority. Fix = single greedy longest-match
  pass over tokens (never re-examines emitted output; also removes the Minor about
  word-boundary-free substring matching). Cost if wrong: one query term maps oddly on a
  board not built until Phase 3.

Ruling: F13 — two of the three order-dependent behaviors the brief called "subtle" are
  correctly coded but NOT pinned: no _FIXED_OFFSET_DAYS key contains a digit (so the
  regex can never collide with it), and no interval key is a substring of another (so the
  longest-first sort is currently a no-op). Reviewer enumerated all 26 keys to establish
  this. Finding UPHELD — Task 8 imports detect_interval, and a later dict edit could
  silently break precedence. Fix = add one genuine-collision test per function.
  Cost if wrong: two extra tests.

Task 6: minor (deferred): `test_bm_job_types_resolve` covers 4 of 6 new JobType values —
  `sementara` and `praktikal` never round-tripped (brief-mandated gap).
Task 6: minor (deferred): whitespace/lower normalization duplicated across all three
  public functions in language.py; a private _normalize() would DRY it.

Controller error, recorded: my Task 6 review dispatch claimed the implementer's report
  said "5 values" while listing six. The report actually said "Five JobType enum tuples
  updated", which is correct (5 members, 6 values). I introduced a false premise into the
  review prompt; the reviewer checked it and correctly dismissed it. No harm, but the
  dispatch should have quoted the report rather than paraphrasing it.
Task 6: fix round 1/5 dispatched to original implementer.
Task 6: fix round 1/5 (3 addressed, 0 open; commits 6648722..fbbd2cf). Controller also
  independently executed to_bm_query on all 6 documented cases post-fix: correct.
Task 6: complete (commits b3b1fdd..fbbd2cf, review clean after 1 fix round). 50 tests.
Task 7: dispatched (sonnet, BASE fbbd2cf) — carries rulings F3, F8, F9 plus the measured
  gazetteer seed data and the Task 4 canonical-state invariant.
Task 7: implementer DONE (commit bfd0bf9), 90 tests. Controller verified against 20 REAL
  (city,state) pairs from the live baseline: 17/20 resolved; the 3 misses are all correct
  misses (Remote, Kampong Api Api, Malaysia-as-state). All four verified ISO codes map
  right. This also resolves the reviewer's ⚠️ (spot-check gazetteer vs baseline table).
Task 7: review = NEEDS FIXES. 1 Important (plan-mandated), 2 Minor.

Ruling: F14 — raw `state` pass-through on the unmatched path IS a defect. I raised this
  tension to the reviewer without resolving it (my dispatch's invariant said "never pass
  an unrecognized state through" while the brief said "pass through untouched"); the
  reviewer adjudicated it and I UPHOLD its finding. Decisive argument, which I had not
  made myself: `unmatched` already carries the raw text so nulling `state` loses zero
  information, while Task 10's `_compatible_location` groups jobs by equal state — so two
  unrelated unresolved jobs both carrying the junk value 'Malaysia' (a value that really
  does occur, 400-row sample) could be falsely grouped. That directly violates the spec's
  "tuned conservative / a wrong group asserts two distinct openings are the same job"
  rule. Fix = null `state` on the miss path only; keep `city` and `country`, keep
  `unmatched` as-is. Cost if wrong: the DataFrame's state column loses raw values that
  are still recoverable from `location`.
Task 7: minor (deferred): `_canonical_state_rate` rebuilds the valid-state set per call.
Task 7: minor (deferred): loop variables leak as module-level names in location.py
  (shared with the brief's own starter code).
Task 7: fix round 1/5 dispatched to original implementer.
Task 7: fix round 1/5 (1 addressed, 0 open; commits bfd0bf9..5d63b15). Controller re-ran
  the 20-pair real-data probe: misses now yield state=None, city preserved, unmatched
  intact, 17/20 still resolving.
Task 7: complete (commits fbbd2cf..5d63b15, review clean after 1 fix round). 90 tests.

## Real salary data (controller probe, 40 live Indeed descriptions, 27 unique RM snippets)

Dominant real format is Indeed's own footer: "Pay: RM3,500.00 - RM4,000.00 per month"
(~20 of 27). Others seen: "RM 3,000.00 to RM 3,500.00", "RM6,000 - RM9,000/month"
(en-dash + /month), "Pay: From RM1,800.00 per month", "Pay: Up to RM800.00 per month",
"* Basic Salary: **RM 3000**" (markdown bold), "RM1,700.00 - RM4,129.48 per month".
NOTE: 100% of intervals seen were monthly; no hourly/daily examples in the sample.
NOTE: descriptions DO carry pay even though Indeed's structured compensation field is
null — which is exactly why salary fill rate was 0% and why this parser is the only lever.

Ruling: F15 — the plan's monthly floor of RM1,000 would WRONGLY REJECT real postings.
  Live data contains "Pay: RM800.00 per month" and "Pay: Up to RM800.00 per month".
  The plan's own rationale for the floor was that a bare RM800 is likelier hourly than
  monthly — but that reasoning only holds when the interval is INFERRED. When the text
  states "per month" there is nothing to infer, and rejecting it discards a correctly
  stated wage. Decision: apply the tight MY sanity bands ONLY when the interval was
  inferred (defaulted to monthly); when an interval word is explicitly present, accept any
  positive amount below an absurdity ceiling. Cost if wrong: a mis-stated salary in a
  posting that explicitly names its interval is accepted; bounded by the ceiling.
Task 8: implementer DONE (commit ab850b9), 117 tests.
  FOUND A REAL BUG IN THE PLAN'S REGEX: `_AMOUNT`'s first alternative
  `\d{1,3}(?:,\d{3})*` matches "300" out of "3000" (the comma group can match zero times,
  so the branch succeeds early and the engine never tries the `\d+` alternative) —
  a 10x under-report on every comma-less 4+ digit amount. Exposed by the real string
  "* Basic Salary: **RM 3000**" that the controller supplied from live data; the plan's
  invented test cases all used commas and would never have caught it. Fix: `*` -> `+`.
  Controller verified all 11 real strings parse and all 4 negative cases reject:
  RM 3000 -> 3000; RM800.00 per month -> 800 (F15 works); bare RM800 -> None (band still
  guards inferred intervals); $-amounts and inverted ranges -> None.
Task 8: review dispatched (sonnet).
Task 8: complete (commits 5d63b15..ab850b9, review clean — spec OK, quality Approved,
  0 Critical/Important, 2 Minor). Reviewer independently re-derived the regex bug and the
  fix, traced short/multi-comma/silent-wrong-number cases. Controller cleared its ⚠️ by
  re-running the suite: 117 passed, 0 warnings.
Task 8: minor (deferred): no direct positive assertion on a triple-comma amount value
  (only indirect via a reject-band test).
Task 8: minor (deferred, CONSEQUENCE OF RULING F15): `_ABSURDITY_CEILING` is uniform
  across intervals, so an explicit but absurd "RM 3,000,000 per hour" is accepted. F15
  removed the FLOOR check on the explicit path; a per-interval CEILING would not
  reintroduce the RM800 problem and could be reinstated. Flagged for the final review to
  triage — not fixed here because it is a Minor and would extend an approved task.
Task 9: dispatched (haiku, BASE ab850b9).
Task 9: implementer DONE (commit 8c03387). Review = NEEDS FIXES. 3 Important (all
  plan-mandated, all empirically verified by the reviewer executing the classifier), 2 Minor.

Ruling: F16 — three regexes I wrote produce false positives on ordinary job-posting
  boilerplate. All three UPHELD; the patterns are mine, not implementer deviations.
  (a) `\b(?:est|pst|cst|pdt|edt)\b` matches "est." = established -> false other_country.
  (b) `gmt[+-]...(?=.*\b(?:us|america)\b)` reads the PRONOUN "us" ("contact us",
      "about us") as the United States -> false other_country, and it fires on exactly
      the GMT+8 postings the apac branch exists to catch.
  (c) `\bsgt\b` matches "Sgt" (Sergeant) -> false apac.
  (a) and (b) sit on the HIGHEST-precedence branch, so they override a correct MY signal
  in the same text — the design's own stated worst case. Fixes: drop the ambiguous
  abbreviations `est`/`cst` and add unambiguous full phrases; DELETE the GMT lookahead
  entirely (its real signal is already covered by the explicit exclusion phrases, and
  `\bus\b` cannot be disambiguated from the pronoun); drop `sgt`.
  Cost if wrong: we lose a weak US-timezone signal and classify a few genuinely US-only
  remote jobs as `unknown` instead of `other_country` — a far cheaper error than the
  false exclusion it replaces, since the field sorts rather than filters.
Task 9: minor (deferred): Country enum special-casing is Malaysia-only, so a structured
  Country.SINGAPORE signal contributes nothing to the haystack.
Task 9: minor (deferred): precedence among my/apac/global is not pinned by a test with
  two competing signals (only other_country-beats-generic is pinned).
Task 9: fix round 1/5 dispatched to original implementer.
Task 9: fix round 1/5 (3 addressed, 0 open; commits 8c03387..4b4ba52). Re-reviewer
  confirmed test integrity: only the authorized "Core hours are EST." expectation moved;
  the other six pre-existing cases unchanged. Controller ran 16 branch cases: 0 mismatches.
  Note: "Team works Eastern Standard Time." still -> other_country, so the full-phrase
  patterns recover most of the signal that dropping `est` gave up. F16's cost is smaller
  than I estimated when I made the ruling.
Task 9: complete (commits ab850b9..4b4ba52, review clean after 1 fix round). 122 tests.

## Real company/title data (controller probe, 120 live rows, 94 distinct companies)

TWO REAL INSTANCES of the exact seniority-collision the guard exists to prevent:
  AVEVA: "Full-Stack Engineer (.NET + Angular)" vs "Senior Full-Stack Engineer (.NET + Angular)"
  Applify Technologies Sdn Bhd: "MES System Developer" vs "Senior MES System Developer"
Both would score very high on raw title similarity and MUST NOT group. Handed to Task 10
as required tests — the plan's invented cases used a bare "Senior Software Engineer",
these are messier and more realistic.

Real company-suffix forms seen: "Sdn Bhd", "SDN BHD" (uppercase), "(M) Sdn Bhd"
(Conspec Builders (M) Sdn Bhd — parenthesised Malaysia marker), "GmbH", "Inc.",
"Beyondsoft Singapore", "Experian Asia Pacific".
Task 10: dispatched (sonnet, BASE 4b4ba52) with the above as required test data.
Task 10: implementer DONE (commit a401ea4), 150 tests. Reported TWO defects in the
  brief's own code (both real, both mine):
  (a) `assign_groups` skipped singleton clusters, so 3 of the brief's OWN tests
      (`test_never_groups_across_seniority`, `..._different_states`, `..._different_companies`)
      asserted `a.dedup_group != b.dedup_group` on two ungrouped jobs -> None != None -> False.
      My plan's tests could not pass against my plan's implementation.
  (b) `_group_id(company, title, state or "remote")` collapses state=None onto the literal
      "remote" placeholder.

CONTROLLER CORRECTION of my own earlier claim: I told the implementer (and the user) that
  the two real seniority pairs "would score very high" on title similarity. Measured:
  token_sort_ratio is 89.86 (AVEVA) and 85.11 (Applify) under the module's normalization —
  BELOW the 90 threshold, so they would not have merged on score alone. The implementer
  flagged this rather than letting my framing stand, and rewrote its tests to pin the real
  numbers. My claim was overstated and is corrected here.
  BUT the probe also shows token_set_ratio = 100.00 for ALL THREE pairs (incl. the plain
  "Software Engineer"/"Senior Software Engineer" case). So the token_sort_ratio-over-
  token_set_ratio choice IS decisively load-bearing, and AVEVA at 89.86 sits a hair under
  the threshold — the guard still does real work at the margin.

OPEN QUESTION for review (controller probe, NOT yet adjudicated): two non-remote jobs with
  identical company+title and NO resolvable location came back with the SAME dedup_group.
  If they are in separate clusters but share a hash, the code says "not grouped" while the
  data says "grouped", and a downstream groupby would merge them. Handed to the reviewer
  with the probe evidence rather than resolved by me.
Task 10: review dispatched (sonnet).
Task 10: review = Approved verdict BUT 1 Important finding -> fix loop triggers anyway
  (per process: any Important finding enters the loop regardless of the verdict line).

CONTROLLER PROBE WAS WRONG, corrected: my "two unresolved jobs share a dedup_group" probe
  compared `None == None`, which is True in Python. Both jobs had dedup_group=None; the
  clustering had correctly kept them in separate singleton clusters. Not a hash collision.
  My probe asserted equality of two Nones and I reported it as a possible defect — the
  reviewer reproduced it, traced the real cause, and refuted my reading. My instrument was
  the bug, not the code.

Reviewer adjudications (both accepted):
  - Stamping singletons IS the better design, not a test-passing hack: pandas groupby
    drops NaN keys by default, so leaving singletons None would silently delete every
    non-duplicate row from the user's opt-in groupby — inverting the stated design.
  - The None-equality gap is real though: `dedup_group=None` cannot distinguish
    "deliberately not grouped" from "not considered", and the test covering that scenario
    asserts `is None` twice rather than `!=` like its three sibling tests — avoiding the
    one assertion that would expose it.

Ruling: F17 — fix rather than document. Stamp unresolvable rows with a per-row-unique
  STABLE fallback id (derived from the canonical job url) instead of the shared None
  sentinel. This makes the contract uniform — every row always carries an id, duplicates
  share one, and "is this a duplicate?" is a group-size question — which is exactly the
  consistency the singleton-stamping decision already committed to. Documentation alone
  would leave a trap that the controller itself just fell into. Cost if wrong: the column
  is never null, so a null-check idiom for "is duplicate" stops working; group size
  replaces it, as it already had to after singleton stamping.
Task 10: minor (deferred): the two token_sort_ratio "on record" tests assert rapidfuzz
  behavior, not grouping behavior — disclosed honestly in the report as documentation.
Task 10: fix round 1/5 dispatched to original implementer.
Task 10: fix round 1/5 (1 addressed, 0 open; commits a401ea4..7828a15). Fallback id is
  blake2s over "unresolved|" + canonical url (falling back to job.id) — genuinely stable
  across processes and namespaced so it cannot collide with real cluster hashes. The
  re-reviewer confirmed the derivation from the CODE, which my single-process probe could
  not have distinguished from an id()/index-based id.
Task 10: complete (commits 4b4ba52..7828a15, review clean after 1 fix round). 151 tests.
Task 11: dispatched (sonnet, BASE 7828a15) — carries preflight ruling F1.
Task 11: IMPLEMENTER TERMINATED MID-TASK by an API session limit. Its last message:
  "All 158 tests pass (151 previous + 7 new), pristine, no warnings. Now run black on the
  two changed files only." It had written both files and gone green, but never ran black,
  never wrote its report, never committed.

Ruling: F18 — controller completes the interrupted task's MECHANICAL steps rather than
  re-dispatching. Re-dispatching a fresh implementer to run `black` and `git commit` on
  code already written and green would rebuild full context for two commands. The
  controller read BOTH files in full before touching them, re-ran the suite (158 passed,
  0 warnings), ran black (reformatted one signature line in __init__.py only), re-ran the
  suite (158 passed, 0 warnings), and committed as 319bce0. NO implementation logic was
  authored or altered by the controller. The normal task review still gates the work, so
  nothing skips review. Cost if wrong: the controller touched a task it should have
  delegated; the diff is unchanged either way and the reviewer sees it fresh.

  Evidence gaps created by the interruption, disclosed to the reviewer rather than hidden:
  (a) no TDD RED evidence exists — the red-phase output died with the agent;
  (b) the F1 counterfactual (that the brief's original "apac" assertion really WOULD have
      failed) is unverified, since the original assertion no longer exists to run;
  (c) no implementer self-review was recorded.
  A stand-in report documenting all of this was written to task-11-report.md, clearly
  marked as controller-authored and second-hand.
Task 11: review dispatched (sonnet) with the evidence gaps named.
Task 11: review = Approved verdict BUT 1 Important finding -> fix loop triggers.
  RULING F1 CONFIRMED CORRECT BY EXECUTION: the reviewer reconstructed the brief's
  original job (Cyberjaya + "Open to APAC candidates.") and ran normalize() — result was
  remote_scope="my", not "apac". The preflight ruling, made before any code existed, was
  right, and the test was changed for the correct reason rather than on a bad premise.
  The reviewer also traced the mechanism through location.py:278 -> remote.py:68-69 ->
  the _MY_PATTERNS-before-_APAC_PATTERNS precedence.

Ruling: F19 — the Important finding is UPHELD and fixed. "Wrapped is not swallowed" is a
  named global constraint, and its REPORTING half (per-job WARNING + per-stage rollup
  count) has zero regression coverage. The code implements it correctly today, but a
  refactor could delete the rollup block silently — which is precisely the slow
  silent-degradation failure this constraint exists to prevent, and the kind of thing
  nobody notices for months. A constraint worth stating is worth a test.
  Cost if wrong: one extra test.
Task 11: minor (deferred): stage dispatch branches on `stage_name == "location"` to pass
  the extra Counter; fragile if renamed or if a second stage needs shared state.
Task 11: minor (deferred): per-job failure logs carry str(exc) but no exc_info, so a bare
  AttributeError gives a debugger the job url but not the call site.
Task 11: minor (deferred): assign_groups failure is not atomic — already-processed company
  blocks keep their dedup_group while the log says "continuing ungrouped".
Task 11: minor (deferred): two tests would pass against a no-op gutted pipeline.
Task 11: fix round 1/5 dispatched (attempting to resume the original implementer, which
  had died on a session limit that has since reset).
Task 11: fix round 1/5 (1 addressed, 0 open; commits 319bce0..ca680e2, test-only).
  Re-reviewer confirmed the new test cannot pass vacuously: without the propagate
  monkeypatch caplog.records would be empty and `any()` over an empty list is False, so
  it fails loudly rather than passing silently. Implementer also independently re-verified
  the F1 counterfactual by execution and recovered the RED/GREEN evidence lost in the crash.
Task 11: complete (commits 7828a15..ca680e2, review clean after 1 fix round). 159 tests.
Task 12: dispatched (sonnet, BASE ca680e2). Brief confirmed to carry the corrected
  site_by_job/regrouped wiring rather than the fragile first draft.
Task 12: implementer DONE (commit d6d70dc), 163 tests. Hardened the id()-mapping with a
  .get() + logged "unknown"-bucket fallback rather than a raising lookup.

## CONTROLLER END-TO-END PROBE (first full-pipeline run against live boards, 31 rows)

Working as designed: states normalize to canonical values only ('Kuala Lumpur',
'Selangor'), 27/31 state+city filled, 31/31 dedup_group stamped (Task 10 fallback works),
remote_scope all None because no row is is_remote yet (Task 13 adds the remote pass) —
which is the correct None-for-non-remote behavior. The single Indeed row's salary parsed:
"Test Automation Engineer" -> monthly RM3,500-5,000 MYR.

DEFECT FOUND IN COMPLETED WORK (Task 10):
  dedup group 9d9029ef856a grouped "Software Engineer II" with "Software Engineer I"
  at Experian Asia Pacific. Roman-numeral/numeric LEVEL suffixes are not in
  _SENIORITY_MARKERS, so the guard never fires and the titles score ~97% on
  token_sort_ratio. This is the design's stated worst case — a wrong group asserting two
  distinct openings are the same job — and it appeared in a 31-row sample, so it is not rare.

Ruling: F20 — fix NOW rather than deferring to the final whole-branch review. Task 14
  re-runs the live baseline and reports duplicate-rate numbers to the user; measuring with
  a known-broken grouper would put a wrong number in the deliverable and require redoing
  the measurement anyway. Dispatching a targeted fix to the Task 10 implementer, whose
  context is intact. Cost if wrong: one extra fix round before the final measurement.

ALSO NOTED: Indeed returned only 1 row this run vs 15-40 in earlier probes. Likely rate
  limiting from my own repeated probing. Flagged as a risk to Task 14's baseline
  comparability — the "after" run may under-represent Indeed through no fault of the code.
Task 10 (reopened): level-suffix fix committed as 5584e43 BEFORE the implementer lost its
  connection mid-response; only its report append was lost. Controller wrote the report
  section (clearly marked as controller-authored), verified 9 constructed cases — 8 behave
  as intended and the 9th was MY expectation being wrong, not a defect: "Software Engineer 2"
  vs "Software Engineer II" normalize to the same level marker but their raw titles fall
  under the 90 similarity threshold, so they do not group. That is a missed group, the
  cheap error the design explicitly prefers. Suite: 169 passed, 0 warnings.
  Evidence gap: no implementer RED/GREEN observation for the new tests.
Task 10 (reopened): fix re-review dispatched (haiku).
Task 12: review dispatched (sonnet).
Task 12: review = Approved verdict BUT 1 Important finding -> fix loop triggers.
  Reviewer independently verified: the board-failure guard is airtight end-to-end (the
  scraper constructor and .scrape() both run inside the worker thread, so every exception
  surfaces at the guarded future.result(), and neither the logging call nor the empty
  JobResponse construction can itself raise); the Malaysia gate leaves the USA path
  genuinely untouched; the id()-identity assumption holds (it read grouping.py to confirm
  dedupe_exact never copies and assign_groups mutates in place); and the "unknown" site
  fallback is a defensible, honestly-labeled degradation of already-unreachable code.

Ruling: F21 — the Important finding is UPHELD and fixed. There is no test proving
  `scrape_jobs(country_indeed="usa")` skips the Malaysia pipeline. My own dispatch named
  this as the most dangerous regression risk ("would silently change behavior for any
  existing non-MY user"), and it is currently guarded only by reading the code. A risk
  worth naming is worth a test. Cost if wrong: two extra tests.

Ruling: F22 — also fold in the `site` variable-shadowing Minor now rather than deferring.
  `site` is a Site enum in the executor loop and a str in the regrouping loop, same
  function scope. Both the implementer and the reviewer independently flagged it as a trap
  specifically for Task 13, which rewrites that exact region next. Renaming it costs
  nothing now and removes a live hazard from the next task rather than leaving a deferred
  minor in the path of a rewrite. Cost if wrong: a rename touching a few lines.
Task 12: minor (deferred): failure-path logger uses site.value.capitalize() so LinkedIn
  logs as "JobSpy:Linkedin", inconsistent with the success path's special-casing.
Task 12: minor (deferred): ERROR log carries str(exc) without exception type or exc_info.
Task 12: minor (deferred, for whoever next edits jobspy/malaysia/): the "unknown"-bucket
  fallback path is entirely untested, so a future break of the identity contract would be
  caught only by a production WARNING.
Task 12: fix round 1/5 dispatched to original implementer.
Task 10 (reopened): fix round 1/1 ADDRESSED (commits d6d70dc..5584e43). Re-reviewer
  reconstructed the missing RED evidence analytically (naming which 4 tests would have
  failed pre-fix and why the 2 regression tests pass either way), confirmed trailing-only
  anchoring, confirmed same-level jobs still group (the guard blocks only when markers
  DIFFER), and endorsed keeping letter-codes like "L3" in a separate namespace from bare
  digits since the letter usually denotes a job ladder rather than a level.
  It also independently reached my conclusion on the tradeoff direction: any over-firing
  here costs a MISSED group, never a wrong one. Task 10 closed again.
Task 12: fix round 1/5 (2 addressed, 0 open; commits d6d70dc..c3c0882). Re-reviewer
  confirmed the gate tests discriminate in BOTH directions (the pair fails for a missing,
  inverted, always-open OR always-shut gate), confirmed the spy genuinely intercepts
  because scrape_jobs resolves `malaysia_normalize` through the module global at call time
  rather than early-binding it, and checked every renamed reference.
Task 12: complete (commits ca680e2..c3c0882, review clean after 1 fix round). 171 tests.
Task 13: dispatched (sonnet, BASE c3c0882) — rewrites the executor region Task 12 built,
  so it must carry forward both the board-failure guard and the site/site_value rename.
Task 13: implementer DONE_WITH_CONCERNS (commit 0fd1913), 174 tests. Flagged a REAL
  regression it declined to fix as out of its file scope — correct escalation.

Ruling: F23 — CONFIRMED BY READING THE CODE. The two-pass block
  (`if include_remote and not is_remote:`) runs for EVERY country, but the exact dedup that
  absorbs the overlap lives inside `if country_enum == Country.MALAYSIA:`. Since
  include_remote defaults True, `scrape_jobs(country_indeed="usa")` would return every
  listing TWICE. That is a live regression for any non-MY caller, introduced by this task,
  and it is exactly the class of silent behavior change the Task 12 gate test was added to
  guard against.
  Decision: gate the second pass on the SAME Malaysia condition, so the design's invariant
  ("two passes, and exact dedup absorbs the overlap") holds structurally rather than by
  coincidence. Considered and rejected the alternative of running exact dedup for all
  countries: it would mean calling the Malaysia module on behalf of non-MY users, and
  restructuring normalize() to expose a country-agnostic dedup is scope creep at task 13
  of 14. Under this fix non-MY callers get exactly their prior behavior — one pass, no
  doubling — so there is no regression for them at all.
  Cost if wrong: a non-MY caller wanting two-pass remote coverage does not get it; they
  never had it, and `is_remote=True` still gives them a remote-only search.

  Concern 1 (accepted, no action): the implementer pinned the pre-existing
  `test_pipeline_runs_for_malaysia` to include_remote=False with an explanatory comment,
  because its spy replaces normalize() and so bypasses the dedup that would collapse the
  two passes. That isolates the variable the test actually exists to pin (the country
  gate) rather than bending an assertion, and it touched no production code. Sound.
Task 13: fix round 1/5 dispatched to original implementer.
Task 13: review = Approved BUT 1 Important -> fix loop triggers. Reviewer verified the
  board-failure guard and site/site_value split both survived the rewrite by reading the
  code, confirmed the deep-copy semantics and skip-when-already-remote, and independently
  established that gating the second pass is both NECESSARY AND SUFFICIENT (it traced that
  the Malaysia block is the ONLY place any dedup happens, so there was no other mechanism
  the fix could have relied on). It also judged the pinned pre-existing test legitimate
  isolation rather than a weakened assertion, noting only the one test whose spy defeats
  dedup was pinned while two others that exercise real dedup were left unpinned.

Ruling: F24 — the Important finding is UPHELD. This is a fair hit against MY ruling F23.
  I fixed the doubling by gating the second pass on country, which means `include_remote`
  — a public parameter defaulting to True — is now silently a no-op for any non-MY caller,
  with no docstring, no log, and no difference visible in the returned DataFrame. The code
  comment I asked for explains the coupling to a future MAINTAINER but says nothing to a
  CALLER. A default-on parameter that silently does nothing is exactly the kind of quiet
  surprise this project has been trying to avoid. Fix: document it in the signature's
  docstring AND emit a log when the parameter is dropped, so it is discoverable both by
  reading and at runtime. Cost if wrong: a docstring line and one log call.
Task 13: minor (deferred): jobs_to_run builds the full sites x passes cross-product, so
  the Malaysia two-pass case doubles concurrent executor threads — fine at current scale.
Task 13: minor (deferred): the pinned-test comment block is longer than it needs to be.
Task 13: fix round 1/5 dispatched to original implementer.
Task 13: fix round 1/5 (1 addressed, 0 open; commits 2037a96..8ee66ea). Re-reviewer
  traced all four include_remote x country combinations and confirmed only the genuinely
  surprising one logs. Critically, it verified the three NEGATIVE log tests are not
  vacuous: all four tests set verbose=2 (the default verbose=0 gates JobSpy:* loggers to
  ERROR, which would have made "asserts no log" pass no matter what the code did), and the
  implementer's RED/GREEN — replacing log.info with pass, seeing the positive test fail
  while the negatives held — proves they pin absence rather than suppression.
Task 13: complete (commits c3c0882..8ee66ea, review clean after 1 fix round). 179 tests.
Task 14: dispatched (sonnet, BASE 8ee66ea) — code + README only; per the F7 precedent the
  CONTROLLER executes the live baseline capture and its interpretation.

## PHASE 1 BASELINE RESULT (controller-executed) — READ THE CAVEATS

Raw: 204 rows (indeed 4, linkedin 200). Salary fill 2.0%. State match 91.2%.
Remote rate 1.0%. Exact dup rows 39. Committed as docs/baseline/2026-09-23-baseline-phase1.md.

THE COMPARISON IS LARGELY INVALID, and I will not present it as a clean win:

1. INDEED WAS RATE LIMITED TO 4 ROWS (was 200). I caused this by probing the board
   repeatedly all day. Every volume-dependent metric is therefore incomparable, and since
   Indeed is the ONLY source of description text, it is also the only source of parseable
   salary and most remote listings. The remote-rate drop (15.8% -> 1.0%) is explained by
   Indeed's collapse, not by a regression.

2. THE STATE METRIC CHANGED DEFINITION BETWEEN THE TWO RUNS, so 91.2% before and 91.2%
   after are NOT the same measurement and must not be compared. Before it was "has any
   state string" (counting junk like M14 and Malaysia); after, ruling F8 redefined it as
   "has a canonical MalaysianState". Verified the new definition is genuinely wired in
   (metrics.py:85 calls _canonical_state_rate). The identical number is coincidence.
   A true before/after on state would require re-running the OLD baseline with the NEW
   metric, which I have not done.

3. `exact_duplicate_rows: 39` DOES NOT MEASURE WHAT IT APPEARS TO. The runner makes four
   separate scrape_jobs calls and concatenates them (runner.py:68-72). Each call dedups
   internally; duplicates ACROSS the four searches are never removed and were never
   claimed to be. So this metric reports cross-search overlap, not a failure of dedup.

WHAT THE RUN DOES LEGITIMATELY SHOW — location normalization works. Every ISO code is
gone from the location table; it is now uniformly canonical ("Penang, Pulau Pinang,
Malaysia", "Cyberjaya, Selangor, Malaysia"). That is direct evidence, independent of rates.
Also: "Kampong Api Api" — the place I refused to guess at in Task 7 — resolved correctly
via LinkedIn's state field. New gazetteer backlog item found: "Johor Baharu, Malaysia"
(alternate spelling; the gazetteer has "Johor Bahru") and 16 empty-location rows.

INFERENCE (arithmetic, not directly measured): 2.0% of 204 = 4 rows, and Indeed returned
exactly 4 rows. LinkedIn structurally cannot yield description-parsed salary (no
descriptions) and returned 0% structured salary in the before-run. So all 4 salaried rows
are almost certainly Indeed's, i.e. the parser hit 4/4 of the rows it could act on.
Labeled inference; I did not verify it row-by-row.

NEW DEFECT FOUND IN THE REPORT ITSELF: remote_scope renders as THREE buckets —
"None" (102), "nan" (100), "my" (2). Python None and pandas NaN are being counted
separately, so the report shows a split that does not exist in the data. Cosmetic but it
is in the artifact the user reads.

Task 14: review = Approved BUT 1 Important + 2 Minor -> fix loop triggers. Reviewer traced
  EVERY README factual claim to its implementing code (location.py ISO codes, remote.py
  scope values, frame.py salary_source, util.py desired_order, the scrape_jobs signature,
  even the install URL against the real git remote) and found them all accurate and not
  oversold. That was the heaviest-weighted part of the review and it passed cleanly.

Ruling: F25 — the stale roadmap entry is UPHELD as a real defect, and it is MY fault. I
  told the implementer to keep the roadmap intact; it followed that, flagged the
  consequence, and was right to. The README now lists "MYR salary parsing from job
  descriptions" as an unchecked future item while documenting the shipped feature two
  sections later. A README that contradicts itself about what the tool does is exactly
  what this project spent fourteen tasks trying not to produce. Fixing.
  Cost if wrong: a roadmap line reads as done when someone wanted it still listed.

Ruling: F26 — also fixing both Minors and my own report defect, because all three sit in
  user-facing artifacts:
  (a) the Usage example calls country_indeed="malaysia" "required for Indeed" while the
      Parameters block correctly calls it the default — the same README contradicting
      itself on whether the reader must pass an argument;
  (b) the JobPost schema section dropped the Naukri-specific columns, which still exist in
      desired_order and still populate when Naukri is named explicitly — under
      quarantine-not-deletion, removing their docs is wrong;
  (c) the baseline report renders remote_scope as three buckets (None / nan / my) because
      Python None and pandas NaN count separately — a split that does not exist in the data,
      printed in the artifact the user reads.
  Cost if wrong: minor doc churn.
Task 14: fix round 1/5 dispatched to original implementer.
Task 14: fix round 1/5 (4 addressed, 0 open; commits bded8c2..99a8881). Re-reviewer
  confirmed ONLY the salary bullet left the roadmap (it checked each remaining item for
  code references to be sure none were falsely marked done), and judged the "(not remote)"
  null-bucket label honest and non-colliding with the real `unknown` scope value.
Task 14: complete (commits 8ee66ea..99a8881, review clean after 1 fix round). 182 tests.

ALL 14 TASKS COMPLETE. Dispatching final whole-branch review (opus, most capable).

## FINAL WHOLE-BRANCH REVIEW: DO NOT MERGE — 1 Critical, 3 Important

C1 (Critical, CONFIRMED BY CONTROLLER PROBE): `_canonical_url` strips the ENTIRE query
  string, but Indeed encodes job identity as `?jk=<key>`. Every Indeed job canonicalizes
  to "https://malaysia.indeed.com/viewjob", so dedupe_exact — the only destructive stage —
  collapses the whole board to ONE row. Verified: 20 distinct Indeed jobs in, 1 row out;
  LinkedIn (path-based ids) unaffected at 20/20. Glassdoor and ZipRecruiter share the
  query-id shape and collapse identically. It also corrupts _fallback_group_id, colliding
  unrelated unresolved postings onto one dedup_group — defeating ruling F17.

CONTROLLER ERROR, SERIOUS, CORRECTED HERE: I attributed the Phase 1 baseline's
  "indeed: 4 rows (from 200)" to rate limiting from my own probing, and reported that to
  the user with some confidence. IT WAS THIS BUG. The arithmetic the reviewer supplied is
  decisive: SEARCHES has 4 searches, each collapses to exactly 1 surviving Indeed row,
  4 x 1 = 4. The "before" run predates the pipeline being wired (Task 5 ran before Task 12),
  so nothing deduped it: 4 x results_wanted=50 = 200. I ALSO had direct evidence in my own
  end-to-end probe after Task 12 — "indeed: 1" out of 31 rows — and read it as rate
  limiting instead of investigating. A single-row board from a 30-row scrape should have
  been obviously anomalous. I anchored on a hypothesis I had pre-registered and stopped
  looking.

CONSEQUENCE: every Phase 1 measurement is a product of the bug, not evidence about the
  pipeline. The salary-fill inference (4/4 Indeed rows parsed) is a sample of four
  survivors. The remote-rate drop is the collapse. Even "all ISO codes are gone from the
  location table" is ambiguous — consistent with normalization working AND with the
  ISO-bearing Indeed rows having been destroyed. The baseline MUST be re-run after the fix
  before any Phase 1 claim is made.

I1 (Important): `salary_source` reports "direct_data" for description-parsed MYR salaries.
  The pipeline writes parsed results into job.compensation, and frame.py stamps any
  populated compensation as DIRECT_DATA — so the output cannot express the provenance
  distinction, contradicting both the spec and the README, and destroying the ability to
  measure description-parsed fill separately (the one number Phase 1 exists to move).
I2 (Important, PROMOTED from a deferred minor): ruling F15 dropped the salary floor AND
  the ceiling on the explicit-interval path. "You will manage a portfolio worth
  RM2,500,000 and report monthly" parses as monthly RM2,500,000. F15's reasoning only ever
  justified dropping the FLOOR. My own deferral of this was wrong.
I3 (Important): re-run the baseline after C1 (controller).

Reviewer's ruling sanity check: F8 right decision but its stated mitigation was
  impossible (only rendered markdown was committed, so the before-series is
  unrecoverable); F16 correct but its replacement regex fires other_country on
  "Asia Pacific time zones" — the same false-exclusion class it was meant to end;
  F17 correct in intent, not delivered because of C1; all others sound, with F20 and
  F24 singled out as good calls.
Final fix wave: ONE dispatch (opus) covering C1, I1, I2, M1, M2, M4-M7.
Final fix wave: complete (commits 99a8881..34205ad, 4 commits). 182 -> 207 tests.
  Investigation paid off: 4 of 8 boards encode identity in the query string, EVERY scraper
  already stamps a site-prefixed board id on JobPost.id, and Naukri's jdURL carries a
  PER-REQUEST SESSION ID — so the URL-only fix I was inclined to prescribe would have
  silently broken dedup there. Fix keys on board id first, tracking-stripped URL as
  fallback. This is the second time in this project that requiring investigation over
  prescription caught something my instinct would have got wrong (the first was the
  gazetteer ISO codes).
  Controller verified BOTH directions: 20 distinct Indeed jobs -> 20 rows (was 1); and
  identical urls, tracking-param variants, and two-pass overlap all still collapse to 1,
  with the most complete record surviving.

Scoped re-review: READY TO MERGE. All 9 findings addressed. Re-reviewer traced `id=`
  construction across every scraper to rule out over-dedup, confirmed empty/None id falls
  through to the URL path correctly, and confirmed the "structured board data always wins"
  invariant survived the I1 provenance fix. It found one thing the implementer's own board
  table missed (BDJobs has a salted-hash fallback branch when jobid= is absent) and judged
  it non-blocking on the same grounds as Bayt: both are quarantined, non-default boards.

Ruling: F27 — re-running the live baseline on the corrected code (ruling I3). Every Phase 1
  number reported so far was a product of C1 and must not be cited. This run is the first
  measurement of the pipeline as built.
