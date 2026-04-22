"""Gmail IMAP client for parsing LinkedIn job alert emails."""

from __future__ import annotations

import email
import imaplib
import os
import re
from datetime import datetime
from email.header import decode_header
from html.parser import HTMLParser

from career_pilot.models import Job, JobSource


class _LinkExtractor(HTMLParser):
    """Extract LinkedIn job URLs from HTML email bodies."""

    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value and "linkedin.com/jobs/view" in value:
                # Strip tracking params
                clean = re.split(r"[?&]", value)[0]
                if clean not in self.urls:
                    self.urls.append(clean)


def _decode_payload(msg: email.message.Message) -> str:
    """Extract text/html body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        # Fallback to text/plain
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def _extract_title_from_url(url: str) -> str:
    """Best-effort title extraction from LinkedIn job URL slug."""
    match = re.search(r"linkedin\.com/jobs/view/([^/]+)", url)
    if match:
        slug = match.group(1)
        # Remove trailing job ID
        slug = re.sub(r"-\d+$", "", slug)
        return slug.replace("-", " ").title()
    return ""


def fetch_linkedin_alerts(
    days_back: int = 7,
    gmail_address: str | None = None,
    app_password: str | None = None,
) -> list[Job]:
    """Connect to Gmail IMAP and parse LinkedIn job alert emails.

    Requires a Gmail App Password (not regular password).
    Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD env vars, or pass directly.
    """
    addr = gmail_address or os.environ.get("GMAIL_ADDRESS", "")
    pwd = app_password or os.environ.get("GMAIL_APP_PASSWORD", "")

    if not addr or not pwd:
        raise ValueError(
            "Gmail credentials required. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD "
            "environment variables, or pass them directly."
        )

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(addr, pwd)
    mail.select("INBOX")

    # Search for LinkedIn job alert emails from recent days
    search_criteria = (
        f'(FROM "jobs-noreply@linkedin.com" SINCE "{_imap_date(days_back)}")'
    )
    _status, msg_ids = mail.search(None, search_criteria)

    jobs: list[Job] = []
    seen_urls: set[str] = set()

    for msg_id in msg_ids[0].split():
        _status, msg_data = mail.fetch(msg_id, "(RFC822)")
        if not msg_data or not msg_data[0]:
            continue

        raw = msg_data[0]
        if isinstance(raw, tuple):
            msg = email.message_from_bytes(raw[1])
        else:
            continue

        html_body = _decode_payload(msg)
        if not html_body:
            continue

        extractor = _LinkExtractor()
        extractor.feed(html_body)

        for url in extractor.urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)

            title = _extract_title_from_url(url)
            jobs.append(
                Job(
                    url=url,
                    company="(from LinkedIn alert)",
                    title=title,
                    source=JobSource.LINKEDIN_EMAIL,
                    seen_at=datetime.now(),
                )
            )

    mail.logout()
    return jobs


def _imap_date(days_back: int) -> str:
    """Format date for IMAP SINCE query."""
    from datetime import timedelta

    d = datetime.now() - timedelta(days=days_back)
    return d.strftime("%d-%b-%Y")
