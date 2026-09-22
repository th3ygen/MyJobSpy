# Task 6 Report: `language.py` — Bahasa Malaysia parsing

## Summary

Task 6 implements Bahasa Malaysia language parsing utilities for the MyJobSpy Malaysia fork. This is a shared helper module, not a pipeline stage, that provides functions for parsing Malaysian job type enums, relative dates, compensation intervals, and role query translations.

## What Was Implemented

### 1. New Package: `jobspy/malaysia/`

**Created files:**
- `jobspy/malaysia/__init__.py` — Package docstring (minimal module)
- `jobspy/malaysia/language.py` — Main implementation with four functions

**Functions implemented:**

1. **`parse_bm_relative_date(text: str | None, *, today: date | None = None) -> date | None`**
   - Parses Malay relative date phrases like "hari ini" (today), "semalam" (yesterday), "3 hari lepas" (3 days ago)
   - Handles fixed-offset phrases via `_FIXED_OFFSET_DAYS` dictionary
   - Handles numeric patterns via regex `_RELATIVE_RE` with unit multipliers in `_UNIT_DAYS`
   - Returns `None` for non-Malay input

2. **`detect_interval(text: str | None) -> str | None`**
   - Finds compensation interval words in Malay or English (e.g., "sebulan" → "monthly", "per month" → "monthly")
   - Uses longest-first matching to avoid substring collisions (e.g., "per month" wins over bare "month")
   - Combines `BM_INTERVAL_WORDS` and `_EN_INTERVAL_WORDS` dictionaries
   - Returns `None` if no interval found

3. **`to_bm_query(term: str | None) -> str | None`**
   - Translates English job role terms to Malay (e.g., "driver" → "pemandu", "Security Guard" → "pengawal keselamatan")
   - Uses `EN_TO_BM_QUERY_TERMS` mapping (weighted toward blue-collar/admin roles per domain knowledge)
   - Handles multi-word phrases first to prevent partial translations (e.g., "security guard" translates as one unit, not split into "guard")
   - Returns `None` when the input is unchanged after translation (nothing translatable)

4. **`BM_INTERVAL_WORDS` dictionary**
   - Public export: Malay interval keywords and their canonical values
   - Enables consumers (salary parser in Task 8) to check for Malay-specific intervals

### 2. Modified: `jobspy/model.py` — JobType Enum

Added Malay job type values to the existing `JobType` enum:
- **FULL_TIME**: Added `"sepenuhmasa"` (sepenuh masa, full-time)
- **PART_TIME**: Added `"separuhmasa"` (sepa ruh masa, part-time)
- **CONTRACT**: Added `"kontrak"` (contract work)
- **TEMPORARY**: Added `"sementara"` (temporary)
- **INTERNSHIP**: Added `"latihanindustri"` and `"praktikal"` (industry training and practical)

These values are space-stripped, lowercase per existing enum design (matching `"vollzeit"`, `"tempsplein"`, etc.).

### 3. Tests: `tests/malaysia/test_language.py`

Created comprehensive test suite with 26 test cases:
- **Date parsing tests (8)**: Fixed phrases and numeric patterns with various units
- **Non-Malay rejection tests (4)**: Verify `None` return for English or invalid input
- **Interval detection tests (5)**: Malay and English interval keywords
- **Query translation tests (5)**: Multi-word and single-word terms, untranslatable input
- **JobType enum resolution tests (4)**: All four new Malay JobType values

## TDD Evidence

### RED State: Initial Test Run
**Command:**
```powershell
$poetry = "$env:APPDATA\Python\Python312\Scripts\poetry.exe"
& $poetry run pytest tests/malaysia/test_language.py -v
```

**Output:**
```
ModuleNotFoundError: No module named 'jobspy.malaysia'
ERROR tests/malaysia/test_language.py
!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!
```

**Why expected:** Module does not exist yet; tests cannot import.

### GREEN State: After Implementation
**Command:**
```powershell
& $poetry run pytest tests/malaysia/test_language.py -v
```

**Output:**
```
26 passed in 0.03s
```

All 26 tests pass immediately after implementation.

### Full Suite Verification
**Final test run (all tests):**
```
47 passed in 0.11s
```
- 26 new Malaysia language tests
- 21 existing tests (unchanged, all still passing)
- Zero warnings, pristine output

## Files Changed

1. **Created:** `C:\Users\USER\Desktop\dev\forks\MyJobSpy\jobspy\malaysia\__init__.py`
   - Docstring only: `"""Malaysia-specific normalization for scraped job posts."""`

2. **Created:** `C:\Users\USER\Desktop\dev\forks\MyJobSpy\jobspy\malaysia\language.py`
   - 160+ lines of implementation with three dictionaries, one regex, and four functions

3. **Modified:** `C:\Users\USER\Desktop\dev\forks\MyJobSpy\jobspy\model.py`
   - Five JobType enum tuples updated with Malay values
   - Diff: +7 lines, no other changes to file

4. **Created:** `C:\Users\USER\Desktop\dev\forks\MyJobSpy\tests\malaysia\__init__.py`
   - Empty package marker

5. **Created:** `C:\Users\USER\Desktop\dev\forks\MyJobSpy\tests\malaysia\test_language.py`
   - 96 lines: comprehensive parametrized test suite

## Code Quality

**Formatting:** Black applied to all modified files.
- `language.py`: Split function signatures to fit 88-character line limit
- All other files: Already compliant

**Code Review Self-Check:**

Completeness:
- ✓ All four functions implemented per brief specification
- ✓ All five JobType enum tuples modified with correct Malay values
- ✓ All 26 test cases present and passing
- ✓ `__init__.py` is docstring-only (no overbuilding)

Quality & Accuracy:
- ✓ `parse_bm_relative_date`: Fixed-offset-before-regex precedence correct (as per brief)
- ✓ `detect_interval`: Longest-phrase-first sorting implemented
- ✓ `to_bm_query`: Multi-word replacement before single-token split (correct order)
- ✓ Returns `None` on non-translatable input (per spec)
- ✓ Regex patterns match brief exactly (no dropped alternatives)
- ✓ Dictionary entries transcribed verbatim (20 role translations)

Discipline:
- ✓ No unnecessary expansion of `__init__.py`
- ✓ No changes outside Task 6 scope
- ✓ Code follows existing patterns in jobspy codebase

## Concerns

None. Implementation is complete, fully tested, and matches specification verbatim.

## Commit

**SHA:** `6648722`
**Message:** `feat(malaysia): add Bahasa Malaysia date, interval and query parsing`

**Files in commit:**
```
jobspy/malaysia/__init__.py (new)
jobspy/malaysia/language.py (new)
jobspy/model.py (modified)
tests/malaysia/__init__.py (new)
tests/malaysia/test_language.py (new)
```

---

## Review Findings & Fixes

### Finding 1: `to_bm_query` Re-processing Output

**Issue:** The two-phase implementation (multi-word replacement followed by single-token translation) caused re-translation of output. Example: `to_bm_query("production operator")` returned `"pengendali pengeluaran"` instead of `"operator pengeluaran"` because:
1. Multi-word pass: `"production operator"` → `"operator pengeluaran"`
2. Single-token pass: Re-read `"operator"` (also a standalone key) → translated to `"pengendali"`

**Fix Applied:** Replaced two-phase approach with greedy longest-match algorithm that processes each token only once without re-examining output:
- Compute longest phrase length in dictionary
- For each position, try matching phrases from longest to shortest
- Once matched, skip those tokens; never re-examine
- Prevents output re-translation

**Test Added:** `test_multiword_result_is_not_retranslated()`
- Verifies collision case: `to_bm_query("production operator") == "operator pengeluaran"`
- Confirmed fails with old implementation (returned `"pengendali pengeluaran"`)
- Passes with greedy implementation

### Finding 2: Order-Dependent Behavior Tests

**Issue:** Two order-dependent precedence rules were not tested:
1. `parse_bm_relative_date`: Fixed-offset phrases should win over regex patterns
2. `detect_interval`: Longest-matching phrases should win over substring matches

**Tests Added:**

**Test 1:** `test_fixed_offset_phrase_wins_over_relative_pattern()`
- Input: `"hari ini, bukan 3 hari lepas"` (matches BOTH mechanisms)
- Expected: `date(2026, 9, 22)` (fixed phrase "hari ini" wins)
- Confirmed fails when order reversed (regex checked first): returned `date(2026, 9, 19)` (3 days ago)
- Passes with fixed-offset-first precedence

**Test 2:** `test_detect_interval_prefers_the_longest_matching_phrase(monkeypatch)`
- Injects "month" → "weekly" to create collision with existing "per month" → "monthly"
- Input: `"paid per month"`
- Expected: `"monthly"` (longer phrase wins)
- Confirmed passes with longest-first sorting (length-based precedence)

## Fixes Committed

**Commit SHA:** `fbbd2cf`
**Message:** `fix(malaysia): resolve to_bm_query output re-translation bug and add order-dependent precedence tests`

**Changes:**
- `jobspy/malaysia/language.py`: Replaced `to_bm_query` with greedy token-by-token algorithm
- `tests/malaysia/test_language.py`: Added 3 new test cases (total: 29 tests)

## Final Test Results

**Command:**
```powershell
$poetry run pytest tests/malaysia/test_language.py -v
```

**Output:**
```
29 passed in 0.03s
```

**Full suite (all tests):**
```
50 passed in 0.11s
```
- 29 Malaysia language tests (26 original + 3 new)
- 21 existing tests (all still passing)
- Zero warnings, pristine output

## Verification of Test Effectiveness

When ordering was removed, tests behaved as expected:

1. **`test_multiword_result_is_not_retranslated`:**
   - With old two-phase implementation: FAILED (returned `"pengendali pengeluaran"` instead of `"operator pengeluaran"`)
   - With greedy implementation: PASSED

2. **`test_fixed_offset_phrase_wins_over_relative_pattern`:**
   - With regex-first order: FAILED (returned `date(2026, 9, 19)` instead of `date(2026, 9, 22)`)
   - With fixed-offset-first order: PASSED

3. **`test_detect_interval_prefers_the_longest_matching_phrase`:**
   - With longest-first sorting: PASSED
   - Precedence rule is now codified

---

**Task Status:** COMPLETE (with fixes)
**Test Result:** 50/50 passing, zero warnings
**Ready for:** Task 7 (or integration with Task 8 salary parser when reached)
