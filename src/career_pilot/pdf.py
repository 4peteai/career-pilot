"""PDF generator — Playwright HTML-to-PDF for tailored CVs."""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Template

from career_pilot.models import CandidateProfile

CV_TEMPLATE_HTML = (Path(__file__).parent.parent.parent / "templates" / "cv-template.html")


async def generate_cv_pdf(
    profile_path: Path,
    cv_path: Path,
    job_title: str,
    company: str,
    keywords: list[str] | None = None,
    output_dir: Path = Path("output"),
    page_format: str = "A4",
    template_path: Path | None = None,
) -> Path:
    """Generate a tailored CV PDF using Playwright.

    Args:
        profile_path: Path to profile.yml
        cv_path: Path to cv.md
        job_title: Target job title for personalization
        company: Target company name
        keywords: JD keywords to highlight in CV
        output_dir: Directory for output PDF
        page_format: Paper size — "A4" or "Letter"
        template_path: Custom HTML template (uses bundled default if None)

    Returns:
        Path to generated PDF file.
    """
    from playwright.async_api import async_playwright

    profile = CandidateProfile.load(profile_path)
    cv_text = cv_path.read_text()

    # Load HTML template
    tmpl_path = template_path or CV_TEMPLATE_HTML
    template = Template(tmpl_path.read_text())

    # Parse CV markdown into sections
    sections = _parse_cv_sections(cv_text)

    # Render HTML
    html = template.render(
        name=profile.full_name,
        email=profile.email,
        phone=profile.phone,
        linkedin=profile.linkedin,
        github=profile.github,
        portfolio=profile.portfolio_url,
        location=f"{profile.city}, {profile.country}",
        target_title=job_title,
        target_company=company,
        keywords=keywords or [],
        sections=sections,
    )

    # Generate PDF
    output_dir.mkdir(parents=True, exist_ok=True)
    company_slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")
    pdf_path = output_dir / f"{company_slug}-cv.pdf"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        await page.pdf(
            path=str(pdf_path),
            format=page_format,
            margin={"top": "0.6in", "bottom": "0.6in", "left": "0.7in", "right": "0.7in"},
            print_background=True,
        )
        await browser.close()

    return pdf_path


def _parse_cv_sections(cv_text: str) -> list[dict[str, str]]:
    """Parse markdown CV into sections for template rendering."""
    sections: list[dict[str, str]] = []
    current_title = ""
    current_content: list[str] = []

    for line in cv_text.split("\n"):
        if line.startswith("## "):
            if current_title or current_content:
                sections.append({
                    "title": current_title,
                    "content": "\n".join(current_content).strip(),
                })
            current_title = line[3:].strip()
            current_content = []
        elif line.startswith("# "):
            # Top-level heading (name) — skip, handled by template
            continue
        else:
            current_content.append(line)

    # Last section
    if current_title or current_content:
        sections.append({
            "title": current_title,
            "content": "\n".join(current_content).strip(),
        })

    return sections
