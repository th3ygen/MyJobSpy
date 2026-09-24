"""Fixes to the two upstream default boards, Indeed and LinkedIn.

Mostly `user_agent`: scrape_jobs hands one to every board, so each board has
to decide what a caller's string means for its own endpoint.
"""

from __future__ import annotations

import jobspy.indeed as indeed_module
from jobspy.indeed import Indeed
from jobspy.indeed.constant import api_headers
from jobspy.linkedin import LinkedIn
from jobspy.linkedin.constant import headers as linkedin_headers
from jobspy.model import Country, ScraperInput, Site

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class TestLinkedIn:
    """LinkedIn scrapes web pages with a browser UA, so a caller's UA is
    just a different browser - honoured, as Glassdoor and JobStreet do."""

    def test_a_given_user_agent_is_sent(self):
        scraper = LinkedIn(user_agent=BROWSER_UA)

        assert scraper.user_agent == BROWSER_UA
        assert scraper.session.headers["user-agent"] == BROWSER_UA

    def test_without_one_the_default_is_kept(self):
        scraper = LinkedIn()

        assert scraper.user_agent is None
        assert scraper.session.headers["user-agent"] == linkedin_headers["user-agent"]


class FakeResponse:
    ok = True
    status_code = 200

    def json(self):
        return {
            "data": {"jobSearch": {"results": [], "pageInfo": {"nextCursor": None}}}
        }


class RecordingSession:
    def __init__(self):
        self.headers_sent = []

    def post(self, url, headers=None, **kwargs):
        self.headers_sent.append(headers)
        return FakeResponse()


class TestIndeed:
    """Indeed's API is the iPhone app's, and expects the app's UA. Measured
    2026-09-24: a desktop browser UA got a 403 from it, where the app UA
    returned results. Sending the caller's UA would let a UA meant for
    LinkedIn get Indeed blocked in the same scrape_jobs call."""

    def test_stores_the_user_agent(self):
        assert Indeed(user_agent=BROWSER_UA).user_agent == BROWSER_UA

    def test_keeps_the_app_user_agent_on_the_api(self, monkeypatch):
        session = RecordingSession()
        monkeypatch.setattr(indeed_module, "create_session", lambda **kwargs: session)
        scraper = Indeed(user_agent=BROWSER_UA)
        scraper.scrape(
            ScraperInput(
                site_type=[Site.INDEED],
                search_term="engineer",
                country=Country.MALAYSIA,
                results_wanted=5,
            )
        )

        assert session.headers_sent, "the scraper made no request"
        assert all(
            sent["user-agent"] == api_headers["user-agent"]
            for sent in session.headers_sent
        )


class QuerySession(RecordingSession):
    def __init__(self):
        super().__init__()
        self.queries = []

    def post(self, url, headers=None, json=None, **kwargs):
        self.queries.append(json["query"])
        return super().post(url, headers=headers, **kwargs)


def test_indeed_sends_a_radius_when_distance_is_none(monkeypatch):
    """`radius: None` is invalid GraphQL - Indeed answered 400, and still
    400 with the radius left out, so it needs one whenever a location is
    given. None falls back to scrape_jobs' own default of 50."""
    session = QuerySession()
    monkeypatch.setattr(indeed_module, "create_session", lambda **kwargs: session)
    Indeed().scrape(
        ScraperInput(
            site_type=[Site.INDEED],
            search_term="engineer",
            location="Kuala Lumpur",
            country=Country.MALAYSIA,
            distance=None,
            results_wanted=5,
        )
    )

    assert session.queries
    assert "radius: None" not in session.queries[0]
    assert "radius: 50" in session.queries[0]
