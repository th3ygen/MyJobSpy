# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

MyJobSpy is a fork of [cullenwatson/JobSpy](https://github.com/cullenwatson/JobSpy) narrowed to the **Malaysian** job market. It scrapes several job boards concurrently and returns one pandas DataFrame. Upstream scrapers for non-MY markets (ZipRecruiter, Bayt, Naukri, BDJobs, Glassdoor) are kept in the tree but are not targets for this fork — Indeed (`country_indeed="malaysia"`), LinkedIn, JobStreet MY and Hiredly are the four `DEFAULT_SITES`. JobStreet (`my.jobstreet.com`) is the dominant MY board and a primary target for this fork, alongside Indeed MY. The board roadmap in `README.md` is done for now: Maukerja is ruled out by terms that prohibit scraping without written consent, Ricebowl by sharing Maukerja's robots.txt (its own terms are unchecked), and Glints by market fit — don't start Maukerja without that consent, or Ricebowl without reading its terms. A new board, if one comes, follows the recipe below.

## Commands

Poetry project, Python ^3.10. Black (88 cols) is the only linter.

```bash
poetry install                  # deps (dev group: jupyter, black, pre-commit)
poetry run pre-commit install   # one-time; runs black --line-length=88 on commit
poetry run pytest               # unit + integration, offline, ~2s
poetry run black jobspy tests   # format (88 cols, enforced by pre-commit)
poetry build                    # sdist/wheel
```

Tests are offline and fast — run them. A `live` marker is configured and **deselected by default** (`addopts = "-m 'not live'"`) for tests that hit real boards; none exist yet, so live verification today means the baseline runner below or `examples/`.

Two verification layers exist beyond unit tests:

- **`tests/test_scraper_contract.py`** checks every board in `SCRAPER_MAPPING` offline — registered, subclasses `Scraper`, constructor takes `proxies`/`ca_cert`/`user_agent`, `self.site` matches its registry key, has an exception class. A new board should fail these until wired up correctly.
- **`jobspy/baseline/`** measures a fixed search set against live boards and writes a markdown report to `docs/baseline/`. Run it (`poetry run python -m jobspy.baseline.runner`) before and after any change to normalization, and compare — the numbers, not intuition, are how this fork decides whether a change helped.

Smoke-test a change to a scraper by running it directly with `verbose=2` so the per-site loggers print:

```bash
poetry run python -c "
from jobspy import scrape_jobs
df = scrape_jobs(site_name=['indeed'], search_term='software engineer',
                 location='Kuala Lumpur, Malaysia', country_indeed='malaysia',
                 results_wanted=5, verbose=2)
print(df[['site','title','company','location','date_posted']])
"
```

CI (`.github/workflows/tests.yml`) runs the offline suite on Python 3.10 and 3.12 for every push to `main` and every pull request. Nothing publishes to PyPI: the distribution is named `myjobspy` (import name still `jobspy`) and is installed from git.

## Architecture

**Orchestration — `jobspy/__init__.py`.** `scrape_jobs()` is the single public entry point. It maps site strings → `Site` enum → scraper class (module-level `SCRAPER_MAPPING`), runs every requested site in a `ThreadPoolExecutor` (one thread per site), normalizes, then hands off to `build_jobs_dataframe`. One board raising does not kill the run — the failure is logged and the other boards' results are returned.

Note `scrape_jobs` resolves each scraper through `globals()[cls.__name__]` rather than reading `SCRAPER_MAPPING` directly. That is deliberate: tests swap a board out with `monkeypatch.setattr(jobspy, "Indeed", Fake)`, which only takes effect if the class is looked up per call.

**DataFrame assembly — `jobspy/frame.py`.** `build_jobs_dataframe()` flattens `JobPost` → row: job-type joining, email joining, `Location.display_location()`, compensation flattening, `enforce_annual_salary` conversion, column ordering via `util.desired_order`. Extracted from `scrape_jobs` so the output schema is testable without a scrape (`tests/test_frame.py`).

**Malaysia normalization — `jobspy/malaysia/`.** This is what the fork is *for*. `normalize(jobs, *, group_duplicates=True)` runs between scraping and DataFrame assembly, on `list[JobPost]`, so it is board-agnostic — a new scraper gets all of it free, with no per-board wiring:

| Stage | Module | Does |
|---|---|---|
| location | `location.py` | 16-state enum, ~100-entry gazetteer, ISO 3166-2 `M01`–`M16` decode (Indeed emits codes, not state names). Nulls `state` on a miss. |
| salary | `salary.py` | `parse_myr_salary` reads MYR pay out of description text, infers interval, applies sanity bands. Board-supplied `compensation` always wins. |
| remote | `remote.py` | `classify_remote_scope` → `my` / `apac` / `global` / `unknown` from description signals. |
| grouping | `grouping.py` | `dedupe_exact` collapses re-scrapes of one listing; `assign_groups` fuzzy-tags likely duplicates into a shared `dedup_group`. |

Two properties to preserve when touching this:

- **Each per-job stage is individually try/except'd**, counted, and logged as a per-stage rollup. One malformed posting must not abort the batch.
- **Grouping tags, it does not merge.** `assign_groups` labels rows with a shared `dedup_group` id and removes nothing — that was an explicit product decision. `dedupe_exact` (which *does* remove) only ever collapses records of the same listing, keyed on `_identity_key`.

**Contract — `jobspy/model.py`.** Every scraper subclasses `Scraper(ABC)` and implements `scrape(ScraperInput) -> JobResponse`. `ScraperInput` is the normalized query (search term, location, `Country`, distance, `hours_old`, `results_wanted`, `offset`, `description_format`, …); `JobResponse` wraps `list[JobPost]`. `JobPost` is one flat pydantic model shared by all sites — site-specific fields (LinkedIn `job_level`, Indeed company metadata, Naukri `skills`/`experience_range`) are optional fields on that one model rather than subclasses.

**`Country` enum** encodes per-board routing in its tuple: `(comma-separated aliases, indeed_subdomain[:api_country_code], glassdoor_subdomain[:tld])`. `Country.MALAYSIA = ("malaysia", "malaysia:my", "com")` is why `country_indeed="malaysia"` routes to `malaysia.indeed.com` with API code `MY`, and why Glassdoor falls back to the US domain. `indeed_domain_value` / `glassdoor_domain_value` do the parsing; `Country.from_string()` matches user input against the alias list.

**Per-site packages — `jobspy/<site>/`.** Uniform layout: `__init__.py` holds the `Scraper` subclass, `constant.py` holds headers/payloads/GraphQL query strings, `util.py` holds that site's parsing helpers. Shared conventions inside a scraper: `log = create_logger("SiteName")`, a `self.seen_urls` set for dedup, paging until `len(self.seen_urls) >= results_wanted + offset`, and final slicing by `offset:offset+results_wanted`.

**Networking — `jobspy/util.py`.** `create_session()` returns either `TLSRotating` (tls-client, for boards that fingerprint TLS) or `RequestsRotating` (requests + optional `Retry` on 429/5xx). Both mix in `RotatingProxySession`, which cycles the proxy list per request; the literal string `"localhost"` means "no proxy for this turn", which is how you interleave direct and proxied requests. LinkedIn additionally sleeps `random.uniform(delay, delay + band_delay)` between pages because it blocks aggressively.

`util.py` also owns the cross-site helpers: `markdown_converter` / `plain_converter` (description formatting per `DescriptionFormat`), `extract_emails_from_text`, `extract_job_type`, `currency_parser`, `extract_salary`, `convert_to_annual`, and `desired_order`.

## Gotchas

- **`desired_order` is the output schema.** A new `JobPost` field will be silently dropped from the DataFrame unless it is added to `desired_order` in `jobspy/util.py`; list/enum-valued fields also need a flattening line in the row loop in `jobspy/__init__.py`.
- **`util.extract_salary` is USA-only and USD-only; MYR has its own parser.** The upstream description-text fallback runs only when `country_enum == Country.USA` and its regex only matches `$`. Malaysian postings are handled instead by `jobspy.malaysia.salary.parse_myr_salary`, inside the normalization pipeline. When a figure is parsed from text rather than supplied by the board, `salary_source` records that. Don't extend `extract_salary` for MY — extend the MY parser.
- **Descriptions gate salary coverage.** `parse_myr_salary` reads the description, and LinkedIn returns one only when `linkedin_fetch_description=True` (one extra request per job). Leave it off and most LinkedIn pay data disappears — which looks like a parser regression but isn't.
- **`_identity_key` prefers the board-stamped `JobPost.id`.** Every scraper stamps a site-prefixed id (`in-<jk>`, `li-<id>`, …), and exact dedup keys on it, falling back to a tracking-stripped URL. This matters: an earlier version keyed on a URL with the query string stripped, and since Indeed encodes job identity as `?jk=`, it collapsed the entire board to one row. A new scraper that forgets to stamp `id` degrades to the URL path — correct today, but stamp the id.
- **`user_agent` is accepted but ignored by every scraper except Glassdoor.** `scrape_jobs` passes it to all of them, but only Glassdoor forwards it to `super().__init__`, so `self.user_agent` is `None` everywhere else. Indeed and ZipRecruiter likewise never set `self.ca_cert` (they pass the local param straight to `create_session`, so proxy CA certs still work). The seven offenders are grandfathered as `xfail` in `USER_AGENT_NOT_FORWARDED` in the contract test — **a new board must not join that list.**
- **Filter exclusivity.** Indeed accepts only one of `hours_old` / (`job_type` + `is_remote`) / `easy_apply` per search; LinkedIn only one of `hours_old` / `easy_apply`. Scrapers encode this in their query building — check `constant.py` before adding a filter.
- **Google is broken and out of the defaults.** Google Search now answers non-JavaScript clients with a script-only challenge page (`/httpservice/retry/enablejs`, fixture in `tests/fixtures/google/`), so the scraper can never see results; `is_javascript_challenge` detects it and logs an error rather than the old, misleading "try changing your query". Making it work would mean driving a real browser through an anti-bot challenge on a path Google's robots.txt disallows — not a regex fix. When it did work, it was filtered solely by `google_search_term`.
- **JobStreet and Hiredly are the boards with structured MY salary.** Both are marked `salary_source="direct_data"`; Indeed MY and LinkedIn both measure 0% direct-data salary fill. `docs/baseline/2026-09-24-baseline-hiredly.md` is the first report that breaks salary fill out per site (JobStreet 53.9%, Hiredly 43.5%). Quote per-site percentages only from a committed report that breaks them out, and name the report.
- **Hiredly's salary is a bare figure, not a label.** The API returns `"5000 - 7000"` / `"400"` / `"Undisclosed"` with no currency or unit; `jobspy/hiredly/util.py` rewrites it to `"RM 5000 - 7000 per month"` and hands it to `parse_myr_salary` so the shared sanity bands still apply (they reject advertiser junk like `"1700 - 5002500"`). Don't replace that with a local number split. About half of Hiredly's feed is aggregated from employer career sites (`category: "scraped"`) and never carries salary — a drop in Hiredly's per-site fill can be a change in that mix, not a parser regression.
- **Hiredly filters by state, and files remote jobs under a fake state.** Its only location argument is `stateRegions`; `_state_filter` resolves the caller's `location` to a state with `resolve_state` and sends Hiredly's name for it (`Penang`, `Malacca`). Fully-remote jobs have `stateRegion: "Remote"`, so a remote search also sends `"Remote"` (the list is an OR) — without it a KL remote search returns nothing. Rows are then kept by an **allowlist** of the 16 Malaysian names plus `Remote`: Singapore postings carry Singapore's own regions (`"North-East"`), not `"Singapore"`, so a blocklist lets them through.
- **JobStreet's `where` param does not resolve a "City, Country" location.** `location="Kuala Lumpur, Malaysia"` — this fork's own documented convention, shared with Indeed and LinkedIn, and used throughout `README.md` and `examples/` — returned zero JobStreet results before the fix in `_strip_country_suffix` (`jobspy/jobstreet/__init__.py`): the board's search API resolves `where="Kuala Lumpur"` but not the suffixed form. `_build_params` now strips a trailing `", Malaysia"` / `", MY"` before sending `where`, logging when it does, and deliberately leaves a bare `location="Malaysia"` (a legitimate nationwide search) untouched. If you see JobStreet returning suspiciously few rows for a location-scoped search again, check whether a *different* suffix or locale string is slipping through unstripped.
- **`jobstreet_fetch_description` is not a salary lever.** It costs one extra request per job, same shape as `linkedin_fetch_description`, but JobStreet salary comes from the structured `salaryLabel` field regardless of whether the description was fetched. Turning it on buys fuller description text and `remote_scope` signal, not salary coverage — don't reach for it to "fix" JobStreet salary fill the way `linkedin_fetch_description` fixes LinkedIn's.
- **JobStreet's HTML job pages are robots.txt-disallowed; a 403 means stop, not retry.** The scraper calls two endpoints: the JSON search API, and (when `jobstreet_fetch_description=True`) a GraphQL endpoint for full description bodies. Both are open (not TLS-fingerprinted) but sit behind Cloudflare and can still 403. `jobspy/jobstreet/__init__.py` treats a 403 from either as a permanent block for that run rather than retrying — the search loop stops and returns partial results, and `_fetch_description` sets a shared stop flag so a 403 there ends description fetching for the rest of that run (already-collected jobs keep their search teaser) instead of letting the other concurrent description workers hit the same block. Retrying into a 403 is how an IP earns a ban — do not add retry logic to either path.

## Adding a new job board

1. Add the member to `Site` in `jobspy/model.py` (string value = what users pass in `site_name`; `map_str_to_site` does `Site[name.upper()]`), **and an entry in `SITE_DISPLAY_NAMES` beside it** — the log name, matching whatever the board's own module passes to `create_logger`.
2. Create `jobspy/<site>/` with the `__init__.py` / `constant.py` / `util.py` split above; subclass `Scraper`, pass `proxies`, `ca_cert` **and** `user_agent` to `super().__init__`.
3. Register it in the module-level `SCRAPER_MAPPING` in `jobspy/__init__.py` and add a `<Board>Exception` in `jobspy/exception.py`.
4. Stamp a site-prefixed `JobPost.id` from the board's own record key — dedup keys on it.
5. Map the board's fields onto the existing `JobPost` fields wherever they fit; only add a new optional field (plus `desired_order` entry) when nothing fits.
6. Respect `description_format` (`markdown_converter` / `plain_converter`), populate `Location(city=..., state=..., country=Country.MALAYSIA)`, and dedup via `seen_urls`.
7. A board-specific option (a `<board>_fetch_description` switch, an id list) goes on `ScraperInput` as a `<board>_`-prefixed field, is passed through in `scrape_jobs`, and is read off `scraper_input` inside `scrape()`. Never set it onto the instance from `scrape_jobs` — the orchestrator does not know board classes.

Then run `poetry run pytest tests/test_scraper_contract.py` — steps 1–3 are exactly what it checks, so it fails until they are done.

Don't hand-normalize inside a scraper. Emit whatever the board gives you, in the board's own vocabulary, and let `jobspy/malaysia/` do the rest — that is the whole reason normalization is a separate pass. If the gazetteer or salary parser doesn't understand the new board's strings, fix them there, where every board benefits. Unmatched locations are logged at INFO (`unmatched locations - add to the gazetteer: …`) so a new board tells you what it needs; run a scrape at `verbose=2` and read that line.
