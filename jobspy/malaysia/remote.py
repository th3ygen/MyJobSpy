from __future__ import annotations

import re

from jobspy.model import Country, JobPost

# Checked in order. An explicit exclusion must beat a generic remote claim,
# so other_country is evaluated before everything else.
_OTHER_COUNTRY_PATTERNS = (
    r"\bus work authoriz",
    r"\bauthoriz\w* to work in the (?:us|united states|uk|eu)\b",
    r"\bmust (?:be|reside) (?:located |based )?in the (?:us|usa|united states|uk)\b",
    r"\bus[- ]only\b",
    r"\bus[- ]based only\b",
    # Unambiguous US timezone abbreviations only. "est" is excluded deliberately:
    # it collides with "est." (established), and "cst" with other common usages.
    # A missed US-timezone hint costs far less than a false exclusion, because
    # this field sorts rather than filters.
    r"\b(?:pst|pdt|edt|cdt)\b",
    r"\b(?:eastern|pacific|central|mountain)\s+(?:standard\s+|daylight\s+)?time\b",
)

_MY_PATTERNS = (
    r"\bmalaysia\b",
    r"\bmalaysian\b",
    r"\bkuala lumpur\b",
    r"\bmyt\b",
)

_APAC_PATTERNS = (
    r"\bapac\b",
    r"\basia[- ]pacific\b",
    r"\bsoutheast asia\b",
    r"\bsea region\b",
    r"\bsingapore\b",
    r"\bgmt\+8\b",
)

_GLOBAL_PATTERNS = (
    r"\banywhere in the world\b",
    r"\bwork from anywhere\b",
    r"\bfully distributed\b",
    r"\bglobally remote\b",
    r"\bworldwide\b",
)


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def classify_remote_scope(job: JobPost) -> str | None:
    """Tags where a remote job can plausibly be worked from.

    Returns None for non-remote jobs. 'unknown' is expected to dominate -
    most postings never state eligibility. This is a sorting aid, never a
    filter: callers must not drop rows based on it.
    """
    if not job.is_remote:
        return None

    haystack_parts = [job.description or "", job.title or ""]
    if job.location is not None:
        haystack_parts.append(job.location.city or "")
        haystack_parts.append(job.location.state or "")
        if isinstance(job.location.country, str):
            haystack_parts.append(job.location.country)
        elif job.location.country is Country.MALAYSIA:
            haystack_parts.append("malaysia")

    text = re.sub(r"\s+", " ", " ".join(haystack_parts).lower())
    if not text.strip():
        return "unknown"

    if _matches(text, _OTHER_COUNTRY_PATTERNS):
        return "other_country"
    if _matches(text, _MY_PATTERNS):
        return "my"
    if _matches(text, _APAC_PATTERNS):
        return "apac"
    if _matches(text, _GLOBAL_PATTERNS):
        return "global"
    return "unknown"
