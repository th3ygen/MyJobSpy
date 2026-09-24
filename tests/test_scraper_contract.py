"""The contract every registered scraper must satisfy.

These run offline against the class, not a scrape, so they cost nothing and
catch the conventions a new board gets wrong at registration time: a missing
registry entry, a constructor that drops `user_agent`, no exception class.

When you add a board, these tests should fail until you have wired it up
properly. That is the point — they encode steps 1–3 of the "Adding a new job
board" recipe in CLAUDE.md so the recipe cannot be half-followed.
"""

from __future__ import annotations

import inspect

import pytest

import jobspy.exception as exception_module
from jobspy import SCRAPER_MAPPING
from jobspy.model import SITE_DISPLAY_NAMES, JobResponse, Scraper, ScraperInput, Site

REGISTERED = sorted(SCRAPER_MAPPING.items(), key=lambda item: item[0].value)

# Parametrize by site value so a failure names the board, not "<class ...>".
BOARDS = [pytest.param(cls, id=site.value) for site, cls in REGISTERED]


# Upstream scrapers that accept `user_agent` but never forward it to
# `super().__init__`, leaving `self.user_agent` unset. Grandfathered rather
# than fixed here: repairing them is a change to inherited scraper behaviour,
# not to this fork's contract. A NEW board must not join this list — the whole
# reason it exists is to stop the bug spreading to the Malaysian boards.
#
# See the matching gotcha in CLAUDE.md.
USER_AGENT_NOT_FORWARDED = {
    "zip_recruiter",
    "google",
    "bayt",
    "naukri",
    "bdjobs",
}


def test_every_site_has_a_scraper() -> None:
    """A Site member with no registry entry raises KeyError mid-scrape."""
    missing = [site.value for site in Site if site not in SCRAPER_MAPPING]
    assert not missing, f"Site members with no SCRAPER_MAPPING entry: {missing}"


def test_no_scraper_is_registered_twice() -> None:
    classes = [cls for _, cls in REGISTERED]
    assert len(set(classes)) == len(classes), "a scraper class is mapped to two sites"


@pytest.mark.parametrize("scraper_cls", BOARDS)
def test_subclasses_scraper(scraper_cls: type) -> None:
    assert issubclass(scraper_cls, Scraper)


@pytest.mark.parametrize("scraper_cls", BOARDS)
def test_accepts_the_three_standard_constructor_kwargs(scraper_cls: type) -> None:
    """scrape_jobs calls every scraper with exactly these three kwargs."""
    parameters = inspect.signature(scraper_cls.__init__).parameters
    for name in ("proxies", "ca_cert", "user_agent"):
        assert name in parameters, f"{scraper_cls.__name__}.__init__ lacks {name!r}"


@pytest.mark.parametrize("scraper_cls", BOARDS)
def test_constructs_with_no_arguments(scraper_cls: type) -> None:
    """All three kwargs must default, and construction must not hit the network."""
    scraper = scraper_cls()
    assert isinstance(scraper, Scraper)


@pytest.mark.parametrize("scraper_cls", BOARDS)
def test_records_its_own_site(scraper_cls: type) -> None:
    """`self.site` must match the key it is registered under.

    A mismatch mislabels every row the board produces, and the `site` column
    is what callers filter on.
    """
    registered_site = next(site for site, cls in REGISTERED if cls is scraper_cls)
    assert scraper_cls().site == registered_site


@pytest.mark.parametrize("scraper_cls", BOARDS)
def test_forwards_user_agent_to_super(scraper_cls: type) -> None:
    """`self.user_agent` must survive construction.

    scrape_jobs passes `user_agent` to every scraper, but a constructor that
    takes it and forgets to hand it to `super().__init__` silently ignores it.
    """
    site_value = scraper_cls().site.value
    if site_value in USER_AGENT_NOT_FORWARDED:
        pytest.xfail(f"{site_value} drops user_agent (inherited from upstream)")

    scraper = scraper_cls(user_agent="contract-test-agent")
    assert scraper.user_agent == "contract-test-agent"


@pytest.mark.parametrize("scraper_cls", BOARDS)
def test_scrape_takes_a_scraper_input_and_is_implemented(scraper_cls: type) -> None:
    assert not getattr(scraper_cls.scrape, "__isabstractmethod__", False)

    parameters = list(inspect.signature(scraper_cls.scrape).parameters)
    assert parameters[1:2] == ["scraper_input"], (
        f"{scraper_cls.__name__}.scrape must take scraper_input as its first "
        f"argument, got {parameters}"
    )


@pytest.mark.parametrize("scraper_cls", BOARDS)
def test_has_an_exception_class(scraper_cls: type) -> None:
    """Step 3 of the recipe. Without it a board failure raises a bare Exception."""
    exceptions = {
        name.lower()
        for name, obj in vars(exception_module).items()
        if isinstance(obj, type) and issubclass(obj, Exception)
    }
    # LinkedIn -> LinkedInException, BaytScraper -> BaytException. The stem may
    # carry a qualifier before "Exception" (Google -> GoogleJobsException), so
    # match on the prefix rather than demanding an exact name.
    stem = scraper_cls.__name__.lower().removesuffix("scraper")
    assert any(
        name.startswith(stem) and name.endswith("exception") for name in exceptions
    ), (
        f"no {stem.capitalize()}...Exception in jobspy/exception.py for "
        f"{scraper_cls.__name__}"
    )


def test_scraper_input_and_job_response_are_the_shared_contract() -> None:
    """Guards the two types every scraper signature refers to."""
    assert issubclass(JobResponse, object) and hasattr(JobResponse, "model_fields")
    assert "jobs" in JobResponse.model_fields
    assert "results_wanted" in ScraperInput.model_fields


# --- Log display names -------------------------------------------------------
#
# `scrape_jobs` used to derive a board's log name with
# `site.value.capitalize()`, then hand-patch the boards that broke:
# "Zip_recruiter" -> "ZipRecruiter", "Linkedin" -> "LinkedIn". Boards added
# after those patches were written inherited the bug silently — JobStreet
# logged its own lines under "JobStreet" and the orchestrator's under
# "Jobstreet", and BDJobs under "BDJobs" and "Bdjobs". The map below makes a
# missing entry a test failure rather than a cosmetic split nobody notices.


def test_every_site_has_a_display_name() -> None:
    """A new board must declare its log name, not inherit a guess."""
    missing = sorted(site.value for site in Site if site not in SITE_DISPLAY_NAMES)
    assert missing == [], f"no SITE_DISPLAY_NAMES entry for: {', '.join(missing)}"


@pytest.mark.parametrize(
    "site,expected",
    [
        pytest.param(Site.JOBSTREET, "JobStreet", id="jobstreet"),
        pytest.param(Site.BDJOBS, "BDJobs", id="bdjobs"),
        pytest.param(Site.ZIP_RECRUITER, "ZipRecruiter", id="zip_recruiter"),
        pytest.param(Site.LINKEDIN, "LinkedIn", id="linkedin"),
    ],
)
def test_display_name_matches_the_boards_own_logger(site: Site, expected: str) -> None:
    """The four names `.capitalize()` cannot produce.

    Each is the string that board's own module passes to `create_logger`, so
    one board logs under exactly one name.
    """
    assert site.display_name == expected
