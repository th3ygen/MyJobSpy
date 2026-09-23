from __future__ import annotations

from jobspy.jobstreet.constant import JOBS_PER_PAGE, headers
from jobspy.model import JobResponse, Scraper, ScraperInput, Site
from jobspy.util import create_logger, create_session

log = create_logger("JobStreet")


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

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        raise NotImplementedError("filled in by Task 4")
