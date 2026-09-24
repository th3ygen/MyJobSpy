from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, timezone

from jobspy.hiredly.constant import (
    GRAPHQL_URL,
    JOBS_PER_PAGE,
    MALAYSIAN_REGIONS,
    MAX_FILTERED_PAGES,
    REMOTE_REGION,
    SEARCH_QUERY,
    STATE_REGION_NAMES,
    headers,
)
from jobspy.hiredly.util import parse_active_at, parse_job
from jobspy.malaysia.location import resolve_state
from jobspy.model import (
    Country,
    JobPost,
    JobResponse,
    Scraper,
    ScraperInput,
    Site,
)
from jobspy.util import create_logger, create_session

log = create_logger("Hiredly")

# Inputs that mean "all of Malaysia" rather than an unresolved place, so they
# send no state filter without a warning.
_NATIONWIDE = {"malaysia", "my"}


def _now() -> datetime:
    """The clock hours_old is measured against. A function so tests can pin it."""
    return datetime.now(timezone.utc)


class Hiredly(Scraper):
    """Scrapes Hiredly Malaysia through the GraphQL API its own frontend calls.

    One POST per page returns full postings, descriptions included, so there
    is no per-job request. The site's server-rendered HTML ignores the search
    parameter entirely, which is why this does not scrape pages. The API is
    not TLS-fingerprinted, so this uses a plain requests session; it sits
    behind Cloudflare, so a 403 is treated as a block (see the search loop).
    """

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            Site.HIREDLY, proxies=proxies, ca_cert=ca_cert, user_agent=user_agent
        )
        self.session = create_session(
            proxies=self.proxies, ca_cert=ca_cert, is_tls=False, has_retry=True
        )
        self.session.headers.update(headers)
        if user_agent:
            self.session.headers["user-agent"] = user_agent
        self.jobs_per_page = JOBS_PER_PAGE
        self.seen_ids: set[str] = set()

    def _state_filter(self, location: str | None) -> list[str] | None:
        """Maps the caller's location to the board's `stateRegions` filter.

        The board filters by state only, so a city widens to its state. A
        location that is not a Malaysian place sends no filter at all rather
        than an empty one: the board answers a state it has no jobs in with
        zero results, not with everything.
        """
        if not location or location.strip().lower() in _NATIONWIDE:
            return None
        state = resolve_state(location)
        if state is None:
            log.warning(
                f"could not resolve location {location!r} to a Malaysian state; "
                f"searching all of Malaysia"
            )
            return None
        region = STATE_REGION_NAMES[state]
        log.info(f"Hiredly filters by state only: location {location!r} -> {region!r}")
        return [region]

    def _variables(
        self,
        scraper_input: ScraperInput,
        state_regions: list[str] | None,
        after: str | None,
    ) -> dict:
        """Builds one page's variables. Filters the caller did not ask for are
        left out rather than sent empty - an empty value is a filter."""
        variables: dict = {"first": self.jobs_per_page}
        if scraper_input.search_term:
            variables["keyword"] = scraper_input.search_term
        if state_regions:
            if scraper_input.is_remote:
                # Fully-remote jobs are filed under the "Remote" region, not
                # a state, so a state filter alone would exclude exactly what
                # a remote search is for. The board ORs the list.
                state_regions = state_regions + [REMOTE_REGION]
            variables["stateRegions"] = state_regions
        if after:
            variables["after"] = after
        return variables

    def _passes_filters(
        self,
        scraper_input: ScraperInput,
        record: dict,
        job: JobPost,
        cutoff: datetime | None,
    ) -> bool:
        """The filters the board has no argument for, applied per job.

        Run inside the paging loop rather than after it: the loop counts kept
        jobs, so filtering afterwards would stop paging as soon as enough
        *unfiltered* jobs exist, starving results_wanted.
        """
        if scraper_input.is_remote and not job.is_remote:
            return False
        if scraper_input.job_type and scraper_input.job_type not in (
            job.job_type or []
        ):
            return False
        if cutoff is not None:
            active_at = parse_active_at(record)
            # No timestamp is kept, not dropped: nothing proves it is stale.
            if active_at is not None and active_at < cutoff:
                return False
        return True

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.seen_ids = set()

        if scraper_input.country and scraper_input.country != Country.MALAYSIA:
            log.warning(
                f"Hiredly is a Malaysian board and always queries MY; "
                f"country={scraper_input.country.value[0]!r} is ignored. Note "
                f"the Malaysian normalization pipeline only runs when "
                f"country_indeed='malaysia'."
            )
        if scraper_input.distance:
            log.info("Hiredly has no radius filter; distance is ignored")
        if scraper_input.easy_apply:
            log.info("Hiredly has no easy-apply filter; easy_apply is ignored")

        cutoff = (
            _now() - timedelta(hours=scraper_input.hours_old)
            if scraper_input.hours_old
            else None
        )
        filtering = bool(
            scraper_input.is_remote or scraper_input.job_type or cutoff is not None
        )

        # Resolved once, not per page, so its log line is not repeated.
        state_regions = self._state_filter(scraper_input.location)
        wanted = scraper_input.results_wanted + scraper_input.offset
        jobs: list[JobPost] = []
        after: str | None = None
        pages = 0
        abroad = 0

        while len(jobs) < wanted:
            if filtering and pages >= MAX_FILTERED_PAGES:
                # A filter that discards most of every page would otherwise
                # walk the whole board looking for matches that are not there.
                log.warning(
                    f"stopping after {MAX_FILTERED_PAGES} pages of filtered "
                    f"results; found {len(jobs)} of {wanted} wanted"
                )
                break
            try:
                response = self.session.post(
                    GRAPHQL_URL,
                    json={
                        "query": SEARCH_QUERY,
                        "variables": self._variables(
                            scraper_input, state_regions, after
                        ),
                    },
                    timeout=scraper_input.request_timeout,
                )
            except Exception as exc:  # noqa: BLE001 - one page must not kill the scrape
                log.error(f"search request failed on page {pages + 1}: {exc}")
                break
            pages += 1

            if response.status_code == 403:
                # Cloudflare-fronted. Treat a 403 as a block, not a blip -
                # retrying into one is how an IP earns a ban.
                log.error("403 from Hiredly; stopping and returning partial results")
                break
            if response.status_code != 200:
                log.error(f"Hiredly returned {response.status_code}; stopping")
                break

            try:
                payload = response.json()
            except ValueError:
                # A Cloudflare challenge page can arrive with a 200.
                log.error("Hiredly returned a non-JSON body; stopping")
                break
            if not isinstance(payload, dict):
                log.error("Hiredly returned a non-object payload; stopping")
                break
            if payload.get("errors"):
                log.error(f"Hiredly GraphQL errors: {payload['errors']}; stopping")
                break
            result = (payload.get("data") or {}).get("jobListsSearchResults")
            if not isinstance(result, dict):
                log.error("Hiredly returned no search result object; stopping")
                break
            records = result.get("nodes") or []
            if not records:
                break

            for record in records:
                if not isinstance(record, dict):
                    continue
                record_id = record.get("id")
                if record_id in self.seen_ids:
                    continue
                self.seen_ids.add(record_id)
                region = record.get("stateRegion")
                if region and region not in MALAYSIAN_REGIONS:
                    abroad += 1
                    continue
                try:
                    job = parse_job(record, scraper_input.description_format)
                except (
                    Exception
                ) as exc:  # noqa: BLE001 - one record must not lose the page
                    log.warning(f"skipping unparseable record {record_id!r}: {exc}")
                    continue
                if job is None:
                    continue
                if not self._passes_filters(scraper_input, record, job, cutoff):
                    continue
                jobs.append(job)

            page_info = result.get("pageInfo") or {}
            after = page_info.get("endCursor")
            if not page_info.get("hasNextPage") or not after:
                break
            time.sleep(random.uniform(0.5, 1.5))

        if abroad:
            log.info(f"skipped {abroad} postings outside Malaysia")

        start = scraper_input.offset
        return JobResponse(jobs=jobs[start : start + scraper_input.results_wanted])
