from __future__ import annotations

import re

from jobspy.malaysia.language import detect_interval
from jobspy.model import Compensation, CompensationInterval

# Sanity bands from the design spec. These filter nonsense; they are not
# claims about Malaysian pay policy. The monthly floor sits below the
# statutory minimum wage (RM1,700/month as of 2025) on purpose, to allow
# part-time and internship rates through.
#
# These bands apply ONLY when the interval was *inferred* (no interval word
# was found in the text, so we defaulted to "monthly"). When the interval is
# stated explicitly ("per month", "sejam", ...), there is nothing to infer
# and therefore nothing for a tight band to protect against: a posting that
# literally says "RM800.00 per month" is not a mislabeled hourly rate, it is
# a real (if low) monthly wage, and rejecting it would silently discard
# genuine salary data pulled from real Indeed Malaysia listings (Ruling
# F15). Do not collapse this into a single band - the two cases are guarding
# against different failure modes.
_BANDS: dict[str, tuple[float, float]] = {
    "hourly": (8, 150),
    "daily": (30, 1_000),
    "weekly": (200, 8_000),
    "monthly": (1_000, 30_000),
    "yearly": (20_000, 500_000),
}

# Ceiling used only when the interval is explicit in the text - see the
# comment on _BANDS above for why explicit intervals skip the tight band.
# There is no floor beyond "greater than zero" in that case.
_ABSURDITY_CEILING = 10_000_000

# Requires at least one comma group ("+", not "*") so that a plain,
# non-comma-formatted number such as "3000" is never partially matched by
# \d{1,3} and truncated to "300" with the trailing digit dropped. Numbers
# without comma grouping fall through to the second alternative instead,
# which greedily consumes every digit. (Real example that exposed this:
# "* Basic Salary: **RM 3000**" from a live Indeed Malaysia listing.)
_AMOUNT = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*([kK])?"
_SEPARATOR = r"\s*(?:-|–|—|to|hingga|sehingga|until)\s*"

# RM3,000 - RM5,000  /  MYR 3000-5000
_PREFIXED_RANGE = re.compile(
    rf"(?:RM|MYR)\s*{_AMOUNT}{_SEPARATOR}(?:RM|MYR)?\s*{_AMOUNT}", re.IGNORECASE
)
# 3,000 - 5,000 MYR
_SUFFIXED_RANGE = re.compile(
    rf"{_AMOUNT}{_SEPARATOR}{_AMOUNT}\s*(?:RM|MYR)", re.IGNORECASE
)
_PREFIXED_SINGLE = re.compile(rf"(?:RM|MYR)\s*{_AMOUNT}", re.IGNORECASE)
_SUFFIXED_SINGLE = re.compile(rf"{_AMOUNT}\s*(?:RM|MYR)", re.IGNORECASE)


def _to_number(digits: str, k_suffix: str | None) -> float:
    value = float(digits.replace(",", ""))
    return value * 1000 if k_suffix else value


def _extract_pair(text: str) -> tuple[float, float] | None:
    for pattern in (_PREFIXED_RANGE, _SUFFIXED_RANGE):
        match = pattern.search(text)
        if match:
            low = _to_number(match.group(1), match.group(2))
            high = _to_number(match.group(3), match.group(4))
            return low, high

    for pattern in (_PREFIXED_SINGLE, _SUFFIXED_SINGLE):
        match = pattern.search(text)
        if match:
            value = _to_number(match.group(1), match.group(2))
            return value, value

    return None


def parse_myr_salary(text: str | None) -> Compensation | None:
    """Extracts a MYR salary from free text.

    Malaysian postings quote monthly pay by default, so an amount with no
    stated interval is treated as monthly. Returns None when nothing
    plausible is found - callers must not guess on its behalf.
    """
    if not text:
        return None

    pair = _extract_pair(text)
    if pair is None:
        return None

    low, high = pair
    if low > high:
        return None

    explicit_interval = detect_interval(text)
    interval = explicit_interval or "monthly"

    if explicit_interval is not None:
        # The text states its own interval - trust it. Only guard against
        # outright absurdity (typos, misplaced zeros); the tight
        # per-interval band below exists solely to catch amounts whose
        # interval had to be *guessed*, which is not the case here.
        plausible = 0 < low <= _ABSURDITY_CEILING and 0 < high <= _ABSURDITY_CEILING
    else:
        # No interval word was found - we are guessing "monthly". Apply the
        # tight band, because this is exactly the situation it exists to
        # guard: a bare "RM800" is more likely an hourly or daily rate that
        # got quoted without its interval than a genuine monthly wage.
        floor, ceiling = _BANDS[interval]
        plausible = floor <= low <= ceiling and floor <= high <= ceiling

    if not plausible:
        return None

    return Compensation(
        interval=CompensationInterval(interval),
        min_amount=low,
        max_amount=high,
        currency="MYR",
    )
