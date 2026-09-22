from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

from rapidfuzz import fuzz

from jobspy.model import JobPost

_COMPANY_SUFFIXES = (
    "sdn bhd",
    "sdn. bhd.",
    "bhd",
    "berhad",
    "pte ltd",
    "pte. ltd.",
    "pvt ltd",
    "ltd",
    "llc",
    "inc",
    "plc",
    "gmbh",
    "co",
)

# Words that mark a rank rather than a role. Two titles carrying different
# markers are different jobs and must never share a group - this is checked
# before similarity scoring, because set-based similarity gets it backwards:
# token_set_ratio("senior software engineer", "software engineer") == 100.
_SENIORITY_MARKERS = (
    "intern",
    "internship",
    "trainee",
    "graduate",
    "junior",
    "jr",
    "senior",
    "snr",
    "sr",
    "lead",
    "principal",
    "staff",
    "head",
    "manager",
    "director",
    "vp",
    "chief",
)

# Roman-numeral level suffixes, e.g. "Software Engineer II". Only up to "v" -
# beyond that, plain titles essentially never use roman numerals and the
# token risks colliding with an ordinary word.
_ROMAN_LEVELS = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5}

# Letter-number level/track codes, e.g. "L3", "P5", "T5". Kept in their own
# namespace rather than folded into the bare-digit level, because the
# letter usually denotes a distinct job ladder or track, not the same
# level spelled differently - see _level_marker.
_LEVEL_CODE_RE = re.compile(r"^[a-z]\d{1,2}$")


def normalize_company(name: str | None) -> str:
    """Strips corporate suffixes and country tags so one company forms one block."""
    if not name:
        return ""

    lowered = name.lower()
    # "(M)" is a common Malaysian-subsidiary marker, e.g. "Conspec Builders
    # (M) Sdn Bhd". Drop it before punctuation stripping turns it into a
    # stray "m" token that would otherwise survive suffix removal.
    lowered = re.sub(r"\(\s*m\s*\)", " ", lowered)
    text = re.sub(r"[^a-z0-9 ]+", " ", lowered)
    text = re.sub(r"\s+", " ", text).strip()

    changed = True
    while changed:
        changed = False
        for suffix in _COMPANY_SUFFIXES:
            if text.endswith(" " + suffix) or text == suffix:
                text = text[: -len(suffix)].strip()
                changed = True
        if text.endswith(" malaysia"):
            text = text[: -len(" malaysia")].strip()
            changed = True

    return text


def _level_marker(tokens: list[str]) -> str | None:
    """Returns a normalized trailing level marker, or None if the title has
    no trailing level designator.

    Anchored on the LAST token only - a level word appearing mid-title
    (e.g. "Business Intelligence I") is a genuine trailing level and is
    meant to fire; a bare "v" or "i" appearing earlier in a title is not a
    level and must not fire. Anchoring on position, rather than scanning
    every token, gets both right without special-casing.

    "II" and "2" normalize to the same "level:2" marker: these are the same
    real-world convention written two ways (e.g. "Software Engineer II" on
    one board, "Software Engineer 2" on another for the same posting), and
    conflating them lets that posting still group across boards. A
    letter-number code like "L3" is kept in its own "code:" bucket instead,
    since the letter usually denotes a separate job track/ladder rather
    than the same level spelled differently - conflating those risks a
    false merge. Being overcautious here (an extra "code:" bucket, or a
    level distinction that turns out not to matter) only costs a missed
    group, never a wrong one.
    """
    if not tokens:
        return None

    last = tokens[-1]
    if last in _ROMAN_LEVELS:
        return f"level:{_ROMAN_LEVELS[last]}"
    if last.isdigit():
        return f"level:{int(last)}"
    if _LEVEL_CODE_RE.match(last):
        return f"code:{last}"
    return None


def seniority_markers(title: str | None) -> frozenset[str]:
    """Returns the rank words and trailing level designator present in a
    title. Two titles differing only by rank word or level (e.g. "Senior
    Software Engineer" vs "Software Engineer", or "Software Engineer II"
    vs "Software Engineer I") must never share a group - see
    _level_marker and the module-level note on _SENIORITY_MARKERS.
    """
    if not title:
        return frozenset()

    tokens = re.findall(r"[a-z0-9]+", title.lower())
    markers = {marker for marker in _SENIORITY_MARKERS if marker in tokens}

    level = _level_marker(tokens)
    if level is not None:
        markers.add(level)

    return frozenset(markers)


def _normalize_title(title: str | None) -> str:
    if not title:
        return ""
    text = re.sub(r"[^a-z0-9 ]+", " ", title.lower())
    return re.sub(r"\s+", " ", text).strip()


def _canonical_url(url: str | None) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _completeness(job: JobPost) -> int:
    """Higher is richer. Used to pick a winner among exact duplicates."""
    score = 0
    if job.description:
        score += 2
    if job.compensation:
        score += 2
    if job.date_posted:
        score += 1
    if job.job_url_direct:
        score += 1
    return score


def dedupe_exact(jobs: list[JobPost]) -> list[JobPost]:
    """Removes listings that are literally the same posting seen twice.

    This is the only destructive step in the pipeline. It exists because the
    location and remote query passes overlap heavily.
    """
    best: dict[str, JobPost] = {}
    order: list[str] = []

    for job in jobs:
        # Never fall back to a shared constant - a batch of jobs with no url
        # and no id would otherwise collapse into a single row.
        key = (
            _canonical_url(job.job_url)
            or (f"id:{job.id}" if job.id else "")
            or f"obj:{id(job)}"
        )
        if key not in best:
            best[key] = job
            order.append(key)
        elif _completeness(job) > _completeness(best[key]):
            best[key] = job

    return [best[key] for key in order]


def _state_of(job: JobPost) -> str | None:
    if job.location is None:
        return None
    return job.location.state


def _compatible_location(left: JobPost, right: JobPost) -> bool:
    left_state, right_state = _state_of(left), _state_of(right)
    if left.is_remote or right.is_remote:
        return True
    if left_state is None or right_state is None:
        return False
    return left_state == right_state


def _location_key(job: JobPost) -> str | None:
    """Returns the location bucket for the group hash, or None when the job's
    location is unresolved.

    An unresolved, non-remote job (state=None - see Task 7's
    normalize_location) must never share a hashed group with another job on
    this basis, even a fellow unresolved one: the hash is keyed on this
    value, so if it fell back to a shared placeholder, two unrelated jobs
    that both have unknown locations would collide onto the same
    dedup_group. That would be the same "both unknown is not evidence of
    same place" mistake _compatible_location already guards against, just
    committed at hash-construction time instead of comparison time. Callers
    that get None back must stamp the job with a per-row fallback id
    instead (see _fallback_group_id), not leave dedup_group unset.
    """
    if job.is_remote:
        return "remote"
    return _state_of(job)


def _group_id(company: str, title: str, location_key: str) -> str:
    canonical = f"{company}|{title}|{location_key}"
    return hashlib.blake2s(canonical.encode("utf-8"), digest_size=6).hexdigest()


def _fallback_group_id(job: JobPost) -> str:
    """Per-row id for a job whose company or location cannot be resolved
    into a canonical identity.

    dedup_group's contract is uniform across every row: every job always
    carries an id, and "is this row a duplicate?" is answered by group
    size, never by a None sentinel. A shared None would compare equal
    under == to any consumer that doesn't specifically route through
    pandas.groupby(dropna=True) - indistinguishable from an actual match.

    Derived from the same canonical-url normalization dedupe_exact uses, so
    the same listing scraped again tomorrow gets the same id. Two different
    unresolved listings get different ids - "unresolved" is not evidence
    they are the same posting.
    """
    key = _canonical_url(job.job_url) or (job.id or "")
    return hashlib.blake2s(
        f"unresolved|{key}".encode("utf-8"), digest_size=6
    ).hexdigest()


def assign_groups(jobs: list[JobPost], *, threshold: int = 90) -> list[JobPost]:
    """Stamps every job whose identity resolves with a dedup_group id, shared
    by any other job judged to be the same posting.

    Non-destructive: every input job is returned, whether or not it shares a
    group with anything else. Tuned conservative - a missed group costs one
    duplicate row, a wrong group asserts that two distinct openings are the
    same job. Every job always receives a dedup_group: one with an
    unresolved company or an unresolved, non-remote location gets a
    per-row fallback id (see _fallback_group_id) rather than being left at
    None, so the field's contract - "duplicate-ness is answered by group
    size" - holds uniformly for every row.
    """
    blocks: dict[str, list[JobPost]] = {}
    for job in jobs:
        blocks.setdefault(normalize_company(job.company_name), []).append(job)

    for company, members in blocks.items():
        if not company:
            for job in members:
                job.dedup_group = _fallback_group_id(job)
            continue

        clusters: list[list[JobPost]] = []
        for job in sorted(
            members, key=lambda j: (_normalize_title(j.title), j.job_url or "")
        ):
            title = _normalize_title(job.title)
            markers = seniority_markers(job.title)

            placed = False
            for cluster in clusters:
                leader = cluster[0]
                if markers != seniority_markers(leader.title):
                    continue
                if not _compatible_location(job, leader):
                    continue
                if (
                    fuzz.token_sort_ratio(title, _normalize_title(leader.title))
                    >= threshold
                ):
                    cluster.append(job)
                    placed = True
                    break
            if not placed:
                clusters.append([job])

        for cluster in clusters:
            leader = cluster[0]
            location_key = _location_key(leader)
            if location_key is None:
                # Unresolved location: _compatible_location guarantees such
                # a cluster is always a singleton (it never accepts a
                # second member), so give this one job its own stable
                # fallback id rather than a shared group hash - there is no
                # canonical (company, title, state) triple to hash, and no
                # evidence any other row is the same posting.
                for job in cluster:
                    job.dedup_group = _fallback_group_id(job)
                continue
            group = _group_id(company, _normalize_title(leader.title), location_key)
            for job in cluster:
                job.dedup_group = group

    return jobs
