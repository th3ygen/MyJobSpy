# JobStreet MY Scraper — Design

**Date:** 2026-09-23
**Status:** Approved design, pending implementation plan
**Scope:** Phase 2 of [the Malaysia specialization design](2026-09-22-malaysia-specialization-design.md) — one board, JobStreet Malaysia
**Parent decisions this inherits:** 3 (HTTP-first), 4 (group, never merge), 7 (normalization pipeline), 8 (quarantine non-MY boards)

## Context

Phases 0 and 1 shipped: the baseline harness, the four-stage Malaysian normalization pipeline, and 259 offline tests. The pipeline is board-agnostic by construction — it runs on `list[JobPost]` between scraping and DataFrame assembly — so a new board inherits location, salary, remote and grouping normalization with no per-board wiring.

JobStreet MY is the dominant Malaysian board and the first test of whether that claim survives contact with a source the pipeline was not designed around.

It also addresses the fork's largest measured gap. The README records salary fill from direct board data as **0%** across Indeed MY and LinkedIn; every MYR figure in the output today is parsed out of description prose. JobStreet publishes a structured salary string on roughly 70% of postings.

### Reconnaissance findings

Measured against the live board on 2026-09-23. These drive the decisions below, so they are recorded rather than summarized.

| Property | Finding |
|---|---|
| Search endpoint | `GET /api/jobsearch/v5/search` — JSON, no authentication |
| Description endpoint | `POST /graphql`, `jobDetails` query — full HTML body, no authentication |
| Bot gating | Returns `200` with user-agent `jobspy`, `python-requests`, or none at all. No TLS fingerprinting. |
| HTML job page | `GET /job/<id>` returns **403** — the HTML route is the blocked one |
| Completeness | One query: `totalCount` 1264, fetched 1264 rows, **1264 unique, 0 duplicates** |
| Page size | `pageSize=100` honored — 13 requests for that full set instead of 64 |
| Freshness | `sortmode=ListedDate` works; freshest posting observed was 48 minutes old |
| Rate limiting | 40 sequential (~3 req/s) → 40/40 `200`. 20 concurrent at parallelism 10 → 20/20 `200` in 769ms. No `RateLimit-*` or `Retry-After` headers. |
| Server-side filters | `daterange` (whole days) and `worktype` both confirmed working |
| Inventory | 51,689 jobs Malaysia-wide; 14,110 Kuala Lumpur; 15,235 Selangor; 6,010 Penang |
| `salaryLabel` fill | 14 of 20 on the sampled page |

Salary strings were tested against the existing parser rather than assumed compatible:

```
'RM\xa05,000 – RM\xa07,500 per month'  -> 5000.0-7500.0 MONTHLY
'RM\xa01,000 per month'                -> 1000.0-1000.0 MONTHLY
'RM\xa025 per hour'                    -> 25.0-25.0 HOURLY
'$5,000 – $7,000 per month'            -> None
'$14500 - $15500 p.h.'                 -> None
```

`jobspy.malaysia.salary.parse_myr_salary` handles JobStreet's format unmodified — non-breaking spaces, en-dashes, single values, explicit intervals. The two rejections are advertiser junk typed with `$` (2 of 36 sampled). Returning `None` there is correct: the parser declines to guess, and those rows stay unpriced.

### robots.txt

`my.jobstreet.com/robots.txt` disallows both endpoints for the default agent:

```
User-agent: *
Disallow: */job/
Disallow: *?
Disallow: /graphql
Disallow: /api/jobsearch/
```

Recorded because it is a standing risk, not a footnote. The data is public and unauthenticated, and the eight inherited scrapers are already in the same position with their own boards — Indeed and LinkedIn disallow their equivalent endpoints too. There is no robots-clean alternative that works: the `Allow: *?keywords` exception covers the HTML search pages, and those return 403.

The consequence for this design is concrete. A board that disallows an endpoint and fronts it with Cloudflare is more likely to begin enforcing later, so the measured absence of a rate limit is treated as a fact about today, not a property to depend on. This is what decisions 8 and 9 exist for.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **Use the JSON search API, not HTML parsing.** | It is the endpoint the site's own frontend calls, and the HTML route returns 403. There is no HTML fallback to design. |
| 2 | **`pageSize=100`.** | Five times fewer requests for the same data. Verified honored, with zero duplicates across the full result set. |
| 3 | **Descriptions opt-in: `jobstreet_fetch_description=False`.** | One GraphQL call per job. Normally descriptions are load-bearing because MYR salary is parsed from them — but this board supplies salary directly, so the description only serves `remote_scope` and human reading. Mirrors `linkedin_fetch_description`. |
| 4 | **Reuse `parse_myr_salary` for `salaryLabel`; do not write a JobStreet parser.** | Proven against real strings above. The CLAUDE.md rule against normalizing inside a scraper exists to stop boards hand-rolling logic; reusing the shared parser is the opposite of that. |
| 5 | **Emit board vocabulary for location; let the gazetteer normalize.** | Parent decision 7. `locations[0].label` splits on a comma into city and state and goes in as-is. Unmatched strings self-report at INFO. |
| 6 | **Map `workArrangements` to `is_remote` directly.** | The board states `Remote` / `Hybrid` / `On-site` explicitly. This is better remote data than any other board in the fork gives us, and it does not require a description. |
| 7 | **Plain `requests` session, not `tls-client`.** | Verified: the API does not fingerprint TLS and does not inspect user-agent. Paying the tls-client cost would buy nothing. |
| 8 | **Conservative default pacing plus backoff, despite no observed limit.** | See robots.txt above. Absence of enforcement today is not a guarantee, and a scraper that discovers a new limit by getting the IP blocked is worse than one that never provoked it. |
| 9 | **Committed JSON fixtures; the test suite never touches the live board.** | Parent design's middle testing tier. Real captured payloads catch shape drift that hand-written dicts cannot, and they stay offline and fast. |
| 10 | **Add `JOBSTREET` to `DEFAULT_SITES`.** | It is a primary MY board by the fork's own roadmap. Leaving it out of the default would mean the best Malaysian source only runs when asked for by name. |

## Architecture

```
jobspy/
  jobstreet/
    __init__.py     # JobStreet(Scraper) — paging, orchestration
    constant.py     # base URLs, siteKey, sourcesystem, headers,
                    # GraphQL query string, worktype id map
    util.py         # response JSON -> JobPost; salary/location/type parsing
```

The standard three-file layout every other board uses. Nothing outside this package changes except four registration points (`Site`, `SCRAPER_MAPPING`, `exception.py`, `DEFAULT_SITES`) and the new `scrape_jobs` keyword.

### Data flow

```
ScraperInput
  -> build query params (keywords, where, page, pageSize, daterange, worktype)
  -> GET /api/jobsearch/v5/search          [1 request per 100 results]
  -> for each record: util.parse_job() -> JobPost
  -> if jobstreet_fetch_description:
       POST /graphql jobDetails            [1 request per job]
  -> JobResponse
  -> (scrape_jobs) jobspy.malaysia.normalize()
  -> build_jobs_dataframe()
```

Salary needs no pipeline participation. `_apply_salary` returns early when `job.compensation is not None`, and `frame.py` then defaults `salary_source` to `direct_data`. Setting `compensation` in the scraper is sufficient; the correct provenance falls out.

## Field mapping

| JobStreet | `JobPost` | Notes |
|---|---|---|
| `id` | `id` | Prefixed: `js-94830903`. Exact dedup keys on this. |
| `title` | `title` | |
| `companyName` / `advertiser.description` | `company_name` | `companyName` preferred; `advertiser.description` is the fallback |
| `employer.companyUrl` | `company_url` | |
| — | `job_url` | Constructed: `https://my.jobstreet.com/job/<id>` |
| `locations[0].label` | `location` | Split on comma → `city`, `state`; `country=MALAYSIA`. Gazetteer normalizes. |
| `listingDate` | `date_posted` | ISO 8601 UTC → `date` |
| `workTypes[]` | `job_type` | List. Mapped via `constant.py`: `Full time`→`FULL_TIME`, `Part time`→`PART_TIME`, `Contract/Temp`→`CONTRACT`, `Casual/Vacation`→`TEMPORARY` |
| `workArrangements.data[].label.text` | `is_remote` | `Remote` → `True`; `Hybrid` / `On-site` → `False` |
| `salaryLabel` | `compensation` | Via `parse_myr_salary`. `None` when unparseable — never guessed. |
| `teaser` | `description` | Only when `jobstreet_fetch_description=False`, so the field is never empty |
| GraphQL `content` | `description` | Overwrites the teaser when descriptions are fetched. Honors `description_format`. |
| `branding.serpLogoUrl` | `company_logo` | |
| `classifications[].classification.description` | `job_function` | e.g. `Information & Communication Technology` |
| `bulletPoints` | — | Dropped. Marketing copy, already present in the description. |
| `solMetadata`, `tracking`, `userQueryId` | — | Dropped. Per-request tracking tokens; including them would poison URL-based dedup. |

`workTypes` is genuinely a list — postings tagged both `Full time` and `Casual/Vacation` appear under both server-side filters — so it maps to `job_type` as a list, which `JobPost` already expects.

## Query construction

| `ScraperInput` | JobStreet param | Notes |
|---|---|---|
| `search_term` | `keywords` | |
| `location` | `where` | Free text. The response echoes a resolved `location` object. |
| `results_wanted`, `offset` | `page` + `pageSize` | Page until `len(seen_ids) >= results_wanted + offset`, then slice |
| `hours_old` | `daterange` | Whole days only: `ceil(hours_old / 24)`, then filter client-side on `listingDate` for the exact cutoff |
| `job_type` | `worktype` | Verified ids: `242` Full time, `243` Part time, `244` Contract/Temp, `245` Casual/Vacation |
| `is_remote` | — | No server-side param found. Filtered client-side on `workArrangements`. |
| `distance` | — | Unsupported by the endpoint. Ignored, logged once at INFO so it is not silently dropped. |

Constants: `siteKey=MY-Main`, `sourcesystem=houston`.

Sort mode is `ListedDate` when `hours_old` is set — paging newest-first lets the scraper stop as soon as it crosses the cutoff — and the board default (relevance) otherwise.

### Country handling

JobStreet is Malaysia-only and always queries `MY-Main`, ignoring `ScraperInput.country`. One caveat to document rather than engineer around: the Malaysian normalization pipeline is gated on `country_indeed="malaysia"` in `scrape_jobs`. A caller who scrapes JobStreet with a different `country_indeed` gets raw board output with no normalization. Since `country_indeed` already defaults to `"malaysia"`, this only bites someone deliberately mixing markets, and the scraper logs a warning when it sees a non-MY country.

## Rate limiting and failure handling

Defaults sit well under what was measured, per decision 8:

- Sequential paging with a small randomized inter-page delay, in the style of LinkedIn's existing `random.uniform(delay, delay + band_delay)`.
- Description fetches bounded by a small worker pool, not one thread per job.
- `create_session(has_retry=True)` for 429 and 5xx backoff, as every other board uses.
- A `403` is treated as a block signal, not a transient error: log plainly, stop paging, return what was collected. Grinding through a block is how an IP gets a permanent one.

Partial results are always returned. `scrape_jobs` already isolates per-board failures, and the normalization pipeline already isolates per-job stage failures.

## Testing

Three layers, all offline.

**Fixture-based parser tests — the bulk of the value, and the new convention.** Real captured payloads, trimmed to a handful of representative records, committed under `tests/fixtures/jobstreet/`:

| Fixture | Covers |
|---|---|
| `search_page.json` | Nominal records: salaried, unsalaried, multi-location, multi-worktype, each `workArrangements` value |
| `search_empty.json` | Zero results — the paging loop must terminate, not spin |
| `search_last_page.json` | Partial page (the 64-of-100 case) followed by an empty page |
| `job_details.json` | GraphQL description response |
| `search_malformed.json` | Missing `salaryLabel`, missing `locations`, null `companyName` — parser must degrade per-field, not raise |

Tests assert `JobPost` output field by field, including that unparseable salary yields `compensation is None` rather than a guess, and that tracking tokens never reach `job_url`.

**Contract compliance.** `tests/test_scraper_contract.py` parameterizes seven of its ten checks over `SCRAPER_MAPPING`, so registering the board opts it into those automatically, and the three suite-wide checks cover it too. It must pass `test_forwards_user_agent_to_super` — **JobStreet does not join `USER_AGENT_NOT_FORWARDED`.** That list exists to stop the inherited defect spreading to the Malaysian boards, and this is the first board that tests whether it worked.

**Live smoke test.** One `@pytest.mark.live` test, deselected by default. The fork currently has zero live tests; this is the first, and it is the only layer that catches the board changing its API. A passing fixture test means the parser still handles a shape captured in the past — nothing more.

## Measurement

Phase 0's baseline runner is how this gets judged, per parent decision 2. Run `poetry run python -m jobspy.baseline.runner` before and after, and compare:

- **Salary fill rate** — the headline. Expect a large lift on JobStreet rows against the recorded 0% from direct board data.
- **Location match rate**, plus the top unmatched strings. JobStreet's suburb-level labels (`Bukit Bintang, Kuala Lumpur`) are new vocabulary; gazetteer misses are expected and are the point of the INFO line.
- **Duplicate rate** and `dedup_group` behavior with a third board in play — the first real test of cross-board grouping.
- **Normalizer failure counts**, which must not rise.

Gazetteer additions that the baseline reveals are in scope for this phase. They belong in `jobspy/malaysia/location.py`, where every board benefits, not in the scraper.

## Out of scope

- **The other four roadmap boards.** Hiredly, Glints, Maukerja, Ricebowl follow once this board has proved the fixture pattern.
- **Fixing the seven scrapers that drop `user_agent`.** Unrelated inherited defect; stays xfailed.
- **EN→BM query expansion.** `jobspy/malaysia/language.py` exists, but JobStreet posts predominantly in English. It ships with the BM-heavy boards, per parent decision 5.
- **Company profile enrichment.** `companyProfileStructuredDataId` and `employer.companyId` expose further endpoints. No current consumer.
- **Salary-range and classification search filters.** The API supports more filters than `ScraperInput` models. Adding parameters that only one board honors is a change to the shared contract, not to this scraper.
- **Recording anything from `solMetadata`.** Per-request tracking tokens with no analytical value here.
