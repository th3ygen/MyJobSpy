from __future__ import annotations

import re

from jobspy.malaysia.language import detect_interval
from jobspy.model import Compensation, CompensationInterval

# Sanity bands from the design spec. These filter nonsense; they are not
# claims about Malaysian pay policy. The monthly floor sits below the
# statutory minimum wage (RM1,700/month as of 2025) on purpose, to allow
# part-time and internship rates through.
#
# The FLOOR applies only when the interval was *inferred* (no interval word
# was found in the text, so we defaulted to "monthly"). When the interval is
# stated explicitly ("per month", "sejam", ...), there is nothing to infer
# and therefore nothing for a tight floor to protect against: a posting that
# literally says "RM800.00 per month" is not a mislabeled hourly rate, it is
# a real (if low) monthly wage, and rejecting it would silently discard
# genuine salary data pulled from real Indeed Malaysia listings (Ruling
# F15).
#
# The CEILING applies on both paths. Ruling F15 was argued entirely about
# the floor; dropping the ceiling alongside it was an overreach. An interval
# word is evidence about the *interval*, not about whether the amount beside
# it is pay at all, and ordinary prose pairs large MYR figures with interval
# words constantly - "manage a portfolio worth RM2,500,000 and report
# monthly" parsed as a RM2.5m monthly salary. The ceiling is the only thing
# separating a wage from a budget, so an explicit interval must not lift it.
_BANDS: dict[str, tuple[float, float]] = {
    "hourly": (8, 150),
    "daily": (30, 1_000),
    "weekly": (200, 8_000),
    "monthly": (1_000, 30_000),
    "yearly": (20_000, 500_000),
}

# Ceilings for a board's own salary field (board_supplied=True). The prose
# ceiling above exists to tell a wage from a budget figure, and a board's
# salary field is never a budget - so there it only discarded real pay:
# JobStreet senior-role searches returned 19 RM-denominated labels between
# RM30,000 and RM55,000/month (measured 2026-09-24), every one dropped.
# Still a ceiling, not none: board fields carry advertiser typos ("1700 -
# 5002500", "50 - 100000" on Hiredly) that nothing else catches. RM80,000
# leaves headroom over the highest real figure seen; yearly is that x12.
_BOARD_CEILINGS: dict[str, float] = {
    "monthly": 80_000,
    "yearly": 960_000,
}

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


def parse_myr_salary(
    text: str | None, *, board_supplied: bool = False
) -> Compensation | None:
    """Extracts a MYR salary from free text.

    Malaysian postings quote monthly pay by default, so an amount with no
    stated interval is treated as monthly. Returns None when nothing
    plausible is found - callers must not guess on its behalf.

    Pass board_supplied=True only for a board's own salary field (never for
    description text): it raises the ceiling, see _BOARD_CEILINGS.
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

    floor, ceiling = _BANDS[interval]
    if board_supplied:
        ceiling = _BOARD_CEILINGS.get(interval, ceiling)

    if explicit_interval is not None:
        # The text states its own interval - trust it, and drop the floor
        # accordingly (Ruling F15). The ceiling still stands: it is what
        # separates a wage from a figure that merely happens to sit near an
        # interval word, and no interval word makes RM2,500,000 a monthly
        # salary. See the note on _BANDS.
        plausible = 0 < low <= ceiling and 0 < high <= ceiling
    else:
        # No interval word was found - we are guessing "monthly". Apply the
        # floor too, because this is exactly the situation it exists to
        # guard: a bare "RM800" is more likely an hourly or daily rate that
        # got quoted without its interval than a genuine monthly wage.
        plausible = floor <= low <= ceiling and floor <= high <= ceiling

    if not plausible:
        return None

    return Compensation(
        interval=CompensationInterval(interval),
        min_amount=low,
        max_amount=high,
        currency="MYR",
    )
