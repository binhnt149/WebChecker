from __future__ import annotations

import html
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from .checker import CheckResult
from .database import Database


def parse_recipients(raw: str) -> list[str]:
    parts = raw.replace(";", ",").replace("\n", ",").split(",")
    return [part.strip() for part in parts if part.strip()]


class EmailNotifier:
    def __init__(self, db: Database) -> None:
        self.db = db

    def settings(self) -> dict[str, str]:
        defaults = {
            "smtp_enabled": "0",
            "smtp_host": "",
            "smtp_port": "587",
            "smtp_username": "",
            "smtp_password": "",
            "smtp_from": "",
            "smtp_to": "",
            "smtp_use_tls": "1",
            "alert_cooldown_minutes": "30",
        }
        defaults.update(self.db.get_settings())
        return defaults

    def cooldown_expired(self, monitor: dict[str, Any], kind: str = "down") -> bool:
        minutes = int(monitor.get("cooldown_minutes") or self.settings().get("alert_cooldown_minutes") or 30)
        if minutes <= 0:
            return True
        last_key = "last_recovery_alert_at" if kind == "recovery" else "last_alert_at"
        last_value = monitor.get(last_key)
        if not last_value:
            return True
        try:
            last_at = datetime.fromisoformat(str(last_value))
        except ValueError:
            return True
        return datetime.now() - last_at >= timedelta(minutes=minutes)

    def send_monitor_alert(self, kind: str, monitor: dict[str, Any], result: CheckResult) -> tuple[bool, str]:
        if not self.cooldown_expired(monitor, kind):
            return False, "Alert cooldown is active"

        subject_status = "RECOVERED" if kind == "recovery" else "DOWN"
        subject = f"[SiteSentry] {subject_status}: {monitor.get('name')}"
        body = self._monitor_html(kind, monitor, result)
        sent, message = self._send(subject, body)
        if sent and monitor.get("id"):
            self.db.mark_alert_sent(int(monitor["id"]), kind)
        return sent, message

    def send_test_email(self, recipient_override: str | None = None) -> tuple[bool, str]:
        body = """
        <html><body style="font-family:Arial,sans-serif">
        <h2>SiteSentry Desktop test email</h2>
        <p>Your SMTP configuration is working.</p>
        </body></html>
        """
        return self._send("[SiteSentry] Test email", body, recipient_override=recipient_override)

    def _send(
        self,
        subject: str,
        html_body: str,
        recipient_override: str | None = None,
    ) -> tuple[bool, str]:
        settings = self.settings()
        if settings.get("smtp_enabled") != "1":
            return False, "SMTP alerts are disabled"
        host = settings.get("smtp_host", "").strip()
        if not host:
            return False, "SMTP host is empty"
        recipients = parse_recipients(recipient_override or settings.get("smtp_to", ""))
        if not recipients:
            return False, "No alert recipients configured"

        sender = settings.get("smtp_from") or settings.get("smtp_username") or recipients[0]
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = ", ".join(recipients)
        message.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            port = int(settings.get("smtp_port") or 587)
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                if settings.get("smtp_use_tls", "1") == "1":
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                username = settings.get("smtp_username") or ""
                password = settings.get("smtp_password") or ""
                if username:
                    smtp.login(username, password)
                smtp.sendmail(sender, recipients, message.as_string())
            return True, "Email sent"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"

    def _monitor_html(self, kind: str, monitor: dict[str, Any], result: CheckResult) -> str:
        status = "Recovered" if kind == "recovery" else "Incident detected"
        accent = "#16a34a" if kind == "recovery" else "#dc2626"
        rows = {
            "Monitor": monitor.get("name", ""),
            "Type": monitor.get("monitor_type", ""),
            "URL": monitor.get("url", ""),
            "Status": result.status.upper(),
            "HTTP Status": result.status_code if result.status_code is not None else "-",
            "Response Time": f"{result.response_ms} ms" if result.response_ms is not None else "-",
            "Attempts": result.attempts,
            "Checked At": result.checked_at,
            "Error": result.error or "-",
        }
        table = "".join(
            f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
            for key, value in rows.items()
        )
        return f"""
        <html>
        <body style="margin:0;background:#0f172a;padding:24px;font-family:Arial,sans-serif;color:#111827">
          <table role="presentation" width="100%" style="max-width:720px;margin:auto;background:#ffffff;border-collapse:collapse;border-radius:8px;overflow:hidden">
            <tr>
              <td style="padding:20px 24px;background:{accent};color:white">
                <h1 style="margin:0;font-size:22px">SiteSentry Desktop</h1>
                <p style="margin:8px 0 0">{html.escape(status)}</p>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 24px">
                <table width="100%" style="border-collapse:collapse">
                  {table}
                </table>
              </td>
            </tr>
          </table>
        </body>
        </html>
        """
