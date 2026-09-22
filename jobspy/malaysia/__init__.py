"""Malaysia-specific normalization for scraped job posts.

Three per-job stages (location, salary, remote) then one batch-wide stage
(grouping). Runs on list[JobPost] before DataFrame flattening so normalizers
read and write structured fields.
"""

from __future__ import annotations

from collections import Counter

from jobspy.malaysia.grouping import assign_groups, dedupe_exact
from jobspy.malaysia.location import normalize_location
from jobspy.malaysia.remote import classify_remote_scope
from jobspy.malaysia.salary import parse_myr_salary
from jobspy.model import JobPost
from jobspy.util import create_logger

log = create_logger("Malaysia")

__all__ = ["normalize"]


def _apply_location(job: JobPost, unmatched: Counter) -> None:
    normalized, miss = normalize_location(job.location)
    job.location = normalized
    if miss:
        unmatched[miss] += 1


def _apply_salary(job: JobPost) -> None:
    # Structured board data always wins.
    if job.compensation is not None:
        return
    parsed = parse_myr_salary(job.description)
    if parsed is not None:
        job.compensation = parsed
        # Record provenance: the frame cannot tell a parsed figure from a
        # board-supplied one by looking at `compensation` alone.
        job.salary_parsed_from_description = True


def _apply_remote(job: JobPost) -> None:
    job.remote_scope = classify_remote_scope(job)


_PER_JOB_STAGES = (
    ("location", _apply_location),
    ("salary", _apply_salary),
    ("remote", _apply_remote),
)


def normalize(jobs: list[JobPost], *, group_duplicates: bool = True) -> list[JobPost]:
    """Runs the Malaysian normalization pipeline over a batch of jobs.

    A stage that raises on one job is logged and skipped for that job only -
    it must never take the batch down. Exact dedup always runs;
    group_duplicates=False disables fuzzy grouping only.
    """
    if not jobs:
        return []

    unmatched_locations: Counter = Counter()
    failures: Counter = Counter()

    for job in jobs:
        for stage_name, stage in _PER_JOB_STAGES:
            try:
                if stage_name == "location":
                    stage(job, unmatched_locations)
                else:
                    stage(job)
            except (
                Exception
            ) as exc:  # noqa: BLE001 - one bad job must not abort the batch
                failures[stage_name] += 1
                log.warning(
                    f"{stage_name} normalizer failed for {job.job_url!r}: {exc}"
                )

    deduped = dedupe_exact(jobs)
    removed = len(jobs) - len(deduped)
    if removed:
        log.info(f"exact dedup removed {removed} duplicate listing(s)")

    if group_duplicates:
        try:
            deduped = assign_groups(deduped)
        except Exception as exc:  # noqa: BLE001 - grouping is optional, never fatal
            log.warning(f"grouping failed, continuing ungrouped: {exc}")

    if unmatched_locations:
        top = ", ".join(
            f"{name} ({count})" for name, count in unmatched_locations.most_common(10)
        )
        log.info(f"unmatched locations - add to the gazetteer: {top}")

    for stage_name, count in failures.items():
        log.warning(f"{stage_name} normalizer failed on {count} job(s)")

    return deduped
