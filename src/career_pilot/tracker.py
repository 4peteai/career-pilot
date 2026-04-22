"""Application tracker — reads/writes data/applications.md."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from career_pilot.models import Application, ApplicationStatus

TRACKER_HEADER = "| # | Company | Role | Score | Status | Date Added | URL | Notes |\n|---|---------|------|-------|--------|------------|-----|-------|\n"


def load_applications(tracker_path: Path) -> list[Application]:
    """Parse applications.md markdown table into Application models."""
    if not tracker_path.exists():
        return []

    text = tracker_path.read_text()
    apps: list[Application] = []

    for line in text.strip().split("\n"):
        line = line.strip()
        if not line.startswith("|") or line.startswith("| #") or line.startswith("|---"):
            continue

        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 7:
            continue

        try:
            report_num = int(cells[0]) if cells[0].isdigit() else 0
        except ValueError:
            report_num = 0

        try:
            score = float(cells[3]) if cells[3] else 0.0
        except ValueError:
            score = 0.0

        status_str = cells[4].strip()
        try:
            status = ApplicationStatus(status_str)
        except ValueError:
            status = ApplicationStatus.EVALUATED

        apps.append(
            Application(
                report_num=report_num,
                company=cells[1],
                role=cells[2],
                score=score,
                status=status,
                date_added=cells[5],
                url=cells[6],
                notes=cells[7] if len(cells) > 7 else "",
            )
        )

    return apps


def save_applications(tracker_path: Path, apps: list[Application]) -> None:
    """Write applications list back to markdown table."""
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [TRACKER_HEADER.strip()]

    for app in apps:
        line = (
            f"| {app.report_num} "
            f"| {app.company} "
            f"| {app.role} "
            f"| {app.score} "
            f"| {app.status.value} "
            f"| {app.date_added} "
            f"| {app.url} "
            f"| {app.notes} |"
        )
        lines.append(line)

    tracker_path.write_text("\n".join(lines) + "\n")


def add_application(
    tracker_path: Path,
    company: str,
    role: str,
    url: str,
    score: float,
    status: ApplicationStatus,
    report_num: int,
    notes: str = "",
) -> Application:
    """Add a new application entry to the tracker."""
    apps = load_applications(tracker_path)

    app = Application(
        company=company,
        role=role,
        url=url,
        score=score,
        status=status,
        report_num=report_num,
        date_added=datetime.now().strftime("%Y-%m-%d"),
        notes=notes,
    )
    apps.append(app)
    save_applications(tracker_path, apps)
    return app


def get_tracked_urls(tracker_path: Path) -> set[str]:
    """Extract all URLs from the tracker for dedup purposes."""
    apps = load_applications(tracker_path)
    return {app.url for app in apps if app.url}


def update_status(
    tracker_path: Path,
    report_num: int,
    new_status: ApplicationStatus,
) -> bool:
    """Update the status of an application by report number."""
    apps = load_applications(tracker_path)
    for app in apps:
        if app.report_num == report_num:
            app.status = new_status
            save_applications(tracker_path, apps)
            return True
    return False
