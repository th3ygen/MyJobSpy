# MyJobSpy — Malaysia Specialization Design

**Date:** 2026-09-22
**Status:** Approved design, pending implementation plan
**Scope:** Turning the JobSpy fork into a Malaysia-tailored job scraper

## Context

MyJobSpy is a fork of [cullenwatson/JobSpy](https://github.com/cullenwatson/JobSpy). As of this document the code is identical to upstream except for the README rebrand and `CLAUDE.md` — no Malaysia-specific behavior exists yet.

Upstream targets the global/US market. Three of its scrapers work acceptably for Malaysia (Indeed via `malaysia.indeed.com`, LinkedIn, Google Jobs); five do not apply at all (ZipRecruiter, Bayt, Naukri, BDJobs, Glassdoor). More importantly, the data that does come back is not shaped for a Malaysian job search: salaries parsed from description text are gated to `Country.USA` and match only `$`, locations are free-text strings with no Malaysian structure, and the same job appearing on three boards produces three unrelated rows.

This document designs the specialization. It does not design the individual board scrapers beyond the interface they must satisfy.

## Decisions

Recorded with rationale, because several of these constrain everything downstream.

| # | Decision | Rationale |
|---|---|---|
| 1 | **Personal tool now, library later.** Keep `scrape_jobs()` recognizable, but pay no backward-compatibility tax. | No PyPI users to support. Breaking a default is cheap; the option to publish later stays open. |
| 2 | **Measure before building.** The first phase is a baseline harness, not a scraper. | Nobody has run enough MY searches to know whether the pain is coverage or quality. Building on a guess wastes the first phase. |
| 3 | **HTTP-first, browser as fallback.** `requests`/`tls-client` by default; Playwright allowed as an optional extra for boards that genuinely require JS. | Keeps install light and scrapers fast for the common case without declaring hard-JS boards impossible. |
| 4 | **Group duplicates, never merge them.** Every listing stays its own row; likely-duplicates share a `dedup_group` id. | Non-destructive. A wrong grouping is visible and reversible; a wrong merge silently destroys a distinct job posting. |
| 5 | **Parse BM in results; expand BM queries per-board.** English is the default query language. BM query terms are used only by boards where English queries return thin results. | BM parsing is mandatory regardless (Maukerja/Ricebowl post in Malay). Blanket dual-querying would double request volume on boards where it buys nothing. |
| 6 | **Remote jobs in scope, tagged not filtered.** Scrape all remote listings; stamp each with a `remote_scope` eligibility signal. | Consistent with decision 4. Hard-filtering on eligibility would silently drop postings whose eligibility is simply unstated — which is the majority case. |
| 7 | **Normalization pipeline architecture** (over board-first, or an MY-only core rewrite). | Cross-board grouping has no home inside any single scraper. Once that layer exists, salary and location normalization belong beside it, and every future board inherits them at zero marginal cost. |
| 8 | **Quarantine non-MY boards, do not delete.** Drop from default `site_name`, mark unsupported, leave the code. | Deleting is pure cost. `Country` is what routes Indeed to `malaysia.indeed.com`; tearing out the abstraction breaks three working scrapers and buys nothing. |

## Architecture

All Malaysia-specific behavior lands in one new package plus a single call site in `scrape_jobs`.

```
jobspy/
  __init__.py        # collect → normalize → flatten → DataFrame
  model.py           # JobPost gains: dedup_group, remote_scope
  malaysia/
    __init__.py      # normalize(jobs: list[JobPost]) -> list[JobPost]
    location.py      # MY place → (city, state); remote-aware
    salary.py        # MYR free-text → Compensation
    language.py      # BM parsing maps + EN→BM query terms (shared helper)
    remote.py        # remote_scope eligibility tagging
    grouping.py      # exact dedup + fuzzy dedup_group, batch-wide
  jobstreet/         # phase 2; an ordinary Scraper subclass
```

### The pipeline runs on `JobPost`, before DataFrame flattening

This is the load-bearing choice. Today `scrape_jobs` flattens each job to a dict inside its row loop and does salary and location work on those dicts mid-loop. Normalizing earlier means normalizers read and write structured fields — a real `Location`, a real `Compensation` — so they are unit-testable with no pandas involved, and `location.py` can return `Location(city="Cyberjaya", state="Selangor", country=MALAYSIA)` rather than massaging a display string after the fact.

It also gives grouping somewhere to stand: per-job normalizers cannot assign duplicate groups, because that requires the whole collection at once.

### Stages

The pipeline is four stages — three per-job (map) and one batch-wide (reduce). The batch-wide stage, `grouping.py`, runs two distinct mechanisms internally:

```
location  →  salary  →  remote  →  [ exact dedup  →  fuzzy grouping ]
└──────────── per job ──────────┘  └──── grouping.py, whole batch ───┘
```

`group_duplicates=False` disables **fuzzy grouping only**. Exact dedup always runs — without it the two query passes hand back visibly doubled rows.

`language.py` is **not** a stage. BM job types and relative dates are parsed at scrape time inside each scraper; `language.py` is a shared helper module imported by both scrapers and pipeline stages.

### Integration point

Three lines in `scrape_jobs`: threads collect into `site_to_jobs_dict` as today → `jobs = malaysia.normalize(all_jobs)` → existing row loop. The upstream USA `extract_salary` path stays untouched behind its `Country.USA` gate. No changes to the LinkedIn, Indeed, or Google scrapers beyond BM-aware date and job-type parsing.

### Query strategy

Two passes per board, unioned: the location query and a remote-flagged query, enabled by `include_remote=True`. The passes overlap heavily; exact dedup absorbs the overlap.

Query language rides on the scraper class as a declared attribute (`query_language = EN` or `EN_THEN_BM`), not on the pipeline. `language.py` supplies the term map; the scraper decides whether to reach for it. This keeps LinkedIn from ever issuing Malay queries.

## Components

### location.py

A curated gazetteer mapping MY place names to `(canonical_city, MalaysianState)`. `MalaysianState` enumerates the 13 states — Johor, Kedah, Kelantan, Melaka, Negeri Sembilan, Pahang, Perak, Perlis, Pulau Pinang, Sabah, Sarawak, Selangor, Terengganu — and the 3 federal territories: Kuala Lumpur, Labuan, Putrajaya.

The work is in the aliases. `WP Kuala Lumpur` / `Federal Territory of Kuala Lumpur` / `KL` collapse to one entry. `Penang` / `Pulau Pinang` / `George Town` / `Bayan Lepas` / `Butterworth` span a state and several of its cities. `Cyberjaya` is in Selangor; neighbouring `Putrajaya` is its own federal territory.

**Kuala Lumpur resolves to `state="Kuala Lumpur"`, not `state=None`.** It is a federal territory, and filtering by state must work uniformly across all rows.

**Unmatched locations pass through untouched and are logged.** The baseline harness reports the most frequent unmatched strings each run. The gazetteer starts at roughly 100 places covering Klang Valley and the main tech hiring centres, and grows from measured misses rather than from guesses.

A `region` concept (Klang Valley and similar) is deferred: it spans KL, Putrajaya and parts of Selangor, it is genuinely fuzzy, and it is derivable downstream from state.

### salary.py

**MY postings quote monthly by default** — the exact inverse of the US assumption baked into `extract_salary`. `RM5,000` with no stated interval means RM5,000 per month.

Formats handled: `RM3,000`; `RM 3,000 - RM 5,000`; `MYR 3000-5000`; `3,000 - 5,000 MYR`; `RM3k-5k`; and BM phrasings such as `Gaji RM2,500 sebulan` and `RM3,000 hingga RM4,500`. Interval words come from `language.py`: `sebulan` / `per month` / `p.m.`, `setahun` / `per annum`, `sejam` / `per hour`.

Sanity bands anchored on Malaysian reality rather than the inherited US thresholds:

| Interval | Accepted range |
|---|---|
| Monthly | RM1,000 – RM30,000 |
| Annual | RM20,000 – RM500,000 |
| Hourly | RM8 – RM150 |

The statutory minimum wage (RM1,700/month as of 2025) is the reasoning behind the monthly floor: a bare `RM800` is far more likely hourly or daily than a monthly wage, so it is rejected rather than guessed. These bands are heuristics for filtering nonsense, not policy claims.

Precedence is unchanged from today: structured board data always wins, and this parser only fills when `compensation` is absent. Output sets `salary_source=DESCRIPTION` and `currency="MYR"`.

### language.py

`JobType` in `model.py` is **already a multilingual enum** — `FULL_TIME` carries `"vollzeit"`, `"tempsplein"`, `"tempopieno"` and a dozen more, matched as space-stripped lowercase. BM job types therefore need no new machinery, only new tuple entries: `"sepenuhmasa"`, `"separuhmasa"`, `"kontrak"`, `"latihanindustri"`. `get_enum_from_job_type` works unchanged.

The module itself owns:

- **Relative date parsing** — `hari ini`, `semalam`, `3 hari lepas`, `minggu lepas`, `bulan lepas`, `baru sahaja`.
- **Salary interval vocabulary** — consumed by `salary.py`.
- **The EN→BM query term map** — skewed deliberately toward blue-collar and administrative roles: `kerani`, `pemandu`, `pengawal keselamatan`, `juruwang`, `pembantu`, `jururawat`, `juruteknik`, `tukang masak`. Malaysian tech and white-collar postings are written in English even on BM-heavy boards, so a term map full of software job titles would be effort spent on queries nobody issues in Malay.

### remote.py

Classifies `remote_scope` into `my` / `apac` / `global` / `other_country` / `unknown` from three signal types:

1. **Explicit location strings** — `Remote, Malaysia`, `Remote (APAC)`.
2. **Eligibility phrases in the description** — `must be based in Malaysia`, `open to candidates across APAC`, `anywhere in the world`, `US work authorization required`.
3. **Timezone hints** — `GMT+8` / `MYT` / `SGT` imply APAC; `EST` / `PST` imply another country.

Precedence: an explicit exclusion beats a generic "fully remote" claim.

**`unknown` is expected to be the most common value, by a wide margin** — most postings simply do not state eligibility. This is acceptable because the field tags rather than filters, but it means `remote_scope` is a sorting aid and not a guarantee. The field must not be used to drop rows.

### grouping.py

Two mechanisms, deliberately not sharing code because they solve different problems.

**Exact dedup — destructive, uncontroversial.** Keys on normalized `job_url` (tracking parameters stripped) or `(site, board_id)`. This is the same listing seen twice, almost always the location and remote passes colliding. On collision it keeps the most complete record — description present, salary present — rather than the first seen.

**Fuzzy grouping — non-destructive, tagged.** Blocks on normalized company name to avoid O(n^2) comparison, then within each block compares title similarity and state.

- Company normalization strips MY corporate suffixes (`Sdn Bhd`, `Bhd`, `Pte Ltd`) and a trailing `Malaysia`, so `Grab`, `Grab Malaysia` and `GrabTaxi Holdings Sdn Bhd` land in one block.
- **A seniority guard runs before similarity scoring, not as part of it.** Each title is scanned for a seniority marker (`intern`, `junior`, `senior`, `lead`, `principal`, `staff`, `head`, `director`, `manager`); if the two titles carry *different* markers, they never group, whatever their similarity score. This must be a hard precondition rather than a scoring input, because the obvious similarity metric gets this exactly wrong: `token_set_ratio("senior software engineer", "software engineer")` returns 100, since set-based comparison discards the unmatched token. Seniority is the single most common way two genuinely different openings at one company look alike.
- After the guard passes, two listings group when `token_sort_ratio` ≥ 90 **and** they share a state, or one of them is remote. `token_sort_ratio` respects every token, unlike `token_set_ratio`. The threshold is a starting value to be calibrated against phase 0 data.
- The matcher is tuned conservative: a missed group costs one duplicate row; a wrong group asserts that two distinct openings are the same job.
- `dedup_group` is a stable short hash of the canonical `(company, title, state)` triple, so groups are comparable across runs rather than being per-batch sequence numbers.

**New dependency: `rapidfuzz`** for string similarity. Small, fast, no build toolchain. Hand-rolling token-set ratio on `difflib` would be both slower and worse.

## Data model and API changes

### `JobPost` (`jobspy/model.py`)

| Field | Type | Meaning |
|---|---|---|
| `dedup_group` | `str \| None` | Stable hash shared by likely-duplicate listings across boards |
| `remote_scope` | `str \| None` | `my` / `apac` / `global` / `other_country` / `unknown` |

Both must also be added to `desired_order` in `jobspy/util.py`, or they will be silently dropped from the DataFrame.

### `scrape_jobs()` signature

```python
scrape_jobs(
    country_indeed="malaysia",   # default flipped from "usa"
    include_remote=True,         # new: second remote-flagged pass per board
    group_duplicates=True,       # new: fuzzy dedup_group tagging
)
```

`country_indeed="malaysia"` as the default is mildly breaking and intentional — this is a Malaysian tool, and requiring users to pass a country to get the default behavior is backwards.

### `Site`

Gains `JOBSTREET` in phase 2 and further members in phase 3. Non-MY members are marked unsupported and dropped from the default `site_name` list; their code stays in the tree.

## Phasing

This design spans more work than one implementation plan should carry. **Each phase gets its own plan**, written when the preceding phase lands — phases 2 and 3 in particular should be planned against real phase 0 numbers rather than against the assumptions in this document. The immediate next step is a plan covering phases 0 and 1 together, since phase 0 is small and phase 1 is what it measures.

### Phase 0 — Baseline harness

A runner that executes a fixed set of Malaysian searches and emits a report: per-board volume, salary fill rate, location match rate plus the top unmatched strings, duplicate rate, `remote_scope` distribution, and normalizer failure counts. Committed as markdown so runs diff against each other.

It exists because nobody has yet measured what MY searches return, but it earns its keep permanently: it is how phase 1 proves it lifted salary fill rate instead of assuming it did, and it is the regression check every later board runs against.

### Phase 1 — Pipeline on existing boards

All four pipeline stages plus `language.py`, wired into `scrape_jobs`, against Indeed MY / LinkedIn / Google only. No new scrapers. Includes the `include_remote` two-pass, since `remote.py` has nothing to tag without it, and the `future.result()` fix described below. Re-run phase 0 and measure the lift.

### Phase 2 — JobStreet MY

The dominant Malaysian board, and the first real test of whether the pipeline generalizes to a source it was not designed around.

### Phase 3 — Remaining boards

Hiredly, Glints MY, Maukerja, Ricebowl — ordered by what the phase 1 baseline shows is actually missing, not by assumption. EN→BM query expansion ships here alongside Maukerja/Ricebowl; it is inert until there is a BM-heavy board to point it at.

## Testing

The repository has **zero tests today**, so this establishes the pattern rather than extending one. `pytest` is added as a dev dependency.

Three tiers, deliberately unequal in weight:

**Pure unit tests over the normalizers.** Nearly all the test value sits here. Every module in `jobspy/malaysia/` is a pure function over strings and `JobPost`s, so these are table-driven tests with real Malaysian examples, no network, no pandas, no mocking: `RM3k-5k` → `(MONTHLY, 3000, 5000, MYR)`; `Cyberjaya` → `(Cyberjaya, Selangor)`. They are the natural TDD target — write the table of salary strings first, then the parser.

**Fixture-based scraper tests.** One recorded HTTP response per board, asserting the parser yields the expected `JobPost`s. Worth having, with one caveat stated plainly: a passing fixture test does not mean the board still works. It means the parser still handles a response shape captured at some point in the past.

**Opt-in live smoke tests.** Marked `@pytest.mark.live` and excluded from the default run. This is the only tier that catches a board changing its API, and it is run manually or on a schedule.

## Failure handling

**An existing bug to fix in phase 1.** `scrape_jobs` calls `future.result()` with no guard (`jobspy/__init__.py:126`). Any scraper that raises propagates out and kills the entire multi-board run — one flaky board returns nothing instead of returning the boards that worked. Tolerable at three boards, unacceptable at eight. The fix is a per-site catch: log the failure, return an empty `JobResponse`, continue.

The same principle one level down: a per-job normalizer that chokes on a malformed salary string must not take the batch with it. Each per-job stage is wrapped, and a failure leaves that field unset.

**Wrapped is not swallowed.** Both layers log at warning level with the offending input, and the phase 0 report surfaces failure counts as a line item. Without that, the pipeline degrades quietly — fill rates drift down over months and nothing ever reports that a parser broke.

Rate limiting keeps the existing handling: `create_session(has_retry=True)` retries 429 and 5xx with backoff, and LinkedIn's inter-page sleep stays.

Playwright is an optional extra (`pip install myjobspy[browser]`). A board that requires it and cannot find it raises a clear install message, not a bare `ImportError`.

## Out of scope

Deferred deliberately, recorded so they are not rediscovered as gaps:

- **Merging duplicate listings into single rows** — rejected in favour of tagging (decision 4).
- **A `region` concept** (Klang Valley and similar) — derivable downstream from state.
- **EN→BM query expansion** — designed here, but only ships in phase 3 with the boards that need it.
- **Deleting the non-MY scrapers** — quarantined instead (decision 8).
- **Glassdoor MY support** — no Malaysian Glassdoor domain exists; `Country.MALAYSIA` falls back to `www.glassdoor.com` and returns US-centric results.
- **Publishing to PyPI.** The inherited `.github/workflows/publish-to-pypi.yml` fires on push to `main` under the upstream package name `python-jobspy` and is not to be relied on.
