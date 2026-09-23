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

# Paging continues past a page whose raw record count is a full page even
# when `is_remote` filters most or all of it out, because the loop counts
# post-filter matches (see the scrape loop). Without a ceiling, a search for
# is_remote=True with too few matching postings to ever reach
# results_wanted would page all the way to the board's own result cap
# (README: "~1000 jobs per search", i.e. ~10 pages at JOBS_PER_PAGE=100)
# instead of giving up once further paging is clearly not paying off.
MAX_REMOTE_PAGES = 20

headers = {
    "accept": "application/json",
    "accept-language": "en-MY,en;q=0.9",
    "content-type": "application/json",
    # A browser UA, matching every sibling scraper's convention. Sent to a
    # Cloudflare-fronted endpoint; python-requests' default UA is a plausible
    # contributor to the 403s this board is known to return under load.
    # JobStreet.__init__ overrides this with the caller-supplied user_agent
    # when one is given.
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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
