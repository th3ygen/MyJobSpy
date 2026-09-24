"""Hiredly response parsing.

Pure functions over one `jobListsSearchResults` node. Everything here emits
Hiredly's own vocabulary - its region names, its free-text location - and
leaves normalization to jobspy/malaysia/, which runs over every board at once.

The one deliberate exception is salary: the board hands us a bare figure
("5000 - 7000") rather than structured numbers, so it is parsed here with the
shared MYR parser. That is reuse of a tested component, not board-specific
logic.
"""

from __future__ import annotations

from datetime import datetime

from jobspy.hiredly.constant import BASE_URL, JOB_TYPE_MAP, REMOTE_REGION
from jobspy.malaysia.salary import parse_myr_salary
from jobspy.model import (
    Compensation,
    Country,
    DescriptionFormat,
    JobPost,
    JobType,
    Location,
)
from jobspy.util import create_logger, markdown_converter, plain_converter

log = create_logger("Hiredly")


def parse_company_name(record: dict) -> str | None:
    """Falls back to `aggregatedCompanyName` when there is no company object."""
    name = (record.get("company") or {}).get("name")
    return name or record.get("aggregatedCompanyName") or None


def parse_location(record: dict) -> Location:
    """The free-text location as city, the region as state - both as-is.

    `location` is whatever the employer typed, often a full street address,
    and is kept whole. `stateRegion` is the board's own state vocabulary
    ("Penang", "Malacca"); the gazetteer resolves it. The board's "Remote"
    region is not a place, so it never reaches `state` - parse_is_remote
    reads it instead.
    """
    region = record.get("stateRegion") or None
    return Location(
        country=Country.MALAYSIA,
        city=record.get("location") or None,
        state=None if region == REMOTE_REGION else region,
    )


def parse_is_remote(record: dict) -> bool | None:
    """Reads the board's two remote signals.

    Returns None when the board says nothing, which is different from it
    saying the role is not remote - remote.py can still infer from the
    description later.
    """
    if record.get("stateRegion") == REMOTE_REGION:
        return True
    preference = (record.get("globalHirePreferences") or {}).get(
        "workingArrangementRemote"
    )
    if preference is True:
        return True
    if preference is False:
        return False
    return None


def parse_job_types(record: dict) -> list[JobType] | None:
    """Unknown strings are dropped rather than guessed at: a wrong job_type is
    worse than an absent one, because callers filter on it."""
    job_type = JOB_TYPE_MAP.get(record.get("jobType"))
    return [job_type] if job_type else None


def parse_active_at(record: dict) -> datetime | None:
    """The full timestamp, offset included.

    Kept separate from `date_posted` (a date) because hours_old filters on
    it - truncating to a date first is what made JobStreet's age filter
    day-granular.
    """
    raw = record.get("activeAt")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        log.warning(f"unparseable activeAt {raw!r}, leaving date_posted unset")
        return None


def parse_compensation(record: dict) -> Compensation | None:
    """Rewrites the bare figure into a sentence the shared MYR parser reads.

    The board shows these as monthly ringgit, so "5000 - 7000" becomes
    "RM 5000 - 7000 per month". Routing through parse_myr_salary rather than
    splitting the numbers here keeps its sanity bands, which reject
    advertiser typos like "1700 - 5002500". "Undisclosed" and anything else
    without a figure parses to None.
    """
    salary = (record.get("salary") or "").strip()
    if not salary or salary.lower() == "undisclosed":
        return None
    return parse_myr_salary(f"RM {salary} per month", board_supplied=True)


def parse_description(
    record: dict, description_format: DescriptionFormat | None
) -> str | None:
    """Joins the description and requirements, then converts once."""
    parts = []
    if record.get("description"):
        parts.append(record["description"])
    if record.get("requirements"):
        parts.append(f"<h3>Requirements</h3>{record['requirements']}")
    if not parts:
        return None
    html = "".join(parts)
    if description_format == DescriptionFormat.HTML:
        return html
    if description_format == DescriptionFormat.PLAIN:
        return plain_converter(html)
    return markdown_converter(html)


def parse_experience_range(record: dict) -> str | None:
    """The board uses -1 to mean "no experience needed"; read it as 0."""
    low = record.get("minYearsExperience")
    high = record.get("maxYearsExperience")
    if low is None and high is None:
        return None
    low = max(low or 0, 0)
    high = max(high or 0, 0)
    if low >= high:
        return f"{low} years"
    return f"{low}-{high} years"


def _absolute_url(url: str | None) -> str | None:
    """Logos come protocol-relative ("//host/path")."""
    if not url:
        return None
    return f"https:{url}" if url.startswith("//") else url


def parse_job(
    record: dict,
    description_format: DescriptionFormat | None = DescriptionFormat.MARKDOWN,
) -> JobPost | None:
    """Maps one search node onto a JobPost.

    Returns None only when the node has no id or no title - without those
    there is nothing usable. Every other field degrades to None on its own.
    """
    job_id = record.get("id")
    title = (record.get("title") or "").strip()
    if not job_id or not title:
        log.warning(f"skipping record with no id or title: {job_id!r}")
        return None

    active_at = parse_active_at(record)
    skills = [
        skill["name"]
        for skill in (record.get("skills") or [])
        if isinstance(skill, dict) and skill.get("name")
    ]

    return JobPost(
        # Site-prefixed so exact dedup can key on it without colliding with
        # another board that happens to reuse the id.
        id=f"hd-{job_id}",
        title=title,
        company_name=parse_company_name(record),
        job_url=f"{BASE_URL}/jobs/{record.get('slug') or job_id}",
        # Aggregated listings point at the employer's own careers page.
        job_url_direct=record.get("externalJobUrl") or None,
        location=parse_location(record),
        date_posted=active_at.date() if active_at else None,
        job_type=parse_job_types(record),
        is_remote=parse_is_remote(record),
        compensation=parse_compensation(record),
        description=parse_description(record, description_format),
        company_logo=_absolute_url((record.get("company") or {}).get("logo")),
        job_level=record.get("careerLevel") or None,
        skills=skills or None,
        experience_range=parse_experience_range(record),
    )
