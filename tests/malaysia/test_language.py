from __future__ import annotations

from datetime import date

import pytest

from jobspy.malaysia.language import (
    detect_interval,
    parse_bm_relative_date,
    to_bm_query,
)
from jobspy.util import get_enum_from_job_type
from jobspy.model import JobType

TODAY = date(2026, 9, 22)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("hari ini", date(2026, 9, 22)),
        ("Baru sahaja", date(2026, 9, 22)),
        ("semalam", date(2026, 9, 21)),
        ("3 hari lepas", date(2026, 9, 19)),
        ("2 minggu lepas", date(2026, 9, 8)),
        ("1 bulan lepas", date(2026, 8, 23)),
        ("5 jam lepas", date(2026, 9, 22)),
        ("30 minit yang lepas", date(2026, 9, 22)),
    ],
)
def test_parses_bm_relative_dates(text, expected):
    assert parse_bm_relative_date(text, today=TODAY) == expected


@pytest.mark.parametrize("text", ["3 days ago", "", "gibberish", None])
def test_returns_none_for_non_bm_dates(text):
    assert parse_bm_relative_date(text, today=TODAY) is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("RM3,000 sebulan", "monthly"),
        ("RM50 sejam", "hourly"),
        ("RM90,000 setahun", "yearly"),
        ("RM3,000 per month", "monthly"),
        ("RM3,000", None),
    ],
)
def test_detects_interval(text, expected):
    assert detect_interval(text) == expected


@pytest.mark.parametrize(
    "term,expected",
    [
        ("driver", "pemandu"),
        ("Security Guard", "pengawal keselamatan"),
        ("admin clerk", "pentadbir kerani"),
        ("software engineer", "software jurutera"),
        ("blockchain wizard", None),
    ],
)
def test_translates_query_terms(term, expected):
    assert to_bm_query(term) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("sepenuhmasa", JobType.FULL_TIME),
        ("separuhmasa", JobType.PART_TIME),
        ("kontrak", JobType.CONTRACT),
        ("latihanindustri", JobType.INTERNSHIP),
    ],
)
def test_bm_job_types_resolve(value, expected):
    assert get_enum_from_job_type(value) == expected


def test_multiword_result_is_not_retranslated():
    # "operator" is also a standalone key; the multi-word result must not be re-read.
    assert to_bm_query("production operator") == "operator pengeluaran"


def test_fixed_offset_phrase_wins_over_relative_pattern():
    # Text matching BOTH mechanisms: the fixed phrase must win.
    assert parse_bm_relative_date("hari ini, bukan 3 hari lepas", today=TODAY) == date(
        2026, 9, 22
    )


def test_detect_interval_prefers_the_longest_matching_phrase(monkeypatch):
    from jobspy.malaysia import language

    # Inject a shorter key that would win under dict order but must lose on length.
    monkeypatch.setitem(language._EN_INTERVAL_WORDS, "month", "weekly")
    assert language.detect_interval("paid per month") == "monthly"
