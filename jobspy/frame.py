from __future__ import annotations

import pandas as pd

from jobspy.model import Country, JobResponse, Location, SalarySource
from jobspy.util import convert_to_annual, desired_order, extract_salary


def build_jobs_dataframe(
    site_to_jobs: dict[str, JobResponse],
    *,
    country_enum: Country,
    enforce_annual_salary: bool = False,
) -> pd.DataFrame:
    """Flattens scraped JobPosts into the canonical output DataFrame."""
    jobs_dfs: list[pd.DataFrame] = []

    for site, job_response in site_to_jobs.items():
        for job in job_response.jobs:
            job_data = job.model_dump()
            job_data["site"] = site
            job_data["company"] = job_data["company_name"]
            job_data["job_type"] = (
                ", ".join(job_type.value[0] for job_type in job_data["job_type"])
                if job_data["job_type"]
                else None
            )
            job_data["emails"] = (
                ", ".join(job_data["emails"]) if job_data["emails"] else None
            )
            if job_data["location"]:
                location = Location(**job_data["location"])
                job_data["city"] = location.city
                job_data["state"] = location.state
                job_data["location"] = location.display_location()

            compensation_obj = job_data.get("compensation")
            if compensation_obj and isinstance(compensation_obj, dict):
                job_data["interval"] = (
                    compensation_obj.get("interval").value
                    if compensation_obj.get("interval")
                    else None
                )
                job_data["min_amount"] = compensation_obj.get("min_amount")
                job_data["max_amount"] = compensation_obj.get("max_amount")
                job_data["currency"] = compensation_obj.get("currency", "USD")
                # A populated `compensation` is not by itself evidence the
                # board supplied the figure: the Malaysian pipeline writes
                # description-parsed MYR salary into the same field. Trust
                # the marker the pipeline sets, and default to direct_data
                # for every other path (where nothing parses into
                # `compensation`, so the board is the only source).
                job_data["salary_source"] = (
                    SalarySource.DESCRIPTION.value
                    if job_data.get("salary_parsed_from_description")
                    else SalarySource.DIRECT_DATA.value
                )
                if enforce_annual_salary and (
                    job_data["interval"]
                    and job_data["interval"] != "yearly"
                    and job_data["min_amount"]
                    and job_data["max_amount"]
                ):
                    convert_to_annual(job_data)
            elif country_enum == Country.USA:
                (
                    job_data["interval"],
                    job_data["min_amount"],
                    job_data["max_amount"],
                    job_data["currency"],
                ) = extract_salary(
                    job_data["description"],
                    enforce_annual_salary=enforce_annual_salary,
                )
                job_data["salary_source"] = SalarySource.DESCRIPTION.value

            job_data["salary_source"] = (
                job_data.get("salary_source") if job_data.get("min_amount") else None
            )

            job_data["skills"] = (
                ", ".join(job_data["skills"]) if job_data["skills"] else None
            )

            jobs_dfs.append(pd.DataFrame([job_data]))

    if not jobs_dfs:
        return pd.DataFrame()

    filtered_dfs = [df.dropna(axis=1, how="all") for df in jobs_dfs]
    jobs_df = pd.concat(filtered_dfs, ignore_index=True)

    for column in desired_order:
        if column not in jobs_df.columns:
            jobs_df[column] = None

    jobs_df = jobs_df[desired_order]
    return jobs_df.sort_values(
        by=["site", "date_posted"], ascending=[True, False]
    ).reset_index(drop=True)
