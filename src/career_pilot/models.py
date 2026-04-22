"""Shared data models for the career-pilot pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class JobSource(str, Enum):
    """Origin of a job listing (board API or inbound channel)."""

    GREENHOUSE = "greenhouse"
    ASHBY = "ashby"
    LEVER = "lever"
    LINKEDIN_EMAIL = "linkedin-email"
    MANUAL = "manual"


class ApplicationStatus(str, Enum):
    """Lifecycle state for a tracked application."""

    EVALUATED = "Evaluated"
    APPLIED = "Applied"
    RESPONDED = "Responded"
    INTERVIEW = "Interview"
    OFFER = "Offer"
    REJECTED = "Rejected"
    DISCARDED = "Discarded"
    SKIP = "Skip"


class LocationType(str, Enum):
    """Classification of a job's location for policy filtering."""

    REMOTE = "Remote"
    HYBRID = "Hybrid"
    ONSITE = "On-site"


class Job(BaseModel):
    """A job listing discovered from any source, pre-evaluation."""

    url: str
    company: str
    title: str
    source: JobSource
    location: str = ""
    location_type: LocationType | None = None
    description: str = ""
    seen_at: datetime = Field(default_factory=datetime.now)

    @property
    def slug(self) -> str:
        """Filesystem-safe identifier combining company and title."""
        return f"{self.company.lower().replace(' ', '-')}-{self.title.lower().replace(' ', '-')}"


class EvaluationBlock(BaseModel):
    """One labelled section of an evaluation response (A-F or Score)."""

    label: str
    content: str


class Evaluation(BaseModel):
    """Result of scoring a job against the candidate's CV."""

    job: Job
    archetype: str = ""
    score: float = 0.0
    blocks: list[EvaluationBlock] = Field(default_factory=list)
    report_path: str = ""
    report_num: int = 0


class Application(BaseModel):
    """A row in the application tracker — one job the candidate is pursuing."""

    company: str
    role: str
    url: str
    score: float = 0.0
    status: ApplicationStatus = ApplicationStatus.EVALUATED
    report_num: int = 0
    date_added: str = ""
    date_applied: str = ""
    notes: str = ""


class TitleFilter(BaseModel):
    """Positive/negative keyword lists used to gate job titles."""

    positive: list[str] = Field(default_factory=list)
    negative: list[str] = Field(default_factory=list)


class TrackedCompany(BaseModel):
    """Configuration for a single company tracked in the scanner."""

    career_url: str = ""
    scan_method: str = "greenhouse"
    api_endpoint: str = ""
    notes: str = ""


class PortalConfig(BaseModel):
    """Parsed `portals.yml` — filter rules, tracked companies, search queries."""

    title_filter: TitleFilter = Field(default_factory=TitleFilter)
    search_queries: list[dict[str, str]] = Field(default_factory=list)
    tracked_companies: dict[str, TrackedCompany] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> PortalConfig:
        """Load and validate a portals.yml file from disk."""
        raw = yaml.safe_load(path.read_text())
        if not raw:
            return cls()

        title_filter = TitleFilter(**(raw.get("title_filter", {})))

        companies: dict[str, TrackedCompany] = {}
        for name, cfg in raw.get("tracked_companies", {}).items():
            if isinstance(cfg, dict):
                companies[name] = TrackedCompany(**cfg)

        return cls(
            title_filter=title_filter,
            search_queries=raw.get("search_queries", []),
            tracked_companies=companies,
        )


class CandidateProfile(BaseModel):
    """Parsed `profile.yml` — identity, targets, compensation, location."""

    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    portfolio_url: str = ""
    github: str = ""
    target_roles: list[str] = Field(default_factory=list)
    archetypes: list[dict[str, Any]] = Field(default_factory=list)
    headline: str = ""
    compensation: dict[str, Any] = Field(default_factory=dict)
    country: str = ""
    city: str = ""
    timezone: str = ""

    @classmethod
    def load(cls, path: Path) -> CandidateProfile:
        """Load and validate a profile.yml file from disk."""
        raw = yaml.safe_load(path.read_text())
        if not raw:
            return cls()

        candidate = raw.get("candidate", {})
        narrative = raw.get("narrative", {})
        location = raw.get("location", {})
        roles = raw.get("target_roles", {})

        return cls(
            full_name=candidate.get("full_name", ""),
            email=candidate.get("email", ""),
            phone=candidate.get("phone", ""),
            location=candidate.get("location", ""),
            linkedin=candidate.get("linkedin", ""),
            portfolio_url=candidate.get("portfolio_url", ""),
            github=candidate.get("github", ""),
            target_roles=roles.get("primary", []),
            archetypes=roles.get("archetypes", []),
            headline=narrative.get("headline", ""),
            compensation=raw.get("compensation", {}),
            country=location.get("country", ""),
            city=location.get("city", ""),
            timezone=location.get("timezone", ""),
        )
