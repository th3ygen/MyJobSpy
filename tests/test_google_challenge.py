"""Google Search now answers non-JavaScript clients with a challenge page.

Measured 2026-09-24: status 200, ~93KB, 99% script, no results markup, and a
<noscript> redirect to /httpservice/retry/enablejs. The scraper used to read
that as "no cursor found" and suggest the query was wrong. These tests pin
that it now says what actually happened.
"""

from __future__ import annotations

from pathlib import Path

import jobspy.google as google_module
from jobspy.google import Google
from jobspy.google.util import is_javascript_challenge
from jobspy.model import Country, ScraperInput, Site

CHALLENGE = (
    Path(__file__).parent / "fixtures" / "google" / "js_challenge.html"
).read_text(encoding="utf-8")

# Just enough of the old results markup to be told apart from the challenge.
RESULTS_PAGE = (
    '<html><body><div jsname="Yust4d" data-async-fc="abc"></div></body></html>'
)


class FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.status_code = 200


class FakeSession:
    def __init__(self, text: str):
        self.text = text
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        return FakeResponse(self.text)


class RecordingLog:
    def __init__(self):
        self.lines: list[tuple[str, str]] = []

    def __getattr__(self, level):
        return lambda message, *a, **k: self.lines.append((level, message))


def run(monkeypatch, text: str):
    session = FakeSession(text)
    log = RecordingLog()
    monkeypatch.setattr(google_module, "create_session", lambda **kwargs: session)
    monkeypatch.setattr(google_module, "log", log)
    jobs = (
        Google()
        .scrape(
            ScraperInput(
                site_type=[Site.GOOGLE],
                search_term="software engineer",
                country=Country.MALAYSIA,
                results_wanted=20,
            )
        )
        .jobs
    )
    return jobs, session, log


class TestDetection:
    def test_recognises_the_captured_challenge_page(self):
        assert is_javascript_challenge(CHALLENGE) is True

    def test_does_not_flag_a_results_page(self):
        assert is_javascript_challenge(RESULTS_PAGE) is False

    def test_does_not_flag_an_empty_body(self):
        assert is_javascript_challenge("") is False


class TestScraper:
    def test_returns_no_jobs_and_says_why(self, monkeypatch):
        jobs, _, log = run(monkeypatch, CHALLENGE)

        assert jobs == []
        errors = [message for level, message in log.lines if level == "error"]
        assert len(errors) == 1
        assert "JavaScript" in errors[0]

    def test_no_longer_blames_the_query(self, monkeypatch):
        """The old warning told users to change their query - wrong advice
        for a page that never contained results."""
        _, _, log = run(monkeypatch, CHALLENGE)

        assert not any("changing your query" in message for _, message in log.lines)

    def test_does_not_page_past_the_challenge(self, monkeypatch):
        _, session, _ = run(monkeypatch, CHALLENGE)

        assert session.calls == 1
