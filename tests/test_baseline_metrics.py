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


def test_salary_fill_rate_by_site():
    """The blended salary_fill_rate can hide a board with strong direct-data
    coverage sitting alongside boards with essentially none - this is what
    F4 asks metrics.py to surface per site instead."""
    df = _frame(
        [
            # jobstreet: 2 of 2 priced -> 100%
            ["jobstreet", "u1", "A", "X", "KL", None, None, None, 5000, False, None],
            ["jobstreet", "u2", "B", "X", "KL", None, None, None, 6000, False, None],
            # indeed: 0 of 2 priced -> 0%
            ["indeed", "u3", "C", "X", "KL", None, None, None, None, False, None],
            ["indeed", "u4", "D", "X", "KL", None, None, None, None, False, None],
        ]
    )

    m = compute_metrics(df)

    assert m.salary_fill_rate_by_site == {"indeed": 0.0, "jobstreet": 1.0}
    # The blended rate (2 of 4) must not be mistaken for either site's own
    # number - this is exactly the confusion F4 flags.
    assert m.salary_fill_rate == 0.5


def test_salary_fill_rate_by_site_is_empty_without_a_site_column():
    df = pd.DataFrame({"min_amount": [5000, None]})

    assert compute_metrics(df).salary_fill_rate_by_site == {}


def test_render_report_includes_salary_fill_by_site():
    df = _frame(
        [
            ["jobstreet", "u1", "A", "X", "KL", None, None, None, 5000, False, None],
            ["indeed", "u2", "B", "X", "KL", None, None, None, None, False, None],
        ]
    )

    report = render_report(compute_metrics(df), title="Baseline")

    assert "## Salary fill rate by site" in report
    assert "| indeed | 0.0% |" in report
    assert "| jobstreet | 100.0% |" in report


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


def test_remote_scope_collapses_null_like_values_into_one_bucket():
    """A live run showed None and NaN counted as two separate buckets
    (value_counts(dropna=False) treats them as distinct keys in a mixed
    object column). remote_scope is None-by-design for non-remote jobs, so
    every null-like value must collapse into a single, clearly-labeled
    bucket rather than inventing a false split in the report."""
    df = pd.DataFrame(
        {
            "remote_scope": pd.array(
                ["my", None, float("nan"), "my", None], dtype="object"
            )
        }
    )

    m = compute_metrics(df)

    assert m.remote_scope_counts == {"my": 2, "(not remote)": 3}


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
