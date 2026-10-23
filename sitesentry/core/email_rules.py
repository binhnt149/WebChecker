from __future__ import annotations

import re
import string
from email.utils import getaddresses
from typing import Any


RULE_TYPES = {
    "incident": "DOWN and recovery",
    "recovery_only": "Recovery only",
    "daily_summary": "Daily summary",
}
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
TEMPLATE_FIELDS = {
    "monitor_name", "url", "status", "checked_at", "error", "date",
    "total", "up", "down", "unknown", "down_count", "downtime",
}


def parse_recipients(raw: str) -> list[str]:
    recipients: list[str] = []
    for _, address in getaddresses([raw.replace(";", ",").replace("\n", ",")]):
        address = address.strip()
        if not address:
            continue
        if not re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+", address):
            raise ValueError(f"Invalid recipient: {address}")
        if address.casefold() not in {item.casefold() for item in recipients}:
            recipients.append(address)
    return recipients


def validate_template(template: str) -> None:
    for _, field, spec, conversion in string.Formatter().parse(template):
        if field is not None and (field not in TEMPLATE_FIELDS or spec or conversion):
            raise ValueError(f"Unsupported email placeholder: {field}")


def render_template(template: str, values: dict[str, Any]) -> str:
    validate_template(template)
    return template.format_map({key: str(values.get(key, "")) for key in TEMPLATE_FIELDS})


def normalize_rule(data: dict[str, Any]) -> dict[str, Any]:
    name = str(data.get("name") or "").strip()
    kind = str(data.get("rule_type") or "incident")
    if not name:
        raise ValueError("Schedule name is required")
    if kind not in RULE_TYPES:
        raise ValueError("Invalid email schedule type")
    hour = int(data.get("hour", 18))
    minute = int(data.get("minute", 0))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Send time is invalid")
    days = [day for day in str(data.get("weekdays") or "").split(",") if day]
    if kind == "daily_summary" and (not days or any(day not in WEEKDAYS for day in days)):
        raise ValueError("Select at least one valid weekday")
    period = str(data.get("report_period") or "today")
    if period not in {"today", "yesterday"}:
        raise ValueError("Invalid report period")
    recipients = str(data.get("recipients") or "").strip()
    if recipients:
        parse_recipients(recipients)
    subject = str(data.get("subject_template") or "").strip()
    if not subject:
        subject = "[SiteSentry] Daily summary {date}" if kind == "daily_summary" else "[SiteSentry] {status}: {monitor_name}"
    if "\n" in subject or "\r" in subject:
        raise ValueError("Subject must be a single line")
    body = str(data.get("body_template") or "")
    if not data.get("include_details", True) and not body.strip():
        raise ValueError("Message is required when the default HTML report is disabled")
    validate_template(subject)
    validate_template(body)
    return {
        "name": name, "rule_type": kind, "enabled": int(bool(data.get("enabled", True))),
        "recipients": recipients, "hour": hour, "minute": minute,
        "weekdays": ",".join(day for day in WEEKDAYS if day in days),
        "report_period": period, "subject_template": subject, "body_template": body,
        "include_details": int(bool(data.get("include_details", True))),
    }
