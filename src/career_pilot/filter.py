"""Filter and dedup engine for job listings."""

from __future__ import annotations

import json
import re
from pathlib import Path

from career_pilot.models import Job, LocationType, PortalConfig


def load_seen_urls(history_path: Path) -> set[str]:
    """Load previously seen job URLs from scan history."""
    if not history_path.exists():
        return set()
    data = json.loads(history_path.read_text())
    return set(data.get("seen_urls", []))


def save_seen_urls(history_path: Path, urls: set[str]) -> None:
    """Persist seen URLs to scan history."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps({"seen_urls": sorted(urls)}, indent=2))


def matches_title_filter(title: str, config: PortalConfig) -> bool:
    """Check if a job title passes positive/negative keyword filters."""
    title_lower = title.lower()
    tf = config.title_filter

    # Must match at least one positive keyword (if any defined)
    if tf.positive:
        has_positive = any(kw.lower() in title_lower for kw in tf.positive)
        if not has_positive:
            return False

    # Must not match any negative keyword
    if tf.negative:
        has_negative = any(kw.lower() in title_lower for kw in tf.negative)
        if has_negative:
            return False

    return True


def classify_location(location_str: str) -> LocationType | None:
    """Classify a location string into Remote/Hybrid/On-site."""
    loc = location_str.lower()
    if not loc:
        return None

    if "remote" in loc:
        return LocationType.REMOTE
    if "hybrid" in loc:
        return LocationType.HYBRID

    # Keywords that suggest on-site
    onsite_patterns = [
        r"\b(office|on-?site|in-?person)\b",
    ]
    for pattern in onsite_patterns:
        if re.search(pattern, loc):
            return LocationType.ONSITE

    # If it's just a city/country name, assume on-site
    if loc.strip() and "remote" not in loc and "hybrid" not in loc:
        return LocationType.ONSITE

    return None


def passes_location_rules(
    job: Job,
    home_country: str = "Bulgaria",
    home_city: str = "Sofia",
) -> bool:
    """Apply location rules: home country = hybrid/remote OK, world = remote only."""
    loc_type = job.location_type or classify_location(job.location)
    location_lower = job.location.lower()

    # Remote is always OK
    if loc_type == LocationType.REMOTE:
        return True

    # Check if the job is in the home country/city
    is_home = (
        home_country.lower() in location_lower or home_city.lower() in location_lower
    )

    if is_home:
        # Accept hybrid or on-site in home location
        return True

    # Non-home location: only remote passes
    if loc_type in (LocationType.HYBRID, LocationType.ONSITE):
        return False

    # Unknown location type — let it through for manual review
    return True


def filter_and_dedup(
    jobs: list[Job],
    config: PortalConfig,
    seen_urls: set[str],
    tracker_urls: set[str] | None = None,
    home_country: str = "Bulgaria",
    home_city: str = "Sofia",
) -> list[Job]:
    """Apply all filters: title, location, dedup. Returns qualified jobs."""
    tracker_urls = tracker_urls or set()
    result: list[Job] = []

    for job in jobs:
        # Dedup: skip if already seen or in tracker
        if job.url in seen_urls or job.url in tracker_urls:
            continue

        # Title filter
        if not matches_title_filter(job.title, config):
            continue

        # Location rules
        if not passes_location_rules(job, home_country, home_city):
            continue

        result.append(job)

    return result
