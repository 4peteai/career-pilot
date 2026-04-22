"""Job board API scanners for Greenhouse, Ashby, and Lever."""

from __future__ import annotations

from datetime import datetime

import httpx

from career_pilot.models import Job, JobSource


async def scan_greenhouse(company_slug: str) -> list[Job]:
    """Fetch open positions from Greenhouse boards API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    jobs: list[Job] = []
    for item in data.get("jobs", []):
        location = ""
        if item.get("location", {}).get("name"):
            location = item["location"]["name"]

        jobs.append(
            Job(
                url=item.get("absolute_url", ""),
                company=company_slug,
                title=item.get("title", ""),
                source=JobSource.GREENHOUSE,
                location=location,
                seen_at=datetime.now(),
            )
        )
    return jobs


async def scan_ashby(company_slug: str) -> list[Job]:
    """Fetch open positions from Ashby GraphQL API."""
    url = "https://jobs.ashbyhq.com/api/non-user-graphql"
    query = {
        "operationName": "ApiJobBoardWithTeams",
        "variables": {"organizationHostedJobsPageName": company_slug},
        "query": """
            query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
                jobBoard: jobBoardWithTeams(
                    organizationHostedJobsPageName: $organizationHostedJobsPageName
                ) {
                    teams {
                        ... on JobBoardTeam {
                            jobs {
                                id
                                title
                                locationName
                                employmentType
                                publishedAt
                            }
                        }
                    }
                }
            }
        """,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=query)
        resp.raise_for_status()
        data = resp.json()

    jobs: list[Job] = []
    board = data.get("data", {}).get("jobBoard", {})
    for team in board.get("teams", []):
        for item in team.get("jobs", []):
            job_id = item.get("id", "")
            jobs.append(
                Job(
                    url=f"https://jobs.ashbyhq.com/{company_slug}/{job_id}",
                    company=company_slug,
                    title=item.get("title", ""),
                    source=JobSource.ASHBY,
                    location=item.get("locationName", ""),
                    seen_at=datetime.now(),
                )
            )
    return jobs


async def scan_lever(company_slug: str) -> list[Job]:
    """Fetch open positions from Lever postings API."""
    url = f"https://api.lever.co/v0/postings/{company_slug}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params={"mode": "json"})
        resp.raise_for_status()
        data = resp.json()

    jobs: list[Job] = []
    for item in data if isinstance(data, list) else []:
        location = item.get("categories", {}).get("location", "")
        jobs.append(
            Job(
                url=item.get("hostedUrl", ""),
                company=company_slug,
                title=item.get("text", ""),
                source=JobSource.LEVER,
                location=location,
                seen_at=datetime.now(),
            )
        )
    return jobs


SCANNERS = {
    "greenhouse": scan_greenhouse,
    "ashby": scan_ashby,
    "lever": scan_lever,
}


async def scan_company(company_slug: str, method: str = "greenhouse") -> list[Job]:
    """Scan a single company using the specified method."""
    scanner = SCANNERS.get(method)
    if not scanner:
        raise ValueError(f"Unknown scan method: {method}. Use: {list(SCANNERS.keys())}")
    return await scanner(company_slug)
