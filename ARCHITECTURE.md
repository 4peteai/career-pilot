# Architecture

This document explains the design decisions behind Career Pilot — what was chosen, what was rejected, and why.

## One-Sentence Summary

A pipeline where **API clients pull structured job data**, **pure-Python filters enforce policy**, and **Claude produces structured evaluations** that feed a file-based tracker — all composed as small, async-first modules behind a single Typer CLI.

---

## Module Map

```
                       ┌─────────────────────────────────────┐
                       │              cli.py                 │
                       │  (Typer entry point — thin shell)   │
                       └──────────────┬──────────────────────┘
                                      │
         ┌────────────────┬───────────┼───────────┬──────────────┬──────────────┐
         ▼                ▼           ▼           ▼              ▼              ▼
     scanner.py       gmail.py    evaluator.py  pdf.py       tracker.py    scheduler.py
     (3 APIs)        (IMAP)      (Claude API)  (Playwright) (Markdown DB)  (launchd/cron)
         │                │           │           │              │
         └────────────────┴──────┬────┴───────────┴──────────────┘
                                 ▼
                              models.py
                       (Pydantic — one shared type system)

                              filter.py
                       (policy — runs after scanner/gmail)

                             dashboard.py
                       (Textual TUI — reads tracker)
```

**Dependency direction:** `cli` → feature modules → `models`. Nothing else points upward. `filter.py` is a pure-function utility used by multiple commands.

---

## Why Python

- **Ecosystem fit.** The AI stack lives in Python — Anthropic SDK, Pydantic for schemas, LlamaIndex, LangChain, pgvector clients. Staying in-language removes glue code.
- **Async-native I/O.** Scanners and the Claude API client are both async — job-board APIs are latency-dominated, and `asyncio` lets a multi-company scan finish in seconds instead of tens-of-seconds serial.
- **Types as contracts.** Pydantic + mypy strict give us data-layer guarantees at boundaries (API responses, config files, LLM output) without runtime overhead.
- **Operational minimalism.** `pip install -e .` + `pyproject.toml` is the entire dev loop. No Node, no Docker-for-dev, no build step.

## Why Claude API (not local models, not a framework)

- **Production quality at a known cost.** Claude's evaluation quality is well above the open-source tier Pete can self-host, and API billing is predictable for a tool used dozens of times per day.
- **No framework dependency.** The only LLM interaction is `client.messages.create()` with a prompt and a markdown-shaped response. There is no LangChain, no LangGraph, no CrewAI — because a career-evaluation agent is one prompt with structured output, not a multi-step orchestration.
- **Model swapping is trivial.** The model name is a CLI flag. If Sonnet 4.6 isn't good enough, `--model claude-opus-4-7` is one character change. No vendor lock-in beyond the SDK.

## Structured Prompting vs. Tool Calling

Career Pilot uses **structured prompting** — the prompt instructs Claude to return markdown with labelled sections (A through F and a `## Score` block), which `evaluator.py` parses back into Pydantic `Evaluation` + `EvaluationBlock` models.

**Why not tool calling?** Tool calling is the right abstraction when the LLM needs to *invoke external operations* — fetch a URL, query a database, call a function. The evaluation task is different: given a JD and a CV, produce a structured report. There's no tool to call; the LLM reasons from the input and emits the output. Adding tool-calling machinery would be ceremony without function.

**Where tool calling would earn its keep in this codebase:**
- If the evaluator needed to *fetch* the JD from a URL rather than receiving it pre-populated — a `fetch_jd` tool would belong here.
- If the system needed to *query recent salary data* — a tool bound to a compensation API.
- If evaluation produced an action (apply / schedule / email) — tools for each side effect.

This is a deliberate boundary, not a missing feature.

## File-Based State (No Database)

- `config/profile.yml` — candidate profile (PII, gitignored)
- `config/cv.md` — canonical CV in markdown (PII, gitignored)
- `config/portals.yml` — target companies and filter rules (gitignored)
- `data/applications.md` — application tracker (markdown table)
- `data/scan_history.json` — URL dedup cache
- `reports/*.md` — per-evaluation reports

**Why markdown and JSON, not SQLite or Postgres?**
- Human-readable. The tracker is the user's source of truth and they should be able to hand-edit it.
- Git-diffable. Changes to the pipeline show up as readable diffs.
- Zero operational cost. No migrations, no backups, no running service.
- The corpus is small (hundreds of entries). A database would be ceremony at this scale.

**Where this would break:** multi-user access, concurrent writes, queries beyond linear scans. At that scale the right move is SQLite → Postgres, not a bigger markdown file.

## Evaluation Design — Six-Block Prompt

`evaluator.py` asks Claude for six labelled blocks:

| Block | Purpose |
|-------|---------|
| A — Role Summary | Classify archetype, domain, seniority, location |
| B — CV Match | Requirement-to-CV mapping with gap analysis |
| C — Level Strategy | Seniority fit; positioning advice if over/underqualified |
| D — Compensation & Market | Pay range estimate and demand signal |
| E — Personalization Plan | Top CV and LinkedIn changes by impact |
| F — Interview Preparation | STAR stories, case study, red-flag Q&A |

Then a numeric score out of 5.0. The score drives routing (≥3.5 = "Ready to Apply", <3.5 = "Skip").

**Why this structure:** each block is independently useful. Block B is what a recruiter reads; Block F is what the candidate reads before an interview. Structured output means downstream consumers can route by block rather than re-parsing free text.

## Async Patterns

- **I/O is async.** `httpx.AsyncClient`, `anthropic.AsyncAnthropic`, Playwright's async API. A single `asyncio.run()` at the CLI layer.
- **Compute is sync.** Filter logic, markdown parsing, tracker reads/writes — none of these benefit from async, so they stay synchronous and composable.
- **No task queues.** Scans are initiated by the user or by `launchd`/cron. Sub-minute latency doesn't need a queue.

## Filtering as Policy

`filter.py` is the policy layer. It composes three independent predicates:

1. **Title filter** — positive/negative keyword match from `portals.yml`.
2. **Location rules** — home-country allows hybrid/on-site; elsewhere remote-only.
3. **Deduplication** — against `scan_history.json` and the tracker.

Each predicate is a pure function. Rules live in config, not code — changing the policy doesn't require a deploy.

## Security & Config Separation

- Secrets (`ANTHROPIC_API_KEY`, `GMAIL_APP_PASSWORD`) live in `.env` and are loaded via `python-dotenv`. `.env` is gitignored; `.env.example` is the template.
- PII (name, phone, CV text, target companies) lives in `config/*.yml` — also gitignored. `*.example.*` templates are committed.
- No hardcoded credentials anywhere in source. `gmail.py` and `evaluator.py` both raise explicit errors if required env vars are missing.

## What I'd Change at Scale

- **Observability.** Structured logs for each pipeline run; score distributions and rejection reasons exported as metrics.
- **Eval harness.** A corpus of ~50 hand-labelled JD/score pairs; regression test on every prompt change with LLM-as-judge grading.
- **Vector retrieval for CV matching.** At the current scale (one CV, small JD count) string matching is fine. Past ~10k JDs, pgvector + hybrid retrieval earns its keep.
- **Proper workflow engine.** Bash + `launchd` is right for one user. For a team service, Temporal or Prefect.
- **Multi-tenant isolation.** If this became a shared platform, config becomes per-user records in Postgres with row-level security.

## What I Deliberately Skipped

- **ORMs.** No SQLAlchemy. Filesystem is the storage layer until the scale justifies a DB.
- **Web framework.** No FastAPI. This is a CLI; adding HTTP would double the surface area for no user benefit.
- **Plugin system.** New scan methods go in `SCANNERS` dict in `scanner.py` — simple, obvious, discoverable. A plugin framework would be premature.
- **Retry middleware.** Scanners fail gracefully and move on. The scheduler re-runs twice a day.
- **Caching layer.** The dedup cache and tracker *are* the cache.

---

## Evolution Notes

Career Pilot is intentionally small (~1,000 lines of Python). It is a personal tool first; the architecture is designed to be **legible** rather than extensible. Every file should be readable end-to-end in under five minutes. If the user base grew beyond one, the obvious migrations are: markdown tracker → Postgres, CLI → web UI, file-based config → per-user records, launchd → Temporal. None of those are needed yet.
