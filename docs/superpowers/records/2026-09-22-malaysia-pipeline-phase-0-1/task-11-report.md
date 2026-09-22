# Task 11 report — normalize() pipeline

## Provenance of this report (read first)

**The implementer agent was terminated mid-task by an API session limit.** It had already
written both files and run the suite green, and its final message before dying was:

> "All 158 tests pass (151 previous + 7 new), pristine, no warnings. Now run black on the
> two changed files only."

It never wrote this report file, never ran Black, and never committed.

The controller completed only those mechanical steps and wrote this file in its place.
**No implementation logic was authored or altered by the controller.** Specifically the
controller: read both files in full, re-ran the suite (158 passed, 0 warnings), ran
`black` on the two changed files (it reformatted `jobspy/malaysia/__init__.py` — a
signature line rewrap only), re-ran the suite again (158 passed, 0 warnings), and
committed.

This report is therefore second-hand for everything except the verification steps listed
above. The reviewer should treat the diff as the primary evidence and should NOT treat
any claim here as the implementer's own attested account.

## Files changed

- `jobspy/malaysia/__init__.py` — docstring-only stub replaced with the pipeline (99 lines)
- `tests/malaysia/test_pipeline.py` — new, 7 tests (90 lines)

## What the code does

Four stages. Three per-job (`location` → `salary` → `remote`) driven by a
`_PER_JOB_STAGES` tuple, then one batch-wide step: `dedupe_exact` unconditionally,
followed by `assign_groups` only when `group_duplicates=True`.

Behaviours visible in the code:

- **Error isolation** — each per-job stage is wrapped in `try/except Exception`; a
  failure increments a `failures` Counter and logs at WARNING with the offending
  `job_url` and exception. The batch continues.
- **Not swallowed** — after the loop, a per-stage WARNING reports the total failure count
  for each stage that failed.
- **Structured data wins** — `_apply_salary` returns early when `job.compensation` is
  already set.
- **Module-global call** — `_apply_salary` calls `parse_myr_salary` through the module
  global, which is what makes the monkeypatch test meaningful.
- **Gazetteer backlog** — unmatched location strings are counted and the top 10 logged at
  INFO as `"unmatched locations - add to the gazetteer: ..."`.
- **Grouping is never fatal** — `assign_groups` is itself wrapped; a failure logs and
  continues ungrouped.
- **Empty input** — returns `[]` before doing any work.

## Ruling F1

Applied. `test_normalizes_location_salary_and_remote` drops the
"Open to APAC candidates." sentence and asserts `remote_scope == "my"`, with an 12-line
comment explaining that location runs before remote, that the location stage stamps
`country=Country.MALAYSIA` on the resolved Cyberjaya location, and that the classifier's
`my` check outranks `apac` — so `"my"` is the correct result and the revised assertion
additionally pins the stage ordering.

**Caveat:** the controller could NOT verify the counterfactual — i.e. that the brief's
original `"apac"` assertion really would have failed — because the implementer died
before reporting its RED observation, and the original assertion no longer exists to run.
The reasoning is sound on inspection but is unconfirmed by execution. Flagged for the
reviewer.

## Tests

7 new tests in `tests/malaysia/test_pipeline.py`:

1. `test_normalizes_location_salary_and_remote` — all three per-job stages, F1 assertion
2. `test_does_not_overwrite_structured_compensation`
3. `test_removes_exact_duplicates`
4. `test_group_duplicates_false_skips_grouping`
5. `test_exact_dedup_runs_even_when_grouping_is_off`
6. `test_a_failing_normalizer_does_not_abort_the_batch` (monkeypatch)
7. `test_empty_input_is_safe`

Full suite: **158 passed, 0 warnings** (`poetry run pytest tests/ -q -W "default"`),
verified by the controller both before and after Black.

## Known gaps in this task's evidence

- No TDD RED evidence exists. The implementer's red-phase output died with it.
- The F1 counterfactual is unverified (see above).
- No implementer self-review was recorded.

These are evidence gaps, not known defects — the reviewer should weight the diff
accordingly and may reasonably ask for the RED step to be reproduced.

---

## Fix pass (post-review, same implementer resumed after the session-limit death)

The review came back **Approved** with one Important finding and closed most of the gaps
above along the way.

### F1 counterfactual — now verified by execution

Before dying, the original implementer had already run this check but the observation was
lost with the session. Resumed and repeated it independently: built the brief's original
job (with the `"Open to APAC candidates."` sentence retained) as a standalone pytest case
asserting `remote_scope == "apac"`, and ran it against the committed pipeline.

```
$poetry run pytest tests/malaysia/test_f1_check_tmp.py -v -s
```

Result: **FAILED**.

```
ACTUAL remote_scope: my
...
>       assert result.remote_scope == "apac"
E       AssertionError: assert 'my' == 'apac'
E         - apac
E         + my
```

Confirms the brief's original assertion genuinely fails against the brief's own
implementation, and that `"my"` is the real result — Ruling F1 is correct. This
independently matches the reviewer's own verification (they reported the same rebuild,
same result). The temp file was deleted after the check; it is not part of the diff.

### Important finding: rollup logging had no test — fixed

The reviewer noted that "wrapped is not swallowed" (per-job WARNING + per-stage rollup
count) was implemented correctly but unguarded — no test asserted the log lines actually
fire, so a future refactor could delete the rollup-logging block silently and every
existing test would still pass.

**Fix:** added `test_normalizer_failures_are_counted_and_reported` to
`tests/malaysia/test_pipeline.py`. It monkeypatches `parse_myr_salary` to raise for 3
jobs, re-enables propagation on `pipeline.log` (required because `create_logger` sets
`propagate = False`, so `caplog` — which attaches to the root logger — would otherwise
see nothing), and asserts both:

- a per-job warning containing `"salary normalizer failed for"` (names the offending
  input)
- the per-stage rollup containing `"salary normalizer failed on 3 job(s)"` (the
  summary block the finding was about)

**TDD evidence for this fix:**

GREEN (test passes against the current, correct implementation):

```
$poetry run pytest tests/malaysia/test_pipeline.py -v
...
tests/malaysia/test_pipeline.py::test_normalizer_failures_are_counted_and_reported PASSED
============================== 8 passed in 0.04s ==============================
```

RED (test bites): temporarily commented out the rollup-logging loop in
`jobspy/malaysia/__init__.py` —

```python
    # TEMP-DISABLED-FOR-TDD-CHECK
    # for stage_name, count in failures.items():
    #     log.warning(f"{stage_name} normalizer failed on {count} job(s)")
```

— and reran just the new test:

```
$poetry run pytest tests/malaysia/test_pipeline.py::test_normalizer_failures_are_counted_and_reported -v
...
E       assert False
E        +  where False = any(<generator object ...>)
tests\malaysia\test_pipeline.py:112: AssertionError
---------------------------- Captured stderr call -----------------------------
... salary normalizer failed for 'https://x/0': bad input
... salary normalizer failed for 'https://x/1': bad input
... salary normalizer failed for 'https://x/2': bad input
1 failed in 0.13s
```

The first assertion (per-job warning) still passed — only the second (rollup) failed,
exactly matching what was disabled. Confirms the test exercises the specific block the
finding was about, not just the per-job log path already covered by
`test_a_failing_normalizer_does_not_abort_the_batch`. Restored the rollup loop
immediately after (`git diff jobspy/malaysia/__init__.py` shows no changes versus the
committed `319bce0` version).

### Verification after the fix

```
$poetry run pytest tests/malaysia/test_pipeline.py -v   # 8 passed
$poetry run pytest tests/ -v --tb=short                  # 159 passed, 0 warnings
```

Black run on the changed file only:

```
$poetry run black tests/malaysia/test_pipeline.py
reformatted tests\malaysia\test_pipeline.py
```

(Rewrapped the new test's list-comprehension line; no logic change.)
`jobspy/malaysia/__init__.py` was not touched by this fix pass and has no diff against
`319bce0`.

### Commit

`ca680e2` — `test(malaysia): pin error-isolation logging in the normalize() pipeline`
(1 file changed, 24 insertions — `tests/malaysia/test_pipeline.py` only).

### Self-review of the fix

- **Completeness:** both halves of "wrapped is not swallowed" (per-job log, per-stage
  rollup) are now pinned by one test.
- **Correctness:** verified RED/GREEN against the actual implementation, not assumed.
- **Discipline:** no changes to `jobspy/malaysia/__init__.py` or any of the four
  normalizer modules; only the test file grew. No changes to unrelated tests.
- **Scope:** the four deferred Minors (stage_name string dispatch, missing `exc_info`,
  non-atomic `assign_groups` failure, tests that would survive a gutted pipeline) were
  left untouched as instructed.
- **Testing:** full suite 159 passed, 0 warnings, both before and after Black.

### Remaining concerns

None outstanding. The four Minors remain deferred per the controller's explicit
instruction and are not blocking.
