"""Outbound email with graceful degradation.

`send()` returns True only when SMTP is configured and the message went out. Callers then decide
whether to expose the link on screen (`link_for_response`), which only happens when
EMAIL_LINK_FALLBACK is on — a local-testing convenience that must stay off in production, or
anyone could verify an address they don't own.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from ..config import get_settings

log = logging.getLogger(__name__)


def is_configured() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.smtp_from)


def send(to: str, subject: str, body: str) -> bool:
    s = get_settings()
    if not is_configured():
        log.info("SMTP not configured; email to %s not sent (%s)", to, subject)
        return False
    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if s.smtp_username:
                smtp.login(s.smtp_username, s.smtp_password)
            smtp.send_message(msg)
        return True
    except Exception:  # never let email problems break signup/invites
        log.exception("Failed to send email to %s", to)
        return False


def link_for_response(sent: bool, link: str) -> str | None:
    if not sent and get_settings().email_link_fallback:
        return link
    return None
