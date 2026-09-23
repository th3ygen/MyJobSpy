from __future__ import annotations

import math
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from jobspy.jobstreet.constant import (
    DESCRIPTION_WORKERS,
    GRAPHQL_URL,
    JOB_DETAILS_QUERY,
    JOBS_PER_PAGE,
    SEARCH_URL,
    SITE_KEY,
    SOURCE_SYSTEM,
    WORK_TYPE_IDS,
    headers,
)
from jobspy.jobstreet.util import parse_job
from jobspy.model import (
    Country,
    DescriptionFormat,
    JobPost,
    JobResponse,
    Scraper,
    ScraperInput,
    Site,
)
from jobspy.util import (
    create_logger,
    create_session,
    markdown_converter,
    plain_converter,
)

log = create_logger("JobStreet")

# Matches a trailing ", Malaysia" or ", MY" (any case, tolerant of
# surrounding whitespace) so it can be stripped before the value is sent as
# `where`.
_COUNTRY_SUFFIX_RE = re.compile(r",\s*(?:malaysia|my)\s*$", re.IGNORECASE)


def _strip_country_suffix(where: str) -> str:
    """Strips a trailing country suffix from a `where` value before it is sent.

    JobStreet's `where` param does not resolve the "City, Country" form at
    all - it returns zero results for e.g. "Kuala Lumpur, Malaysia" where
    "Kuala Lumpur" alone returns real results - but "City, Malaysia" is this
    fork's own documented location convention (README.md), shared with
    Indeed and LinkedIn. Left unhandled, a user following the README gets a
    silent empty result from JobStreet with no error, which reads as "no
    jobs found" rather than "your location string was not understood".

    Only strips when a non-empty remainder survives: location="Malaysia" on
    its own is a legitimate nationwide search and must not be reduced to an
    empty `where`, which would silently change the query's meaning.
    """
    stripped = _COUNTRY_SUFFIX_RE.sub("", where).strip()
    if stripped and stripped != where.strip():
        log.info(
            f"stripped country suffix from location for JobStreet: {where!r} -> {stripped!r}"
        )
        return stripped
    return where.strip()


class JobStreet(Scraper):
    """Scrapes JobStreet Malaysia through its public JSON search API.

    The board's HTML job pages return 403, but the JSON API its own
    frontend calls is open and does not fingerprint TLS - so this uses a
    plain requests session rather than tls-client.
    """

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            Site.JOBSTREET, proxies=proxies, ca_cert=ca_cert, user_agent=user_agent
        )
        self.session = create_session(
            proxies=self.proxies, ca_cert=ca_cert, is_tls=False, has_retry=True
        )
        self.session.headers.update(headers)
        if user_agent:
            self.session.headers["user-agent"] = user_agent
        self.scraper_input: ScraperInput | None = None
        self.jobs_per_page = JOBS_PER_PAGE
        self.seen_ids: set[str] = set()
        self.fetch_description = False

    def _build_params(self, page: int) -> dict:
        """Builds one search query.

        Filters the board has no parameter for are left out entirely rather
        than sent empty - an empty value is a filter, and would silently
        narrow the search.
        """
        params: dict = {
            "siteKey": SITE_KEY,
            "sourcesystem": SOURCE_SYSTEM,
            "page": page,
            "pageSize": self.jobs_per_page,
        }
        if self.scraper_input.search_term:
            params["keywords"] = self.scraper_input.search_term
        if self.scraper_input.location:
            params["where"] = _strip_country_suffix(self.scraper_input.location)

        if self.scraper_input.hours_old:
            # daterange is whole days. Round up so the window is never
            # narrower than asked for, then filter exactly in _within_age.
            params["daterange"] = math.ceil(self.scraper_input.hours_old / 24)
            # Newest-first lets paging stop as soon as it crosses the cutoff.
            params["sortmode"] = "ListedDate"

        work_type_id = WORK_TYPE_IDS.get(self.scraper_input.job_type)
        if work_type_id:
            params["worktype"] = work_type_id

        return params

    def _within_age(self, job: JobPost) -> bool:
        """Applies the exact hours_old cutoff the day-granular filter cannot."""
        if not self.scraper_input.hours_old or job.date_posted is None:
            return True
        cutoff = date.today() - timedelta(
            days=math.ceil(self.scraper_input.hours_old / 24)
        )
        return job.date_posted >= cutoff

    def _fetch_description(self, job_id: str) -> str | None:
        """Fetches one job's body from the board's GraphQL endpoint.

        Returns None on any failure. The caller keeps the search teaser in
        that case, so a flaky description never costs us the job.
        """
        try:
            response = self.session.post(
                GRAPHQL_URL,
                json={
                    "operationName": "jobDetails",
                    "variables": {"jobId": job_id},
                    "query": JOB_DETAILS_QUERY,
                },
                timeout=self.scraper_input.request_timeout,
            )
            payload = response.json() or {}
            # payload is only guaranteed falsy-normalized above - a
            # truthy-but-non-dict JSON root (a bare list, string, number)
            # would make .get() raise below, so the traversal stays inside
            # this same try: any shape of payload must be contained here.
            job = ((payload.get("data") or {}).get("jobDetails") or {}).get("job") or {}
            content = job.get("content")
        except Exception as exc:  # noqa: BLE001 - one description is not the batch
            log.warning(f"description fetch failed for {job_id}: {exc}")
            return None

        if not content:
            return None

        # Matches the branch every other scraper uses: DescriptionFormat.HTML
        # falls through untouched, because the board already sends HTML.
        if self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
            return markdown_converter(content)
        elif self.scraper_input.description_format == DescriptionFormat.PLAIN:
            return plain_converter(content)
        return content

    def _add_descriptions(self, jobs: list[JobPost]) -> None:
        """Fills descriptions in place, bounded to a small pool.

        Search costs one request per hundred jobs; this costs one per job,
        so it is the only part of the scrape worth bounding.
        """

        def fill(job: JobPost) -> None:
            body = self._fetch_description(job.id.removeprefix("js-"))
            if body:
                job.description = body

        with ThreadPoolExecutor(max_workers=DESCRIPTION_WORKERS) as executor:
            list(executor.map(fill, jobs))

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        self.seen_ids = set()

        if scraper_input.country and scraper_input.country != Country.MALAYSIA:
            log.warning(
                f"JobStreet is a Malaysian board and always queries MY; "
                f"country={scraper_input.country.value[0]!r} is ignored. Note "
                f"the Malaysian normalization pipeline only runs when "
                f"country_indeed='malaysia'."
            )
        if scraper_input.distance:
            log.info("JobStreet has no radius filter; distance is ignored")

        wanted = scraper_input.results_wanted + scraper_input.offset
        jobs: list[JobPost] = []
        page = 1

        while len(jobs) < wanted:
            try:
                response = self.session.get(
                    SEARCH_URL,
                    params=self._build_params(page),
                    timeout=scraper_input.request_timeout,
                )
            except Exception as exc:  # noqa: BLE001 - one page must not kill the scrape
                log.error(f"search request failed on page {page}: {exc}")
                break

            if response.status_code == 403:
                # The board disallows this endpoint in robots.txt and sits
                # behind Cloudflare. Treat a 403 as a block, not a blip -
                # retrying into one is how an IP earns a permanent ban.
                log.error("403 from JobStreet; stopping and returning partial results")
                break
            if response.status_code != 200:
                log.error(f"JobStreet returned {response.status_code}; stopping")
                break

            records = (response.json() or {}).get("data") or []
            if not records:
                break

            for record in records:
                if record.get("id") in self.seen_ids:
                    continue
                self.seen_ids.add(record.get("id"))
                job = parse_job(record)
                if job is not None and self._within_age(job):
                    jobs.append(job)

            # A short page is the last page.
            if len(records) < self.jobs_per_page:
                break

            page += 1
            time.sleep(random.uniform(0.5, 1.5))

        if scraper_input.is_remote:
            jobs = [job for job in jobs if job.is_remote]

        start = scraper_input.offset
        selected = jobs[start : start + scraper_input.results_wanted]
        if self.fetch_description:
            self._add_descriptions(selected)
        return JobResponse(jobs=selected)
