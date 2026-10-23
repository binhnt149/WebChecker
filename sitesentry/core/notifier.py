from __future__ import annotations

import html
import json
import logging
import smtplib
import ssl
import threading
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from .checker import CheckResult
from .database import Database
from .email_rules import parse_recipients, render_template
from .reports import format_duration


class EmailNotifier:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._dispatch_lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def start(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._delivery_worker, name="sitesentry-email", daemon=True)
        self._worker.start()
        self.wake()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def wake(self) -> None:
        self._wake.set()

    def _delivery_worker(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(30)
            self._wake.clear()
            if not self._stop.is_set():
                try:
                    self.process_pending()
                except Exception:
                    logging.getLogger(__name__).exception("Email queue processing failed")

    def process_pending(self) -> None:
        if self.settings().get("smtp_enabled") != "1" or not self._dispatch_lock.acquire(blocking=False):
            return
        try:
            while not self._stop.is_set():
                pending = self.db.pending_email_deliveries()
                if not pending:
                    break
                any_sent = False
                for delivery in pending:
                    if self._stop.is_set():
                        break
                    delivery_id = int(delivery["delivery_id"])
                    self.db.mark_delivery_attempt(delivery_id)
                    try:
                        subject, body = self._rule_message(delivery)
                        remaining = delivery["remaining_recipients_json"]
                        recipients = json.loads(remaining) if remaining is not None else None
                        sent, message = self._send(
                            subject, body, recipient_override=delivery["recipients"],
                            delivery_id=delivery_id, pending_recipients=recipients,
                        )
                    except Exception as exc:
                        sent, message = False, f"{type(exc).__name__}: {exc}"
                    self.db.finish_email_delivery(delivery_id, sent, message)
                    any_sent = any_sent or sent
                if not any_sent:
                    break
        finally:
            self._dispatch_lock.release()

    def _rule_message(self, delivery: dict[str, Any]) -> tuple[str, str]:
        payload = json.loads(delivery["payload_json"])
        if delivery["kind"] == "daily_summary":
            report = payload["report"]
            values = {**report, "date": report["start_at"][:10], "status": "SUMMARY", "downtime": format_duration(report["downtime_seconds"])}
            default_body = self._summary_html(report)
        else:
            monitor = payload["monitor"]
            result = CheckResult(**payload["result"])
            values = {
                "monitor_name": monitor["name"], "url": monitor["url"], "status": "UP" if result.ok else "DOWN",
                "checked_at": result.checked_at, "error": result.error, "date": result.checked_at[:10],
            }
            default_body = self._monitor_html(delivery["kind"], monitor, result)
        subject = render_template(delivery["subject_template"], values).replace("\r", " ").replace("\n", " ")
        custom = render_template(delivery["body_template"], values)
        fragment = f'<div style="font-family:Arial,sans-serif;padding:20px">{html.escape(custom).replace(chr(10), "<br>")}</div>' if custom else ""
        if delivery["include_details"]:
            body = default_body.replace("</body>", fragment + "</body>")
        else:
            body = f"<html><body>{fragment}</body></html>"
        return subject, body

    def _summary_html(self, report: dict[str, Any]) -> str:
        rows = "".join(
            "<tr>" + "".join(f'<td style="padding:8px;border-bottom:1px solid #ddd">{html.escape(str(value))}</td>' for value in (
                row["monitor_name"], row["last_status"].upper(), row["down_count"], row["incident_count"],
                format_duration(row["downtime_seconds"]), format_duration(row["average_down_seconds"]),
            )) + "</tr>"
            for row in report["rows"]
        )
        return f'''<html><body style="font-family:Arial,sans-serif;color:#1f2937;padding:24px">
        <h2>SiteSentry daily dashboard: {html.escape(report['start_at'][:10])}</h2>
        <p>Total: {report['total']} | UP: {report['up']} | DOWN: {report['down']} | Unknown: {report['unknown']}</p>
        <p>From {html.escape(report['start_at'])} to {html.escape(report['as_of'])}</p>
        <table style="border-collapse:collapse;width:100%"><thead><tr>
        <th>Monitor</th><th>Status</th><th>DOWN checks</th><th>Incidents</th><th>Total DOWN</th><th>Average DOWN</th>
        </tr></thead><tbody>{rows}</tbody></table></body></html>'''

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
        delivery_id: int | None = None,
        pending_recipients: list[str] | None = None,
    ) -> tuple[bool, str]:
        settings = self.settings()
        if settings.get("smtp_enabled") != "1":
            return False, "SMTP alerts are disabled"
        host = settings.get("smtp_host", "").strip()
        if not host:
            return False, "SMTP host is empty"
        try:
            recipients = pending_recipients if pending_recipients is not None else parse_recipients(recipient_override or settings.get("smtp_to", ""))
        except ValueError as exc:
            return False, str(exc)
        if delivery_id is not None and pending_recipients == []:
            return True, "All recipients already accepted"
        if not recipients:
            return False, "No alert recipients configured"
        if delivery_id is not None:
            self.db.set_delivery_recipients(delivery_id, recipients)

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
                refused = smtp.sendmail(sender, recipients, message.as_string())
                remaining = [recipient for recipient in recipients if recipient in refused]
                if delivery_id is not None:
                    self.db.set_delivery_recipients(delivery_id, remaining)
                if remaining:
                    return False, "SMTP refused some recipients; accepted recipients will not be resent"
            return True, "Email sent"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"

    def _monitor_html(self, kind: str, monitor: dict[str, Any], result: CheckResult) -> str:
        status = "Recovered" if kind == "recovery" else "Incident detected"
        accent = "#16a34a" if kind == "recovery" else "#dc2626"
        rows = {
            "Monitor": monitor.get("name", ""),
            "Type": monitor.get("monitor_type", ""),
            "Language": monitor.get("language", ""),
            "Web server": monitor.get("web_server", ""),
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
