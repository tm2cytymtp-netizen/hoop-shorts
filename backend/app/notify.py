"""Notifications: Discord/Slack webhook and/or email. Failures never break the pipeline."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

import httpx

from .config import env

log = logging.getLogger("notify")


def notify(subject: str, body: str = "", link: str = "") -> None:
    text = f"**{subject}**\n{body}" + (f"\n{link}" if link else "")
    if env.notify_webhook_url:
        try:
            # Discord uses `content`, Slack uses `text`; send both.
            httpx.post(env.notify_webhook_url, json={"content": text[:1900], "text": text}, timeout=10)
        except Exception as e:  # pragma: no cover
            log.warning("webhook notify failed: %s", e)
    if env.smtp_host and env.notify_email_to:
        try:
            msg = EmailMessage()
            msg["Subject"] = f"[History Channel] {subject}"
            msg["From"] = env.smtp_user or env.notify_email_to
            msg["To"] = env.notify_email_to
            msg.set_content(f"{body}\n\n{link}")
            with smtplib.SMTP(env.smtp_host, env.smtp_port, timeout=20) as s:
                s.starttls()
                if env.smtp_user:
                    s.login(env.smtp_user, env.smtp_password)
                s.send_message(msg)
        except Exception as e:  # pragma: no cover
            log.warning("email notify failed: %s", e)
    log.info("NOTIFY: %s — %s", subject, body)
