from __future__ import annotations

import pandas as pd

from jobspy.baseline.metrics import compute_metrics, render_report


def _frame(rows):
    columns = [
        "site",
        "job_url",
        "title",
        "company",
        "location",
        "city",
        "state",
        "date_posted",
        "min_amount",
        "is_remote",
        "remote_scope",
    ]
    return pd.DataFrame(rows, columns=columns)


def test_counts_rows_per_site():
    df = _frame(
        [
            [
                "indeed",
                "u1",
                "Engineer",
                "Acme",
                "KL",
                None,
                None,
                "2026-09-01",
                None,
                False,
                None,
            ],
            [
                "indeed",
                "u2",
                "Analyst",
                "Acme",
                "KL",
                None,
                None,
                "2026-09-01",
                None,
                False,
                None,
            ],
            [
                "linkedin",
                "u3",
                "Engineer",
                "Acme",
                "KL",
                None,
                None,
                "2026-09-01",
                None,
                False,
                None,
            ],
        ]
    )

    m = compute_metrics(df)

    assert m.total_rows == 3
    assert m.rows_per_site == {"indeed": 2, "linkedin": 1}


def test_salary_fill_rate():
    df = _frame(
        [
            ["indeed", "u1", "A", "X", "KL", None, None, None, 5000, False, None],
            ["indeed", "u2", "B", "X", "KL", None, None, None, None, False, None],
        ]
    )

    assert compute_metrics(df).salary_fill_rate == 0.5


def test_counts_exact_duplicate_urls():
    df = _frame(
        [
            ["indeed", "u1", "A", "X", "KL", None, None, None, None, False, None],
            ["linkedin", "u1", "A", "X", "KL", None, None, None, None, False, None],
            ["google", "u2", "B", "X", "KL", None, None, None, None, False, None],
        ]
    )

    assert compute_metrics(df).exact_duplicate_rows == 1


def test_top_locations_are_ranked():
    df = _frame(
        [
            [
                "indeed",
                "u1",
                "A",
                "X",
                "Kuala Lumpur",
                None,
                None,
                None,
                None,
                False,
                None,
            ],
            [
                "indeed",
                "u2",
                "B",
                "X",
                "Kuala Lumpur",
                None,
                None,
                None,
                None,
                False,
                None,
            ],
            ["indeed", "u3", "C", "X", "Penang", None, None, None, None, False, None],
        ]
    )

    assert compute_metrics(df).top_locations[0] == ("Kuala Lumpur", 2)


def test_state_match_rate_is_zero_when_unpopulated():
    df = _frame(
        [
            ["indeed", "u1", "A", "X", "KL", None, None, None, None, False, None],
        ]
    )

    assert compute_metrics(df).state_match_rate == 0.0


def test_state_match_rate_counts_only_canonical_states():
    """A raw, unnormalized value (an ISO code) must not count as a match,
    while a canonical MalaysianState value must."""
    df = _frame(
        [
            ["indeed", "u1", "A", "X", "KL", None, "M14", None, None, False, None],
            ["indeed", "u2", "B", "X", "KL", None, "Selangor", None, None, False, None],
        ]
    )

    m1 = compute_metrics(df.iloc[[0]])
    m2 = compute_metrics(df.iloc[[1]])

    assert m1.state_match_rate == 0.0
    assert m2.state_match_rate == 1.0


def test_empty_frame_is_safe():
    m = compute_metrics(pd.DataFrame())

    assert m.total_rows == 0
    assert m.salary_fill_rate == 0.0


def test_render_report_contains_headline_numbers():
    df = _frame(
        [
            ["indeed", "u1", "A", "X", "KL", None, "Selangor", None, 5000, False, None],
        ]
    )

    report = render_report(compute_metrics(df), title="Baseline")

    assert "# Baseline" in report
    assert "Total rows | 1" in report
