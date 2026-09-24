"""Endpoint, headers, query and vocabulary maps for Hiredly Malaysia.

Values verified against the live board on 2026-09-24. See
docs/superpowers/specs/2026-09-24-hiredly-scraper-design.md for how they were
measured.
"""

from __future__ import annotations

from jobspy.malaysia.location import MalaysianState
from jobspy.model import JobType

BASE_URL = "https://my.hiredly.com"
# The API host the site's own frontend calls (its JS bundle's `baseURL`).
GRAPHQL_URL = "https://my-api.hiredly.com/api/job_seeker/v1/graphql"

# The board accepts first: 500 and returned a whole 386-result search in one
# call. 100 matches JobStreet and keeps any single response modest.
JOBS_PER_PAGE = 100

# Bounds a search whose client-side filters (is_remote, hours_old, job_type)
# discard most of every page, so it cannot walk the whole board.
MAX_FILTERED_PAGES = 20

headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "origin": BASE_URL,
    "referer": f"{BASE_URL}/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}

# Every node field the parser reads, and nothing else. `globalHirePreferences`
# and `skills` are JSON scalars on this schema - selecting sub-fields on them
# is a GraphQL error, so they are requested whole.
NODE_FIELDS = """
    id
    title
    slug
    salary
    stateRegion
    location
    jobType
    activeAt
    category
    externalJobUrl
    aggregatedCompanyName
    description
    requirements
    careerLevel
    minYearsExperience
    maxYearsExperience
    globalHirePreferences
    skills
    company { name logo }
"""

# Arguments are variables rather than string-interpolated as the site's own
# frontend does, so a search term can never break out of the query.
SEARCH_QUERY = (
    """
query Search($keyword: String, $stateRegions: [String!], $first: Int, $after: String) {
  jobListsSearchResults(
    keyword: $keyword
    stateRegions: $stateRegions
    expectedSalary: 0
    first: $first
    after: $after
    showScraped: true
  ) {
    totalCount
    pageInfo { hasNextPage endCursor }
    nodes { %s }
  }
}
"""
    % NODE_FIELDS
)

JOB_TYPE_MAP: dict[str, JobType] = {
    "Full-Time": JobType.FULL_TIME,
    "Part-Time": JobType.PART_TIME,
    "Contract": JobType.CONTRACT,
    "Internship": JobType.INTERNSHIP,
}

# The `stateRegion` value that means "not in a place". Treated as a remote
# signal, never as a state.
REMOTE_REGION = "Remote"

# Hiredly's name for each state, from the location list its own pages carry
# (`cmsLocations`). Only two differ from the canonical names.
STATE_REGION_NAMES: dict[MalaysianState, str] = {
    state: state.value for state in MalaysianState
} | {
    MalaysianState.PULAU_PINANG: "Penang",
    MalaysianState.MELAKA: "Malacca",
}

# The only `stateRegion` values kept. An allowlist, not a blocklist of
# "Singapore"/"Overseas": Singapore postings carry Singapore's own regions
# ("North-East", ...), so a blocklist on the board's filter names lets them
# straight through.
MALAYSIAN_REGIONS = frozenset(STATE_REGION_NAMES.values()) | {REMOTE_REGION}
