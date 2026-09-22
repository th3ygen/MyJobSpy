from __future__ import annotations

import re
from datetime import date, timedelta

# Relative-date phrases with a fixed day offset.
_FIXED_OFFSET_DAYS: dict[str, int] = {
    "hari ini": 0,
    "baru sahaja": 0,
    "baru saja": 0,
    "sebentar tadi": 0,
    "semalam": 1,
    "kelmarin": 2,
}

# "<n> <unit> lepas" — approximate month as 30 days, matching how boards round.
_UNIT_DAYS: dict[str, float] = {
    "minit": 0.0,
    "saat": 0.0,
    "jam": 0.0,
    "hari": 1.0,
    "minggu": 7.0,
    "bulan": 30.0,
    "tahun": 365.0,
}

_RELATIVE_RE = re.compile(
    r"(\d+)\s*(minit|saat|jam|hari|minggu|bulan|tahun)\s*(?:yang\s+)?lepas",
    re.IGNORECASE,
)

BM_INTERVAL_WORDS: dict[str, str] = {
    "sejam": "hourly",
    "per jam": "hourly",
    "sehari": "daily",
    "per hari": "daily",
    "seminggu": "weekly",
    "per minggu": "weekly",
    "sebulan": "monthly",
    "per bulan": "monthly",
    "/bulan": "monthly",
    "setahun": "yearly",
    "per tahun": "yearly",
}

_EN_INTERVAL_WORDS: dict[str, str] = {
    "per hour": "hourly",
    "hourly": "hourly",
    "per day": "daily",
    "daily": "daily",
    "per week": "weekly",
    "weekly": "weekly",
    "per month": "monthly",
    "monthly": "monthly",
    "a month": "monthly",
    "/month": "monthly",
    "p.m.": "monthly",
    "per annum": "yearly",
    "per year": "yearly",
    "yearly": "yearly",
    "annually": "yearly",
}

# Deliberately weighted toward blue-collar and administrative roles: Malaysian
# tech and white-collar postings are written in English even on BM-heavy boards.
EN_TO_BM_QUERY_TERMS: dict[str, str] = {
    "security guard": "pengawal keselamatan",
    "general worker": "pekerja am",
    "production operator": "operator pengeluaran",
    "accountant": "akauntan",
    "administrator": "pentadbir",
    "admin": "pentadbir",
    "assistant": "pembantu",
    "cashier": "juruwang",
    "chef": "tukang masak",
    "cleaner": "pencuci",
    "clerk": "kerani",
    "cook": "tukang masak",
    "driver": "pemandu",
    "engineer": "jurutera",
    "guard": "pengawal",
    "manager": "pengurus",
    "mechanic": "mekanik",
    "nurse": "jururawat",
    "operator": "pengendali",
    "receptionist": "penyambut tetamu",
    "sales": "jualan",
    "supervisor": "penyelia",
    "tailor": "tukang jahit",
    "teacher": "guru",
    "technician": "juruteknik",
    "waiter": "pelayan",
    "warehouse": "gudang",
}


def parse_bm_relative_date(
    text: str | None, *, today: date | None = None
) -> date | None:
    """Parses Malay relative dates ('3 hari lepas') into an absolute date.

    Returns None for anything that is not a recognised Malay phrase.
    """
    if not text:
        return None

    today = today or date.today()
    normalized = re.sub(r"\s+", " ", text.strip().lower())

    for phrase, days in _FIXED_OFFSET_DAYS.items():
        if phrase in normalized:
            return today - timedelta(days=days)

    match = _RELATIVE_RE.search(normalized)
    if not match:
        return None

    quantity = int(match.group(1))
    unit_days = _UNIT_DAYS[match.group(2).lower()]
    return today - timedelta(days=round(quantity * unit_days))


def detect_interval(text: str | None) -> str | None:
    """Finds a compensation interval word in Malay or English. None if absent."""
    if not text:
        return None

    normalized = re.sub(r"\s+", " ", text.lower())
    # Longest phrases first so 'per month' wins over a bare 'month' substring.
    for phrase, interval in sorted(
        {**BM_INTERVAL_WORDS, **_EN_INTERVAL_WORDS}.items(),
        key=lambda item: -len(item[0]),
    ):
        if phrase in normalized:
            return interval
    return None


def to_bm_query(term: str | None) -> str | None:
    """Translates known role words in a query to Malay.

    Returns None when nothing in the term is translatable, so callers can skip
    issuing a redundant second query.
    """
    if not term:
        return None

    normalized = re.sub(r"\s+", " ", term.strip().lower())
    tokens = normalized.split(" ")
    longest_key = max(len(key.split(" ")) for key in EN_TO_BM_QUERY_TERMS)

    out: list[str] = []
    i = 0
    while i < len(tokens):
        # Longest phrase first, so "security guard" is never split into "guard".
        for size in range(min(longest_key, len(tokens) - i), 0, -1):
            phrase = " ".join(tokens[i : i + size])
            if phrase in EN_TO_BM_QUERY_TERMS:
                out.append(EN_TO_BM_QUERY_TERMS[phrase])
                i += size
                break
        else:
            out.append(tokens[i])
            i += 1

    translated = " ".join(out)
    return translated if translated != normalized else None
