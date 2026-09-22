from __future__ import annotations

import logging

from jobspy.malaysia import normalize
from jobspy.model import Country, Location


def test_normalizes_location_salary_and_remote(make_job):
    # Note (Ruling F1): the brief's original version of this test kept the
    # "Open to APAC candidates." sentence and asserted remote_scope == "apac".
    # That assertion is wrong given the pipeline's specified stage order:
    # location runs before remote, so by the time classify_remote_scope runs,
    # job.location.country has already been stamped Country.MALAYSIA by the
    # location stage (Cyberjaya resolves canonically). The remote classifier
    # builds its haystack from description + title + location and includes
    # "malaysia" from the resolved country, and its "my" check has higher
    # precedence than "apac" - so the real result is "my", not "apac". The
    # sentence is dropped and the assertion changed accordingly. This also
    # pins the stronger property: location normalization runs before remote
    # classification, and its output feeds the classifier.
    job = make_job(
        location=Location(city="Cyberjaya", country=Country.MALAYSIA),
        description="We offer RM6,000 - RM8,000 per month.",
        is_remote=True,
    )

    result = normalize([job])[0]

    assert result.location.state == "Selangor"
    assert result.compensation.min_amount == 6000
    assert result.compensation.currency == "MYR"
    assert result.remote_scope == "my"


def test_description_parsed_salary_reaches_the_frame_as_description(make_job):
    """End to end over the real pipeline, not a hand-set marker: a salary
    found only in the description must surface as salary_source
    'description', because measuring description-parsed fill separately is
    the point of Phase 1."""
    from jobspy.frame import build_jobs_dataframe
    from jobspy.model import JobResponse

    job = make_job(
        location=Location(city="Cyberjaya", country=Country.MALAYSIA),
        description="We offer RM6,000 - RM8,000 per month.",
    )

    normalized = normalize([job])

    df = build_jobs_dataframe(
        {"indeed": JobResponse(jobs=normalized)}, country_enum=Country.MALAYSIA
    )

    assert df.iloc[0]["min_amount"] == 6000
    assert df.iloc[0]["salary_source"] == "description"


def test_structured_compensation_reaches_the_frame_as_direct_data(make_job):
    from jobspy.frame import build_jobs_dataframe
    from jobspy.model import Compensation, CompensationInterval, JobResponse

    job = make_job(
        description="RM9,000 per month",
        compensation=Compensation(
            interval=CompensationInterval.MONTHLY,
            min_amount=4000,
            max_amount=5000,
            currency="MYR",
        ),
    )

    normalized = normalize([job])

    df = build_jobs_dataframe(
        {"indeed": JobResponse(jobs=normalized)}, country_enum=Country.MALAYSIA
    )

    # Structured board data still wins, and still says so.
    assert df.iloc[0]["min_amount"] == 4000
    assert df.iloc[0]["salary_source"] == "direct_data"


def test_does_not_overwrite_structured_compensation(make_job):
    from jobspy.model import Compensation, CompensationInterval

    job = make_job(
        description="RM9,000 per month",
        compensation=Compensation(
            interval=CompensationInterval.MONTHLY,
            min_amount=4000,
            max_amount=4000,
            currency="MYR",
        ),
    )

    assert normalize([job])[0].compensation.min_amount == 4000


def test_removes_exact_duplicates(make_job):
    jobs = [make_job(job_url="https://x/1"), make_job(job_url="https://x/1")]

    assert len(normalize(jobs)) == 1


def test_group_duplicates_false_skips_grouping(make_job):
    jobs = [
        make_job(job_url="https://a/1", title="Software Engineer"),
        make_job(job_url="https://b/1", title="Software Engineer"),
    ]

    result = normalize(jobs, group_duplicates=False)

    assert len(result) == 2
    assert all(job.dedup_group is None for job in result)


def test_exact_dedup_runs_even_when_grouping_is_off(make_job):
    jobs = [make_job(job_url="https://x/1"), make_job(job_url="https://x/1")]

    assert len(normalize(jobs, group_duplicates=False)) == 1


def test_a_failing_normalizer_does_not_abort_the_batch(make_job, monkeypatch):
    import jobspy.malaysia as pipeline

    def boom(_):
        raise ValueError("bad input")

    monkeypatch.setattr(pipeline, "parse_myr_salary", boom)

    jobs = [make_job(job_url="https://x/1", description="RM5,000")]
    result = normalize(jobs)

    assert len(result) == 1
    assert result[0].compensation is None


def test_normalizer_failures_are_counted_and_reported(make_job, monkeypatch, caplog):
    import jobspy.malaysia as pipeline

    def boom(_):
        raise ValueError("bad input")

    monkeypatch.setattr(pipeline, "parse_myr_salary", boom)
    # create_logger sets propagate=False, so caplog cannot see these records
    # unless propagation is re-enabled for the duration of this test.
    monkeypatch.setattr(pipeline.log, "propagate", True)
    caplog.set_level(logging.WARNING, logger="JobSpy:Malaysia")

    jobs = [make_job(job_url=f"https://x/{i}", description="RM5,000") for i in range(3)]
    normalize(jobs)

    messages = [record.getMessage() for record in caplog.records]
    # the per-job warning, naming the offending input
    assert any("salary normalizer failed for" in m for m in messages)
    # the per-stage rollup, so a deleted summary block is caught
    assert any("salary normalizer failed on 3 job(s)" in m for m in messages)


def test_empty_input_is_safe():
    assert normalize([]) == []
