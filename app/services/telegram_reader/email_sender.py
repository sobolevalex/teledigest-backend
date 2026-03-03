"""Email delivery: send digest via SMTP (Gmail)."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_TIMEOUT: int = 60
SMTP_HOST: str = "smtp.gmail.com"
SMTP_PORT_TLS: int = 587
SMTP_PORT_SSL: int = 465


class EmailSender:
    """Sends digest emails via Gmail SMTP."""

    def __init__(
        self,
        smtp_user: str,
        smtp_password: str,
        to_email: str,
        log: logging.Logger | None = None,
    ) -> None:
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.to_email = to_email
        self._log = log or logger

    def send_digest(self, content: str, subject: str) -> None:
        """
        Build a plain-text message and send it to to_email.
        Tries port 587 with STARTTLS first; falls back to 465 (SSL).
        Raises on failure (caller may catch and log).
        """
        msg = MIMEMultipart()
        msg["From"] = self.smtp_user
        msg["To"] = self.to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(content, "plain"))

        try:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT_TLS, timeout=SMTP_TIMEOUT)
            server.starttls()
        except (OSError, TimeoutError):
            self._log.info("Port 587 unavailable, trying 465...")
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT_SSL, timeout=SMTP_TIMEOUT)

        try:
            self._log.info("Sending email...")
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)
            self._log.info("Email sent successfully.")
        finally:
            server.quit()
