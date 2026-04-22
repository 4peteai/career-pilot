"""CLI entry point — all career-pilot commands."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()

app = typer.Typer(
    name="career-pilot",
    help="AI-powered job search pipeline — scan, filter, evaluate, and track opportunities.",
    no_args_is_help=True,
)

console = Console()

# Default paths relative to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
OUTPUT_DIR = PROJECT_ROOT / "output"


def _resolve_paths() -> tuple[Path, Path, Path, Path, Path, Path]:
    """Resolve all project paths."""
    profile = CONFIG_DIR / "profile.yml"
    cv = CONFIG_DIR / "cv.md"
    portals = CONFIG_DIR / "portals.yml"
    tracker = DATA_DIR / "applications.md"
    history = DATA_DIR / "scan_history.json"
    return profile, cv, portals, tracker, history, REPORTS_DIR


# ── Scan ──────────────────────────────────────────────────────────────

@app.command()
def scan(
    company: Optional[str] = typer.Option(None, help="Scan a single company by slug"),
    method: str = typer.Option("greenhouse", help="Scan method: greenhouse, ashby, lever"),
    all: bool = typer.Option(False, "--all", help="Scan all companies from portals.yml"),
) -> None:
    """Scan job boards (Greenhouse, Ashby, Lever) for new listings."""
    from career_pilot.filter import (
        filter_and_dedup,
        load_seen_urls,
        save_seen_urls,
    )
    from career_pilot.models import PortalConfig
    from career_pilot.scanner import scan_company
    from career_pilot.tracker import get_tracked_urls

    profile, cv, portals_path, tracker, history, _ = _resolve_paths()
    config = PortalConfig.load(portals_path)
    seen = load_seen_urls(history)
    tracked = get_tracked_urls(tracker)

    async def _scan() -> None:
        all_jobs = []

        if all:
            for name, comp in config.tracked_companies.items():
                console.print(f"[cyan]Scanning {name}...[/cyan]")
                try:
                    jobs = await scan_company(name, comp.scan_method or "greenhouse")
                    all_jobs.extend(jobs)
                    console.print(f"  Found {len(jobs)} listings")
                except Exception as e:
                    console.print(f"  [red]Error: {e}[/red]")
        elif company:
            console.print(f"[cyan]Scanning {company} via {method}...[/cyan]")
            jobs = await scan_company(company, method)
            all_jobs.extend(jobs)
        else:
            console.print("[red]Specify --company or --all[/red]")
            raise typer.Exit(1)

        # Filter and dedup
        qualified = filter_and_dedup(all_jobs, config, seen, tracked)

        # Update seen URLs
        for job in all_jobs:
            seen.add(job.url)
        save_seen_urls(history, seen)

        # Report results
        if qualified:
            table = Table(title=f"New Qualified Jobs ({len(qualified)})")
            table.add_column("Company")
            table.add_column("Title")
            table.add_column("Location")
            table.add_column("Source")
            for job in qualified:
                table.add_row(job.company, job.title, job.location, job.source.value)
            console.print(table)
        else:
            console.print("[dim]No new qualified jobs found.[/dim]")

    asyncio.run(_scan())


# ── Gmail Fetch ───────────────────────────────────────────────────────

@app.command("gmail-fetch")
def gmail_fetch(
    days: int = typer.Option(7, help="Look back N days for alert emails"),
) -> None:
    """Fetch LinkedIn job alerts from Gmail via IMAP."""
    from career_pilot.filter import (
        filter_and_dedup,
        load_seen_urls,
        save_seen_urls,
    )
    from career_pilot.gmail import fetch_linkedin_alerts
    from career_pilot.models import PortalConfig
    from career_pilot.tracker import get_tracked_urls

    _, _, portals_path, tracker, history, _ = _resolve_paths()
    config = PortalConfig.load(portals_path)
    seen = load_seen_urls(history)
    tracked = get_tracked_urls(tracker)

    console.print(f"[cyan]Fetching LinkedIn alerts from Gmail (last {days} days)...[/cyan]")
    try:
        jobs = fetch_linkedin_alerts(days_back=days)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(f"  Found {len(jobs)} job links in alert emails")

    qualified = filter_and_dedup(jobs, config, seen, tracked)

    for job in jobs:
        seen.add(job.url)
    save_seen_urls(history, seen)

    if qualified:
        table = Table(title=f"New Jobs from LinkedIn Alerts ({len(qualified)})")
        table.add_column("Title")
        table.add_column("URL", max_width=60)
        for job in qualified:
            table.add_row(job.title, job.url)
        console.print(table)
    else:
        console.print("[dim]No new qualified jobs from Gmail.[/dim]")


# ── Evaluate ──────────────────────────────────────────────────────────

@app.command()
def evaluate(
    url: str = typer.Argument(help="Job posting URL to evaluate"),
    company: str = typer.Option("", help="Company name (auto-detected if omitted)"),
    title: str = typer.Option("", help="Job title (auto-detected if omitted)"),
    description: str = typer.Option("", help="Job description text (reads from stdin if '-')"),
    model: str = typer.Option("claude-sonnet-4-6", help="Claude model for evaluation"),
) -> None:
    """Evaluate a job posting against your CV using Claude."""
    import sys

    from career_pilot.evaluator import evaluate_job, score_to_status
    from career_pilot.models import Job, JobSource
    from career_pilot.tracker import add_application

    profile, cv, _, tracker, _, reports = _resolve_paths()

    # Read description from stdin if '-'
    desc = description
    if description == "-":
        desc = sys.stdin.read()

    job = Job(
        url=url,
        company=company or _extract_company(url),
        title=title or "(auto-detect)",
        source=JobSource.MANUAL,
        description=desc,
    )

    console.print(f"[cyan]Evaluating: {job.company} — {job.title}[/cyan]")
    console.print(f"  URL: {url}")
    console.print(f"  Model: {model}")

    async def _eval() -> None:
        evaluation = await evaluate_job(job, cv, profile, reports, model=model)
        status = score_to_status(evaluation.score)

        # Add to tracker
        add_application(
            tracker,
            company=job.company,
            role=job.title,
            url=url,
            score=evaluation.score,
            status=status,
            report_num=evaluation.report_num,
        )

        console.print(f"\n[bold]Score: {evaluation.score} / 5.0[/bold]")
        console.print(f"Status: {status.value}")
        console.print(f"Report: {evaluation.report_path}")

    asyncio.run(_eval())


# ── PDF ───────────────────────────────────────────────────────────────

@app.command()
def pdf(
    company: str = typer.Argument(help="Target company name"),
    job_title: str = typer.Option("", help="Target job title"),
    page_format: str = typer.Option("A4", help="Page format: A4 or Letter"),
) -> None:
    """Generate a tailored CV PDF for a specific company/role."""
    from career_pilot.pdf import generate_cv_pdf

    profile, cv, _, _, _, _ = _resolve_paths()

    console.print(f"[cyan]Generating CV PDF for {company}...[/cyan]")

    async def _gen() -> None:
        path = await generate_cv_pdf(
            profile_path=profile,
            cv_path=cv,
            job_title=job_title,
            company=company,
            output_dir=OUTPUT_DIR,
            page_format=page_format,
        )
        console.print(f"[green]PDF saved: {path}[/green]")

    asyncio.run(_gen())


# ── Track ─────────────────────────────────────────────────────────────

@app.command()
def track(
    status: Optional[str] = typer.Option(None, help="Filter by status"),
) -> None:
    """View the application tracker."""
    from career_pilot.tracker import load_applications

    _, _, _, tracker, _, _ = _resolve_paths()
    apps = load_applications(tracker)

    if status:
        apps = [a for a in apps if a.status.value.lower() == status.lower()]

    if not apps:
        console.print("[dim]No applications tracked yet.[/dim]")
        return

    table = Table(title=f"Applications ({len(apps)})")
    table.add_column("#", justify="right")
    table.add_column("Company")
    table.add_column("Role")
    table.add_column("Score", justify="right")
    table.add_column("Status")
    table.add_column("Date")

    for a in apps:
        table.add_row(
            str(a.report_num),
            a.company,
            a.role,
            str(a.score),
            a.status.value,
            a.date_added,
        )

    console.print(table)


# ── Dashboard ─────────────────────────────────────────────────────────

@app.command()
def dashboard() -> None:
    """Launch the interactive pipeline dashboard (TUI)."""
    from career_pilot.dashboard import run_dashboard

    _, _, _, tracker, _, _ = _resolve_paths()
    run_dashboard(tracker)


# ── Schedule ──────────────────────────────────────────────────────────

@app.command()
def schedule(
    action: str = typer.Argument(help="install or remove"),
    hours: str = typer.Option("9,18", help="Comma-separated hours for scans (24h)"),
) -> None:
    """Install or remove scheduled twice-daily scans."""
    from career_pilot.scheduler import install_schedule, remove_schedule

    if action == "install":
        hour_list = [int(h.strip()) for h in hours.split(",")]
        msg = install_schedule(hour_list)
        console.print(f"[green]{msg}[/green]")
    elif action == "remove":
        msg = remove_schedule()
        console.print(f"[yellow]{msg}[/yellow]")
    else:
        console.print("[red]Usage: career-pilot schedule [install|remove][/red]")
        raise typer.Exit(1)


# ── Init ──────────────────────────────────────────────────────────────

@app.command()
def init() -> None:
    """Initialize career-pilot config (interactive setup)."""
    console.print("[bold]Career Pilot — First-Time Setup[/bold]\n")

    profile, cv, portals, tracker, _, _ = _resolve_paths()

    for path, label in [(profile, "profile.yml"), (cv, "cv.md"), (portals, "portals.yml")]:
        if path.exists():
            console.print(f"  [green]Found {label}[/green]")
        else:
            console.print(f"  [yellow]Missing {label} — copy from config/ examples[/yellow]")

    if not tracker.exists():
        from career_pilot.tracker import TRACKER_HEADER

        tracker.parent.mkdir(parents=True, exist_ok=True)
        tracker.write_text(TRACKER_HEADER)
        console.print("  [green]Created empty applications.md tracker[/green]")

    console.print("\n[bold]Setup complete.[/bold] Next steps:")
    console.print("  1. Edit config/profile.yml with your details")
    console.print("  2. Place your CV in config/cv.md")
    console.print("  3. Configure target companies in config/portals.yml")
    console.print("  4. Set ANTHROPIC_API_KEY in .env")
    console.print("  5. Run: career-pilot scan --all")


# ── Helpers ───────────────────────────────────────────────────────────

def _extract_company(url: str) -> str:
    """Best-effort company extraction from job URL."""
    import re
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or ""

    # Greenhouse: boards.greenhouse.io/company
    if "greenhouse" in host:
        parts = parsed.path.strip("/").split("/")
        if parts:
            return parts[0]

    # Ashby: jobs.ashbyhq.com/company
    if "ashby" in host:
        parts = parsed.path.strip("/").split("/")
        if parts:
            return parts[0]

    # Lever: jobs.lever.co/company
    if "lever" in host:
        parts = parsed.path.strip("/").split("/")
        if parts:
            return parts[0]

    # LinkedIn: extract from path
    if "linkedin" in host:
        return "(LinkedIn)"

    # Fallback: domain name
    parts = host.split(".")
    if len(parts) >= 2:
        return parts[-2]

    return "(unknown)"


if __name__ == "__main__":
    app()
