from __future__ import annotations

import pytest

from jobspy.malaysia.salary import parse_myr_salary


@pytest.mark.parametrize(
    "text,interval,low,high",
    [
        ("Salary: RM3,000 - RM5,000", "monthly", 3000, 5000),
        ("RM 3,000 - RM 5,000 per month", "monthly", 3000, 5000),
        ("MYR 3000-5000", "monthly", 3000, 5000),
        ("3,000 - 5,000 MYR", "monthly", 3000, 5000),
        ("RM3k-5k", "monthly", 3000, 5000),
        ("Gaji RM2,500 sebulan", "monthly", 2500, 2500),
        ("RM3,000 hingga RM4,500", "monthly", 3000, 4500),
        ("RM90,000 setahun", "yearly", 90000, 90000),
        ("RM 25 sejam", "hourly", 25, 25),
        ("Up to RM12,000", "monthly", 12000, 12000),
        # --- Real-world Indeed Malaysia description shapes (live sample) ---
        (
            "Pay: RM3,500.00 - RM4,000.00 per month",
            "monthly",
            3500,
            4000,
        ),  # dominant form: .00 decimals on both bounds
        (
            "Pay: RM1,700.00 - RM4,129.48 per month",
            "monthly",
            1700,
            4129.48,
        ),  # non-zero cents
        (
            "**Salary:** RM6,000 – RM9,000/month",
            "monthly",
            6000,
            9000,
        ),  # en-dash separator combined with "/month"
        (
            "* Expected salary in between RM 3,000.00 to RM 3,500.00",
            "monthly",
            3000,
            3500,
        ),  # "to" separator, no interval word -> inferred monthly
        (
            "* Basic Salary: **RM 3000**",
            "monthly",
            3000,
            3000,
        ),  # markdown bold around the amount
        (
            "Pay: From RM1,800.00 per month",
            "monthly",
            1800,
            1800,
        ),  # "From" + single-amount form
        (
            "Pay: Up to RM800.00 per month",
            "monthly",
            800,
            800,
        ),  # "Up to" + single amount, below the monthly floor but interval explicit
        (
            "Pay: RM800.00 per month",
            "monthly",
            800,
            800,
        ),  # explicit interval below the tight floor must still be trusted (F15)
    ],
)
def test_parses_myr_salaries(text, interval, low, high):
    compensation = parse_myr_salary(text)

    assert compensation is not None
    assert compensation.interval.value == interval
    assert compensation.min_amount == low
    assert compensation.max_amount == high
    assert compensation.currency == "MYR"


def test_bare_amount_defaults_to_monthly():
    # MY postings quote monthly by default - the inverse of the US assumption.
    assert parse_myr_salary("RM5,000").interval.value == "monthly"


@pytest.mark.parametrize(
    "text",
    [
        "RM800",  # below the monthly floor; likelier hourly or daily
        "RM2,000,000",  # above the monthly ceiling and not marked annual
        "$3,000 - $5,000",  # USD, not ours to parse
        "Competitive salary",
        "",
        None,
    ],
)
def test_rejects_implausible_or_absent_salaries(text):
    assert parse_myr_salary(text) is None


def test_annual_band_is_wider_than_monthly():
    assert parse_myr_salary("RM120,000 per annum") is not None


def test_inverted_range_is_rejected():
    assert parse_myr_salary("RM5,000 - RM3,000") is None
