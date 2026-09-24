# Hiredly scraper — design

**Date:** 2026-09-24 · **Status:** approved · **Board #2 of the Phase 2 roadmap**

Follows the template set by
[`2026-09-23-jobstreet-my-scraper-design.md`](2026-09-23-jobstreet-my-scraper-design.md).
Only what differs from JobStreet is argued here.

## Reconnaissance (measured 2026-09-24)

| Question | Finding |
|---|---|
| robots.txt | `my.hiredly.com/robots.txt` has groups only for named crawlers and **no `User-agent: *` group**, so under RFC 9309 nothing is disallowed for a generic client. |
| API | `POST https://my-api.hiredly.com/api/job_seeker/v1/graphql`, found in the site's JS bundles (`baseURL`). No auth, no TLS fingerprinting, Cloudflare-fronted. |
| Search field | `jobListsSearchResults(keyword, stateRegions, jobTypeIds, expectedSalary, first, last, before, after, showScraped)` returning `totalCount`, `totalPage`, `pageInfo {hasNextPage endCursor}`, `nodes`. |
| Paging | Cursor is base64 of an integer offset (`MzA` = "30"). Page 1 and page 2 did not overlap. |
| Page size | Uncapped: `first: 500` returned all 386 "software engineer" results in one call. |
| Volume | 5,992 live jobs board-wide; 386 for "software engineer". |
| Rate limit | 20 back-to-back requests, all 200, median 0.09s. No rate-limit headers. |
| Freshness | No sort-by-date argument found. `activeAt` spans a year in the unfiltered feed. |
| Descriptions | **Inline** in search nodes (`description`, `requirements`, both HTML). 0/500 empty, median ~2k chars. No per-job request. |
| Salary | `salary` is a bare string: `"5000 - 7000"` (178/500), `"400"` (25), `"Undisclosed"` (297). Present on **203/232 (87.5%) organic** listings, ~0% of aggregated ones. |
| State | `stateRegion` uses the board's 18-value vocabulary (16 MY states + `Singapore`, `Overseas`), plus `Remote`. All MY values seen resolve in the gazetteer unchanged. |
| Free-text location | Often a street address; only 64/500 resolve on their own. |
| Aggregated listings | `category: "scraped"` = copied from employer career sites (e.g. Workday), with `externalJobUrl`. 268/500 of the unfiltered feed. |
| HTML page | Server-rendered `/jobs?search=…` **ignores the search parameter** — HTML scraping cannot search. |

## Decisions

1. **One GraphQL POST per page, `first: 100`.** The board allows 500; 100 matches JobStreet and keeps any single response modest.
2. **Descriptions come from the search nodes.** `description` + `requirements`, joined, converted per `description_format`. No `hiredly_fetch_description` option — there is nothing to switch.
3. **`showScraped: true`.** Matches what the site shows. Aggregated jobs are real, carry a direct employer URL (`job_url_direct`), and grouping tags any cross-board duplicates. They lower Hiredly's salary fill; that is reported, not hidden.
4. **Salary via the shared parser.** The bare `"5000 - 7000"` is rewritten to `"RM 5000 - 7000 per month"` and handed to `parse_myr_salary`, keeping its sanity bands (which correctly reject junk such as `"1700 - 5002500"`). Monthly is the board's display unit. `"Undisclosed"` → `None`.
5. **Location out:** `Location(city=<free-text location>, state=<stateRegion>)`, raw. `normalize_location` resolves state from `stateRegion` and keeps the address as city. `stateRegion == "Remote"` → `state=None`, `is_remote=True`.
6. **Location in:** `location` is mapped to a `stateRegions` filter by resolving it to a `MalaysianState` through the gazetteer (new public `resolve_state()` in `jobspy/malaysia/location.py`) and then to Hiredly's name for it (`Pulau Pinang` → `Penang`, `Melaka` → `Malacca`). A trailing `", Malaysia"` is stripped first — the JobStreet lesson. City-level input widens to its state, logged. Unresolvable input sends no state filter, logged. This is query construction, not output normalization.
7. **Non-Malaysian rows are skipped by allowlist.** Only rows whose `stateRegion` is one of the 16 Malaysian names or `Remote` are kept; the rest are dropped inside the paging loop and counted in one INFO line. Not a blocklist: a `stateRegions: ["Singapore"]` search returned a posting whose `stateRegion` is `"North-East"` — Singapore postings carry Singapore's own regions, not the filter name. Also measured: a zero-match state filter returns 0 (Perlis, Labuan), not a silent fallback to the whole board; only the `Overseas` filter behaves as no filter, and it is never sent.
8. **`hours_old`, `is_remote`, `job_type` are client-side and inline**, inside the paging loop so `results_wanted` counts filtered jobs (JobStreet review F3). `hours_old` compares the full `activeAt` timestamp, so it is genuinely hour-precise. A page ceiling bounds filtered searches.
9. **403 = stop.** Same posture as JobStreet: no retry, partial results returned.
10. **Identity:** `id="hd-<uuid>"`, `job_url=https://my.hiredly.com/jobs/<slug>` (verified 200).
11. **Registered and default-on.** `Site.HIREDLY`, `SITE_DISPLAY_NAMES["Hiredly"]`, `SCRAPER_MAPPING`, `HiredlyException`, added to `DEFAULT_SITES`.

## Field mapping

| JobPost | Hiredly |
|---|---|
| `id` | `"hd-" + id` |
| `title` | `title` (stripped) |
| `company_name` | `company.name`, else `aggregatedCompanyName` |
| `job_url` | `https://my.hiredly.com/jobs/{slug}` |
| `job_url_direct` | `externalJobUrl` when non-empty |
| `location` | `city=location`, `state=stateRegion` (None for `Remote`) |
| `is_remote` | `stateRegion == "Remote"` or `globalHirePreferences.workingArrangementRemote is True`, else None |
| `job_type` | `Full-Time`/`Part-Time`/`Contract`/`Internship` → `JobType` |
| `compensation` | decision 4 |
| `date_posted` | `activeAt` date |
| `description` | `description` + `requirements` |
| `company_logo` | `company.logo`, protocol-relative → `https:` |
| `job_level` | `careerLevel` |
| `skills` | `skills[].name` |
| `experience_range` | `minYearsExperience`–`maxYearsExperience` |

## Testing

Offline fixtures captured live (trimmed), mirroring JobStreet's layout: `tests/fixtures/hiredly/`. Util tests per field, scraper tests for paging / filters / 403 / query construction, a pipeline test proving normalization needs no Hiredly-specific code, a `live`-marked smoke test, and the contract test. Then `hiredly` joins the baseline searches and the baseline is re-run.

## Out of scope

`jobTypeIds` / `experienceIds` server-side filters (ids not yet mapped), company pages, Singapore board.
