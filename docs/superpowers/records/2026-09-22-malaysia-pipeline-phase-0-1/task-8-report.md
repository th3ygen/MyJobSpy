# Task 8 Report: `salary.py` — MYR salary parsing

## Summary

Implemented `jobspy/malaysia/salary.py` with `parse_myr_salary(text: str | None) -> Compensation | None`,
following the brief's design almost exactly, with two deliberate deviations required by real data
(Instruction 1's conditional sanity bands, and a regex fix for bare multi-digit amounts).

## Files changed

- `jobspy/malaysia/salary.py` (new, 121 lines)
- `tests/malaysia/test_salary.py` (new, 107 lines, 27 test cases)

## TDD evidence

**RED** — wrote `tests/malaysia/test_salary.py` first (brief's Step 1 tests plus the additional
real-world cases from Instructions 1 and 2), then ran:

```powershell
$poetry = "$env:APPDATA\Python\Python312\Scripts\poetry.exe"
& $poetry run pytest tests/malaysia/test_salary.py -v
```

Result: collection error, as expected —

```
ModuleNotFoundError: No module named 'jobspy.malaysia.salary'
```

This is the expected failure reason: the module did not exist yet.

**GREEN** — implemented `jobspy/malaysia/salary.py`, then ran the same command:

```
collected 27 items
...
27 passed in 0.03s
```

All 27 parametrized cases passed on the first implementation attempt, because the regex fix
(below) was designed in up front by manually tracing the brief's regex against every real-data
string before writing the implementation, rather than discovered by a failing run.

**Full suite** — ran `& $poetry run pytest tests/ -q`:

```
117 passed in 0.14s
```

(90 pre-existing + 27 new). Zero warnings, pristine output.

## Deviations from the brief (both required, both intentional)

### 1. Conditional sanity bands (Instruction 1 / Ruling F15)

The brief's `parse_myr_salary` applied `_BANDS[interval]` unconditionally, regardless of whether
the interval was detected in the text or defaulted to `"monthly"`. Per Instruction 1, this was
changed to branch on `detect_interval(text)`:

- **Explicit interval detected** (`detect_interval` returned non-`None`): trust it. Accept any
  amount `0 < amount <= 10,000,000` (new `_ABSURDITY_CEILING`), skipping the tight per-interval
  band entirely.
- **Interval inferred** (`detect_interval` returned `None`, defaulted to `"monthly"`): apply the
  brief's tight `_BANDS` exactly as written.

This is commented in both `_BANDS` and inline at the branch point, explaining that the two paths
guard against different failure modes (guessed interval vs. absurd/typo'd amount) and warning
against collapsing them back into one band.

Verified directly by the pair of tests:
- `"Pay: RM800.00 per month"` → parses to monthly 800/800 (explicit interval, below tight floor).
- `"RM800"` (bare, no interval word) → `None` (already present in the brief's reject list).

### 2. Amount regex: require a comma group before falling back to a bare digit run

While tracing the brief's `_AMOUNT` regex against the real strings, I found it would silently
**truncate** bare 4+ digit amounts with no comma grouping. Example: `"* Basic Salary: **RM 3000**"`.

Original: `_AMOUNT = r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*([kK])?"`

For `"RM 3000"`, the first alternation branch (`\d{1,3}(?:,\d{3})*...`) greedily matches `\d{1,3}`
as `"300"` (bounded to 3 digits), then `(?:,\d{3})*` matches zero times (no comma follows), and
since the single-amount patterns (`_PREFIXED_SINGLE`/`_SUFFIXED_SINGLE`) have nothing required
after the amount, this partial match succeeds immediately — `re.search` never backtracks into
consuming the trailing `"0"`. Result: `low = high = 300`, which then fails the monthly floor
(300 < 1,000) and the string is wrongly rejected, even though the text was a well-formed real
salary of RM3,000.

(The range patterns, `_PREFIXED_RANGE`/`_SUFFIXED_RANGE`, happen to be unaffected because the
separator that must follow forces the engine to backtrack into the second alternative when the
first one leaves un-consumable characters — e.g. `"MYR 3000-5000"` still parses correctly by
accident of what follows. Only the two single-amount patterns had no such downstream pressure.)

**Fix:** changed `(?:,\d{3})*` to `(?:,\d{3})+` (require *at least one* comma group for that
branch). Now a comma-less number like `"3000"` fails the first alternative outright (no comma
present) and falls through cleanly to the second alternative, `\d+(?:\.\d+)?`, which consumes all
digits unambiguously. Comma-grouped numbers (`"3,000"`, `"12,000.00"`, `"2,000,000"`) still match
via the first branch as before. Verified against every real-data string in the task brief,
including the multi-group case `"RM2,000,000"` (reject test) and all `.00`/non-zero-cent cases.

**Real-world string that forced this fix:** `"* Basic Salary: **RM 3000**"`.

## Test coverage added beyond the brief

All strings are the exact real-data strings from the task brief:

- `.00` decimals on both bounds (dominant form): `"Pay: RM3,500.00 - RM4,000.00 per month"`
- non-zero cents: `"Pay: RM1,700.00 - RM4,129.48 per month"`
- en-dash separator + `/month`: `"**Salary:** RM6,000 – RM9,000/month"`
- `to` separator, no interval word: `"* Expected salary in between RM 3,000.00 to RM 3,500.00"`
- markdown bold around the amount: `"* Basic Salary: **RM 3000**"`
- `From` + single amount: `"Pay: From RM1,800.00 per month"`
- `Up to` + single amount, explicit interval, below tight floor: `"Pay: Up to RM800.00 per month"`
- plain explicit-interval below-floor case (Instruction 1's specific pair): `"Pay: RM800.00 per month"`

The bare-`"RM800"`-with-no-interval → `None` case was already present in the brief's own reject
parametrize list, so it was kept rather than duplicated.

## Self-review

- **Completeness:** both branches of the conditional band rule are implemented, commented, and
  each has a direct test (`"Pay: RM800.00 per month"` accepted vs. bare `"RM800"` rejected). All
  real-data formats from Instruction 2 are covered in `test_parses_myr_salaries`.
- **Correctness:** confirmed via test run — `"RM800"` bare → `None`; `"RM800.00 per month"` →
  parses; `"RM5,000 - RM3,000"` (inverted) → `None`; `"RM2,000,000"` (implausible, no explicit
  interval) → `None`.
- **Discipline:** `detect_interval` is imported from `jobspy.malaysia.language` and used as-is,
  not reimplemented. No compensation-precedence / "prefer structured data" logic was added — that
  gating is explicitly deferred to Task 11 per the brief.
- **Testing:** full suite is 117 passed, 0 warnings, pristine output. Black run only on the two
  changed files (`jobspy/malaysia/salary.py`, `tests/malaysia/test_salary.py`) — no reformatting
  needed, both already compliant with line-length 88.
- **Currency/interval typing:** `currency="MYR"` hardcoded as instructed; `salary_source` is not
  touched (caller's responsibility per Global Constraints).

## Concerns

None blocking. One note for a future reader: the regex fix (`*` → `+` in `_AMOUNT`'s first
alternative) is a general correctness fix, not something scoped only to the "markdown bold" case —
it also would have silently mis-parsed any bare comma-less 4+ digit number in *any* position
(single or range, prefixed or suffixed), even though the range patterns happened to route around
the bug by luck of their trailing separator/currency requirements. Worth keeping in mind if this
regex is ever extended further.

## Commit

- `ab850b9` — `feat(malaysia): parse MYR salaries from description text`
