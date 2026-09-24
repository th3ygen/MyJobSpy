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


@pytest.mark.parametrize(
    "text",
    [
        # Ruling F15 dropped the per-interval *floor* on the explicit path so
        # that a genuine "RM800.00 per month" would stop being rejected. It
        # dropped the ceiling with it, which was an overreach: an explicit
        # interval word is evidence about the interval, not about whether the
        # amount beside it is pay at all. Ordinary prose then parses as salary.
        "You will manage a portfolio worth RM2,500,000 and report monthly "
        "to the board.",
        "Oversee an annual budget of RM48,000,000 across the region.",
        "The successful candidate will handle RM900,000 in daily transactions.",
    ],
)
def test_explicit_interval_does_not_lift_the_ceiling(text):
    assert parse_myr_salary(text) is None


def test_explicit_interval_still_clears_the_floor():
    """The case Ruling F15 exists for must keep working: RM800/month is
    below the monthly band's floor but is a real, if low, monthly wage."""
    parsed = parse_myr_salary("Pay: RM800.00 per month")

    assert parsed is not None
    assert parsed.min_amount == 800
    assert parsed.interval.value == "monthly"


def test_annual_band_is_wider_than_monthly():
    assert parse_myr_salary("RM120,000 per annum") is not None


def test_inverted_range_is_rejected():
    assert parse_myr_salary("RM5,000 - RM3,000") is None


# --- Board-supplied salary fields ---------------------------------------------
#
# A board's own salary field is always a salary, so the RM30,000/month ceiling
# - which exists to tell a wage from a budget figure in prose - discards real
# senior pay there. Measured 2026-09-24: JobStreet senior-role searches
# returned 19 RM-denominated labels between RM30,000 and RM55,000/month, all
# dropped. Board fields get a higher ceiling, not none: Hiredly's
# "1700 - 5002500" and "50 - 100000" are advertiser typos only a ceiling stops.


@pytest.mark.parametrize(
    "label,low,high",
    [
        ("RM\xa040,000 \u2013 RM\xa055,000 per month", 40_000, 55_000),
        ("RM\xa030,000 \u2013 RM\xa045,000 per month", 30_000, 45_000),
        ("RM 35,000 - 50,000 per month", 35_000, 50_000),
    ],
)
def test_board_fields_keep_real_senior_monthly_pay(label, low, high):
    pay = parse_myr_salary(label, board_supplied=True)
    assert (pay.min_amount, pay.max_amount) == (low, high)


def test_the_same_figure_in_prose_is_still_rejected():
    """The prose ceiling is unchanged - a description can pair a budget
    figure with an interval word."""
    assert parse_myr_salary("RM 40,000 - RM 55,000 per month") is None


@pytest.mark.parametrize(
    "label",
    ["RM 1700 - 5002500 per month", "RM 50 - 100000 per month"],
)
def test_board_fields_still_reject_typos_above_the_board_ceiling(label):
    assert parse_myr_salary(label, board_supplied=True) is None


def test_board_yearly_ceiling_is_the_monthly_one_times_twelve():
    assert parse_myr_salary("RM 660,000 per year", board_supplied=True) is not None
    assert parse_myr_salary("RM 1,200,000 per year", board_supplied=True) is None
