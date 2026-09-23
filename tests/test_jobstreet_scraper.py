"""Paging and orchestration for the JobStreet scraper.

The session is stubbed - these test how the scraper drives the API, not how
the API behaves. Parsing is covered in test_jobstreet_util.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobspy.jobstreet import JobStreet
from jobspy.model import Country, JobType, ScraperInput, Site

FIXTURES = Path(__file__).parent / "fixtures" / "jobstreet"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload


class FakeSession:
    """Serves queued pages and records every call made."""

    def __init__(self, pages: list[dict]):
        self._pages = list(pages)
        self.calls: list[dict] = []
        self.headers: dict = {}

    def get(self, url, params=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "params": params})
        if not self._pages:
            return FakeResponse(load("search_empty.json"))
        return FakeResponse(self._pages.pop(0))

    def post(self, url, json=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "json": json})
        return FakeResponse(load("job_details.json"))


def make_scraper(pages: list[dict]) -> JobStreet:
    scraper = JobStreet()
    scraper.session = FakeSession(pages)
    return scraper


def an_input(**overrides) -> ScraperInput:
    params = {
        "site_type": [Site.JOBSTREET],
        "search_term": "software engineer",
        "location": "Kuala Lumpur",
        "country": Country.MALAYSIA,
        "results_wanted": 5,
    }
    params.update(overrides)
    return ScraperInput(**params)


def test_returns_jobs_from_one_page():
    scraper = make_scraper([load("search_page.json")])
    response = scraper.scrape(an_input(results_wanted=5))

    assert len(response.jobs) == 5
    assert all(job.id.startswith("js-") for job in response.jobs)


def test_stops_on_an_empty_page_instead_of_spinning():
    """An empty first page must terminate the loop, not page forever."""
    scraper = make_scraper([load("search_empty.json")])
    response = scraper.scrape(an_input(results_wanted=50))

    assert response.jobs == []
    assert len(scraper.session.calls) == 1


def test_stops_on_a_short_page():
    """A page shorter than pageSize is the last page."""
    scraper = make_scraper([load("search_last_page.json")])
    response = scraper.scrape(an_input(results_wanted=50))

    assert len(response.jobs) == 3
    assert len(scraper.session.calls) == 1


def test_does_not_return_the_same_job_twice():
    """The board can repeat a listing across pages; seen_ids absorbs that."""
    page = load("search_page.json")
    scraper = make_scraper([page, page])
    # The fixture page holds 8 records. With the real jobs_per_page (100)
    # that reads as a short page and paging stops after page 1, so the
    # second (duplicate) page would never be requested and seen_ids would
    # never be exercised - the assertion below would pass vacuously.
    # Overriding jobs_per_page to match the fixture's record count makes
    # page 1 look full, forcing a page-2 request that genuinely feeds in
    # duplicate ids.
    scraper.jobs_per_page = 8
    response = scraper.scrape(an_input(results_wanted=50))

    ids = [job.id for job in response.jobs]
    assert len(ids) == len(set(ids))
    # Guards against the fix above silently regressing to the vacuous case:
    # both duplicate pages must actually have been requested (page 1, then
    # page 2). A third, empty-page request follows - a full 8-record page
    # never looks "short" to the paging loop even when every id on it is a
    # duplicate, so it probes page 3 before the empty fixture fallback stops
    # it - but that trailing request isn't what this test is checking.
    assert [call["params"]["page"] for call in scraper.session.calls[:2]] == [1, 2]
    assert len(scraper.session.calls) >= 2


def test_applies_offset():
    full = load("search_page.json")
    first = make_scraper([full]).scrape(an_input(results_wanted=8)).jobs
    offset = make_scraper([full]).scrape(an_input(results_wanted=3, offset=2)).jobs

    assert [job.id for job in offset] == [job.id for job in first[2:5]]


class TestQueryParameters:
    def test_sends_the_board_identifiers_and_query(self):
        scraper = make_scraper([load("search_page.json")])
        scraper.scrape(an_input())
        params = scraper.session.calls[0]["params"]

        assert params["siteKey"] == "MY-Main"
        assert params["sourcesystem"] == "houston"
        assert params["keywords"] == "software engineer"
        assert params["where"] == "Kuala Lumpur"
        assert params["pageSize"] == 100

    def test_maps_hours_old_to_whole_days(self):
        """daterange is day-granular, so 30 hours must round up to 2."""
        scraper = make_scraper([load("search_page.json")])
        scraper.scrape(an_input(hours_old=30))

        assert scraper.session.calls[0]["params"]["daterange"] == 2

    def test_sorts_by_date_only_when_filtering_by_age(self):
        with_age = make_scraper([load("search_page.json")])
        with_age.scrape(an_input(hours_old=24))
        assert with_age.session.calls[0]["params"]["sortmode"] == "ListedDate"

        without = make_scraper([load("search_page.json")])
        without.scrape(an_input())
        assert "sortmode" not in without.session.calls[0]["params"]

    def test_maps_job_type_to_the_worktype_id(self):
        scraper = make_scraper([load("search_page.json")])
        scraper.scrape(an_input(job_type=JobType.CONTRACT))

        assert scraper.session.calls[0]["params"]["worktype"] == "244"

    def test_omits_filters_that_were_not_requested(self):
        scraper = make_scraper([load("search_page.json")])
        scraper.scrape(an_input())
        params = scraper.session.calls[0]["params"]

        assert "daterange" not in params
        assert "worktype" not in params

    def test_strips_a_trailing_malaysia_suffix_from_where(self):
        """This fork's documented location convention is "City, Malaysia" -

        shared with Indeed and LinkedIn - but JobStreet's `where` does not
        resolve that form and returns zero results for it. Left unhandled,
        a user following the README gets a silent empty result.
        """
        scraper = make_scraper([load("search_page.json")])
        scraper.scrape(an_input(location="Kuala Lumpur, Malaysia"))

        assert scraper.session.calls[0]["params"]["where"] == "Kuala Lumpur"

    def test_strips_a_trailing_my_suffix_from_where(self):
        scraper = make_scraper([load("search_page.json")])
        scraper.scrape(an_input(location="Kuala Lumpur, MY"))

        assert scraper.session.calls[0]["params"]["where"] == "Kuala Lumpur"

    def test_tolerates_whitespace_around_the_suffix(self):
        scraper = make_scraper([load("search_page.json")])
        scraper.scrape(an_input(location="Kuala Lumpur , Malaysia"))

        assert scraper.session.calls[0]["params"]["where"] == "Kuala Lumpur"

    def test_leaves_an_unsuffixed_location_untouched(self):
        scraper = make_scraper([load("search_page.json")])
        scraper.scrape(an_input(location="Kuala Lumpur"))

        assert scraper.session.calls[0]["params"]["where"] == "Kuala Lumpur"

    def test_does_not_strip_a_bare_country_search_to_empty(self):
        """location="Malaysia" alone is a legitimate nationwide search - it

        must survive as "Malaysia", not be reduced to an empty `where`,
        which would silently change what the query means.
        """
        scraper = make_scraper([load("search_page.json")])
        scraper.scrape(an_input(location="Malaysia"))

        assert scraper.session.calls[0]["params"]["where"] == "Malaysia"


class TestDescriptions:
    def test_teaser_is_used_when_descriptions_are_off(self):
        """The field is never empty: the teaser ships with the search result."""
        scraper = make_scraper([load("search_page.json")])
        jobs = scraper.scrape(an_input(results_wanted=1)).jobs

        assert jobs[0].description
        assert all(call["url"].endswith("/search") for call in scraper.session.calls)

    def test_no_graphql_calls_when_descriptions_are_off(self):
        scraper = make_scraper([load("search_page.json")])
        scraper.scrape(an_input(results_wanted=3))

        assert not [c for c in scraper.session.calls if c["url"].endswith("/graphql")]

    def test_fetches_and_converts_descriptions_when_on(self):
        scraper = make_scraper([load("search_page.json")])
        scraper.fetch_description = True
        jobs = scraper.scrape(an_input(results_wanted=2)).jobs

        graphql = [c for c in scraper.session.calls if c["url"].endswith("/graphql")]
        assert len(graphql) == 2
        # _add_descriptions runs on a ThreadPoolExecutor with 5 workers, so
        # the order calls land in scraper.session.calls is nondeterministic.
        # Compare the set of requested ids rather than positional order.
        requested = {c["json"]["variables"]["jobId"] for c in graphql}
        assert requested == {job.id.removeprefix("js-") for job in jobs}
        # markdown_converter ran: the fixture body is HTML, the output is not.
        assert "<p>" not in jobs[0].description

    def test_a_failed_description_leaves_the_teaser(self):
        """One bad description must not lose the job."""

        class Failing(FakeSession):
            def post(self, *args, **kwargs):
                raise RuntimeError("boom")

        scraper = JobStreet()
        scraper.session = Failing([load("search_page.json")])
        scraper.fetch_description = True
        jobs = scraper.scrape(an_input(results_wanted=1)).jobs

        assert len(jobs) == 1
        assert jobs[0].description  # the teaser survived

    def test_a_malformed_graphql_payload_leaves_the_teaser(self):
        """A truthy-but-non-dict JSON root must not escape _fetch_description.

        `payload.get(...)` only works on a dict; a bare list (or string, or
        number) root is truthy, so `payload or {}` does not normalize it
        away, and `.get("data")` would raise AttributeError if the
        envelope traversal ever slipped outside the try/except.
        """

        class NonDictPayload(FakeSession):
            def post(self, url, json=None, timeout=None, **kwargs):
                self.calls.append({"url": url, "json": json})
                return FakeResponse([1, 2, 3])

        scraper = JobStreet()
        scraper.session = NonDictPayload([load("search_page.json")])
        scraper.fetch_description = True
        jobs = scraper.scrape(an_input(results_wanted=1)).jobs

        assert len(jobs) == 1
        assert jobs[0].description  # the teaser survived
