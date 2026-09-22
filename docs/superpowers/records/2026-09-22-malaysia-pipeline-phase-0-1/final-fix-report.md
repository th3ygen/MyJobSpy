# Final fix wave — report

Branch `feat/malaysia-pipeline-phase-0-1`. Four commits, suite 182 → **207 passing, 0 warnings**, no test touches the network.

| Commit | Subject |
|---|---|
| `09f6b0b` | fix(malaysia): key exact dedup on board identity, not a query-stripped URL |
| `1ad9a24` | fix(malaysia): carry salary provenance through to salary_source |
| `b8f38fb` | fix(malaysia): restore the salary ceiling and stop excluding APAC timezones |
| `34205ad` | docs: correct the README output example and record the BM-date deferral |

---

## C1 — exact dedup destroyed ~95% of results from several boards

### What the investigation actually found

I read every scraper's `job_url` construction rather than assuming shapes. Two distinct families:

| Board | `job_url` built by this repo | Identity lives in | `JobPost.id` |
|---|---|---|---|
| Indeed | `f'{base}/viewjob?jk={job["key"]}'` | **query** `jk` | `in-{key}` |
| Glassdoor | `f"{base}job-listing/j?jl={job_id}"` | **query** `jl` | `gd-{listingId}` |
| ZipRecruiter | `f"{base}/jobs//j?lvk={listing_key}"` | **query** `lvk` | `zr-{listing_key}` |
| BDJobs | scraped href carrying `?jobid=…` | **query** `jobid` | bare numeric `jobid` |
| LinkedIn | `f"{base}/jobs/view/{job_id}"` | path | `li-{job_id}` |
| Naukri | `f"https://www.naukri.com{job['jdURL']}"` | path, **plus a per-request session id in the query** | `nk-{jobId}` |
| Google | `job_info[3][0][0]` — an arbitrary third-party ATS/board URL | arbitrary | `go-{job_info[28]}` |
| Bayt | scraped href | path | `bayt-{abs(hash(job_url))}` |

Four of eight boards encode identity in the query string. `_canonical_url` discarded the query wholesale, so all four collapsed onto a single key and `dedupe_exact` — the pipeline's only destructive stage — returned one row per board. Confirmed by the new tests before the fix: 25 Indeed-shaped jobs → 1, and 20 through `scrape_jobs` end-to-end → 1 row, while the LinkedIn control returned 20.

The **second** finding of the investigation is what determined the fix: **every scraper already stamps a site-prefixed board id on `JobPost.id`**, derived from the board's own record key. That is a better identity than any URL — exact, stable between the located and remote passes, and immune to every question about which query parameters mean what.

Naukri is the concrete reason URL-only would still have been wrong: `jdURL` carries a session id that changes between requests, so a URL-keyed dedup (with any honest denylist) would fail to collapse the two passes' overlap for that board. The review's warning about per-request parameters is real and this board exhibits it.

### The fix

`_identity_key(job)` — **board id first, normalized URL as fallback**:

```python
def _identity_key(job: JobPost) -> str:
    if job.id:
        return f"id:{job.id}"
    return _canonical_url(job.job_url)
```

Used by both `dedupe_exact` and `_fallback_group_id` (they must agree; the F17 bug existed because the shared key had lost the distinguishing information).

Cross-site collision is impossible: ids are site-prefixed (`in-`, `li-`, `gd-`, `zr-`, `nk-`, `go-`, `bayt-`), and BDJobs' bare numeric id cannot equal a prefixed one.

`_canonical_url` now strips a **denylist** of tracking parameters and preserves everything else, sorting the survivors so param order doesn't matter.

### Which parameters I strip, and why each is safe

| Stripped | Why it is safe |
|---|---|
| `utm_*` (prefix) | Urchin campaign tags. A reserved-by-convention namespace for campaign attribution; no board uses a `utm_`-prefixed key as a record id. Required by the pre-existing `?utm_source=email` test. |
| `gclid`, `dclid`, `gbraid`, `wbraid` | Google Ads click identifiers, minted per ad click. |
| `fbclid` | Meta click identifier, minted per click. |
| `msclkid` | Microsoft Ads click identifier. |
| `ttclid`, `twclid`, `igshid` | TikTok / X / Instagram click and share identifiers. |
| `yclid` | Yandex click identifier. |
| `mc_cid`, `mc_eid` | Mailchimp campaign and recipient identifiers. |
| `_ga`, `_gl` | Google Analytics cross-domain linker values — regenerated on every request, so keeping them would *break* dedup. |

Every entry is an industry-standard analytics/ad token with a published meaning, not a guess about a particular board's URL scheme.

**Deliberately NOT stripped**, and this is the important half: `from`, `src`, `ref`, `source`, `sid`, `trk`, `tk`, `vjk`, `advn`. These look like navigation noise, and several probably are, but they are ambiguous — some sites use `src`/`ref`/`sid` as record keys. The two errors are not symmetric: keeping a noise parameter costs one duplicate row, while stripping an identity parameter silently destroys listings, which is the failure being fixed. With the board id as the primary key, real scraped jobs never reach this path anyway, so the conservative choice costs essentially nothing.

### TDD evidence

Tests written first; **8 failed against the pre-fix code**, with exactly the reported signature:

```
FAILED test_exact_dedup_keeps_distinct_listings_on_every_board_shape[indeed]       assert 1 == 2
FAILED test_exact_dedup_keeps_distinct_listings_on_every_board_shape[glassdoor]    assert 1 == 2
FAILED test_exact_dedup_keeps_distinct_listings_on_every_board_shape[ziprecruiter] assert 1 == 2
FAILED test_exact_dedup_keeps_distinct_listings_on_every_board_shape[bdjobs]       assert 1 == 2
FAILED test_exact_dedup_never_merges_distinct_board_ids                            assert 1 == 3
FAILED test_a_batch_of_query_id_listings_is_not_collapsed                          assert 1 == 25
FAILED test_unresolved_fallback_ids_differ_for_two_unrelated_listings
        assert '194aa6b9d3ff' != '194aa6b9d3ff'
FAILED test_a_page_of_query_id_listings_survives_the_pipeline                      assert 1 == 20
8 failed, 45 passed
```

The `[linkedin]` parametrization **passed** before the fix — the path-distinguished control, which is why 182 tests missed this.

New tests:
- `_REAL_BOARD_URLS` — real-shaped URLs for all five distinguishable boards, each annotated with the source line it was copied from. No `https://x/1` placeholders.
- `test_exact_dedup_survives_tracking_params_on_a_query_id_url` — one Indeed listing bare, with `utm_source`+`utm_campaign`, and with `gclid`+`fbclid` → 1 row.
- `test_exact_dedup_prefers_the_board_assigned_id` / `..._never_merges_distinct_board_ids` — both directions of the board-id key.
- `test_unresolved_fallback_ids_differ_for_two_unrelated_listings` — the F17 property.
- `tests/test_scrape_jobs_integration.py::test_a_page_of_query_id_listings_survives_the_pipeline` — a fake returning **20** jobs (every prior fake returned exactly one, and a 1-in/1-out board cannot exhibit a collapse). It runs with `include_remote=True`, so both passes return the same 20 listings: it pins both halves of the contract at once — 40 raw rows must collapse to 20, not to 1 and not to 40.
- `..._path_id_listings_survives_the_pipeline` — the LinkedIn control at integration level.

### One behaviour change worth flagging

`_fallback_group_id` for a post with **neither** id nor URL now falls back to object identity instead of hashing a shared empty string. The old code collided such rows. Object identity is unique within the run (which is what the no-collision guarantee needs) but not reproducible across runs — the honest answer when the posting offers nothing reproducible to key on. Documented in the docstring.

---

## I1 — `salary_source` reported the wrong provenance

`JobPost` gains `salary_parsed_from_description: bool = False`. The salary stage sets it *only* on the parsed path; `frame.py` reads it and stamps `DESCRIPTION`, defaulting to `DIRECT_DATA` everywhere else.

The "structured board data always wins" invariant is untouched — `_apply_salary` still early-returns when `job.compensation` is already set, so the marker can never be raised over a board-supplied figure. The field is not in `desired_order`, so it adds no output column (asserted by `test_provenance_marker_is_not_leaked_as_a_column`).

**TDD evidence** — 2 failed before the fix, both with the reported value:

```
FAILED test_frame.py::test_malaysian_description_parsed_salary_reports_description_source
        assert 'direct_data' == 'description'
FAILED test_pipeline.py::test_description_parsed_salary_reaches_the_frame_as_description
        assert 'direct_data' == 'description'
```

Four tests added: the requested `tests/test_frame.py` Malaysian case, its `direct_data` counterpart, the no-leaked-column check, and two end-to-end cases in `test_pipeline.py` that run the **real** pipeline into the real frame rather than hand-setting the marker — so the test would still catch a regression if the marker mechanism were replaced.

---

## I2 — explicit-interval salaries had no upper bound

Restored the per-interval **ceiling** on the explicit path; floor stays dropped, so Ruling F15's case still works. `_ABSURDITY_CEILING` is now dead and removed, and the `_BANDS` comment rewritten to say floor and ceiling have different scopes and why.

**TDD evidence** — the exact sentence from the review reproduced:

```
FAILED test_explicit_interval_does_not_lift_the_ceiling[You will manage a portfolio worth RM2,500,000 and report monthly to the board.]
        assert Compensation(interval=MONTHLY, min_amount=2500000.0, ...) is None
FAILED test_explicit_interval_does_not_lift_the_ceiling[The successful candidate will handle RM900,000 in daily transactions.]
        assert Compensation(interval=DAILY, min_amount=900000.0, ...) is None
```

The third parametrization (`RM48,000,000` annual budget) already passed — it exceeded even the flat RM10m ceiling, which is a good illustration that the old guard only caught the most extreme cases. `test_explicit_interval_still_clears_the_floor` pins `"Pay: RM800.00 per month"` explicitly (in addition to the existing parametrized case).

---

## M1 — `"Asia Pacific time zones"` classified as `other_country`

`r"(?<!asia )(?<!asia-)\b(?:eastern|pacific|central|mountain)\s+(?:standard\s+|daylight\s+)?time\b"`.

Two fixed-width lookbehinds (both 5 chars) cover the spaced and hyphenated spellings. The text is already lowercased and whitespace-collapsed before matching, so no case handling is needed.

**TDD evidence** — 2 failed before the fix:

```
FAILED test_asia_pacific_time_is_not_a_us_timezone             assert 'other_country' != 'other_country'
FAILED test_hyphenated_asia_pacific_time_is_not_a_us_timezone  assert 'other_country' != 'other_country'
```

Four tests: both APAC spellings must not be `other_country`; `"Pacific Standard Time"` and `"Eastern Time"` must still be. The APAC cases now classify `apac`, falling through to the intended branch.

---

## Minor fixes

- **M2** — `parse_bm_relative_date` verified to have no production caller (`grep` finds the definition plus tests only). Added as a fifth entry in the plan's "Deferred from the spec" section, with the reason and the phase to wire it up in.
- **M4** — Output example rewritten so every row shows the post-normalization location shape, plus a line explaining why Kuala Lumpur appears twice in a KL row (it is both city and federal territory). Note the finding named only the Indeed row, but three of five rows were un-normalized; I fixed all of them, since a half-corrected example still contradicts the claim below it. Indeed's "No rate limiting" replaced with this project's experience.
- **M5** — Sentence added to the `remote_scope` bullet explaining that location normalization stamps `country=MALAYSIA` and `my` outranks `apac`, so location decides most rows.
- **M6** — All-or-nothing `dedup_group` documented in three places: the README parameter block, the README output bullet, and both the `scrape_jobs` and `normalize` docstrings.
- **M7** — Unused `Site` import removed from `tests/test_scrape_jobs_integration.py`.

---

## Files changed

| File | Change |
|---|---|
| `jobspy/malaysia/grouping.py` | `_identity_key`, denylist-based `_canonical_url`, `dedupe_exact` and `_fallback_group_id` rekeyed |
| `jobspy/malaysia/salary.py` | ceiling restored on the explicit path, `_ABSURDITY_CEILING` removed |
| `jobspy/malaysia/remote.py` | timezone lookbehinds |
| `jobspy/malaysia/__init__.py` | sets `salary_parsed_from_description`; docstring |
| `jobspy/model.py` | `JobPost.salary_parsed_from_description` |
| `jobspy/frame.py` | reads the marker for `salary_source` |
| `jobspy/__init__.py` | `group_duplicates` docstring |
| `tests/malaysia/test_grouping.py` | +7 tests (one parametrized ×5) |
| `tests/malaysia/test_salary.py` | +4 tests |
| `tests/malaysia/test_remote.py` | +4 tests |
| `tests/malaysia/test_pipeline.py` | +2 tests |
| `tests/test_frame.py` | +3 tests |
| `tests/test_scrape_jobs_integration.py` | +2 tests, `Site` import removed |
| `README.md` | M4, M5, M6 |
| `docs/superpowers/plans/2026-09-22-malaysia-pipeline-phase-0-1.md` | M2 |

Black run on changed files only.

---

## Disagreements

None with the findings themselves. All five substantive findings reproduced exactly as described, with the reported values (`1` row from 20, `194aa6b9d3ff` shared, `('monthly', 2500000.0, 2500000.0)`, `'direct_data'`). Two notes on scope:

1. **C1's framing.** The review offered "normalized `job_url`" *or* `(site, board_id)` as alternatives. I used both, board id first, because neither alone is sufficient: board id doesn't cover posts built without one, and URL normalization cannot be made correct for Naukri's session-id query. Layering them costs nothing and each covers the other's gap.

2. **M4 was slightly understated** — three of the five example rows were un-normalized, not just the Indeed one.

## Things found along the way

- **Naukri's `jdURL` carries a per-request session id.** This is the concrete instance of the hazard the review warned about abstractly, and it is why I did not ship a URL-only fix. Worth knowing if anyone later proposes simplifying `_identity_key` down to the URL.
- **`Bayt.id` is `f"bayt-{abs(hash(job_url))}"`.** Python's string hash is salted per process, so this id is stable within a run but not across runs. `dedupe_exact` runs in-process and is unaffected. `_fallback_group_id`, though, documents cross-run stability, and for Bayt specifically that promise does not hold. Bayt is quarantined and not in `DEFAULT_SITES`, so this is noted rather than fixed — the real fix belongs in Bayt's id assignment, not in the Malaysia pipeline.
- **`JobPost` has no `site` field.** `jobspy/bdjobs/__init__.py:238` passes `site=self.site` to the constructor, which Pydantic silently drops as an extra. Harmless today (site attribution lives in the `site_to_jobs_dict` key and `scrape_jobs` carries it via `site_by_job`), but it is dead code that reads as though it works. Not touched; flagging it.
- **`jobspy/baseline/metrics.py` measures only overall `salary_fill_rate`.** With I1 fixed, splitting that by `salary_source` is now possible and is the measurement Phase 1 is actually steering on. I did not add it — it would change the baseline report format, which is outside this fix wave — but it is the obvious next step.
- **`CLAUDE.md` is untracked in the repo root** and was briefly swept into a commit by a `git add -A`; I amended it back out. It remains untracked, exactly as I found it.
