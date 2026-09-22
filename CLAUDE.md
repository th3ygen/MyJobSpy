# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

MyJobSpy is a fork of [cullenwatson/JobSpy](https://github.com/cullenwatson/JobSpy) narrowed to the **Malaysian** job market. It scrapes several job boards concurrently and returns one pandas DataFrame. Upstream scrapers for non-MY markets (ZipRecruiter, Bayt, Naukri, BDJobs, Glassdoor) are kept in the tree but are not targets for this fork — Indeed (`country_indeed="malaysia"`), LinkedIn and Google are. The roadmap in `README.md` (JobStreet MY, Hiredly, Maukerja, Ricebowl, Glints) drives most new work, so *adding a scraper* is the most common task here.

## Commands

Poetry project, Python ^3.10. There is **no test suite and no linter config beyond Black** — verification is done by actually running a scrape.

```bash
poetry install                  # deps (dev group: jupyter, black, pre-commit)
poetry run pre-commit install   # one-time; runs black --line-length=88 on commit
poetry run black jobspy         # format (88 cols, enforced by pre-commit)
poetry build                    # sdist/wheel
```

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

Note `.github/workflows/publish-to-pypi.yml` publishes to PyPI on push to `main` under the upstream package name `python-jobspy` — it is inherited from upstream and will fail/misfire for this fork; don't rely on it.

## Architecture

**Orchestration — `jobspy/__init__.py`.** `scrape_jobs()` is the single public entry point. It maps site strings → `Site` enum → scraper class (`SCRAPER_MAPPING`), runs every requested site in a `ThreadPoolExecutor` (one thread per site), then flattens each `JobPost` into a row and concatenates. Post-processing lives here, not in the scrapers: job-type joining, email joining, `Location.display_location()`, compensation flattening, `enforce_annual_salary` conversion, and column ordering via `util.desired_order`.

**Contract — `jobspy/model.py`.** Every scraper subclasses `Scraper(ABC)` and implements `scrape(ScraperInput) -> JobResponse`. `ScraperInput` is the normalized query (search term, location, `Country`, distance, `hours_old`, `results_wanted`, `offset`, `description_format`, …); `JobResponse` wraps `list[JobPost]`. `JobPost` is one flat pydantic model shared by all sites — site-specific fields (LinkedIn `job_level`, Indeed company metadata, Naukri `skills`/`experience_range`) are optional fields on that one model rather than subclasses.

**`Country` enum** encodes per-board routing in its tuple: `(comma-separated aliases, indeed_subdomain[:api_country_code], glassdoor_subdomain[:tld])`. `Country.MALAYSIA = ("malaysia", "malaysia:my", "com")` is why `country_indeed="malaysia"` routes to `malaysia.indeed.com` with API code `MY`, and why Glassdoor falls back to the US domain. `indeed_domain_value` / `glassdoor_domain_value` do the parsing; `Country.from_string()` matches user input against the alias list.

**Per-site packages — `jobspy/<site>/`.** Uniform layout: `__init__.py` holds the `Scraper` subclass, `constant.py` holds headers/payloads/GraphQL query strings, `util.py` holds that site's parsing helpers. Shared conventions inside a scraper: `log = create_logger("SiteName")`, a `self.seen_urls` set for dedup, paging until `len(self.seen_urls) >= results_wanted + offset`, and final slicing by `offset:offset+results_wanted`.

**Networking — `jobspy/util.py`.** `create_session()` returns either `TLSRotating` (tls-client, for boards that fingerprint TLS) or `RequestsRotating` (requests + optional `Retry` on 429/5xx). Both mix in `RotatingProxySession`, which cycles the proxy list per request; the literal string `"localhost"` means "no proxy for this turn", which is how you interleave direct and proxied requests. LinkedIn additionally sleeps `random.uniform(delay, delay + band_delay)` between pages because it blocks aggressively.

`util.py` also owns the cross-site helpers: `markdown_converter` / `plain_converter` (description formatting per `DescriptionFormat`), `extract_emails_from_text`, `extract_job_type`, `currency_parser`, `extract_salary`, `convert_to_annual`, and `desired_order`.

## Gotchas

- **`desired_order` is the output schema.** A new `JobPost` field will be silently dropped from the DataFrame unless it is added to `desired_order` in `jobspy/util.py`; list/enum-valued fields also need a flattening line in the row loop in `jobspy/__init__.py`.
- **`extract_salary` is USA-only and USD-only.** The description-text salary fallback in `scrape_jobs` runs only when `country_enum == Country.USA`, and its regex only matches `$`. MY postings that state pay only in free text get empty `min_amount`/`max_amount` — MYR parsing is an open roadmap item, so don't assume it works.
- **`user_agent` is accepted but ignored by every scraper except Glassdoor.** `scrape_jobs` passes it to all of them, but only Glassdoor forwards it to `super().__init__` and applies it to its headers. Indeed and ZipRecruiter likewise never set `self.ca_cert` (they pass the local param straight to `create_session`, so proxy CA certs still work). Wire the forwarding up when touching a scraper that needs it — don't assume `self.user_agent` is set.
- **`__all__` in `jobspy/__init__.py` is `["BDJobs"]`** (leftover from an upstream PR). `from jobspy import scrape_jobs` works; `from jobspy import *` does not export it.
- **Filter exclusivity.** Indeed accepts only one of `hours_old` / (`job_type` + `is_remote`) / `easy_apply` per search; LinkedIn only one of `hours_old` / `easy_apply`. Scrapers encode this in their query building — check `constant.py` before adding a filter.
- **Google Jobs is filtered solely by `google_search_term`**; `location`, `job_type` etc. do not narrow it.

## Adding a new job board

1. Add the member to `Site` in `jobspy/model.py` (string value = what users pass in `site_name`; `map_str_to_site` does `Site[name.upper()]`).
2. Create `jobspy/<site>/` with the `__init__.py` / `constant.py` / `util.py` split above; subclass `Scraper`, pass `proxies`, `ca_cert` **and** `user_agent` to `super().__init__`.
3. Register it in `SCRAPER_MAPPING` in `jobspy/__init__.py` and add an exception class in `jobspy/exception.py`.
4. Map the board's fields onto the existing `JobPost` fields wherever they fit; only add a new optional field (plus `desired_order` entry) when nothing fits.
5. Respect `description_format` (`markdown_converter` / `plain_converter`), populate `Location(city=..., state=..., country=Country.MALAYSIA)`, and dedup via `seen_urls`.
