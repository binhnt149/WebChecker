from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .database import Database


def format_duration(seconds: float) -> str:
    seconds = max(0, round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def build_report(db: Database, start: datetime, end: datetime, now: datetime | None = None) -> dict[str, Any]:
    if start > end:
        raise ValueError("From must be before To")
    effective_end = min(end, now or datetime.now())
    monitors = db.list_monitors(include_disabled=True)
    rows: dict[tuple[str, Any], dict[str, Any]] = {}
    for monitor in monitors:
        rows[("id", monitor["id"])] = {
            "monitor_id": monitor["id"], "monitor_name": monitor["name"],
            "language": monitor.get("language", ""), "web_server": monitor.get("web_server", ""),
            "down_count": 0, "incident_count": 0, "downtime_seconds": 0.0,
            "average_down_seconds": 0.0, "open_incidents": 0, "last_status": "unknown",
            "last_error_type": "", "error_counts": {},
        }
    active: dict[tuple[str, Any], tuple[datetime, bool]] = {}
    incidents: list[dict[str, Any]] = []
    active_errors: dict[tuple[str, Any], set[str]] = {}

    def close_incident(key: tuple[str, Any], until: datetime, is_open: bool) -> None:
        began, carried = active.pop(key)
        counted_from = max(began, start)
        counted_until = min(until, effective_end)
        if counted_until < counted_from or (carried and counted_until == counted_from):
            return
        seconds = (counted_until - counted_from).total_seconds()
        row = rows[key]
        row["incident_count"] += 1
        row["downtime_seconds"] += seconds
        row["open_incidents"] += int(is_open)
        incidents.append({
            "monitor_id": row["monitor_id"], "monitor_name": row["monitor_name"],
            "counted_from": counted_from.isoformat(timespec="seconds"),
            "counted_until": counted_until.isoformat(timespec="seconds"),
            "recovered_at": None if is_open else until.isoformat(timespec="seconds"),
            "duration_seconds": seconds, "carried_in": carried, "open": is_open,
            "error_types": sorted(active_errors.pop(key, set())),
        })

    logs = db.report_logs(start.isoformat(timespec="seconds"), effective_end.isoformat(timespec="seconds")) if effective_end >= start else []
    for log in logs:
        key = ("id", log["monitor_id"]) if log["monitor_id"] is not None else ("name", log["monitor_name"])
        if key not in rows:
            rows[key] = {
                "monitor_id": log["monitor_id"], "monitor_name": log["monitor_name"], "language": "", "web_server": "",
                "down_count": 0, "incident_count": 0, "downtime_seconds": 0.0,
                "average_down_seconds": 0.0, "open_incidents": 0, "last_status": "unknown",
                "last_error_type": "", "error_counts": {},
            }
        row = rows[key]
        checked_at = datetime.fromisoformat(log["checked_at"])
        state = log["status"]
        if state == "down":
            error_type = log.get("error_type") or "unknown"
            if checked_at >= start:
                row["down_count"] += 1
                row["error_counts"][error_type] = row["error_counts"].get(error_type, 0) + 1
            if key not in active:
                active[key] = (max(checked_at, start), checked_at < start)
                active_errors[key] = set()
            active_errors[key].add(error_type)
        elif state == "up" and key in active:
            close_incident(key, checked_at, False)
        if state in {"up", "down"}:
            row["last_status"] = state
            row["last_error_type"] = (log.get("error_type") or "unknown") if state == "down" else ""
    for key in list(active):
        close_incident(key, effective_end, True)
    for row in rows.values():
        if row["incident_count"]:
            row["average_down_seconds"] = row["downtime_seconds"] / row["incident_count"]
    values = sorted(rows.values(), key=lambda row: row["monitor_name"].casefold())
    current_ids = {monitor["id"] for monitor in monitors}
    current = [row for row in values if row["monitor_id"] in current_ids]
    error_counts: dict[str, int] = {}
    for row in values:
        for code, count in row["error_counts"].items():
            error_counts[code] = error_counts.get(code, 0) + count
    return {
        "start_at": start.isoformat(timespec="seconds"), "end_at": end.isoformat(timespec="seconds"),
        "as_of": effective_end.isoformat(timespec="seconds"), "rows": values, "incidents": incidents,
        "total": len(current), "up": sum(row["last_status"] == "up" for row in current),
        "down": sum(row["last_status"] == "down" for row in current),
        "unknown": sum(row["last_status"] == "unknown" for row in current),
        "down_count": sum(row["down_count"] for row in values),
        "downtime_seconds": sum(row["downtime_seconds"] for row in values),
        "error_counts": error_counts,
    }


def filter_email_summary(report: dict[str, Any], excluded: set[str]) -> dict[str, Any]:
    result = dict(report)
    rows = [row for row in report["rows"] if not (row["last_status"] == "down" and row.get("last_error_type", "unknown") in excluded)]
    result["rows"] = rows
    result["excluded_monitor_count"] = len(report["rows"]) - len(rows)
    current = [row for row in rows if row["monitor_id"] is not None]
    result.update(total=len(current), up=sum(row["last_status"] == "up" for row in current), down=sum(row["last_status"] == "down" for row in current), unknown=sum(row["last_status"] == "unknown" for row in current), down_count=sum(row["down_count"] for row in rows), downtime_seconds=sum(row["downtime_seconds"] for row in rows))
    return result


def export_report(report: dict[str, Any], path: str | Path) -> None:
    from .report_export import export_report as write_report
    write_report(report, path)
