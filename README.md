# MyJobSpy 🇲🇾

**MyJobSpy** is a job scraping library tailored for the **Malaysian** job market. It aggregates postings from multiple job boards into a single pandas DataFrame, with sensible defaults for Malaysian locations, currency, and search patterns.

> Fork of [cullenwatson/JobSpy](https://github.com/cullenwatson/JobSpy) (MIT). Upstream targets the global/US market; this fork narrows the focus to Malaysia — MY-relevant scrapers, MY locations, MYR salaries, and local job boards.

## Features

- Scrapes **Indeed Malaysia**, **LinkedIn**, and **Google Jobs** concurrently by default — the five other upstream boards (Glassdoor, ZipRecruiter, Bayt, Naukri, BDJobs) are quarantined out of the default set but still work if named explicitly in `site_name`
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
    site_name=["indeed", "linkedin", "google"],
    search_term="software engineer",
    google_search_term="software engineer jobs in Kuala Lumpur Malaysia since yesterday",
    location="Kuala Lumpur, Malaysia",
    country_indeed="malaysia",          # required for Indeed — routes to malaysia.indeed.com
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
| **Indeed** | ✅ Default | Uses `malaysia.indeed.com`. Requires `country_indeed="malaysia"`. No rate limiting. Returns real results, but no structured salary data — see caveats below. |
| **LinkedIn** | ✅ Default | Searches globally via `location`. Heavily rate limited — proxies recommended. Returns real results, but no salary data and no description text unless `linkedin_fetch_description=True`. |
| **Google** | ✅ Default | Filtered *only* by `google_search_term`. Needs very specific phrasing (see FAQ) — returned zero rows across every search tried during this project's measurements. |
| Glassdoor | ⚠️ Quarantined | No Malaysian Glassdoor domain; falls back to `www.glassdoor.com` and returns US-centric results. Not in the default `site_name`; pass `site_name="glassdoor"` to use it anyway. |
| ZipRecruiter | ❌ Quarantined | US/Canada only. Not in the default `site_name`; pass it explicitly to use it anyway. |
| Bayt | ❌ Quarantined | Middle East / North Africa. Not in the default `site_name`; pass it explicitly to use it anyway. |
| Naukri | ❌ Quarantined | India. Not in the default `site_name`; pass it explicitly to use it anyway. |
| BDJobs | ❌ Quarantined | Bangladesh. Not in the default `site_name`; pass it explicitly to use it anyway. |

The default `site_name` (used whenever the parameter is omitted) is `indeed`, `linkedin`, `google` — the three boards worth querying for a Malaysian search. The other five are inherited from upstream and left in the codebase, fully importable and usable, but are quarantined out of the default set: pass them by name (e.g. `site_name="bayt"` or `site_name=["indeed", "bayt"]`) to use them anyway.

## Roadmap — Malaysian job boards

None of the following are implemented yet. They are the intended direction of this fork:

- [ ] **JobStreet Malaysia** (`my.jobstreet.com`) — the dominant MY board, highest priority
- [ ] **Hiredly** (formerly WOBB) — startup / young-professional roles
- [ ] **Maukerja** — Bahasa Malaysia listings, blue-collar & retail heavy
- [ ] **Ricebowl** — SME and fresh-grad roles
- [ ] **Glints Malaysia** — tech and startup roles
- [ ] MYR salary parsing from job descriptions (see caveat below)
- [ ] Bahasa Malaysia search-term handling (e.g. *jurutera*, *kerani*, *pemandu*)

Contributions toward any of these are welcome.

## Malaysia-specific caveats

**Salary parsing.** Neither Indeed Malaysia nor LinkedIn returns structured salary data in practice — measured salary fill from direct board data was 0% across live listings. For `country_indeed="malaysia"`, salary is instead parsed out of the job's *description text* looking for MYR amounts (`RM 5,000 - RM 7,000`, `RM3k-5k`, `RM 25 sejam`, etc.); structured data from the board still wins when a board does provide it. This only works where a description is present: **LinkedIn does not fetch description text by default** (`linkedin_fetch_description=False`), so description-parsed salary is effectively Indeed-only unless you turn that flag on. `salary_source` on each row tells you whether the figure came from `direct_data` or was `description`-parsed.

**`enforce_annual_salary=True`** converts monthly MYR figures to annual — useful since most Malaysian postings quote monthly pay.

**Indeed state codes.** Indeed returns location state as an ISO 3166-2 code (`M14`, `M10`, `M07`, …) rather than a state name. The pipeline normalizes these to canonical Malaysian state names in the `state` output column.

**Job types.** `job_type` accepts `fulltime`, `parttime`, `internship`, `contract`. Malaysian "permanent" roles map to `fulltime`.

## Parameters for `scrape_jobs()`

```plaintext
Optional
├── site_name (list|str):
|    defaults to indeed, linkedin, google when omitted (the MY-relevant boards)
|    also available, but quarantined out of the default - pass explicitly:
|    glassdoor, zip_recruiter, bayt, naukri, bdjobs
│
├── search_term (str)
|
├── google_search_term (str)
|     search term for Google Jobs. This is the only param that filters Google results.
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
│
├── description_format (str): markdown (default) or html
│
├── enforce_annual_salary (bool): converts monthly/hourly wages to annual
│
├── group_duplicates (bool): default True.
|    fuzzy-groups likely-duplicate listings (e.g. the same role cross-posted
|    to Indeed and LinkedIn, or a located + remote pass of the same board)
|    into a shared dedup_group id. Never removes a row - grouping only adds
|    a label so duplicates can be filtered or ranked downstream. Runs only
|    when country_indeed="malaysia"; exact-URL dedup runs regardless.
│
├── linkedin_fetch_description (bool):
|    fetches full description + direct job url (increases requests by O(n))
│
├── linkedin_company_ids (list[int])
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
SITE      TITLE                       COMPANY            LOCATION                  JOB_TYPE  INTERVAL  MIN_AMOUNT  MAX_AMOUNT  CURRENCY
indeed    Software Engineer           Setel Ventures     Kuala Lumpur, MY          fulltime  monthly   6000        9000        MYR
indeed    Backend Developer           Grab               Petaling Jaya, Selangor   fulltime  monthly   7000        11000       MYR
linkedin  Senior Software Engineer    AirAsia            Kuala Lumpur, Malaysia    fulltime  None      None        None        None
linkedin  Full-Stack Developer        Carsome            Cyberjaya, Selangor       fulltime  None      None        None        None
google    Software Engineer (Fresh)   Maxis              Kuala Lumpur              fulltime  None      None        None        None
```

For `country_indeed="malaysia"` the DataFrame carries four additional columns, populated by the Malaysia normalization pipeline (`jobspy/malaysia/`):

- **`city`**, **`state`** — the posting's location, split out of `location`. `state` is normalized to a canonical Malaysian state name even when the board itself reports something else — Indeed, for example, returns ISO 3166-2 codes (`M14`, `M10`, `M07`, …) which are mapped to `Kuala Lumpur`, `Selangor`, `Pulau Pinang`, etc.
- **`dedup_group`** — a shared id assigned to listings that look like the same job (e.g. cross-posted to two boards, or picked up by both the located and remote search pass). Grouping never removes a row; it only labels likely duplicates so they can be filtered or ranked downstream.
- **`remote_scope`** — one of `my`, `apac`, `global`, `other_country`, `unknown`, or `None` for non-remote postings, inferred from the description text (and location, when there's no description). Treat it as a sorting aid, not a guarantee: most postings never state remote eligibility at all, so `unknown` is expected to dominate.

## FAQ

**Q: Indeed is returning unrelated roles.**
Indeed searches the description text too. Narrow it with operators:

```python
search_term='"software engineer" (python OR golang) -sales -insurance'
```

Use `-` to exclude words and `""` for exact matches.

---

**Q: No results from `google`?**
Google Jobs requires very specific phrasing. Search Google Jobs in your browser, apply filters, then copy the exact text from the search box into `google_search_term`.

---

**Q: Getting a 429 response?**
You've been rate limited. Wait between scrapes, or use the `proxies` param to rotate IPs. LinkedIn typically blocks around the 10th page from a single IP.

---

**Q: Why so few results per search?**
All job board endpoints cap out around 1000 jobs per search. Split broad searches by location or job title.

## JobPost schema

```plaintext
JobPost
├── title
├── company
├── company_url
├── job_url
├── location
│   ├── country
│   ├── city
│   └── state
├── is_remote
├── description
├── job_type: fulltime, parttime, internship, contract
├── job_function
│   ├── interval: yearly, monthly, weekly, daily, hourly
│   ├── min_amount
│   ├── max_amount
│   ├── currency
│   └── salary_source: direct_data, description (parsed from posting)
├── date_posted
├── emails
├── dedup_group (Malaysia normalization pipeline)
└── remote_scope: my, apac, global, other_country, unknown (Malaysia normalization pipeline)

LinkedIn specific
└── job_level

LinkedIn & Indeed specific
└── company_industry

Indeed specific
├── company_country
├── company_addresses
├── company_employees_label
├── company_revenue_label
├── company_description
└── company_logo
```

## Credits

Built on [JobSpy](https://github.com/cullenwatson/JobSpy) by Cullen Watson and Zachary Hampton. Licensed under MIT — see [LICENSE](LICENSE).
