"""Claude API evaluator — scores jobs A-F against CV and profile."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

import anthropic

from career_pilot.models import (
    ApplicationStatus,
    CandidateProfile,
    Evaluation,
    EvaluationBlock,
    Job,
)

EVAL_PROMPT = """\
You are an expert career advisor evaluating a job opportunity for a candidate.

## Candidate CV
{cv}

## Candidate Profile
- Name: {name}
- Location: {location}
- Target roles: {target_roles}
- Headline: {headline}

## Job to Evaluate
- Company: {company}
- Title: {title}
- URL: {url}
- Location: {job_location}

## Job Description
{description}

## Instructions
Evaluate this job opportunity with the following 6 blocks. Be honest and specific.

**A) Role Summary**
Classify the role archetype, domain, seniority level, remote/hybrid/onsite, and write a 2-sentence TL;DR.

**B) CV Match**
Create a table mapping the top 10 JD requirements to specific lines from the candidate's CV.
For each, note: Requirement | CV Evidence | Gap? | Mitigation.
Distinguish hard blockers from nice-to-haves.

**C) Level & Strategy**
Assess seniority fit. Provide talking points if overqualified or underqualified.
Include a "sell senior without lying" strategy if applicable.

**D) Compensation & Market**
Estimate compensation range for this role and location.
Assess market demand and company reputation.

**E) Personalization Plan**
Recommend the top 5 CV changes and top 5 LinkedIn changes to maximize fit.
Rank by impact.

**F) Interview Preparation**
Suggest 6-8 STAR+Reflection stories mapped to JD requirements.
Include a case study recommendation and red-flag question answers.

## Scoring
At the end, provide:
- Match Score: X.X / 5.0
- Status recommendation: "Ready to Apply" (≥3.5) or "Skip" (<3.5)

Format your response as markdown with clear ## headers for each block (A through F),
followed by a ## Score section with the numeric score on its own line like:
**Score: X.X / 5.0**
"""


def _parse_blocks(text: str) -> list[EvaluationBlock]:
    """Parse evaluation text into labeled blocks."""
    blocks: list[EvaluationBlock] = []
    # Split on ## headers that start with A) through F) or "Score"
    sections = re.split(r"(?m)^## ", text)
    for section in sections:
        section = section.strip()
        if not section:
            continue
        # First line is the header
        lines = section.split("\n", 1)
        label = lines[0].strip()
        content = lines[1].strip() if len(lines) > 1 else ""
        blocks.append(EvaluationBlock(label=label, content=content))
    return blocks


def _extract_score(text: str) -> float:
    """Extract numeric score from evaluation text."""
    match = re.search(r"\*?\*?Score:\s*(\d+\.?\d*)\s*/\s*5\.0\*?\*?", text)
    if match:
        return float(match.group(1))
    return 0.0


async def evaluate_job(
    job: Job,
    cv_path: Path,
    profile_path: Path,
    reports_dir: Path,
    model: str = "claude-sonnet-4-6",
) -> Evaluation:
    """Evaluate a job against the candidate's CV using Claude API.

    Returns an Evaluation with scored blocks and a saved report file.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is required")

    cv_text = cv_path.read_text()
    profile = CandidateProfile.load(profile_path)

    prompt = EVAL_PROMPT.format(
        cv=cv_text,
        name=profile.full_name,
        location=f"{profile.city}, {profile.country}",
        target_roles=", ".join(profile.target_roles),
        headline=profile.headline,
        company=job.company,
        title=job.title,
        url=job.url,
        job_location=job.location,
        description=job.description or "(No description available — evaluate based on title and company)",
    )

    client = anthropic.AsyncAnthropic(api_key=api_key)
    message = await client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text

    # Parse response
    blocks = _parse_blocks(response_text)
    score = _extract_score(response_text)

    # Determine report number
    existing = list(reports_dir.glob("*.md"))
    report_num = len(existing) + 1

    # Save report
    date_str = datetime.now().strftime("%Y-%m-%d")
    company_slug = re.sub(r"[^a-z0-9]+", "-", job.company.lower()).strip("-")
    report_filename = f"{report_num:03d}-{company_slug}-{date_str}.md"
    report_path = reports_dir / report_filename

    report_content = f"# {job.title} @ {job.company}\n\n"
    report_content += f"- **URL:** {job.url}\n"
    report_content += f"- **Location:** {job.location}\n"
    report_content += f"- **Score:** {score} / 5.0\n"
    report_content += f"- **Date:** {date_str}\n\n---\n\n"
    report_content += response_text

    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_content)

    return Evaluation(
        job=job,
        archetype=blocks[0].content[:100] if blocks else "",
        score=score,
        blocks=blocks,
        report_path=str(report_path),
        report_num=report_num,
    )


def score_to_status(score: float) -> ApplicationStatus:
    """Convert numeric score to application status recommendation."""
    if score >= 3.5:
        return ApplicationStatus.EVALUATED
    return ApplicationStatus.SKIP
