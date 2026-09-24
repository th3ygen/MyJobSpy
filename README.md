# MyJobSpy 🇲🇾

**MyJobSpy** is a job scraping library tailored for the **Malaysian** job market. It aggregates postings from multiple job boards into a single pandas DataFrame, with sensible defaults for Malaysian locations, currency, and search patterns.

> Fork of [cullenwatson/JobSpy](https://github.com/cullenwatson/JobSpy) (MIT). Upstream targets the global/US market; this fork narrows the focus to Malaysia — MY-relevant scrapers, MY locations, MYR salaries, and local job boards.

## Features

- Scrapes **Indeed Malaysia**, **LinkedIn**, **JobStreet Malaysia** and **Hiredly** concurrently by default — the other upstream boards (Google, Glassdoor, ZipRecruiter, Bayt, Naukri, BDJobs) are quarantined out of the default set but still work if named explicitly in `site_name`
- Malaysian locations out of the box — Kuala Lumpur, Selangor, Penang, Johor, Cyberjaya, and more
- Aggregates everything into one pandas DataFrame → CSV / Excel
- Proxy support to work around rate limiting

## Installation

Not published to PyPI — install from this repo:

```bash
pip install git+https://github.com/th3ygen/MyJobSpy.git
```

_Requires Python >= [3.10](https://www.python.org/downloads/release/python-3100/)_

## Usage

```python
import csv
from jobspy import scrape_jobs

jobs = scrape_jobs(
    site_name=["indeed", "linkedin", "jobstreet", "hiredly"],
    search_term="software engineer",
    location="Kuala Lumpur, Malaysia",
    country_indeed="malaysia",          # already the default; shown for clarity — routes to malaysia.indeed.com
    results_wanted=20,
    hours_old=72,

    # linkedin_fetch_description=True   # full description + direct job url (slower)
    # proxies=["user:pass@host:port", "localhost"],
)

print(f"Found {len(jobs)} jobs")
jobs.to_csv("jobs_my.csv", quoting=csv.QUOTE_NONNUMERIC, escapechar="\\", index=False)
```

### Common Malaysian locations

`location` accepts any free-text place that the board itself understands:

| Klang Valley | Northern | Southern | East Coast / East Malaysia |
|---|---|---|---|
| Kuala Lumpur | Penang | Johor Bahru | Kuantan |
| Petaling Jaya | George Town | Iskandar Puteri | Kota Kinabalu |
| Cyberjaya | Ipoh | Melaka | Kuching |
| Shah Alam | Alor Setar | Seremban | Kota Bharu |
| Subang Jaya | Butterworth | Nusajaya | Miri |

Use `location="Malaysia"` for a nationwide search, or add `is_remote=True` for remote-friendly roles.

## Supported job boards

| Board | Status | Notes |
|---|---|---|
| **Indeed** | ✅ Default | Uses `malaysia.indeed.com`. Requires `country_indeed="malaysia"`. Rate limited in practice — sustained or large-`results_wanted` runs start returning empty pages, so pace your scrapes and use proxies for anything heavy. Returns real results, but no structured salary data — see caveats below. |
| **LinkedIn** | ✅ Default | Searches globally via `location`. Heavily rate limited — proxies recommended. Returns real results, but no salary data and no description text unless `linkedin_fetch_description=True`. |
| **Google** | ⛔ Not default — broken | Google Search now answers non-JavaScript clients with a challenge page containing no results (measured 2026-09-24), so this scraper returns nothing and logs an error saying so. It returned zero rows in every baseline this fork has run. Still importable by name; would need a real browser to work again. |
| **JobStreet** | ✅ Default | Uses `my.jobstreet.com`'s public JSON search API, plus a GraphQL endpoint for full descriptions when `jobstreet_fetch_description=True`. Structured MY salary via `salaryLabel` — see caveats below. Both endpoints sit behind Cloudflare and can return 403 (its HTML job pages are also robots.txt-disallowed, but the scraper never requests those); the scraper treats a 403 from either as a block and stops rather than retrying, so a JobStreet run can end early with partial results — or with plain search teasers instead of full descriptions — if the board decides to block it. |
| **Hiredly** | ✅ Default | Uses the GraphQL API `my.hiredly.com`'s own frontend calls; full descriptions arrive with the search, so there is no per-job request. Salary is structured (`salary_source="direct_data"`). Filters by **state only** — a city such as `"Petaling Jaya"` widens to Selangor. About half its listings are aggregated from employer career sites; those carry no salary, and `job_url_direct` links to the employer's own posting. Postings located outside Malaysia (the board also lists Singapore jobs) are dropped. Cloudflare-fronted; a 403 stops the run rather than retrying. |
| Glassdoor | ⚠️ Quarantined | No Malaysian Glassdoor domain; falls back to `www.glassdoor.com` and returns US-centric results. Not in the default `site_name`; pass `site_name="glassdoor"` to use it anyway. |
| ZipRecruiter | ❌ Quarantined | US/Canada only. Not in the default `site_name`; pass it explicitly to use it anyway. |
| Bayt | ❌ Quarantined | Middle East / North Africa. Not in the default `site_name`; pass it explicitly to use it anyway. |
| Naukri | ❌ Quarantined | India. Not in the default `site_name`; pass it explicitly to use it anyway. |
| BDJobs | ❌ Quarantined | Bangladesh. Not in the default `site_name`; pass it explicitly to use it anyway. |

The default `site_name` (used whenever the parameter is omitted) is `indeed`, `linkedin`, `jobstreet`, `hiredly` — the four boards worth querying for a Malaysian search. The other six are inherited from upstream and left in the codebase, fully importable and usable, but are quarantined out of the default set: pass them by name (e.g. `site_name="bayt"` or `site_name=["indeed", "bayt"]`) to use them anyway.

## Roadmap — Malaysian job boards

- [x] **JobStreet Malaysia** (`my.jobstreet.com`) — the dominant MY board, highest priority
- [x] **Hiredly** (formerly WOBB) — startup / young-professional roles
- [ ] Bahasa Malaysia search-term handling (e.g. *jurutera*, *kerani*, *pemandu*)

**Not pursued** (decided 2026-09-24):

- **Maukerja** — its terms of use prohibit scraping, crawling or systematically extracting data without prior written consent, and its robots.txt disallows every search and API path. Worth adding only with that consent, e.g. through a partner feed. This leaves blue-collar and Bahasa Malaysia listings, Maukerja's niche, largely uncovered.
- **Ricebowl** — its robots.txt is identical to Maukerja's, line for line, including the shared API paths, which suggests one operator. Its own terms were not checked; read them before reconsidering.
- **Glints** — its market is mainly Indonesia and Singapore; its Malaysian coverage is too small to justify a board.

## Malaysia-specific caveats

**Salary parsing.** Indeed Malaysia and LinkedIn return no structured salary data in practice (measured direct-data fill: 0%), so for those boards salary is instead parsed out of the job's *description text* looking for MYR amounts (`RM 5,000 - RM 7,000`, `RM3k-5k`, `RM 25 sejam`, etc.); structured data from the board still wins when a board does provide it. This only works where a description is present: **LinkedIn does not fetch description text by default** (`linkedin_fetch_description=False`), so description-parsed salary is effectively Indeed-only unless you turn that flag on. **JobStreet and Hiredly are the exceptions** — both publish structured salary (JobStreet a `salaryLabel`, Hiredly a bare `"5000 - 7000"` read as monthly MYR), used directly and marked `salary_source="direct_data"` with no description fetch required. `docs/baseline/2026-09-24-baseline-hiredly.md` (748 rows) is the first report to break salary fill out per site: **JobStreet 53.9%** (254 rows), **Hiredly 43.5%** (69 rows), Indeed 41.3%, LinkedIn 0.0%. Hiredly's figure is held down by its aggregated listings, which never carry salary; its own organic listings measured 87.5% during reconnaissance. `salary_source` on each row tells you whether the figure came from `direct_data` or was `description`-parsed. Figures parsed from description text above RM30,000/month are discarded as likely budget or revenue numbers rather than pay; a board's own salary field is trusted up to RM80,000/month, since senior roles on JobStreet do list RM30,000–55,000.

**`enforce_annual_salary=True`** converts monthly MYR figures to annual — useful since most Malaysian postings quote monthly pay.

**Indeed state codes.** Indeed returns location state as an ISO 3166-2 code (`M14`, `M10`, `M07`, …) rather than a state name. The pipeline normalizes these to canonical Malaysian state names in the `state` output column.

**Job types.** `job_type` accepts `fulltime`, `parttime`, `internship`, `contract`. Malaysian "permanent" roles map to `fulltime`.

## Parameters for `scrape_jobs()`

```plaintext
Optional
├── site_name (list|str):
|    defaults to indeed, linkedin, jobstreet, hiredly when omitted (the
|    MY-relevant boards)
|    also available, but quarantined out of the default - pass explicitly:
|    glassdoor, zip_recruiter, bayt, naukri, bdjobs, google (currently
|    broken - see Supported job boards)
│
├── search_term (str)
|
├── google_search_term (str)
|     search term for Google Jobs, the only param that filters it. Google is
|     currently broken (it requires JavaScript), so this has no effect.
│
├── location (str): e.g. "Kuala Lumpur, Malaysia"
│
├── country_indeed (str):
|    controls which Indeed domain is used. Defaults to "malaysia"
|    (routes to malaysia.indeed.com); the Malaysia normalization pipeline
|    (dedup_group, remote_scope, state/city normalization, description
|    salary parsing) only runs when this is "malaysia".
│
├── distance (int): in miles, default 50
|    Indeed and LinkedIn only; JobStreet and Hiredly have no radius filter.
│
├── job_type (str): fulltime, parttime, internship, contract
│
├── is_remote (bool)
│
├── include_remote (bool): default True.
|    Malaysia only (country_indeed="malaysia"). Runs a second,
|    remote-flagged search pass per board and unions it with the located
|    pass; the exact-dedup step absorbs the overlap between the two. For
|    any other country_indeed this is a no-op (a single, located-only
|    pass) and a log line says so - a default-on parameter doing nothing
|    must be observable, not just documented.
│
├── results_wanted (int):
|    number of results to retrieve per site in 'site_name'
│
├── hours_old (int):
|    filters jobs by hours since posting
│
├── offset (int):
|    start the search from an offset (e.g. 25 starts at the 25th result)
│
├── proxies (list):
|    format ['user:pass@host:port', 'localhost']
|    each scraper round-robins through the proxies
│
├── ca_cert (str): path to CA certificate file for proxies
│
├── user_agent (str): override the default user agent
|    sent by JobStreet, Hiredly, LinkedIn and Glassdoor. Indeed keeps its
|    mobile-app user agent regardless: its API refused a browser one (403).
│
├── description_format (str): markdown (default), html or plain
│
├── enforce_annual_salary (bool): converts monthly/hourly wages to annual
│
├── group_duplicates (bool): default True.
|    fuzzy-groups likely-duplicate listings (e.g. the same role cross-posted
|    to Indeed and LinkedIn, or a located + remote pass of the same board)
|    into a shared dedup_group id. Never removes a row - grouping only adds
|    a label so duplicates can be filtered or ranked downstream. Runs only
|    when country_indeed="malaysia"; exact dedup runs regardless. Set it to
|    False and the dedup_group column is all-None, not partially filled -
|    df.groupby("dedup_group") then yields nothing at all.
│
├── linkedin_fetch_description (bool):
|    fetches full description + direct job url (increases requests by O(n))
│
├── linkedin_company_ids (list[int])
│
├── jobstreet_fetch_description (bool):
|    fetches each JobStreet job's full description via GraphQL (one extra
|    request per job). Buys fuller description text and remote_scope signal,
|    not salary - JobStreet's salary comes from a structured field either
|    way. Off by default; without it, JobStreet's description is the search
|    result teaser.
│
├── easy_apply (bool):
|    filters for jobs hosted on the board itself
│
└── verbose (int) {0, 1, 2}:
     0 = errors only, 1 = errors + warnings, 2 = all logs. Default is 0.
```

### Filter limitations

```
├── Indeed: only ONE of these per search
|    - hours_old
|    - job_type & is_remote
|    - easy_apply
│
└── LinkedIn: only ONE of these per search
     - hours_old
     - easy_apply
```

## Output

```
SITE      TITLE                       COMPANY            LOCATION                              JOB_TYPE  INTERVAL  MIN_AMOUNT  MAX_AMOUNT  CURRENCY
indeed    Software Engineer           Setel Ventures     Kuala Lumpur, Kuala Lumpur, Malaysia  fulltime  monthly   6000        9000        MYR
indeed    Backend Developer           Grab               Petaling Jaya, Selangor, Malaysia     fulltime  monthly   7000        11000       MYR
linkedin  Senior Software Engineer    AirAsia            Kuala Lumpur, Kuala Lumpur, Malaysia  fulltime  None      None        None        None
linkedin  Full-Stack Developer        Carsome            Cyberjaya, Selangor, Malaysia         fulltime  None      None        None        None
```

`location` is the *normalized* location — city, canonical state, country — whatever shape the board originally reported (Indeed's raw `Kuala Lumpur, MY` becomes the row above). Kuala Lumpur appears twice in a KL row because it is both the city and the federal territory that serves as its state.

For `country_indeed="malaysia"` the DataFrame carries four additional columns, populated by the Malaysia normalization pipeline (`jobspy/malaysia/`):

- **`city`**, **`state`** — the posting's location, split out of `location`. `state` is normalized to a canonical Malaysian state name even when the board itself reports something else — Indeed, for example, returns ISO 3166-2 codes (`M14`, `M10`, `M07`, …) which are mapped to `Kuala Lumpur`, `Selangor`, `Pulau Pinang`, etc.
- **`dedup_group`** — a shared id assigned to listings that look like the same job (e.g. cross-posted to two boards, or picked up by both the located and remote search pass). Grouping never removes a row; it only labels likely duplicates so they can be filtered or ranked downstream. **Populated on every row only when `group_duplicates=True`** (the default); with `group_duplicates=False` the column is all-`None`, so `df.groupby("dedup_group")` silently yields no groups rather than erroring.
- **`remote_scope`** — one of `my`, `apac`, `global`, `other_country`, `unknown`, or `None` for non-remote postings, inferred from the description text (and location, when there's no description). Treat it as a sorting aid, not a guarantee: most postings never state remote eligibility at all, so `unknown` is expected to dominate. In practice the location does most of the work: location normalization stamps `country=MALAYSIA` on any resolvable Malaysian posting, and the `my` check outranks `apac`, so a remote job located in Malaysia classifies `my` whatever its description says about wider eligibility.

## FAQ

**Q: Indeed is returning unrelated roles.**
Indeed searches the description text too. Narrow it with operators:

```python
search_term='"software engineer" (python OR golang) -sales -insurance'
```

Use `-` to exclude words and `""` for exact matches.

---

**Q: No results from `google`?**
Expected. Google Search now requires JavaScript and serves a challenge page to this scraper instead of results; the log line `Google requires JavaScript for search results` confirms it. Changing `google_search_term` will not help. That is why Google is no longer a default board.

---

**Q: Getting a 429 response?**
You've been rate limited. Wait between scrapes, or use the `proxies` param to rotate IPs. LinkedIn typically blocks around the 10th page from a single IP.

---

**Q: Why so few results per search?**
Most boards cap out around 1000 jobs per search (Hiredly does not). Split broad searches by location or job title, and check `results_wanted` — it is per board, and defaults to 15.

## Output columns

```plaintext
Every board
├── id                 site-prefixed board id (js-, hd-, in-, li-, ...)
├── site
├── title, company
├── job_url            the posting on the board
├── job_url_direct     the employer's own posting, where the board links one
├── location, city, state
├── date_posted
├── job_type           fulltime, parttime, internship, contract, ...
├── is_remote
├── description
├── emails             found in the description
├── compensation
│   ├── interval       yearly, monthly, weekly, daily, hourly
│   ├── min_amount, max_amount
│   ├── currency
│   └── salary_source  direct_data (board field) or description (parsed)
├── dedup_group        Malaysia pipeline
└── remote_scope       my, apac, global, other_country, unknown (Malaysia pipeline)

Filled only by some boards
├── company_logo       JobStreet, Hiredly, Indeed, LinkedIn
├── company_url        JobStreet, Indeed, LinkedIn
├── job_level          Hiredly, LinkedIn
├── job_function       JobStreet, LinkedIn
├── skills             Hiredly
├── experience_range   Hiredly
├── company_industry   Indeed, LinkedIn
└── company_addresses, company_num_employees,
    company_revenue, company_description      Indeed

(Quarantined upstream boards fill a few more, e.g. Naukri's company_rating.)
```

## Credits

Built on [JobSpy](https://github.com/cullenwatson/JobSpy) by Cullen Watson and Zachary Hampton. Licensed under MIT — see [LICENSE](LICENSE).
