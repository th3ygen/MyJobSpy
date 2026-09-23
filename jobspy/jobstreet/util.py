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
