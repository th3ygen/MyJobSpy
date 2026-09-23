# JobStreet MY Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a JobStreet Malaysia scraper to MyJobSpy, registered as a first-class board and covered by offline fixture tests.

**Architecture:** An ordinary `Scraper` subclass in `jobspy/jobstreet/`, following the three-file layout every other board uses. It reads JobStreet's public JSON search API, maps each record onto the shared flat `JobPost`, and optionally fetches descriptions from the board's GraphQL endpoint. It does no Malaysian normalization of its own — `jobspy/malaysia/` already runs board-agnostically between scraping and DataFrame assembly, so location, remote-scope and grouping come free.

**Tech Stack:** Python 3.10+, Poetry, pydantic v2, `requests` (not `tls-client` — this API does not fingerprint), pytest, Black at 88 columns.

**Spec:** [`docs/superpowers/specs/2026-09-23-jobstreet-my-scraper-design.md`](../specs/2026-09-23-jobstreet-my-scraper-design.md)

## Global Constraints

- **Black, 88 columns.** Enforced by pre-commit. Format **only the files you touch** — `black jobspy tests` reformats 14 inherited upstream files and creates a large spurious diff. Use `black jobspy/jobstreet tests/test_jobstreet*.py`.
- **Poetry lives at an absolute path on this machine:** `C:\Users\USER\AppData\Roaming\Python\Python312\Scripts\poetry.exe`. Every command below assumes `poetry` means that binary.
- **Never hand-normalize inside a scraper.** Emit the board's own vocabulary and let `jobspy/malaysia/` normalize. The single exception is salary, which reuses the shared `parse_myr_salary` — that is reuse, not hand-rolling.
- **Stamp a site-prefixed `JobPost.id`**: `js-<board id>`. Exact dedup keys on it.
- **Forward `proxies`, `ca_cert` **and** `user_agent` to `super().__init__`.** JobStreet must NOT join `USER_AGENT_NOT_FORWARDED` in `tests/test_scraper_contract.py`.
- **A new `JobPost` field would need a `desired_order` entry** in `jobspy/util.py` or it is silently dropped from the DataFrame. This plan adds no new fields.
- **Tests are offline.** No task hits the network except Task 8, which is `@pytest.mark.live` and deselected by default.
- **Board constants:** `siteKey=MY-Main`, `sourcesystem=houston`, base `https://my.jobstreet.com`.

---

## File Structure

| File | Responsibility |
|---|---|
| `jobspy/jobstreet/__init__.py` | Create — the `JobStreet(Scraper)` class: paging, orchestration, description fetching |
| `jobspy/jobstreet/constant.py` | Create — URLs, headers, GraphQL query, work-type id and name maps |
| `jobspy/jobstreet/util.py` | Create — pure functions: JSON record → `JobPost`, and its field-level helpers |
| `jobspy/model.py` | Modify — add `Site.JOBSTREET` |
| `jobspy/exception.py` | Modify — add `JobStreetException` |
| `jobspy/__init__.py` | Modify — import, `SCRAPER_MAPPING` entry, `DEFAULT_SITES`, `jobstreet_fetch_description` kwarg |
| `tests/test_jobstreet_util.py` | Create — parser unit tests against fixtures (the bulk of the value) |
| `tests/test_jobstreet_scraper.py` | Create — paging and orchestration tests with a stubbed session |
| `tests/test_jobstreet_live.py` | Create — one `@pytest.mark.live` smoke test |
| `tests/fixtures/jobstreet/` | **Already committed** — see its `README.md` |
| `CLAUDE.md`, `README.md` | Modify — document the board (Task 9) |

**The fixtures already exist.** They were captured from the live board during planning and committed with this plan, so every task below is offline and deterministic. Read `tests/fixtures/jobstreet/README.md` before Task 2 — it explains why each record is present.

---

## Task 1: Register the board

Registration first, so the contract test starts failing immediately and guards everything after it.

**Files:**
- Modify: `jobspy/model.py` (the `Site` enum, ~line 309)
- Modify: `jobspy/exception.py` (append)
- Modify: `jobspy/__init__.py` (imports, `DEFAULT_SITES` ~line 31, `SCRAPER_MAPPING` ~line 37)
- Create: `jobspy/jobstreet/__init__.py`, `jobspy/jobstreet/constant.py`

**Interfaces:**
- Consumes: `Scraper`, `ScraperInput`, `JobResponse`, `Site` from `jobspy.model`
- Produces: `class JobStreet(Scraper)`; `Site.JOBSTREET`; `JobStreetException`

- [ ] **Step 1: Write the failing test**

No new test file. The existing contract test already covers this the moment the board is registered. Confirm what currently passes so you can see it change:

```bash
poetry run pytest tests/test_scraper_contract.py -q
```

Expected now: `52 passed, 7 xfailed`.

- [ ] **Step 2: Add the Site member**

In `jobspy/model.py`, in `class Site(Enum)`:

```python
class Site(Enum):
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    ZIP_RECRUITER = "zip_recruiter"
    GLASSDOOR = "glassdoor"
    GOOGLE = "google"
    BAYT = "bayt"
    NAUKRI = "naukri"
    BDJOBS = "bdjobs"  # Add this line
    JOBSTREET = "jobstreet"
```

- [ ] **Step 3: Run the contract test to watch it fail**

```bash
poetry run pytest tests/test_scraper_contract.py::test_every_site_has_a_scraper -q
```

Expected: FAIL — `Site members with no SCRAPER_MAPPING entry: ['jobstreet']`. This is the guard doing its job.

- [ ] **Step 4: Add the exception class**

Append to `jobspy/exception.py`:

```python
class JobStreetException(Exception):
    def __init__(self, message=None):
        super().__init__(message or "An error occurred with JobStreet")
```

- [ ] **Step 5: Write the constants module**

Create `jobspy/jobstreet/constant.py`:

```python
"""Endpoints, headers and vocabulary maps for JobStreet Malaysia.

Values verified against the live board on 2026-09-23. See
docs/superpowers/specs/2026-09-23-jobstreet-my-scraper-design.md for how
they were measured.
"""

from __future__ import annotations

from jobspy.model import JobType

BASE_URL = "https://my.jobstreet.com"
SEARCH_URL = f"{BASE_URL}/api/jobsearch/v5/search"
GRAPHQL_URL = f"{BASE_URL}/graphql"

# JobStreet's own site identifiers, lifted from the requests its frontend
# makes. MY-Main is what routes the query to the Malaysian board.
SITE_KEY = "MY-Main"
SOURCE_SYSTEM = "houston"

# The API honours pageSize=100, which is five times fewer requests than the
# site's own default of 20 for the same data.
JOBS_PER_PAGE = 100

# Bounded because descriptions cost one request per job, unlike search which
# costs one per hundred.
DESCRIPTION_WORKERS = 5

headers = {
    "accept": "application/json",
    "accept-language": "en-MY,en;q=0.9",
    "content-type": "application/json",
}

# The board states work arrangement explicitly, which is better remote data
# than any other board in this fork provides.
REMOTE_ARRANGEMENT = "Remote"

# JobStreet's workTypes strings -> the shared JobType enum. A posting may
# carry more than one, so job_type is a list.
WORK_TYPE_MAP: dict[str, JobType] = {
    "Full time": JobType.FULL_TIME,
    "Part time": JobType.PART_TIME,
    "Contract/Temp": JobType.CONTRACT,
    "Casual/Vacation": JobType.TEMPORARY,
}

# The server-side `worktype` filter ids, confirmed by querying each one and
# checking the workTypes of what came back.
WORK_TYPE_IDS: dict[JobType, str] = {
    JobType.FULL_TIME: "242",
    JobType.PART_TIME: "243",
    JobType.CONTRACT: "244",
    JobType.TEMPORARY: "245",
}

# Minimal query: the board returns the full description body for it. Asking
# for less than the site's own frontend does keeps the payload small.
JOB_DETAILS_QUERY = """
query jobDetails($jobId: ID!) {
  jobDetails(id: $jobId) {
    job {
      title
      content(platform: WEB)
    }
  }
}
"""
```

- [ ] **Step 6: Write the minimal scraper class**

Create `jobspy/jobstreet/__init__.py`. Enough to satisfy the contract; `scrape` is filled in during Task 4.

```python
from __future__ import annotations

from jobspy.jobstreet.constant import JOBS_PER_PAGE, headers
from jobspy.model import JobResponse, Scraper, ScraperInput, Site
from jobspy.util import create_logger, create_session

log = create_logger("JobStreet")


class JobStreet(Scraper):
    """Scrapes JobStreet Malaysia through its public JSON search API.

    The board's HTML job pages return 403, but the JSON API its own
    frontend calls is open and does not fingerprint TLS - so this uses a
    plain requests session rather than tls-client.
    """

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            Site.JOBSTREET, proxies=proxies, ca_cert=ca_cert, user_agent=user_agent
        )
        self.session = create_session(
            proxies=self.proxies, ca_cert=ca_cert, is_tls=False, has_retry=True
        )
        self.session.headers.update(headers)
        if user_agent:
            self.session.headers["user-agent"] = user_agent
        self.scraper_input: ScraperInput | None = None
        self.jobs_per_page = JOBS_PER_PAGE
        self.seen_ids: set[str] = set()

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        raise NotImplementedError("filled in by Task 4")
```

Note `super().__init__` takes all three kwargs. That is the whole point of the contract check this board must pass.

- [ ] **Step 7: Register in the mapping and defaults**

In `jobspy/__init__.py`, add the import beside the others:

```python
from jobspy.indeed import Indeed
from jobspy.jobstreet import JobStreet
from jobspy.linkedin import LinkedIn
```

Add to `DEFAULT_SITES`:

```python
DEFAULT_SITES: list[Site] = [
    Site.INDEED,
    Site.LINKEDIN,
    Site.GOOGLE,
    Site.JOBSTREET,
]
```

Add to `SCRAPER_MAPPING`:

```python
    Site.BDJOBS: BDJobs,
    Site.JOBSTREET: JobStreet,
}
```

- [ ] **Step 8: Run the contract test to verify it passes**

```bash
poetry run pytest tests/test_scraper_contract.py -q
```

Expected: `59 passed, 7 xfailed` — seven more than before, and **still seven xfailed, not eight**. If you see eight, `user_agent` is not reaching `super().__init__`; fix that rather than adding `jobstreet` to `USER_AGENT_NOT_FORWARDED`.

- [ ] **Step 9: Run the whole suite**

```bash
poetry run pytest -q
```

Expected: all pass. `DEFAULT_SITES` changed, so watch for integration tests that assert on default board counts; if one fails, it is asserting on the old default and should be updated to include `jobstreet`.

- [ ] **Step 10: Commit**

```bash
poetry run black jobspy/jobstreet
git add jobspy/jobstreet jobspy/model.py jobspy/exception.py jobspy/__init__.py
git commit -m "feat: register JobStreet MY as a board

Site member, exception class, SCRAPER_MAPPING entry and DEFAULT_SITES.
scrape() is a stub; the contract test now covers the board."
```

---

## Task 2: Parse one search record into a JobPost

The core of the work. Pure functions over JSON, tested against real captured records.

**Files:**
- Create: `jobspy/jobstreet/util.py`
- Create: `tests/test_jobstreet_util.py`
- Read first: `tests/fixtures/jobstreet/README.md`

**Interfaces:**
- Consumes: `WORK_TYPE_MAP`, `REMOTE_ARRANGEMENT`, `BASE_URL` from `jobspy.jobstreet.constant`; `parse_myr_salary` from `jobspy.malaysia.salary`
- Produces:
  - `parse_job(record: dict) -> JobPost | None`
  - `parse_location(record: dict) -> Location`
  - `parse_job_types(record: dict) -> list[JobType] | None`
  - `parse_is_remote(record: dict) -> bool | None`
  - `parse_company_name(record: dict) -> str | None`
  - `parse_date_posted(record: dict) -> date | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_jobstreet_util.py`:

```python
"""Parser tests for JobStreet MY, against real captured responses.

The fixtures are trimmed live payloads - see tests/fixtures/jobstreet/README.md
for why each record is in there. Assertions quote the board's real strings,
non-breaking spaces and all.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from jobspy.jobstreet.util import parse_job
from jobspy.model import Country, JobType

FIXTURES = Path(__file__).parent / "fixtures" / "jobstreet"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def records() -> dict[str, dict]:
    """Search-page records keyed by board id, for addressing one at a time."""
    return {r["id"]: r for r in load("search_page.json")["data"]}


def test_parses_the_nominal_record(records):
    job = parse_job(records["94689504"])

    assert job.id == "js-94689504"
    assert job.title
    assert job.company_name
    assert job.job_url == "https://my.jobstreet.com/job/94689504"
    assert job.location.country == Country.MALAYSIA


def test_stamps_a_site_prefixed_id(records):
    """Exact dedup keys on this; an unprefixed id collides across boards."""
    for record in records.values():
        assert parse_job(record).id == f"js-{record['id']}"


def test_job_url_carries_no_tracking_query(records):
    """A tracking token in the URL would defeat URL-based dedup."""
    for record in records.values():
        assert "?" not in parse_job(record).job_url
```

- [ ] **Step 2: Run it to verify it fails**

```bash
poetry run pytest tests/test_jobstreet_util.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'jobspy.jobstreet.util'`.

- [ ] **Step 3: Write the parser**

Create `jobspy/jobstreet/util.py`:

```python
"""JobStreet MY response parsing.

Pure functions over the board's JSON. Everything here emits JobStreet's own
vocabulary - raw location strings, the board's salary label - and leaves
normalization to jobspy/malaysia/, which runs over every board at once.

The one deliberate exception is salary: the board hands us a formatted
string rather than numbers, so it is parsed here with the shared MYR parser.
That is reuse of a tested component, not board-specific logic.
"""

from __future__ import annotations

from datetime import date, datetime

from jobspy.jobstreet.constant import BASE_URL, REMOTE_ARRANGEMENT, WORK_TYPE_MAP
from jobspy.malaysia.salary import parse_myr_salary
from jobspy.model import Compensation, Country, JobPost, JobType, Location
from jobspy.util import create_logger

log = create_logger("JobStreet")


def parse_company_name(record: dict) -> str | None:
    """Falls back to the advertiser when companyName is absent.

    Private advertisers have no `companyName` key at all - only
    `advertiser.description`, which reads "Private Advertiser".
    """
    name = record.get("companyName")
    if name:
        return name
    return (record.get("advertiser") or {}).get("description") or None


def parse_location(record: dict) -> Location:
    """Splits the board's label into city and state, as-is.

    The label is a comma-separated string: "Kuala Lumpur" or
    "Bukit Bintang, Kuala Lumpur". The rightmost part is the state and the
    rest is the city. No spelling is corrected and no place is looked up
    here - the gazetteer in jobspy/malaysia/location.py does that for every
    board, and reports what it could not match.
    """
    locations = record.get("locations") or []
    label = (locations[0].get("label") if locations else None) or ""

    parts = [part.strip() for part in label.split(",") if part.strip()]
    if not parts:
        return Location(country=Country.MALAYSIA)
    if len(parts) == 1:
        return Location(country=Country.MALAYSIA, state=parts[0])
    # Three-part labels ("Bayan Lepas, Bayan Baru, Penang") keep the last
    # part as state and rejoin the rest as the city.
    return Location(
        country=Country.MALAYSIA,
        city=", ".join(parts[:-1]),
        state=parts[-1],
    )


def parse_job_types(record: dict) -> list[JobType] | None:
    """A posting may carry several work types, so this returns a list.

    Unknown strings are dropped rather than guessed at: a wrong job_type is
    worse than an absent one, because callers filter on it.
    """
    types = [
        WORK_TYPE_MAP[name]
        for name in (record.get("workTypes") or [])
        if name in WORK_TYPE_MAP
    ]
    return types or None


def parse_is_remote(record: dict) -> bool | None:
    """Reads the board's stated work arrangement.

    Returns None when the board says nothing, which is different from
    saying On-site - remote.py can still infer from the description later.
    """
    entries = (record.get("workArrangements") or {}).get("data") or []
    labels = [(entry.get("label") or {}).get("text") for entry in entries]
    labels = [label for label in labels if label]
    if not labels:
        return None
    return REMOTE_ARRANGEMENT in labels


def parse_date_posted(record: dict) -> date | None:
    raw = record.get("listingDate")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        log.warning(f"unparseable listingDate {raw!r}, leaving date_posted unset")
        return None


def parse_compensation(record: dict) -> Compensation | None:
    """Parses the board's salary label with the shared MYR parser.

    Returns None when the label is absent or unparseable. Roughly 6% of
    labels are advertiser junk typed with a dollar sign; leaving those
    unpriced is correct, because a guess would be indistinguishable from a
    real figure downstream.
    """
    return parse_myr_salary(record.get("salaryLabel"))


def parse_job(record: dict) -> JobPost | None:
    """Maps one search record onto a JobPost.

    Returns None only when the record has no id or no title - without those
    there is nothing usable. Every other field degrades to None on its own.
    """
    job_id = record.get("id")
    title = record.get("title")
    if not job_id or not title:
        log.warning(f"skipping record with no id or title: {record.get('id')!r}")
        return None

    classifications = record.get("classifications") or []
    job_function = None
    if classifications:
        job_function = (classifications[0].get("classification") or {}).get(
            "description"
        )

    return JobPost(
        # Site-prefixed so exact dedup can key on it without colliding with
        # another board that happens to reuse the number.
        id=f"js-{job_id}",
        title=title,
        company_name=parse_company_name(record),
        # Built from the id rather than taken from the response: the board's
        # own links carry per-request tracking tokens, which would make every
        # re-scrape look like a new job to URL-based dedup.
        job_url=f"{BASE_URL}/job/{job_id}",
        company_url=(record.get("employer") or {}).get("companyUrl"),
        location=parse_location(record),
        date_posted=parse_date_posted(record),
        job_type=parse_job_types(record),
        is_remote=parse_is_remote(record),
        compensation=parse_compensation(record),
        description=record.get("teaser") or None,
        company_logo=(record.get("branding") or {}).get("serpLogoUrl"),
        job_function=job_function,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
poetry run pytest tests/test_jobstreet_util.py -q
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
poetry run black jobspy/jobstreet tests/test_jobstreet_util.py
git add jobspy/jobstreet/util.py tests/test_jobstreet_util.py
git commit -m "feat: parse JobStreet search records into JobPost"
```

---

## Task 3: Cover every parser branch

Task 2 proved the happy path. This covers the branches the fixtures were chosen for — the ones real data actually hits.

**Files:**
- Modify: `tests/test_jobstreet_util.py` (append)

**Interfaces:**
- Consumes: everything Task 2 produced

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_jobstreet_util.py`:

```python
class TestSalary:
    def test_parses_a_range(self, records):
        """The board sends non-breaking spaces and en-dashes. Both must work."""
        job = parse_job(records["94689504"])
        assert job.compensation.min_amount == 5000
        assert job.compensation.max_amount == 7500
        assert job.compensation.interval.value == "monthly"

    def test_parses_a_single_value_as_both_bounds(self, records):
        job = parse_job(records["94333139"])
        assert job.compensation.min_amount == 1000
        assert job.compensation.max_amount == 1000

    def test_leaves_dollar_junk_unpriced(self, records):
        """'$5,000 - $7,000' is an advertiser typo, not a USD salary.

        Guessing it is MYR would be indistinguishable downstream from a
        figure the board actually vouched for.
        """
        assert parse_job(records["94553263"]).compensation is None

    def test_absent_label_yields_no_compensation(self, records):
        assert parse_job(records["94830903"]).compensation is None

    def test_does_not_mark_salary_as_description_parsed(self, records):
        """This is what makes salary_source come out as direct_data.

        jobspy/malaysia/__init__.py skips its own salary stage when
        compensation is already set, and frame.py then defaults the source
        to direct_data. Setting this flag here would mislabel the board's
        own figure as scraped from prose.
        """
        job = parse_job(records["94689504"])
        assert job.salary_parsed_from_description is False


class TestLocation:
    def test_bare_state(self, records):
        job = parse_job(records["94462128"])
        assert job.location.state == "Kuala Lumpur"
        assert job.location.city is None

    def test_suburb_and_state(self, records):
        job = parse_job(records["94831259"])
        assert job.location.city == "Bukit Bintang"
        assert job.location.state == "Kuala Lumpur"

    def test_always_stamps_malaysia(self, records):
        for record in records.values():
            assert parse_job(record).location.country == Country.MALAYSIA


class TestWorkTypeAndArrangement:
    def test_single_work_type(self, records):
        assert parse_job(records["94689504"]).job_type == [JobType.FULL_TIME]

    def test_multiple_work_types(self, records):
        """One posting can be tagged both - it appears under both filters."""
        types = parse_job(records["94586568"]).job_type
        assert set(types) == {JobType.TEMPORARY, JobType.FULL_TIME}

    def test_remote_is_true_only_for_remote(self, records):
        assert parse_job(records["94462128"]).is_remote is True
        assert parse_job(records["94234551"]).is_remote is False  # Hybrid
        assert parse_job(records["94689504"]).is_remote is False  # On-site


class TestCompanyName:
    def test_falls_back_to_advertiser(self, records):
        """94462128 has no companyName key at all - only an advertiser."""
        assert parse_job(records["94462128"]).company_name == "Private Advertiser"


class TestMalformedRecords:
    """Every case here is a shape the live API emits. None may raise."""

    @pytest.fixture(scope="class")
    def bad(self) -> dict[str, dict]:
        return {r["id"]: r for r in load("search_malformed.json")["data"]}

    def test_no_company_anywhere(self, bad):
        assert parse_job(bad["90000001"]).company_name is None

    def test_empty_locations_list(self, bad):
        job = parse_job(bad["90000002"])
        assert job.location.city is None and job.location.state is None
        assert job.location.country == Country.MALAYSIA

    def test_missing_locations_key(self, bad):
        assert parse_job(bad["90000003"]).location.state is None

    def test_null_company_and_unparseable_salary(self, bad):
        job = parse_job(bad["90000004"])
        assert job.company_name is None
        assert job.compensation is None
        assert job.job_type is None  # "Permanent" is not a known work type

    def test_unparseable_date_leaves_field_unset(self, bad):
        job = parse_job(bad["90000005"])
        assert job.date_posted is None
        assert job.title == "Bad Date"  # the job survives

    def test_three_part_location_label(self, bad):
        job = parse_job(bad["90000006"])
        assert job.location.state == "Penang"
        assert job.location.city == "Bayan Lepas, Bayan Baru"

    def test_record_without_id_is_skipped(self):
        assert parse_job({"title": "No Id"}) is None

    def test_record_without_title_is_skipped(self):
        assert parse_job({"id": "123"}) is None
```

- [ ] **Step 2: Run them**

```bash
poetry run pytest tests/test_jobstreet_util.py -q
```

Expected: all pass. If `test_multiple_work_types` fails, check `WORK_TYPE_MAP` spelling against the fixture — the board writes `"Part time"`, lowercase `t`, not `"Part Time"`.

- [ ] **Step 3: Commit**

```bash
poetry run black tests/test_jobstreet_util.py
git add tests/test_jobstreet_util.py
git commit -m "test: cover every JobStreet parser branch"
```

---

## Task 4: Search, page, and return a JobResponse

**Files:**
- Modify: `jobspy/jobstreet/__init__.py`
- Create: `tests/test_jobstreet_scraper.py`

**Interfaces:**
- Consumes: `parse_job` from `jobspy.jobstreet.util`; `SEARCH_URL`, `SITE_KEY`, `SOURCE_SYSTEM`, `JOBS_PER_PAGE`, `WORK_TYPE_IDS` from `jobspy.jobstreet.constant`
- Produces: `JobStreet.scrape(scraper_input) -> JobResponse`; `JobStreet._build_params(page: int) -> dict`

- [ ] **Step 1: Write the failing test**

Create `tests/test_jobstreet_scraper.py`:

```python
"""Paging and orchestration for the JobStreet scraper.

The session is stubbed - these test how the scraper drives the API, not how
the API behaves. Parsing is covered in test_jobstreet_util.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobspy.jobstreet import JobStreet
from jobspy.model import Country, JobType, ScraperInput, Site

FIXTURES = Path(__file__).parent / "fixtures" / "jobstreet"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload


class FakeSession:
    """Serves queued pages and records every call made."""

    def __init__(self, pages: list[dict]):
        self._pages = list(pages)
        self.calls: list[dict] = []
        self.headers: dict = {}

    def get(self, url, params=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "params": params})
        if not self._pages:
            return FakeResponse(load("search_empty.json"))
        return FakeResponse(self._pages.pop(0))

    def post(self, url, json=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "json": json})
        return FakeResponse(load("job_details.json"))


def make_scraper(pages: list[dict]) -> JobStreet:
    scraper = JobStreet()
    scraper.session = FakeSession(pages)
    return scraper


def an_input(**overrides) -> ScraperInput:
    params = {
        "site_type": [Site.JOBSTREET],
        "search_term": "software engineer",
        "location": "Kuala Lumpur",
        "country": Country.MALAYSIA,
        "results_wanted": 5,
    }
    params.update(overrides)
    return ScraperInput(**params)


def test_returns_jobs_from_one_page():
    scraper = make_scraper([load("search_page.json")])
    response = scraper.scrape(an_input(results_wanted=5))

    assert len(response.jobs) == 5
    assert all(job.id.startswith("js-") for job in response.jobs)


def test_stops_on_an_empty_page_instead_of_spinning():
    """An empty first page must terminate the loop, not page forever."""
    scraper = make_scraper([load("search_empty.json")])
    response = scraper.scrape(an_input(results_wanted=50))

    assert response.jobs == []
    assert len(scraper.session.calls) == 1


def test_stops_on_a_short_page():
    """A page shorter than pageSize is the last page."""
    scraper = make_scraper([load("search_last_page.json")])
    response = scraper.scrape(an_input(results_wanted=50))

    assert len(response.jobs) == 3
    assert len(scraper.session.calls) == 1


def test_does_not_return_the_same_job_twice():
    """The board can repeat a listing across pages; seen_ids absorbs that."""
    page = load("search_page.json")
    scraper = make_scraper([page, page])
    response = scraper.scrape(an_input(results_wanted=50))

    ids = [job.id for job in response.jobs]
    assert len(ids) == len(set(ids))


def test_applies_offset():
    full = load("search_page.json")
    first = make_scraper([full]).scrape(an_input(results_wanted=8)).jobs
    offset = make_scraper([full]).scrape(an_input(results_wanted=3, offset=2)).jobs

    assert [job.id for job in offset] == [job.id for job in first[2:5]]


class TestQueryParameters:
    def test_sends_the_board_identifiers_and_query(self):
        scraper = make_scraper([load("search_page.json")])
        scraper.scrape(an_input())
        params = scraper.session.calls[0]["params"]

        assert params["siteKey"] == "MY-Main"
        assert params["sourcesystem"] == "houston"
        assert params["keywords"] == "software engineer"
        assert params["where"] == "Kuala Lumpur"
        assert params["pageSize"] == 100

    def test_maps_hours_old_to_whole_days(self):
        """daterange is day-granular, so 30 hours must round up to 2."""
        scraper = make_scraper([load("search_page.json")])
        scraper.scrape(an_input(hours_old=30))

        assert scraper.session.calls[0]["params"]["daterange"] == 2

    def test_sorts_by_date_only_when_filtering_by_age(self):
        with_age = make_scraper([load("search_page.json")])
        with_age.scrape(an_input(hours_old=24))
        assert with_age.session.calls[0]["params"]["sortmode"] == "ListedDate"

        without = make_scraper([load("search_page.json")])
        without.scrape(an_input())
        assert "sortmode" not in without.session.calls[0]["params"]

    def test_maps_job_type_to_the_worktype_id(self):
        scraper = make_scraper([load("search_page.json")])
        scraper.scrape(an_input(job_type=JobType.CONTRACT))

        assert scraper.session.calls[0]["params"]["worktype"] == "244"

    def test_omits_filters_that_were_not_requested(self):
        scraper = make_scraper([load("search_page.json")])
        scraper.scrape(an_input())
        params = scraper.session.calls[0]["params"]

        assert "daterange" not in params
        assert "worktype" not in params
```

- [ ] **Step 2: Run to verify it fails**

```bash
poetry run pytest tests/test_jobstreet_scraper.py -q
```

Expected: FAIL — `NotImplementedError: filled in by Task 4`.

- [ ] **Step 3: Implement scrape and paging**

Replace the `scrape` stub in `jobspy/jobstreet/__init__.py`, and add these imports at the top:

```python
import math
import random
import time

from jobspy.jobstreet.constant import (
    JOBS_PER_PAGE,
    SEARCH_URL,
    SITE_KEY,
    SOURCE_SYSTEM,
    WORK_TYPE_IDS,
    headers,
)
from jobspy.jobstreet.util import parse_job
from jobspy.model import JobPost, JobResponse, Scraper, ScraperInput, Site
```

Then the methods:

```python
    def _build_params(self, page: int) -> dict:
        """Builds one search query.

        Filters the board has no parameter for are left out entirely rather
        than sent empty - an empty value is a filter, and would silently
        narrow the search.
        """
        params: dict = {
            "siteKey": SITE_KEY,
            "sourcesystem": SOURCE_SYSTEM,
            "page": page,
            "pageSize": self.jobs_per_page,
        }
        if self.scraper_input.search_term:
            params["keywords"] = self.scraper_input.search_term
        if self.scraper_input.location:
            params["where"] = self.scraper_input.location

        if self.scraper_input.hours_old:
            # daterange is whole days. Round up so the window is never
            # narrower than asked for, then filter exactly in _within_age.
            params["daterange"] = math.ceil(self.scraper_input.hours_old / 24)
            # Newest-first lets paging stop as soon as it crosses the cutoff.
            params["sortmode"] = "ListedDate"

        work_type_id = WORK_TYPE_IDS.get(self.scraper_input.job_type)
        if work_type_id:
            params["worktype"] = work_type_id

        return params

    def _within_age(self, job: JobPost) -> bool:
        """Applies the exact hours_old cutoff the day-granular filter cannot."""
        if not self.scraper_input.hours_old or job.date_posted is None:
            return True
        cutoff = date.today() - timedelta(
            days=math.ceil(self.scraper_input.hours_old / 24)
        )
        return job.date_posted >= cutoff

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        self.seen_ids = set()

        if scraper_input.country and scraper_input.country != Country.MALAYSIA:
            log.warning(
                f"JobStreet is a Malaysian board and always queries MY; "
                f"country={scraper_input.country.value[0]!r} is ignored. Note "
                f"the Malaysian normalization pipeline only runs when "
                f"country_indeed='malaysia'."
            )
        if scraper_input.distance:
            log.info("JobStreet has no radius filter; distance is ignored")

        wanted = scraper_input.results_wanted + scraper_input.offset
        jobs: list[JobPost] = []
        page = 1

        while len(jobs) < wanted:
            try:
                response = self.session.get(
                    SEARCH_URL,
                    params=self._build_params(page),
                    timeout=scraper_input.request_timeout,
                )
            except Exception as exc:  # noqa: BLE001 - one page must not kill the scrape
                log.error(f"search request failed on page {page}: {exc}")
                break

            if response.status_code == 403:
                # The board disallows this endpoint in robots.txt and sits
                # behind Cloudflare. Treat a 403 as a block, not a blip -
                # retrying into one is how an IP earns a permanent ban.
                log.error("403 from JobStreet; stopping and returning partial results")
                break
            if response.status_code != 200:
                log.error(f"JobStreet returned {response.status_code}; stopping")
                break

            records = (response.json() or {}).get("data") or []
            if not records:
                break

            for record in records:
                if record.get("id") in self.seen_ids:
                    continue
                self.seen_ids.add(record.get("id"))
                job = parse_job(record)
                if job is not None and self._within_age(job):
                    jobs.append(job)

            # A short page is the last page.
            if len(records) < self.jobs_per_page:
                break

            page += 1
            time.sleep(random.uniform(0.5, 1.5))

        if scraper_input.is_remote:
            jobs = [job for job in jobs if job.is_remote]

        start = scraper_input.offset
        return JobResponse(jobs=jobs[start : start + scraper_input.results_wanted])
```

Add `from datetime import date, timedelta` and `from jobspy.model import Country` to the imports.

- [ ] **Step 4: Run to verify it passes**

```bash
poetry run pytest tests/test_jobstreet_scraper.py -q
```

Expected: all pass.

- [ ] **Step 5: Run the whole suite**

```bash
poetry run pytest -q
```

- [ ] **Step 6: Commit**

```bash
poetry run black jobspy/jobstreet tests/test_jobstreet_scraper.py
git add jobspy/jobstreet/__init__.py tests/test_jobstreet_scraper.py
git commit -m "feat: page the JobStreet search API and return a JobResponse"
```

---

## Task 5: Fetch descriptions on request

**Files:**
- Modify: `jobspy/jobstreet/__init__.py`
- Modify: `tests/test_jobstreet_scraper.py` (append)

**Interfaces:**
- Consumes: `GRAPHQL_URL`, `JOB_DETAILS_QUERY`, `DESCRIPTION_WORKERS` from `jobspy.jobstreet.constant`
- Produces: `JobStreet._fetch_description(job_id: str) -> str | None`; a `fetch_description: bool = False` attribute set by `scrape_jobs`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_jobstreet_scraper.py`:

```python
class TestDescriptions:
    def test_teaser_is_used_when_descriptions_are_off(self):
        """The field is never empty: the teaser ships with the search result."""
        scraper = make_scraper([load("search_page.json")])
        jobs = scraper.scrape(an_input(results_wanted=1)).jobs

        assert jobs[0].description
        assert all(call["url"].endswith("/search") for call in scraper.session.calls)

    def test_no_graphql_calls_when_descriptions_are_off(self):
        scraper = make_scraper([load("search_page.json")])
        scraper.scrape(an_input(results_wanted=3))

        assert not [c for c in scraper.session.calls if c["url"].endswith("/graphql")]

    def test_fetches_and_converts_descriptions_when_on(self):
        scraper = make_scraper([load("search_page.json")])
        scraper.fetch_description = True
        jobs = scraper.scrape(an_input(results_wanted=2)).jobs

        graphql = [c for c in scraper.session.calls if c["url"].endswith("/graphql")]
        assert len(graphql) == 2
        assert graphql[0]["json"]["variables"]["jobId"] == jobs[0].id.removeprefix("js-")
        # markdown_converter ran: the fixture body is HTML, the output is not.
        assert "<p>" not in jobs[0].description

    def test_a_failed_description_leaves_the_teaser(self):
        """One bad description must not lose the job."""

        class Failing(FakeSession):
            def post(self, *args, **kwargs):
                raise RuntimeError("boom")

        scraper = JobStreet()
        scraper.session = Failing([load("search_page.json")])
        scraper.fetch_description = True
        jobs = scraper.scrape(an_input(results_wanted=1)).jobs

        assert len(jobs) == 1
        assert jobs[0].description  # the teaser survived
```

- [ ] **Step 2: Run to verify it fails**

```bash
poetry run pytest tests/test_jobstreet_scraper.py -k Descriptions -q
```

Expected: FAIL — `AttributeError` on `fetch_description`, or no GraphQL calls made.

- [ ] **Step 3: Implement description fetching**

In `__init__`, add:

```python
        self.fetch_description = False
```

Add the methods, and these imports (`ThreadPoolExecutor`, `markdown_converter`, `plain_converter`, `DescriptionFormat`, and the constants):

```python
    def _fetch_description(self, job_id: str) -> str | None:
        """Fetches one job's body from the board's GraphQL endpoint.

        Returns None on any failure. The caller keeps the search teaser in
        that case, so a flaky description never costs us the job.
        """
        try:
            response = self.session.post(
                GRAPHQL_URL,
                json={
                    "operationName": "jobDetails",
                    "variables": {"jobId": job_id},
                    "query": JOB_DETAILS_QUERY,
                },
                timeout=self.scraper_input.request_timeout,
            )
            payload = response.json() or {}
        except Exception as exc:  # noqa: BLE001 - one description is not the batch
            log.warning(f"description fetch failed for {job_id}: {exc}")
            return None

        job = ((payload.get("data") or {}).get("jobDetails") or {}).get("job") or {}
        content = job.get("content")
        if not content:
            return None

        # Matches the branch every other scraper uses: DescriptionFormat.HTML
        # falls through untouched, because the board already sends HTML.
        if self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
            return markdown_converter(content)
        elif self.scraper_input.description_format == DescriptionFormat.PLAIN:
            return plain_converter(content)
        return content

    def _add_descriptions(self, jobs: list[JobPost]) -> None:
        """Fills descriptions in place, bounded to a small pool.

        Search costs one request per hundred jobs; this costs one per job,
        so it is the only part of the scrape worth bounding.
        """
        def fill(job: JobPost) -> None:
            body = self._fetch_description(job.id.removeprefix("js-"))
            if body:
                job.description = body

        with ThreadPoolExecutor(max_workers=DESCRIPTION_WORKERS) as executor:
            list(executor.map(fill, jobs))
```

Call it in `scrape`, immediately before the final slice:

```python
        start = scraper_input.offset
        selected = jobs[start : start + scraper_input.results_wanted]
        if self.fetch_description:
            self._add_descriptions(selected)
        return JobResponse(jobs=selected)
```

Fetching after slicing is deliberate: descriptions are the expensive call, and there is no reason to buy them for jobs the caller will not receive.

- [ ] **Step 4: Run to verify it passes**

```bash
poetry run pytest tests/test_jobstreet_scraper.py -q
```

- [ ] **Step 5: Commit**

```bash
poetry run black jobspy/jobstreet tests/test_jobstreet_scraper.py
git add jobspy/jobstreet/__init__.py tests/test_jobstreet_scraper.py
git commit -m "feat: optional JobStreet description fetching via GraphQL"
```

---

## Task 6: Wire the flag through scrape_jobs

**Files:**
- Modify: `jobspy/__init__.py` (signature, and `scrape_site` ~line 131)
- Modify: `tests/test_scrape_jobs_integration.py` (append)

**Interfaces:**
- Consumes: `JobStreet.fetch_description`
- Produces: `scrape_jobs(..., jobstreet_fetch_description: bool = False)`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scrape_jobs_integration.py`:

```python
def test_jobstreet_fetch_description_reaches_the_scraper(monkeypatch):
    """The kwarg is board-specific, so it is set after construction."""
    seen = {}

    class FakeJobStreet(jobspy.JobStreet):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

        def scrape(self, scraper_input):
            seen["fetch_description"] = self.fetch_description
            return JobResponse(jobs=[])

    monkeypatch.setattr(jobspy, "JobStreet", FakeJobStreet, raising=False)

    jobspy.scrape_jobs(
        site_name=["jobstreet"],
        search_term="engineer",
        jobstreet_fetch_description=True,
    )
    assert seen["fetch_description"] is True


def test_jobstreet_fetch_description_defaults_to_false(monkeypatch):
    seen = {}

    class FakeJobStreet(jobspy.JobStreet):
        def scrape(self, scraper_input):
            seen["fetch_description"] = self.fetch_description
            return JobResponse(jobs=[])

    monkeypatch.setattr(jobspy, "JobStreet", FakeJobStreet, raising=False)

    jobspy.scrape_jobs(site_name=["jobstreet"], search_term="engineer")
    assert seen["fetch_description"] is False
```

- [ ] **Step 2: Run to verify it fails**

```bash
poetry run pytest tests/test_scrape_jobs_integration.py -k jobstreet -q
```

Expected: FAIL — `scrape_jobs` does not accept `jobstreet_fetch_description` (it lands in `**kwargs` and is ignored).

- [ ] **Step 3: Add the parameter**

In the `scrape_jobs` signature, beside the LinkedIn equivalent:

```python
    linkedin_fetch_description: bool | None = False,
    linkedin_company_ids: list[int] | None = None,
    jobstreet_fetch_description: bool = False,
```

Document it in the docstring:

```python
    :param jobstreet_fetch_description: fetch each JobStreet job's full
        description, at one extra request per job. Unlike LinkedIn, leaving
        this off costs little salary coverage - JobStreet supplies salary
        directly - so it mainly affects remote_scope and readability.
```

In `scrape_site`, after constructing the scraper:

```python
        scraper = scraper_class(proxies=proxies, ca_cert=ca_cert, user_agent=user_agent)
        # Board-specific and not part of ScraperInput, which every board
        # shares. Set by attribute so the shared contract stays unchanged.
        if isinstance(scraper, JobStreet):
            scraper.fetch_description = jobstreet_fetch_description
        scraped_data: JobResponse = scraper.scrape(site_input)
```

Note: `isinstance` works because `scrapers` resolves the class through `globals()`, so a monkeypatched subclass still matches.

- [ ] **Step 4: Run to verify it passes**

```bash
poetry run pytest tests/test_scrape_jobs_integration.py -q
```

- [ ] **Step 5: Run the whole suite**

```bash
poetry run pytest -q
```

- [ ] **Step 6: Commit**

```bash
poetry run black jobspy/__init__.py tests/test_scrape_jobs_integration.py
git add jobspy/__init__.py tests/test_scrape_jobs_integration.py
git commit -m "feat: expose jobstreet_fetch_description on scrape_jobs"
```

---

## Task 7: Prove the pipeline normalizes JobStreet output

The spec's central claim is that a new board inherits normalization for free. Test it rather than assert it.

**Files:**
- Create: `tests/test_jobstreet_pipeline.py`

**Interfaces:**
- Consumes: `parse_job`; `jobspy.malaysia.normalize`; `jobspy.frame.build_jobs_dataframe`

- [ ] **Step 1: Write the failing test**

```python
"""JobStreet output through the Malaysian pipeline and into the DataFrame.

The spec claims a new board inherits normalization at zero marginal cost.
These tests are what make that claim falsifiable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobspy.frame import build_jobs_dataframe
from jobspy.jobstreet.util import parse_job
from jobspy.malaysia import normalize
from jobspy.model import Country, JobResponse

FIXTURES = Path(__file__).parent / "fixtures" / "jobstreet"


@pytest.fixture(scope="module")
def jobs():
    records = json.loads(
        (FIXTURES / "search_page.json").read_text(encoding="utf-8")
    )["data"]
    return [job for job in (parse_job(r) for r in records) if job]


def test_normalize_accepts_jobstreet_jobs_without_wiring(jobs):
    normalized = normalize(list(jobs), group_duplicates=True)
    assert len(normalized) == len(jobs)


def test_board_salary_is_not_overwritten_by_the_description_parser(jobs):
    """The board's own figure must win, and must not be relabelled."""
    priced = [job for job in jobs if job.compensation is not None]
    assert priced, "fixture should contain salaried records"

    before = {job.id: job.compensation.min_amount for job in priced}
    for job in normalize(list(jobs)):
        if job.id in before:
            assert job.compensation.min_amount == before[job.id]
            assert job.salary_parsed_from_description is False


def test_remote_scope_is_assigned(jobs):
    for job in normalize(list(jobs)):
        assert job.remote_scope is not None


def test_rows_reach_the_dataframe_with_salary_marked_direct(jobs):
    normalized = normalize(list(jobs))
    df = build_jobs_dataframe(
        {"jobstreet": JobResponse(jobs=normalized)},
        country_enum=Country.MALAYSIA,
        enforce_annual_salary=False,
    )

    assert len(df) == len(normalized)
    assert set(df["site"]) == {"jobstreet"}

    priced = df[df["min_amount"].notna()]
    assert not priced.empty
    assert set(priced["salary_source"]) == {"direct_data"}


def test_state_survives_normalization(jobs):
    """Gazetteer misses null the state; KL must not be one of them."""
    normalized = normalize(list(jobs))
    states = {job.location.state for job in normalized if job.location}
    assert "Kuala Lumpur" in states
```

- [ ] **Step 2: Run it**

```bash
poetry run pytest tests/test_jobstreet_pipeline.py -q
```

Expected: pass. **If `test_state_survives_normalization` fails**, the gazetteer does not recognise a JobStreet spelling. That is an expected finding, not a bug in this task — add the missing entries to `jobspy/malaysia/location.py` (where every board benefits) and note them in the commit. Do not special-case anything inside `jobspy/jobstreet/`.

- [ ] **Step 3: Commit**

```bash
poetry run black tests/test_jobstreet_pipeline.py
git add tests/test_jobstreet_pipeline.py
git commit -m "test: JobStreet output through the Malaysian pipeline"
```

---

## Task 8: One live smoke test

The fork's first live test. Deselected by default; the only layer that catches the API changing.

**Files:**
- Create: `tests/test_jobstreet_live.py`

- [ ] **Step 1: Write it**

```python
"""Live smoke test against the real JobStreet board.

Deselected by default (pyproject sets addopts = "-m 'not live'"). Run with:

    poetry run pytest tests/test_jobstreet_live.py -m live -v

A fixture test passing means the parser handles a shape captured in the
past. This is what tells you the board still serves that shape today.
"""

from __future__ import annotations

import pytest

from jobspy import scrape_jobs

pytestmark = pytest.mark.live


def test_returns_real_kl_jobs_with_salary():
    df = scrape_jobs(
        site_name=["jobstreet"],
        search_term="software engineer",
        location="Kuala Lumpur",
        country_indeed="malaysia",
        results_wanted=20,
    )

    assert len(df) >= 10, "board returned suspiciously few results"
    assert df["title"].notna().all()
    assert set(df["site"]) == {"jobstreet"}

    # Roughly 70% of postings carried a salary label when measured on
    # 2026-09-23. A floor of 25% catches the label disappearing without
    # failing on normal variation between searches.
    fill = df["min_amount"].notna().mean()
    assert fill > 0.25, f"salary fill collapsed to {fill:.0%}"
    assert set(df[df["min_amount"].notna()]["salary_source"]) == {"direct_data"}

    assert df["state"].notna().mean() > 0.8, "location matching collapsed"


def test_descriptions_arrive_when_requested():
    df = scrape_jobs(
        site_name=["jobstreet"],
        search_term="software engineer",
        location="Kuala Lumpur",
        country_indeed="malaysia",
        results_wanted=3,
        jobstreet_fetch_description=True,
    )

    assert df["description"].notna().all()
    assert df["description"].str.len().min() > 200
```

- [ ] **Step 2: Confirm it is deselected by default**

```bash
poetry run pytest -q
```

Expected: the whole suite passes and says `deselected` for these two.

- [ ] **Step 3: Run it once against the live board**

```bash
poetry run pytest tests/test_jobstreet_live.py -m live -v
```

Expected: both pass. If salary fill is below the floor, do not lower the floor — check whether `salaryLabel` is still present in the raw response first.

- [ ] **Step 4: Commit**

```bash
poetry run black tests/test_jobstreet_live.py
git add tests/test_jobstreet_live.py
git commit -m "test: live smoke test for JobStreet MY"
```

---

## Task 9: Measure, then document

Parent decision 2 — the numbers decide whether this helped, not intuition.

**Files:**
- Modify: `CLAUDE.md`, `README.md`
- Create: `docs/baseline/2026-09-23-baseline-jobstreet.md` (written by the runner)

- [ ] **Step 1: Run the baseline**

```bash
poetry run python -m jobspy.baseline.runner
```

- [ ] **Step 2: Compare against the last run**

Diff against the newest existing report in `docs/baseline/`. Record, specifically:
- **Salary fill rate** — expected to rise substantially; the recorded direct-data rate was 0%
- **Location match rate**, plus the top unmatched strings. JobStreet's suburb labels are new vocabulary; misses are expected
- **Duplicate rate** and `dedup_group` behaviour with a third board present
- **Normalizer failure counts** — these must not rise

- [ ] **Step 3: Add any gazetteer entries the report reveals**

Unmatched locations are logged at INFO as `unmatched locations - add to the gazetteer: ...`. Add them to `jobspy/malaysia/location.py`, with tests in `tests/malaysia/`. Not to the scraper.

- [ ] **Step 4: Update README.md**

Tick the roadmap item:

```markdown
- [x] **JobStreet Malaysia** (`my.jobstreet.com`) — the dominant MY board, highest priority
```

Add `jobstreet` to the `site_name` list in the parameters block, and amend the salary caveat, which currently says MY salary is description-parsed only — no longer true:

```markdown
**Salary parsing.** Indeed Malaysia and LinkedIn return no structured salary
data in practice (measured fill: 0%), so for those boards salary is parsed
out of the description text. **JobStreet is the exception** — it publishes a
salary label on roughly 70% of postings, which is used directly and marked
`salary_source="direct_data"`.
```

- [ ] **Step 5: Update CLAUDE.md**

- Add JobStreet to the board list in **Project**, and note it is a primary MY target
- In **Gotchas**, record that JobStreet is the only board supplying structured MY salary
- Note that `jobstreet_fetch_description` costs one request per job but, unlike LinkedIn's, is not needed for salary coverage
- Add the robots.txt and 403-means-stop posture, so the next person does not "fix" it by retrying

- [ ] **Step 6: Run everything one last time**

```bash
poetry run pytest -q
poetry run pytest tests/test_scraper_contract.py -q
```

Expected: all pass; still **7 xfailed**, not 8.

- [ ] **Step 7: Commit**

```bash
git add README.md CLAUDE.md docs/baseline/ jobspy/malaysia/location.py tests/malaysia/
git commit -m "docs: record the JobStreet baseline and document the board"
```

---

## Self-Review

**Spec coverage.** Every spec section maps to a task: decisions 1/2/7 → Task 1 and 4; decision 3 → Tasks 5 and 6; decision 4 → Task 2 with pipeline proof in Task 7; decisions 5/6 → Tasks 2 and 3; decision 8 → Task 4's 403 handling and inter-page sleep; decision 9 → the committed fixtures plus Tasks 2, 3, 4; decision 10 → Task 1. The field mapping table is implemented in Task 2 and asserted in Task 3. Query construction is Task 4. Testing is Tasks 3, 4, 7, 8. Measurement is Task 9.

**Known gaps, deliberate.** `bulletPoints`, `solMetadata` and `tracking` are dropped per the spec's mapping table, and Task 2's `job_url` construction plus Task 3's `test_job_url_carries_no_tracking_query` are what enforce the tracking exclusion.

**Type consistency.** `parse_job` returns `JobPost | None` throughout. `fetch_description` is the attribute everywhere; `jobstreet_fetch_description` is only the `scrape_jobs` kwarg. `WORK_TYPE_MAP` is name→`JobType`; `WORK_TYPE_IDS` is `JobType`→id string. `seen_ids` holds raw board ids, while `JobPost.id` carries the `js-` prefix — `_fetch_description` strips it with `removeprefix`.
