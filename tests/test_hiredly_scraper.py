"""Paging, filtering and query construction for the Hiredly scraper.

The session is stubbed - these test how the scraper drives the API, not how
the API behaves. Parsing is covered in test_hiredly_util.py.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import jobspy.hiredly as hiredly_module
from jobspy.hiredly import MAX_FILTERED_PAGES, Hiredly
from jobspy.model import Country, DescriptionFormat, JobType, ScraperInput, Site

FIXTURES = Path(__file__).parent / "fixtures" / "hiredly"

MYT = timezone(timedelta(hours=8))

SINGAPORE_ID = "hd-46843029-4cf3-46ea-8400-e6000365fdb5"
REMOTE_REGION_ID = "hd-3279048b-d016-41a9-a260-eb3b211b4ebf"
REMOTE_PREF_ID = "hd-8fd5baae-3fb2-45ae-bd2f-ab48ad19a89b"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def page_ids(name: str) -> list[str]:
    return [
        f"hd-{node['id']}"
        for node in load(name)["data"]["jobListsSearchResults"]["nodes"]
    ]


class FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeSession:
    """Serves queued payloads to POSTs and records every call made."""

    def __init__(self, pages: list):
        self._pages = list(pages)
        self.calls: list[dict] = []
        self.headers: dict = {}

    def post(self, url, json=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "json": json})
        if not self._pages:
            return FakeResponse(load("search_empty.json"))
        page = self._pages.pop(0)
        if isinstance(page, FakeResponse):
            return page
        return FakeResponse(page)

    def variables(self, index: int = 0) -> dict:
        return self.calls[index]["json"]["variables"]


def make_scraper(pages: list) -> Hiredly:
    scraper = Hiredly()
    scraper.session = FakeSession(pages)
    return scraper


def an_input(**overrides) -> ScraperInput:
    params = {
        "site_type": [Site.HIREDLY],
        "search_term": "engineer",
        "country": Country.MALAYSIA,
        "results_wanted": 50,
    }
    params.update(overrides)
    return ScraperInput(**params)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(hiredly_module.time, "sleep", lambda _: None)


@pytest.fixture
def frozen_now(monkeypatch):
    """Pins the scraper's clock just after the newest fixture record."""
    now = datetime(2026, 9, 24, 20, 0, 0, tzinfo=MYT)
    monkeypatch.setattr(hiredly_module, "_now", lambda: now)
    return now


def endless_page() -> dict:
    """A page that always claims there is another one."""
    page = load("search_page.json")
    page["data"]["jobListsSearchResults"]["pageInfo"]["hasNextPage"] = True
    return page


class TestPaging:
    def test_returns_the_malaysian_jobs_from_one_page(self):
        scraper = make_scraper([load("search_page.json")])
        ids = [job.id for job in scraper.scrape(an_input()).jobs]

        expected = [i for i in page_ids("search_page.json") if i != SINGAPORE_ID]
        assert ids == expected

    def test_first_page_sends_no_cursor_and_the_page_size(self):
        scraper = make_scraper([load("search_last_page.json")])
        scraper.scrape(an_input())

        variables = scraper.session.variables(0)
        assert variables["keyword"] == "engineer"
        assert variables["first"] == scraper.jobs_per_page
        assert variables.get("after") is None

    def test_second_page_sends_the_end_cursor(self):
        first = load("search_page.json")
        scraper = make_scraper([first, load("search_last_page.json")])
        scraper.scrape(an_input())

        cursor = first["data"]["jobListsSearchResults"]["pageInfo"]["endCursor"]
        assert scraper.session.variables(1)["after"] == cursor

    def test_stops_when_the_board_says_there_is_no_next_page(self):
        scraper = make_scraper([load("search_last_page.json"), endless_page()])
        scraper.scrape(an_input())

        assert len(scraper.session.calls) == 1

    def test_stops_on_an_empty_page(self):
        scraper = make_scraper([load("search_empty.json"), endless_page()])
        jobs = scraper.scrape(an_input()).jobs

        assert jobs == []
        assert len(scraper.session.calls) == 1

    def test_stops_once_results_wanted_is_met(self):
        scraper = make_scraper([endless_page(), endless_page()])
        jobs = scraper.scrape(an_input(results_wanted=3)).jobs

        assert len(jobs) == 3
        assert len(scraper.session.calls) == 1

    def test_does_not_return_the_same_job_twice(self):
        scraper = make_scraper([endless_page(), load("search_page.json")])
        ids = [job.id for job in scraper.scrape(an_input()).jobs]

        # The duplicate page must actually have been read, or this proves
        # nothing about dedup.
        assert len(scraper.session.calls) >= 2
        assert len(ids) == len(set(ids)) == 9

    def test_applies_offset(self):
        everything = make_scraper([load("search_page.json")])
        all_ids = [job.id for job in everything.scrape(an_input()).jobs]

        scraper = make_scraper([load("search_page.json")])
        jobs = scraper.scrape(an_input(results_wanted=2, offset=3)).jobs
        assert [job.id for job in jobs] == all_ids[3:5]


class TestRegions:
    def test_drops_a_posting_in_a_singapore_region(self):
        """Singapore postings carry "North-East" etc., not "Singapore"."""
        scraper = make_scraper([load("search_page.json")])
        ids = {job.id for job in scraper.scrape(an_input()).jobs}

        assert SINGAPORE_ID not in ids

    def test_keeps_the_remote_region(self):
        scraper = make_scraper([load("search_page.json")])
        ids = {job.id for job in scraper.scrape(an_input()).jobs}

        assert REMOTE_REGION_ID in ids

    def test_keeps_a_posting_with_no_region(self):
        """Nothing proves it is abroad, so it is not dropped."""
        scraper = make_scraper([load("search_malformed.json")])
        titles = {job.title for job in scraper.scrape(an_input()).jobs}

        assert "Every optional field null" in titles


class TestStateFilter:
    @pytest.mark.parametrize(
        "location,expected",
        [
            ("Kuala Lumpur, Malaysia", ["Kuala Lumpur"]),
            ("Penang", ["Penang"]),
            ("Melaka", ["Malacca"]),
            ("Petaling Jaya", ["Selangor"]),
        ],
    )
    def test_maps_a_location_to_the_boards_state_name(self, location, expected):
        scraper = make_scraper([load("search_last_page.json")])
        scraper.scrape(an_input(location=location))

        assert scraper.session.variables(0)["stateRegions"] == expected

    @pytest.mark.parametrize("location", [None, "Malaysia", "Atlantis"])
    def test_sends_no_state_filter_when_there_is_no_state(self, location):
        """An unresolvable location must not become an empty filter - the
        board returns 0 for a state it has no jobs in, not everything."""
        scraper = make_scraper([load("search_last_page.json")])
        scraper.scrape(an_input(location=location))

        assert scraper.session.variables(0).get("stateRegions") is None

    def test_a_remote_search_also_asks_for_the_remote_region(self):
        """Hiredly files fully-remote jobs under stateRegion "Remote", so a
        state filter alone excludes exactly what is_remote is looking for.
        Measured: ["Kuala Lumpur", "Remote"] is an OR (1210 + 3 = 1213)."""
        scraper = make_scraper([load("search_last_page.json")])
        scraper.scrape(an_input(location="Kuala Lumpur", is_remote=True))

        assert scraper.session.variables(0)["stateRegions"] == [
            "Kuala Lumpur",
            "Remote",
        ]

    def test_a_remote_search_without_a_location_sends_no_state_filter(self):
        """Nationwide already includes the Remote region; narrowing to it
        alone would drop remote-preference jobs filed under a real state."""
        scraper = make_scraper([load("search_last_page.json")])
        scraper.scrape(an_input(is_remote=True))

        assert scraper.session.variables(0).get("stateRegions") is None

    def test_omits_the_keyword_when_there_is_no_search_term(self):
        scraper = make_scraper([load("search_last_page.json")])
        scraper.scrape(an_input(search_term=None))

        assert scraper.session.variables(0).get("keyword") is None


class TestFilters:
    def test_is_remote_keeps_only_remote_jobs(self):
        scraper = make_scraper([load("search_page.json")])
        ids = {job.id for job in scraper.scrape(an_input(is_remote=True)).jobs}

        assert ids == {REMOTE_REGION_ID, REMOTE_PREF_ID}

    def test_is_remote_keeps_paging_past_a_page_of_mostly_non_remote_jobs(self):
        """The loop must count filtered jobs - the JobStreet F3 lesson.

        results_wanted=3 is chosen so the two outcomes differ: the first page
        has 9 jobs (enough, if counted unfiltered) but only 2 remote ones (not
        enough). Counting unfiltered jobs stops after one call.
        """
        scraper = make_scraper(
            [endless_page(), endless_page(), load("search_empty.json")]
        )
        scraper.scrape(an_input(is_remote=True, results_wanted=3))

        assert len(scraper.session.calls) == 3

    def test_a_filtered_search_stops_at_the_page_cap(self):
        pages = [endless_page() for _ in range(MAX_FILTERED_PAGES + 5)]
        scraper = make_scraper(pages)
        scraper.scrape(an_input(job_type=JobType.CONTRACT))

        assert len(scraper.session.calls) == MAX_FILTERED_PAGES

    def test_an_unfiltered_search_is_not_capped(self):
        """The cap is for filters that discard pages; plain paging stops on
        results_wanted and hasNextPage."""
        pages = [endless_page() for _ in range(MAX_FILTERED_PAGES + 2)]
        # Distinct ids per page so dedup does not stall the count.
        for number, page in enumerate(pages):
            for node in page["data"]["jobListsSearchResults"]["nodes"]:
                node["id"] = f"{node['id']}-{number}"
        scraper = make_scraper(pages)
        scraper.scrape(an_input(results_wanted=9 * (MAX_FILTERED_PAGES + 1)))

        assert len(scraper.session.calls) == MAX_FILTERED_PAGES + 1

    def test_job_type_keeps_only_that_type(self):
        scraper = make_scraper([load("search_page.json")])
        jobs = scraper.scrape(an_input(job_type=JobType.INTERNSHIP)).jobs

        assert jobs
        assert all(job.job_type == [JobType.INTERNSHIP] for job in jobs)

    def test_hours_old_is_hour_precise(self, frozen_now):
        """Cutoff 20:00 - 3h = 17:00 on 2026-09-24. Only the 18:54 record
        passes; 16:56, 15:48 and the rest of that same date do not - a
        date-only cutoff would keep all seven 2026-09-24 records."""
        scraper = make_scraper([load("search_page.json")])
        jobs = scraper.scrape(an_input(hours_old=3)).jobs

        kept = {job.id for job in jobs}
        assert kept == {"hd-ae1b3068-0265-4aa8-a132-dfe3fc58a4ec"}  # 18:54

    def test_hours_old_keeps_a_record_with_no_timestamp(self, frozen_now):
        scraper = make_scraper([load("search_malformed.json")])
        titles = {job.title for job in scraper.scrape(an_input(hours_old=1)).jobs}

        assert "Every optional field null" in titles


class TestFailures:
    def test_a_403_stops_and_keeps_what_was_already_collected(self):
        scraper = make_scraper(
            [endless_page(), FakeResponse({}, status_code=403), endless_page()]
        )
        # Distinct ids are not needed: page two is never parsed.
        jobs = scraper.scrape(an_input(results_wanted=100)).jobs

        assert len(scraper.session.calls) == 2
        assert len(jobs) == 9

    def test_a_server_error_stops(self):
        scraper = make_scraper([FakeResponse({}, status_code=500), endless_page()])
        assert scraper.scrape(an_input()).jobs == []
        assert len(scraper.session.calls) == 1

    def test_graphql_errors_stop(self):
        errors = {"errors": [{"message": "selectionMismatch"}]}
        scraper = make_scraper([errors, endless_page()])
        assert scraper.scrape(an_input()).jobs == []
        assert len(scraper.session.calls) == 1

    def test_a_non_dict_payload_does_not_raise(self):
        scraper = make_scraper([[1, 2, 3], endless_page()])
        assert scraper.scrape(an_input()).jobs == []

    def test_a_non_json_body_keeps_earlier_pages(self):
        """A Cloudflare challenge page can arrive with status 200."""

        class HtmlResponse(FakeResponse):
            def json(self):
                raise ValueError("Expecting value: line 1 column 1")

        scraper = make_scraper([endless_page(), HtmlResponse(None)])
        jobs = scraper.scrape(an_input(results_wanted=100)).jobs

        assert len(jobs) == 9
        assert len(scraper.session.calls) == 2

    def test_a_non_object_result_does_not_raise(self):
        scraper = make_scraper([{"data": {"jobListsSearchResults": [1, 2]}}])
        assert scraper.scrape(an_input()).jobs == []

    def test_a_null_node_is_skipped(self):
        page = load("search_last_page.json")
        page["data"]["jobListsSearchResults"]["nodes"].insert(0, None)
        jobs = make_scraper([page]).scrape(an_input()).jobs

        assert len(jobs) == 3

    def test_a_record_that_breaks_the_parser_costs_one_row(self):
        """One record of an unexpected type must not lose the page."""
        page = load("search_last_page.json")
        page["data"]["jobListsSearchResults"]["nodes"][0]["salary"] = 5000
        jobs = make_scraper([page]).scrape(an_input()).jobs

        assert len(jobs) == 2

    def test_a_request_exception_stops(self):
        class Raising(FakeSession):
            def post(self, url, json=None, timeout=None, **kwargs):
                self.calls.append({"url": url, "json": json})
                raise ConnectionError("reset")

        scraper = Hiredly()
        scraper.session = Raising([])
        assert scraper.scrape(an_input()).jobs == []
        assert len(scraper.session.calls) == 1

    def test_one_malformed_record_does_not_lose_the_page(self):
        scraper = make_scraper([load("search_malformed.json")])
        jobs = scraper.scrape(an_input()).jobs

        # 7 records: two have no id/title and are skipped, five survive.
        assert len(jobs) == 5


class TestConstruction:
    def test_description_format_is_passed_to_the_parser(self):
        scraper = make_scraper([load("search_page.json")])
        jobs = scraper.scrape(an_input(description_format=DescriptionFormat.HTML)).jobs

        assert "<p>" in jobs[0].description

    def test_user_agent_overrides_the_default_header(self):
        scraper = Hiredly(user_agent="custom-agent/1.0")

        assert scraper.user_agent == "custom-agent/1.0"
        assert scraper.session.headers["user-agent"] == "custom-agent/1.0"

    def test_queries_are_independent_across_scrapes(self):
        """seen_ids must reset, or a second search on one instance returns
        nothing it already saw."""
        scraper = make_scraper([load("search_page.json"), load("search_page.json")])
        # results_wanted=3 is met by one page, so each scrape reads exactly one.
        first = scraper.scrape(an_input(results_wanted=3))
        second = scraper.scrape(an_input(results_wanted=3))

        assert len(first.jobs) == len(second.jobs) > 0

    def test_does_not_mutate_the_payload(self):
        page = load("search_page.json")
        before = copy.deepcopy(page)
        make_scraper([page]).scrape(an_input())

        assert page == before
