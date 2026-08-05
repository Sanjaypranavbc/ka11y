"""
ka11y/utils/gmail_sender.py
===========================
Gmail SMTP sender.

Adapted from the standalone `gmail_smtp` module (KALANITHII/gmail_smtp) so the
credential contract stays identical — same env variable names, same 465-SSL /
587-TLS branching, same App-Password troubleshooting guidance. Three changes
were needed to run it inside the audit pipeline:

  1. ``attachments`` support. The original built a ``MIMEMultipart("alternative")``,
     which carries text-vs-HTML alternatives but cannot carry a file. Sending the
     findings CSV needs a ``"mixed"`` container with the alternative part nested
     inside it. Calls that pass no attachment produce the same message as before.
  2. ``print()`` → ka11y logger, so output lands in the container logs alongside
     the rest of the run.
  3. ``is_configured()``, so callers can skip sending entirely when credentials
     are absent instead of raising — a missing .env must never fail an audit that
     otherwise succeeded.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, Sequence, Tuple, Union

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="mailer")

# (filename, content, mime_subtype). Text content is encoded UTF-8 at attach
# time; bytes are attached as-is, which is what the rendered PDF needs.
Attachment = Tuple[str, Union[str, bytes], str]

# Placeholder values shipped in .env_sample; treated as "not configured" so a
# half-filled .env fails the same way an absent one does.
_PLACEHOLDERS = ("your_email@gmail.com", "your_16_digit_app_password")


class GmailSender:
    """Send mail through Gmail SMTP using an App Password."""

    def __init__(
        self,
        smtp_server: Optional[str] = None,
        smtp_port: Optional[int] = None,
        sender_email: Optional[str] = None,
        sender_password: Optional[str] = None,
    ):
        self.smtp_server = smtp_server or os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(smtp_port or os.getenv("SMTP_PORT", 587))
        self.sender_email = sender_email or os.getenv("SENDER_EMAIL")
        self.sender_password = sender_password or os.getenv("SENDER_PASSWORD")

    def is_configured(self) -> bool:
        """True when real credentials are present.

        Lets the caller skip sending silently rather than raising: an audit that
        completed successfully must not be reported as failed just because SMTP
        was never set up.
        """
        for value in (self.sender_email, self.sender_password):
            if not value or any(p in value for p in _PLACEHOLDERS):
                return False
        return True

    def validate_credentials(self) -> None:
        """Raise ValueError when credentials are missing or still placeholders."""
        if not self.sender_email or any(p in self.sender_email for p in _PLACEHOLDERS):
            raise ValueError(
                "SENDER_EMAIL is not properly configured. "
                "Set it to a valid Gmail address in the environment/.env."
            )
        if not self.sender_password or any(
            p in self.sender_password for p in _PLACEHOLDERS
        ):
            raise ValueError(
                "SENDER_PASSWORD is not properly configured. "
                "Set it to a 16-character Gmail App Password in the environment/.env."
            )

    def send_email(
        self,
        receiver_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        attachments: Optional[Sequence[Attachment]] = None,
    ) -> bool:
        """Send one message. Returns True on success; raises on SMTP failure."""
        self.validate_credentials()

        if not receiver_email:
            raise ValueError("A receiver_email must be specified.")

        # "mixed" is the outer container so file parts sit alongside the body;
        # the text/html alternatives live in their own nested part. With no
        # attachments this still renders identically to a plain alternative
        # message in every mail client.
        msg = MIMEMultipart("mixed")
        msg["From"] = self.sender_email
        msg["To"] = receiver_email
        msg["Subject"] = subject

        body = MIMEMultipart("alternative")
        body.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            body.attach(MIMEText(body_html, "html", "utf-8"))
        msg.attach(body)

        for filename, content, subtype in attachments or ():
            raw = content.encode("utf-8") if isinstance(content, str) else content
            part = MIMEApplication(raw, _subtype=subtype)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)

        logger.info(
            "[mailer] connecting to %s:%s", self.smtp_server, self.smtp_port
        )

        try:
            if self.smtp_port == 465:
                with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                    server.login(self.sender_email, self.sender_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(self.sender_email, self.sender_password)
                    server.send_message(msg)

            logger.info("[mailer] sent to %s", receiver_email)
            return True

        except smtplib.SMTPAuthenticationError as auth_err:
            logger.error(
                "[mailer] SMTP authentication failed (%s). Check that 2-Step "
                "Verification is enabled on the sender account and that "
                "SENDER_PASSWORD is a 16-character App Password, not the "
                "account password.",
                auth_err,
            )
            raise
        except smtplib.SMTPConnectError as conn_err:
            logger.error("[mailer] could not connect to SMTP server: %s", conn_err)
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("[mailer] failed to send email: %s", exc)
            raise
