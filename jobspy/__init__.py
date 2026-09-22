from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple

import pandas as pd

from jobspy.bayt import BaytScraper
from jobspy.bdjobs import BDJobs
from jobspy.glassdoor import Glassdoor
from jobspy.google import Google
from jobspy.indeed import Indeed
from jobspy.linkedin import LinkedIn
from jobspy.naukri import Naukri
from jobspy.frame import build_jobs_dataframe
from jobspy.malaysia import normalize as malaysia_normalize
from jobspy.model import JobType, JobResponse, Country
from jobspy.model import ScraperInput, Site
from jobspy.util import (
    set_logger_level,
    create_logger,
    get_enum_from_value,
    map_str_to_site,
)
from jobspy.ziprecruiter import ZipRecruiter


# Update the SCRAPER_MAPPING dictionary in the scrape_jobs function


def scrape_jobs(
    site_name: str | list[str] | Site | list[Site] | None = None,
    search_term: str | None = None,
    google_search_term: str | None = None,
    location: str | None = None,
    distance: int | None = 50,
    is_remote: bool = False,
    job_type: str | None = None,
    easy_apply: bool | None = None,
    results_wanted: int = 15,
    country_indeed: str = "malaysia",
    proxies: list[str] | str | None = None,
    ca_cert: str | None = None,
    description_format: str = "markdown",
    linkedin_fetch_description: bool | None = False,
    linkedin_company_ids: list[int] | None = None,
    offset: int | None = 0,
    hours_old: int = None,
    enforce_annual_salary: bool = False,
    group_duplicates: bool = True,
    include_remote: bool = True,
    verbose: int = 0,
    user_agent: str = None,
    **kwargs,
) -> pd.DataFrame:
    """
    Scrapes job data from job boards concurrently
    :return: Pandas DataFrame containing job data
    """
    SCRAPER_MAPPING = {
        Site.LINKEDIN: globals()["LinkedIn"],
        Site.INDEED: globals()["Indeed"],
        Site.ZIP_RECRUITER: globals()["ZipRecruiter"],
        Site.GLASSDOOR: globals()["Glassdoor"],
        Site.GOOGLE: globals()["Google"],
        Site.BAYT: globals()["BaytScraper"],
        Site.NAUKRI: globals()["Naukri"],
        Site.BDJOBS: globals()["BDJobs"],
    }
    set_logger_level(verbose)
    job_type = get_enum_from_value(job_type) if job_type else None

    def get_site_type():
        site_types = list(Site)
        if isinstance(site_name, str):
            site_types = [map_str_to_site(site_name)]
        elif isinstance(site_name, Site):
            site_types = [site_name]
        elif isinstance(site_name, list):
            site_types = [
                map_str_to_site(site) if isinstance(site, str) else site
                for site in site_name
            ]
        return site_types

    country_enum = Country.from_string(country_indeed)

    scraper_input = ScraperInput(
        site_type=get_site_type(),
        country=country_enum,
        search_term=search_term,
        google_search_term=google_search_term,
        location=location,
        distance=distance,
        is_remote=is_remote,
        job_type=job_type,
        easy_apply=easy_apply,
        description_format=description_format,
        linkedin_fetch_description=linkedin_fetch_description,
        results_wanted=results_wanted,
        linkedin_company_ids=linkedin_company_ids,
        offset=offset,
        hours_old=hours_old,
    )

    def scrape_site(site: Site, site_input: ScraperInput) -> Tuple[str, JobResponse]:
        scraper_class = SCRAPER_MAPPING[site]
        scraper = scraper_class(proxies=proxies, ca_cert=ca_cert, user_agent=user_agent)
        scraped_data: JobResponse = scraper.scrape(site_input)
        cap_name = site.value.capitalize()
        site_display = "ZipRecruiter" if cap_name == "Zip_recruiter" else cap_name
        site_display = "LinkedIn" if cap_name == "Linkedin" else site_display
        create_logger(site_display).info("finished scraping")
        return site.value, scraped_data

    site_to_jobs_dict: dict[str, JobResponse] = {}

    # The located pass and the remote pass overlap heavily; exact dedup in the
    # Malaysia pipeline absorbs the duplicates.
    passes: list[ScraperInput] = [scraper_input]
    if include_remote and not is_remote:
        remote_input = scraper_input.model_copy(deep=True)
        remote_input.is_remote = True
        passes.append(remote_input)

    jobs_to_run = [
        (site, site_input) for site in scraper_input.site_type for site_input in passes
    ]

    with ThreadPoolExecutor() as executor:
        future_to_site = {
            executor.submit(scrape_site, site, site_input): site
            for site, site_input in jobs_to_run
        }

        for future in as_completed(future_to_site):
            site = future_to_site[future]
            try:
                site_value, scraped_data = future.result()
            except Exception as exc:  # noqa: BLE001 - one board must not kill the run
                create_logger(site.value.capitalize()).error(
                    f"scrape failed, continuing without it: {exc}"
                )
                site_to_jobs_dict.setdefault(site.value, JobResponse(jobs=[]))
                continue
            existing = site_to_jobs_dict.setdefault(site_value, JobResponse(jobs=[]))
            existing.jobs.extend(scraped_data.jobs)

    if country_enum == Country.MALAYSIA:
        # Site attribution lives in the dict key, not on JobPost, so remember
        # which site each job came from before flattening for the pipeline.
        site_by_job = {
            id(job): site_value
            for site_value, response in site_to_jobs_dict.items()
            for job in response.jobs
        }
        all_jobs = [job for r in site_to_jobs_dict.values() for job in r.jobs]
        normalized = malaysia_normalize(all_jobs, group_duplicates=group_duplicates)

        regrouped = {
            site_value: JobResponse(jobs=[]) for site_value in site_to_jobs_dict
        }
        for job in normalized:
            site_value = site_by_job.get(id(job))
            if site_value is None:
                # normalize() is documented to return the same objects it
                # was given, so this should be unreachable. If that
                # contract ever breaks, fail soft (log + keep the job under
                # an "unknown" bucket) rather than raising and taking the
                # whole scrape down - the exact failure mode this task
                # exists to eliminate.
                create_logger("Malaysia").warning(
                    f"normalize() returned a job with no known origin site, "
                    f"keeping it under 'unknown': {job.job_url!r}"
                )
                site_value = "unknown"
                regrouped.setdefault(site_value, JobResponse(jobs=[]))
            regrouped[site_value].jobs.append(job)
        site_to_jobs_dict = regrouped

    return build_jobs_dataframe(
        site_to_jobs_dict,
        country_enum=country_enum,
        enforce_annual_salary=enforce_annual_salary,
    )


# Add BDJobs to __all__
__all__ = [
    "BDJobs",
]
