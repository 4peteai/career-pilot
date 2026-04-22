# Career Pilot

AI-powered job search pipeline in Python. Scans job boards, parses LinkedIn alerts from Gmail, evaluates opportunities with Claude, generates tailored CVs, and tracks the application pipeline — all from the terminal.

> **Status:** personal tool, alpha. Built and used by the author as a daily driver — ~1,000 lines of Python, type-checked, async-first.

Inspired by [career-ops](https://github.com/santifer/career-ops) by Santiago Fernandez; rewritten in Python with an English-only interface and Gmail IMAP as a LinkedIn workaround.

---

## What this demonstrates

This repository is a working end-to-end AI automation — it's also a compact showcase of how I build systems. Five things to notice:

1. **API integration at the boundaries.** `scanner.py` wraps the Greenhouse REST, Ashby GraphQL, and Lever Postings APIs behind one `scan_company()` interface. `gmail.py` speaks IMAP directly (no third-party SDK) and parses multipart/HTML email. `evaluator.py` calls the Anthropic API asynchronously.
2. **LLM integration as structured output, not free text.** The Claude prompt asks for six labelled markdown blocks plus a numeric score; `evaluator.py` parses these back into Pydantic `Evaluation` models. The LLM is a reasoning engine; the pipeline treats its output as typed data. See [ARCHITECTURE.md](ARCHITECTURE.md) for the "structured prompting vs. tool calling" decision.
3. **Python proficiency across the stack.** Async I/O (`httpx`, `anthropic.AsyncAnthropic`, Playwright), Pydantic v2 models, Typer CLI, Jinja2 templating, Textual TUI, strict mypy, ruff formatting. `pyproject.toml` is the single source of truth.
4. **End-to-end delivery.** Scan → filter → evaluate → PDF → track → dashboard → schedule. Every stage is a command; every stage writes an auditable artifact (JSON, markdown, or PDF).
5. **Enterprise thinking.** Config and secrets separated (`.env` + `*.yml` with `*.example.*` templates, all PII gitignored). Explicit failure modes (missing API keys raise specific errors). Filter policy lives in config, not code. No hardcoded credentials anywhere.

---

## Architecture

```
  Job-board APIs          Gmail (IMAP)
  Greenhouse/Ashby/Lever  LinkedIn alerts
        │                       │
        └──────────┬────────────┘
                   ▼
            filter.py (policy)
              title · location · dedup
                   │
                   ▼
         evaluator.py (Claude API)
      six-block structured prompt → score
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
     pdf.py    tracker.py   reports/
   (Playwright)  (markdown)  (markdown)
        │
        ▼
   dashboard.py (Textual TUI)
```

See [**ARCHITECTURE.md**](ARCHITECTURE.md) for design decisions — why Python, why Claude API, why no framework, module boundaries, and what I'd change at scale.

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/4peteai/career-pilot.git
cd career-pilot
pip install -e .
playwright install chromium

# Configure (templates are committed; real files are gitignored)
cp .env.example .env                       # add ANTHROPIC_API_KEY, Gmail creds
cp config/profile.example.yml config/profile.yml
cp config/cv.example.md config/cv.md
cp config/portals.example.yml config/portals.yml
# Edit each to your details

# Initialize and run
career-pilot init
career-pilot scan --all
career-pilot gmail-fetch
career-pilot evaluate https://boards.greenhouse.io/company/jobs/12345
career-pilot pdf "Company Name" --job-title "AI Engineer"
career-pilot track
career-pilot dashboard
```

---

## Commands

| Command | Description |
|---------|-------------|
| `scan` | Scan job boards (Greenhouse / Ashby / Lever) for new listings |
| `gmail-fetch` | Parse LinkedIn alert emails from Gmail IMAP |
| `evaluate <url>` | Score a job against your CV using Claude |
| `pdf <company>` | Generate a tailored CV PDF via Playwright |
| `track` | View application tracker table |
| `dashboard` | Launch interactive TUI dashboard (Textual) |
| `schedule install\|remove` | Install or remove twice-daily scans (launchd / cron) |
| `init` | First-time setup check |

---

## Configuration

### `.env`

```
ANTHROPIC_API_KEY=sk-ant-...
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

Gmail requires an [App Password](https://myaccount.google.com/apppasswords) — regular passwords don't work for IMAP.

### `config/profile.yml`

Candidate profile — contact, target roles, archetypes, compensation, location rules. See `profile.example.yml` for schema.

### `config/cv.md`

Canonical CV in Markdown. Single source of truth for all evaluations and PDF generation.

### `config/portals.yml`

Title filters (positive / negative keywords), tracked companies with board slugs, and search queries.

All three config files are **gitignored** — `*.example.*` templates are tracked.

---

## Evaluation Scoring

Each job is evaluated across six dimensions (Blocks A–F):

| Block | Focus |
|-------|-------|
| **A** | Role summary — archetype, domain, seniority, remote status |
| **B** | CV match — requirement-to-CV mapping with gap analysis |
| **C** | Level strategy — seniority fit and positioning |
| **D** | Compensation & market — pay range, demand, reputation |
| **E** | Personalization — top CV and LinkedIn changes by impact |
| **F** | Interview prep — STAR stories, case studies, red-flag Q&A |

`score >= 3.5 / 5.0` → "Ready to Apply". Otherwise → "Skip".

---

## Project Structure

```
career-pilot/
├── ARCHITECTURE.md          # Design decisions
├── README.md
├── Makefile
├── pyproject.toml
├── .env.example
├── config/
│   ├── profile.example.yml   ← tracked template
│   ├── cv.example.md         ← tracked template
│   ├── portals.example.yml   ← tracked template
│   ├── profile.yml           ← gitignored (personal)
│   ├── cv.md                 ← gitignored (personal)
│   └── portals.yml           ← gitignored (personal)
├── data/                     # gitignored: tracker, scan history
├── reports/                  # gitignored: per-evaluation markdown
├── output/                   # gitignored: generated PDFs
├── templates/
│   └── cv-template.html      # ATS-optimized CV template
└── src/career_pilot/
    ├── cli.py                # Typer CLI entry point
    ├── scanner.py            # Greenhouse / Ashby / Lever clients
    ├── gmail.py              # IMAP LinkedIn alert parser
    ├── filter.py             # Title / location / dedup engine
    ├── evaluator.py          # Claude API evaluator (structured prompting)
    ├── pdf.py                # Playwright HTML → PDF
    ├── tracker.py            # applications.md read/write
    ├── dashboard.py          # Textual TUI
    ├── scheduler.py          # launchd / cron wrapper
    └── models.py             # Pydantic data models
```

---

## Development

```bash
pip install -e ".[dev]"
make lint        # ruff check + format check
make format      # ruff fix + format
make typecheck   # mypy strict
```

---

## Credits

Built on ideas from [career-ops](https://github.com/santifer/career-ops) by [Santiago Fernandez](https://santifer.io). Career Pilot is a ground-up Python rewrite with a different architecture, Gmail IMAP integration, and an English-only interface.

## License

MIT
