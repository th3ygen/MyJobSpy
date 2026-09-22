# Task 10 report: `grouping.py` — exact dedup and fuzzy grouping

## Summary

Implemented `jobspy/malaysia/grouping.py` with two deliberately separate
mechanisms:

- `dedupe_exact(jobs)` — destructive. Collapses literal repeat listings
  (same canonical URL, or same `id` when URL is absent) to the most complete
  record.
- `assign_groups(jobs, *, threshold=90)` — non-destructive. Blocks by
  normalized company name, then greedily clusters same-company jobs by
  title similarity (`rapidfuzz.fuzz.token_sort_ratio`), subject to a hard
  seniority-marker block and a location-compatibility check, and stamps
  each resolved cluster with a stable `dedup_group` hash.

The two mechanisms share no code: `dedupe_exact` uses only `_canonical_url`
and `_completeness`; `assign_groups` uses only `normalize_company`,
`seniority_markers`, `_normalize_title`, `_compatible_location`,
`_location_key`, and `_group_id`.

## Files changed

- `jobspy/malaysia/grouping.py` (new)
- `tests/malaysia/test_grouping.py` (new)

## Defect found in the brief's own implementation (fixed)

The brief's `assign_groups` only stamped a `dedup_group` for clusters with
2+ members (`if len(cluster) < 2: continue`), leaving singleton clusters at
`dedup_group=None`. Against the brief's *own* tests this fails, because
`None != None` is `False`:

- `test_never_groups_across_seniority`
- `test_does_not_group_different_states`
- `test_does_not_group_different_companies`

All three assert `grouped[0].dedup_group != grouped[1].dedup_group` for two
jobs that correctly end up in *separate* singleton clusters — but with the
brief's code both stay `None`, so the inequality assertion fails.

**Fix:** every cluster (including singletons) is now stamped, keyed by a new
`_location_key(job)` helper:

```python
def _location_key(job: JobPost) -> str | None:
    if job.is_remote:
        return "remote"
    return _state_of(job)
```

`_group_id` now takes this resolved `location_key` directly instead of
brief's `state or 'remote'` fallback. That fallback was itself a landmine:
if I had simply removed the `len(cluster) < 2` guard without this change,
two *different*, unrelated jobs that both have `state=None` and are
non-remote would each get their own singleton cluster (correctly kept
apart by `_compatible_location`), but both would hash to the same
`_group_id(company, title, "remote")` — silently re-merging exactly the
"both unknown is not evidence of same place" case Task 7's contract exists
to prevent. `_location_key` returns `None` for that case, and the stamping
loop skips it entirely, leaving `dedup_group=None` — which is what
`test_two_jobs_with_unresolved_state_are_not_grouped` asserts.

This is a real conflict between the brief's test list and its own code, not
a case of bending a test to match an implementation — I re-derived the
fix from the stated design intent ("a wrong group asserts two distinct
openings are the same posting") rather than from the code.

## TDD evidence

**RED** — `poetry run pytest tests/malaysia/test_grouping.py -v` before
`grouping.py` existed:

```
ModuleNotFoundError: No module named 'jobspy.malaysia.grouping'
1 error in 0.17s
```

**First implementation attempt (brief's code verbatim) — still RED**, for
the reason above:

```
FAILED tests/malaysia/test_grouping.py::test_never_groups_across_seniority
FAILED tests/malaysia/test_grouping.py::test_does_not_group_different_states
FAILED tests/malaysia/test_grouping.py::test_does_not_group_different_companies
FAILED tests/malaysia/test_grouping.py::test_never_groups_aveva_seniority_pair
FAILED tests/malaysia/test_grouping.py::test_never_groups_applify_seniority_pair
FAILED tests/malaysia/test_grouping.py::test_aveva_pair_scores_high_on_token_sort_ratio
FAILED tests/malaysia/test_grouping.py::test_applify_pair_scores_high_on_token_sort_ratio
7 failed, 11 passed in 0.16s
```

(The last two failures were a bad test written by me, described below —
not a code defect.)

**GREEN** — after adding `_location_key` and stamping every cluster:

```
poetry run pytest tests/malaysia/test_grouping.py -v
...
18 passed in 0.05s
```

**Full suite GREEN**:

```
poetry run pytest tests/ -q
150 passed in 0.16s
```

(150, not the 122+18=140 mentioned in the brief context — other tasks in
this pipeline branch have evidently added tests since the 122 baseline was
measured. Zero warnings either way.)

## A test I got wrong, and fixed against reality rather than assumption

I initially wrote `test_aveva_pair_scores_high_on_token_sort_ratio` and
`test_applify_pair_scores_high_on_token_sort_ratio` asserting
`score >= 90`, based on the brief context's claim that these real pairs
"would score very high on raw title similarity without [the guard]".
Measured directly:

- AVEVA pair (`"full stack engineer net angular"` vs
  `"senior full stack engineer net angular"`): **89.855**
- Applify pair (`"mes system developer"` vs
  `"senior mes system developer"`): **85.106**

Both are *below* the 90 threshold on title text alone — the AVEVA pair by a
hair (0.145), the Applify pair comfortably (4.9). I rewrote both tests to
pin the actual measured values (`pytest.approx`, documenting them) instead
of asserting a threshold breach that doesn't actually occur for these two
specific titles. The seniority guard is still the mechanism that makes the
non-grouping outcome *absolute* rather than a threshold coincidence — for
the AVEVA pair in particular, a 0.145-point swing in normalization (e.g. a
different punctuation-stripping choice) would have flipped it past 90 with
no guard in place. The two `test_never_groups_*_seniority_pair` tests are
the load-bearing assertions; the `*_token_sort_ratio_is_on_record` tests
are documentation, not proof of necessity for this exact sample.

## The `(M)` residue decision

`normalize_company("Conspec Builders (M) Sdn Bhd")`: stripping punctuation
before suffix removal turns `(M)` into a bare `m` token, which survives
after `sdn bhd` is stripped, leaving `"conspec builders m"` instead of
`"conspec builders"`.

**Decision:** strip the exact pattern `\(\s*m\s*\)` (a parenthesised single
"m", case-insensitive) before general punctuation stripping, since `(M)` is
a specific, recognizable Malaysian-subsidiary marker convention (e.g. also
seen as "XYZ (M) Sdn Bhd" generally) — not a generic single-letter company
name fragment. This is a targeted fix, not general single-token
elimination: a company literally named "M Holdings" is untouched, since
the pattern requires parentheses around a bare "m".

**Why:** the residue matters only if it would prevent two spellings of the
same company (with and without `(M)`) from normalizing to the same block
key. Given the specific "(M) Sdn Bhd" convention appears repeatedly for
Malaysian subsidiaries of foreign or regional groups, and stripping it is
unambiguous (parenthesised, isolated token), I judged it worth the four
extra lines rather than leaving a comment and accepting the risk — this
one has a clear, low-risk fix, unlike more ambiguous residues I would have
left alone with a comment.

Regression test: `test_normalize_company_conspec_parenthesised_malaysia_marker`
asserts `"conspec builders"` is a substring of the result (in case future
edits change how the suffix trailing space is handled), and
`test_normalize_company_real_world_shapes` covers the other seven real
production company-name shapes verbatim.

## Self-review

- **Completeness:** both mechanisms present and separate (verified no
  shared helper functions between `dedupe_exact` and `assign_groups`).
  All brief tests plus real-data tests (AVEVA pair, Applify pair, 7
  production company-name shapes, Conspec `(M)` case, unresolved-location
  case) are present and passing.
- **Correctness:**
  - Fuzzy grouping never drops a row — `assign_groups` returns the same
    `jobs` list, mutating only `dedup_group`; `test_grouping_never_removes_rows`
    passes.
  - Seniority check is genuinely before scoring — `if markers !=
    seniority_markers(leader.title): continue` executes before the
    `fuzz.token_sort_ratio` call, not as an input to it.
  - Two `state=None`, non-remote jobs never share a group — verified by
    `test_two_jobs_with_unresolved_state_are_not_grouped`, which was the
    scenario the task brief flagged as needing confirmation. It did *not*
    hold under the brief's own code without the `_location_key` fix (see
    above) — the test happened to pass under the brief's code by accident
    (both stayed `None`), but only because that code never stamped
    singletons at all; the accident would have broken the moment the
    singleton-stamping bug got fixed without also fixing the placeholder
    collision. Fixing both together is what actually closes the gap.
- **Determinism:** `_group_id` hashes `(company, title, location_key)` from
  the deterministically-chosen cluster leader (jobs are sorted by
  `(normalized_title, job_url)` before clustering, independent of input
  list order), so a rerun with the same jobs in a different order produces
  identical group ids. Verified by `test_group_ids_are_stable_across_runs`.
- **Discipline:** no shared code between the two mechanisms; changes beyond
  the brief were limited to fixing the singleton-stamping/placeholder-hash
  defect and the `(M)` marker, both directly required by the task's
  correctness constraints — no additional scope was added.
- **Testing:** `poetry run pytest tests/ -q` → `150 passed`, zero warnings.

## Concerns

- The greedy, leader-based clustering (inherited from the brief, not
  changed here) is not transitive: if A matches B and B matches C but A
  does not match C, and A is processed first, C forms its own cluster even
  though it matches B. This is a known limitation of single-pass clustering
  against a fixed leader and matches the brief's specified design; flagging
  it for awareness, not proposing a fix, since it was not in scope and the
  existing behavior is still conservative (worst case: an extra ungrouped
  duplicate, never a false merge).
- The AVEVA seniority-pair test's title-similarity margin below threshold
  is only 0.145 points, i.e. this specific real pair is not strong evidence
  of the guard's necessity on its own (though the guard is still correct
  and necessary in general, as the synthetic "Senior Software Engineer"
  case demonstrates unambiguously). Recorded transparently above rather
  than silently asserting a false `>= 90`.

---

## Addendum: post-review fix (None-sentinel ambiguity)

Review came back Approved with one Important finding. Two things the
coordinator had told me during the original task turned out to be wrong,
and the coordinator corrected both up front:

- The "unresolved jobs share a dedup_group" concern was based on a bad
  probe (`None == None` is `True` in Python — comparing two genuinely
  separate `None`s reads as "equal" even though they're not the same
  group). My clustering logic was never wrong on that front.
- The claim that the real AVEVA/Applify seniority pairs "would score very
  high" (implying >=90) was overstated; my original report already flagged
  the actual measured values (89.86, 85.11) as below threshold, and the
  coordinator confirmed that instinct was correct and asked me to keep it.

The real, surviving finding: **leaving `dedup_group=None` for unresolvable
rows makes two independently-unresolved rows compare equal under `==`.**
Two rows deliberately kept in separate clusters (unresolved location, or
unresolved company) both carry `None`, and `None == None` is `True` — so
"deliberately not grouped" and "deliberately not grouped" are
indistinguishable from "same group" to any consumer that doesn't route
through `pandas.groupby(dropna=True)`. The tell in the original test suite
was exactly as the reviewer described: `test_two_jobs_with_unresolved_state_are_not_grouped`
asserted `is None` on each side separately instead of `!=` like its three
"does not group" siblings — the one assertion shape that would have
caught this.

### Fix

Added `_fallback_group_id(job)` to `jobspy/malaysia/grouping.py`: a
per-row, stable id derived from the same canonical-url normalization
`dedupe_exact` already uses (`_canonical_url(job.job_url)`, falling back to
`job.id`), hashed with the same `blake2s` scheme as `_group_id` but under
an `"unresolved|"` prefix so it can never collide with a real
`(company, title, location)` hash. Applied wherever a row previously ended
up unstamped:

- The `if not company: continue` branch in `assign_groups` now stamps every
  member of an unresolvable-company block with its own fallback id before
  `continue`.
- The `location_key is None` branch in the per-cluster stamping loop now
  stamps every job in that (always-singleton, per `_compatible_location`)
  cluster with its own fallback id instead of leaving it unset.

`dedup_group` is now always non-`None` on output. Duplicate-ness is
answered uniformly by group size, never by a shared sentinel.

### TDD evidence for the fix

**RED** — updated `test_two_jobs_with_unresolved_state_are_not_grouped` to
assert `is not None` and `!=` (matching its three siblings), and added
`test_unresolved_fallback_group_id_is_stable_across_runs`, then ran against
the pre-fix code:

```
poetry run pytest tests/malaysia/test_grouping.py -v -k "unresolved"
...
FAILED tests/malaysia/test_grouping.py::test_two_jobs_with_unresolved_state_are_not_grouped
  AssertionError: assert None is not None
FAILED tests/malaysia/test_grouping.py::test_unresolved_fallback_group_id_is_stable_across_runs
  AssertionError: assert None is not None
2 failed, 17 deselected in 0.14s
```

Confirms the before/after: the inequality assertion did fail before the
fix, for the expected reason (both sides `None`).

**GREEN** — after adding `_fallback_group_id` and wiring it into both
unstamped paths:

```
poetry run pytest tests/malaysia/test_grouping.py -v
...
19 passed in 0.04s
```

**Full suite**:

```
poetry run pytest tests/ -q
151 passed in 0.17s
```

(150 -> 151: one net new test, `test_unresolved_fallback_group_id_is_stable_across_runs`;
the `test_two_jobs_with_unresolved_state_are_not_grouped` update was an
edit to an existing test, not an addition.) Zero warnings.

### Other corrections applied

- Moved the "(M)" marker residue comment in the test file from sitting
  above the unrelated `ARRK Engineering GmbH` assertion (a copy/paste
  artifact from an earlier edit) to directly above
  `test_normalize_company_conspec_parenthesised_malaysia_marker`, the test
  it actually describes.
- Confirmed no other existing test asserted `dedup_group is None` — the one
  instance was the test already converted above. No test needed deleting.
- Left the two `test_*_token_sort_ratio_is_on_record` tests unchanged, per
  the coordinator's explicit "not in scope" — they document rapidfuzz
  behavior on real titles, not `grouping.py` behavior, but that was
  disclosed in the original report and has documentary value.

### Files changed (this addendum)

- `jobspy/malaysia/grouping.py` — added `_fallback_group_id`; wired into
  both previously-unstamped paths in `assign_groups`; updated the
  `_location_key` and `assign_groups` docstrings to describe the new
  uniform contract.
- `tests/malaysia/test_grouping.py` — converted
  `test_two_jobs_with_unresolved_state_are_not_grouped` to assert
  inequality of two non-`None` ids; added
  `test_unresolved_fallback_group_id_is_stable_across_runs`; relocated the
  misplaced `(M)` comment.

### Self-review of the fix

- `dedup_group` is now non-`None` for every job on every code path in
  `assign_groups` — verified by inspection of all three stamping sites
  (matched cluster, unresolved-location cluster, unresolved-company
  block) and by the full test suite passing.
- Determinism preserved: the fallback id depends only on the job's own
  canonical url (or `id`), not on iteration order, object identity, or a
  counter — verified by `test_unresolved_fallback_group_id_is_stable_across_runs`.
- No new coupling between the two mechanisms: `_fallback_group_id` reuses
  `_canonical_url`, a pure string helper already used by `dedupe_exact`,
  but does not call into or depend on `dedupe_exact`'s dict-building logic;
  the two mechanisms still don't share stateful code.
- Format: `poetry run black jobspy/malaysia/grouping.py tests/malaysia/test_grouping.py`
  run after the fix (and again after a docstring tweak); only these two
  files touched.

Commit: `7828a15` "fix(malaysia): give unresolvable rows a stable per-row dedup_group"

---

## Level-suffix fix (controller-authored note — implementer died before reporting)

The implementer was resumed to fix a defect found by running the finished pipeline against
live job boards, then **lost its connection mid-response**. Its last message was
"Now appending the fix report to task-10-report.md". It had already committed the work as
`5584e43`; only this report section was lost. The controller wrote this section and
verified the behavior, but authored no code.

### The defect

A 31-row live scrape grouped `"Software Engineer I"` with `"Software Engineer II"` at
Experian Asia Pacific — two different openings presented as one posting, the design's
stated worst case. `_SENIORITY_MARKERS` covered word markers only, so the guard never
fired and the titles scored ~97 on `token_sort_ratio`.

### What was committed

`_ROMAN_LEVELS` (i-v), a bare-digit level, and `_LEVEL_CODE_RE` (`^[a-z]\d{1,2}$`, for
"L3"/"P5"/"T5"), combined in a `_level_marker()` helper anchored on the LAST token only so
a mid-title word cannot fire it. `"II"` and `"2"` normalize to the same `level:2` marker;
letter-codes are kept in their own namespace.

### Controller verification (9 constructed cases)

| Case | Result |
|---|---|
| `Software Engineer I` vs `Software Engineer II` (the real failure) | separate ✓ |
| `Data Engineer 1` vs `Data Engineer 2` | separate ✓ |
| `Analyst III` vs `Analyst IV` | separate ✓ |
| `Engineer L3` vs `Engineer L4` | separate ✓ |
| `Software Engineer II` vs `Software Engineer II` | grouped ✓ |
| `Software Engineer` vs `Software Engineer` | grouped ✓ |
| `Software Engineer` vs `Senior Software Engineer` | separate ✓ |
| `Business Intelligence I` vs `Business Intelligence II` | separate ✓ |
| `Software Engineer 2` vs `Software Engineer II` | separate — see note |

The last case: the level guard correctly normalizes both to `level:2` and lets them
through, but the raw titles differ enough textually to fall under the 90 similarity
threshold, so they do not group. The controller initially expected a group here; on
inspection this is correct conservative behavior — a missed group costs one duplicate row,
which the design explicitly prefers over a wrong group. Not a defect.

Full suite after the fix: **169 passed, 0 warnings**, verified by the controller.

### Evidence gap

No implementer RED/GREEN observation was recorded for the new tests — it died before
reporting. The new tests exist in the commit and pass; whether the implementer confirmed
they fail against the pre-fix code is unverified. The controller's table above is
behavioral verification of the fixed state, not a substitute for that RED step.
