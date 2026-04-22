"""Scheduler — cron/launchd wrapper for twice-daily scans."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

PLIST_NAME = "com.career-pilot.scan"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"


def _get_python() -> str:
    """Get the path to the current Python interpreter."""
    return sys.executable


def _get_career_pilot_bin() -> str:
    """Find the career-pilot CLI binary path."""
    result = subprocess.run(
        ["which", "career-pilot"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    # Fallback: use python -m
    return f"{_get_python()} -m career_pilot.cli"


def _build_plist(hours: list[int] | None = None) -> str:
    """Generate a launchd plist for scheduled scanning."""
    hours = hours or [9, 18]
    career_pilot = _get_career_pilot_bin()

    # Build the calendar interval entries
    intervals = "\n".join(
        f"""\
        <dict>
            <key>Hour</key>
            <integer>{h}</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>"""
        for h in hours
    )

    return dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
          "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>{PLIST_NAME}</string>

            <key>ProgramArguments</key>
            <array>
                <string>{career_pilot}</string>
                <string>scan</string>
                <string>--all</string>
            </array>

            <key>StartCalendarInterval</key>
            <array>
{intervals}
            </array>

            <key>StandardOutPath</key>
            <string>{Path.home()}/career-pilot/logs/scan.log</string>

            <key>StandardErrorPath</key>
            <string>{Path.home()}/career-pilot/logs/scan-error.log</string>

            <key>WorkingDirectory</key>
            <string>{Path.home()}/career-pilot</string>

            <key>EnvironmentVariables</key>
            <dict>
                <key>PATH</key>
                <string>{os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")}</string>
            </dict>
        </dict>
        </plist>
    """)


def _build_crontab_entry(hours: list[int] | None = None) -> str:
    """Generate crontab entries for Linux systems."""
    hours = hours or [9, 18]
    career_pilot = _get_career_pilot_bin()
    project_dir = Path.home() / "career-pilot"

    entries: list[str] = []
    for h in hours:
        entries.append(
            f"0 {h} * * * cd {project_dir} && {career_pilot} scan --all "
            f">> {project_dir}/logs/scan.log 2>&1"
        )
    return "\n".join(entries)


def install_schedule(hours: list[int] | None = None) -> str:
    """Install scheduled scanning (launchd on macOS, crontab on Linux).

    Returns a status message.
    """
    hours = hours or [9, 18]
    log_dir = Path.home() / "career-pilot" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    if sys.platform == "darwin":
        plist_path = PLIST_DIR / f"{PLIST_NAME}.plist"
        PLIST_DIR.mkdir(parents=True, exist_ok=True)
        plist_path.write_text(_build_plist(hours))

        # Load the agent
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        subprocess.run(["launchctl", "load", str(plist_path)], check=True)

        return f"Installed launchd agent: {plist_path}\nScans at: {hours}"
    else:
        # Linux: add to crontab
        entry = _build_crontab_entry(hours)
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = result.stdout if result.returncode == 0 else ""

        # Remove old entries
        lines = [l for l in existing.split("\n") if "career-pilot" not in l]
        lines.append(entry)
        new_crontab = "\n".join(lines).strip() + "\n"

        subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            text=True,
            check=True,
        )
        return f"Installed crontab entries.\nScans at: {hours}"


def remove_schedule() -> str:
    """Remove scheduled scanning."""
    if sys.platform == "darwin":
        plist_path = PLIST_DIR / f"{PLIST_NAME}.plist"
        if plist_path.exists():
            subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
            plist_path.unlink()
            return f"Removed launchd agent: {plist_path}"
        return "No launchd agent found."
    else:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if result.returncode != 0:
            return "No crontab entries found."
        lines = [l for l in result.stdout.split("\n") if "career-pilot" not in l]
        new_crontab = "\n".join(lines).strip() + "\n"
        subprocess.run(["crontab", "-"], input=new_crontab, text=True, check=True)
        return "Removed career-pilot crontab entries."
