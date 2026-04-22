"""Textual TUI dashboard for browsing the application pipeline."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Static

from career_pilot.models import ApplicationStatus
from career_pilot.tracker import load_applications

# Score-to-color mapping
SCORE_COLORS = {
    5: "bold green",
    4: "green",
    3: "yellow",
    2: "red",
    1: "bold red",
    0: "dim",
}

STATUS_COLORS = {
    ApplicationStatus.EVALUATED: "cyan",
    ApplicationStatus.APPLIED: "blue",
    ApplicationStatus.RESPONDED: "yellow",
    ApplicationStatus.INTERVIEW: "bold yellow",
    ApplicationStatus.OFFER: "bold green",
    ApplicationStatus.REJECTED: "red",
    ApplicationStatus.DISCARDED: "dim",
    ApplicationStatus.SKIP: "dim red",
}


class StatsPanel(Static):
    """Summary statistics panel — counts, averages, and status breakdown."""

    def update_stats(self, tracker_path: Path) -> None:
        """Recalculate and render pipeline stats from the tracker file."""
        apps = load_applications(tracker_path)
        total = len(apps)
        by_status: dict[str, int] = {}
        scores: list[float] = []

        for app in apps:
            by_status[app.status.value] = by_status.get(app.status.value, 0) + 1
            if app.score > 0:
                scores.append(app.score)

        avg_score = sum(scores) / len(scores) if scores else 0
        top_score = max(scores) if scores else 0

        lines = [
            f"[bold]Pipeline Overview[/bold]",
            f"Total: {total}  |  Avg Score: {avg_score:.1f}  |  Top: {top_score:.1f}",
            "",
        ]
        for status, count in sorted(by_status.items()):
            lines.append(f"  {status}: {count}")

        self.update("\n".join(lines))


class DetailPanel(Static):
    """Detail view — renders full info for the application currently selected in the table."""

    DEFAULT_CSS = "DetailPanel { height: 100%; padding: 1; }"

    def show_detail(self, row_data: list[str]) -> None:
        """Render detail pane from a table row's cell values."""
        if len(row_data) < 7:
            self.update("Select an application to view details.")
            return

        lines = [
            f"[bold]{row_data[2]}[/bold] @ {row_data[1]}",
            "",
            f"Report #: {row_data[0]}",
            f"Score:    {row_data[3]} / 5.0",
            f"Status:   {row_data[4]}",
            f"Added:    {row_data[5]}",
            f"URL:      {row_data[6]}",
        ]
        if len(row_data) > 7 and row_data[7]:
            lines.extend(["", f"Notes: {row_data[7]}"])

        self.update("\n".join(lines))


class PipelineDashboard(App[None]):
    """Textual TUI for browsing the application pipeline. Read-only view over applications.md."""

    CSS = """
    Screen {
        layout: horizontal;
    }
    #left-panel {
        width: 70%;
    }
    #right-panel {
        width: 30%;
        border-left: solid $accent;
        padding: 1;
    }
    StatsPanel {
        height: auto;
        padding: 1;
        border-bottom: solid $accent;
    }
    DataTable {
        height: 1fr;
    }
    """

    TITLE = "Career Pilot"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("o", "open_url", "Open URL"),
        Binding("s", "sort_score", "Sort by Score"),
    ]

    def __init__(self, tracker_path: Path) -> None:
        super().__init__()
        self.tracker_path = tracker_path

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left-panel"):
                yield StatsPanel(id="stats")
                yield DataTable(id="table")
            with Vertical(id="right-panel"):
                yield DetailPanel(id="detail")
        yield Footer()

    def on_mount(self) -> None:
        self._load_data()

    def _load_data(self) -> None:
        table = self.query_one("#table", DataTable)
        table.clear(columns=True)
        table.add_columns("#", "Company", "Role", "Score", "Status", "Date", "URL")

        apps = load_applications(self.tracker_path)
        for app in apps:
            score_color = SCORE_COLORS.get(int(app.score), "white")
            status_color = STATUS_COLORS.get(app.status, "white")

            table.add_row(
                str(app.report_num),
                app.company,
                app.role,
                Text(str(app.score), style=score_color),
                Text(app.status.value, style=status_color),
                app.date_added,
                app.url,
            )

        stats = self.query_one("#stats", StatsPanel)
        stats.update_stats(self.tracker_path)

    @on(DataTable.RowHighlighted)
    def on_row_selected(self, event: DataTable.RowHighlighted) -> None:
        table = self.query_one("#table", DataTable)
        if event.row_key is not None:
            row = table.get_row(event.row_key)
            detail = self.query_one("#detail", DetailPanel)
            detail.show_detail([str(cell) for cell in row])

    def action_refresh(self) -> None:
        self._load_data()

    def action_open_url(self) -> None:
        import subprocess

        table = self.query_one("#table", DataTable)
        if table.cursor_row is not None:
            row_key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key
            row = table.get_row(row_key)
            if len(row) > 6:
                url = str(row[6])
                subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def action_sort_score(self) -> None:
        table = self.query_one("#table", DataTable)
        table.sort("Score", reverse=True)


def run_dashboard(tracker_path: Path) -> None:
    """Launch the pipeline dashboard TUI."""
    app = PipelineDashboard(tracker_path)
    app.run()
