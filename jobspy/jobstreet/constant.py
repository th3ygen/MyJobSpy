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
