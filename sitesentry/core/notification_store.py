from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from .diagnostics import decoded_exclusions, result_category
from .email_rules import normalize_rule
from .privacy import sanitize, sanitize_result


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _has_classified_evidence(result: dict[str, Any]) -> bool:
    category = result.get("error_type")
    if not category or category == "unknown" or result.get("classification_state") == "undetermined":
        return False
    if result.get("classification_state") == "confirmed" and result.get("evidence"):
        return True
    status = result.get("status_code")
    return type(status) is int and ((category == "auth_credentials" and status == 401) or (category == "http_error" and 400 <= status <= 599))


class NotificationStore:
    """Notification persistence; Database supplies the shared connection and lock."""

    def init_notification_features(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS email_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id INTEGER NOT NULL REFERENCES email_rules(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                ready_at TEXT NOT NULL,
                closed INTEGER NOT NULL DEFAULT 0,
                blocked_monitors_json TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS email_incident_state (
                rule_id INTEGER NOT NULL REFERENCES email_rules(id) ON DELETE CASCADE,
                monitor_id INTEGER NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
                down_queued INTEGER NOT NULL DEFAULT 0,
                error_type TEXT NOT NULL DEFAULT '',
                down_event_id INTEGER,
                PRIMARY KEY(rule_id, monitor_id)
            );
            CREATE INDEX IF NOT EXISTS idx_batches_ready ON email_batches(rule_id, ready_at);
        """)
        for table, definitions in {
            "email_rules": {"excluded_error_types_json": "TEXT NOT NULL DEFAULT '[]'", "batch_window_seconds": "INTEGER NOT NULL DEFAULT 15"},
            "email_deliveries": {"batch_id": "INTEGER REFERENCES email_batches(id) ON DELETE SET NULL", "rule_type_at_creation": "TEXT NOT NULL DEFAULT ''"},
            "email_batches": {"closed": "INTEGER NOT NULL DEFAULT 0", "blocked_monitors_json": "TEXT NOT NULL DEFAULT '[]'"},
            "email_incident_state": {"down_event_id": "INTEGER", "reason_code": "TEXT NOT NULL DEFAULT ''", "phase": "TEXT NOT NULL DEFAULT ''", "evidence_source": "TEXT NOT NULL DEFAULT ''", "evidence_json": "TEXT NOT NULL DEFAULT '{}'"},
        }.items():
            columns = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})")}
            for name, definition in definitions.items():
                if name not in columns:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        self._conn.execute("UPDATE email_deliveries SET rule_type_at_creation = 'legacy_unknown' WHERE rule_type_at_creation = ''")
        wanted = {(row["rule_id"], row["monitor_id"]) for row in self._conn.execute("SELECT rule_id, monitor_id FROM email_incident_state WHERE down_queued = 1 AND down_event_id IS NULL")}
        if wanted:
            history = self._conn.execute("SELECT d.rule_id, e.id, e.payload_json FROM email_deliveries d JOIN notification_events e ON e.id = d.event_id WHERE e.kind = 'down' ORDER BY e.id DESC").fetchall()
            for event in history:
                key = (event["rule_id"], json.loads(event["payload_json"])["monitor"]["id"])
                if key in wanted:
                    prior = json.loads(event["payload_json"]).get("result", {})
                    self._conn.execute("UPDATE email_incident_state SET down_event_id = ?, reason_code = ?, phase = ?, evidence_source = ?, evidence_json = ? WHERE rule_id = ? AND monitor_id = ?", (event["id"], prior.get("reason_code", ""), prior.get("phase", ""), prior.get("evidence_source", ""), json.dumps(prior.get("evidence", {}), ensure_ascii=False), *key))
                    wanted.remove(key)
        initialized = self._conn.execute("SELECT 1 FROM settings WHERE key = 'incident_policy_initialized'").fetchone()
        if not initialized:
            rows = self._conn.execute("""
                SELECT d.rule_id, e.id, e.kind, e.payload_json FROM email_deliveries d
                JOIN notification_events e ON e.id = d.event_id
                WHERE e.kind IN ('down', 'recovery') ORDER BY e.id
            """).fetchall()
            for row in rows:
                payload = json.loads(row["payload_json"])
                monitor_id = payload["monitor"]["id"]
                if row["kind"] == "recovery":
                    self._conn.execute("DELETE FROM email_incident_state WHERE rule_id = ? AND monitor_id = ?", (row["rule_id"], monitor_id))
                elif self._conn.execute("SELECT 1 FROM monitors WHERE id = ? AND last_status = 'down'", (monitor_id,)).fetchone():
                    self._conn.execute(
                        "INSERT OR REPLACE INTO email_incident_state (rule_id, monitor_id, down_queued, error_type, down_event_id, reason_code, phase, evidence_source, evidence_json) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)",
                        (row["rule_id"], monitor_id, payload["result"].get("error_type", "unknown"), row["id"], payload["result"].get("reason_code", ""), payload["result"].get("phase", ""), payload["result"].get("evidence_source", ""), json.dumps(payload["result"].get("evidence", {}), ensure_ascii=False)),
                    )
            self._conn.execute("INSERT INTO settings (key, value, updated_at) VALUES ('incident_policy_initialized', '1', ?)", (now_iso(),))
        self._conn.execute("UPDATE email_deliveries SET status = 'delivery_uncertain', error = 'Interrupted during SMTP attempt' WHERE status = 'sending'")
        pending = self._conn.execute("SELECT d.id, d.event_id, d.rule_id, e.kind, e.payload_json FROM email_deliveries d JOIN notification_events e ON e.id = d.event_id WHERE d.status IN ('pending', 'failed') AND e.kind IN ('down', 'recovery')").fetchall()
        for delivery in pending:
            payload = json.loads(delivery["payload_json"])
            result = payload.get("result", {})
            if not _has_classified_evidence(result):
                self._conn.execute("UPDATE email_deliveries SET status = 'held', error = 'Cause not classified' WHERE id = ?", (delivery["id"],))
                self._conn.execute("UPDATE email_incident_state SET down_queued = 0 WHERE rule_id = ? AND down_event_id = ?", (delivery["rule_id"], delivery["event_id"]))

    def list_email_rules(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM email_rules" + (" WHERE enabled = 1" if enabled_only else "") + " ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def get_email_rule(self, rule_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM email_rules WHERE id = ?", (rule_id,)).fetchone()
        return dict(row) if row else None

    def save_email_rule(self, data: dict[str, Any]) -> int:
        payload = normalize_rule(data)
        stamp = now_iso()
        with self._lock, self._conn:
            if data.get("id"):
                payload["updated_at"] = stamp
                fields = ", ".join(f"{key} = ?" for key in payload)
                self._conn.execute(f"UPDATE email_rules SET {fields} WHERE id = ?", [*payload.values(), int(data["id"])])
                self._suppress_excluded(int(data["id"]), decoded_exclusions(payload))
                return int(data["id"])
            payload.update(created_at=stamp, updated_at=stamp)
            columns = ", ".join(payload)
            values = ", ".join("?" for _ in payload)
            cursor = self._conn.execute(f"INSERT INTO email_rules ({columns}) VALUES ({values})", list(payload.values()))
            return int(cursor.lastrowid)

    def _suppress_excluded(self, rule_id: int, excluded: set[str]) -> None:
        rows = self._conn.execute("""
            SELECT d.id, d.event_id, d.attempts, d.rule_type_at_creation, e.kind, e.payload_json FROM email_deliveries d
            JOIN notification_events e ON e.id = d.event_id
            WHERE d.rule_id = ? AND d.status NOT IN ('sent', 'suppressed') ORDER BY e.id
        """, (rule_id,)).fetchall()
        suppressed_down: dict[int, bool] = {}
        for row in rows:
            if row["kind"] not in {"down", "recovery"}:
                continue
            payload = json.loads(row["payload_json"])
            monitor_id = payload["monitor"]["id"]
            if row["kind"] == "down":
                suppress = row["attempts"] == 0 and payload["result"].get("error_type", "unknown") in excluded
                suppressed_down[monitor_id] = suppress
            else:
                suppress = row["attempts"] == 0 and (suppressed_down.get(monitor_id, False) or (row["rule_type_at_creation"] in {"recovery_only", "legacy_unknown"} and payload["result"].get("error_type", "unknown") in excluded))
            if suppress:
                self._conn.execute("UPDATE email_deliveries SET status = 'suppressed', error = 'Excluded by email rule' WHERE id = ?", (row["id"],))
                self._conn.execute("UPDATE email_incident_state SET down_queued = 0 WHERE rule_id = ? AND monitor_id = ? AND down_event_id = ?", (rule_id, monitor_id, row["event_id"]))

    def delete_email_rule(self, rule_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM email_rules WHERE id = ?", (rule_id,))

    def _queue_event(self, event_key: str, kind: str, payload: dict[str, Any], rule_ids: list[int]) -> int:
        cursor = self._conn.execute(
            "INSERT OR IGNORE INTO notification_events (event_key, kind, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (event_key, kind, json.dumps(payload, ensure_ascii=False), now_iso()),
        )
        if cursor.rowcount:
            event_id = int(cursor.lastrowid)
            for rule_id in rule_ids:
                batch_id = None
                rule = self._conn.execute("SELECT batch_window_seconds, rule_type FROM email_rules WHERE id = ?", (rule_id,)).fetchone()
                window = rule["batch_window_seconds"]
                if kind == "recovery":
                    self._apply_recovery_barrier(rule_id, payload["monitor"]["id"])
                if kind == "down" and window:
                    stamp = now_iso()
                    batch = self._conn.execute("SELECT id, blocked_monitors_json FROM email_batches WHERE rule_id = ? AND closed = 0 AND ready_at > ? ORDER BY id DESC LIMIT 1", (rule_id, stamp)).fetchone()
                    if batch and payload["monitor"]["id"] in json.loads(batch["blocked_monitors_json"]):
                        batch = None
                    if batch:
                        members = self.email_batch_members(batch["id"])
                        if any(json.loads(member["payload_json"])["monitor"]["id"] == payload["monitor"]["id"] for member in members):
                            batch = None
                    if batch:
                        batch_id = batch["id"]
                    else:
                        ready_at = (datetime.fromisoformat(stamp) + timedelta(seconds=window)).isoformat(timespec="seconds")
                        batch_id = self._conn.execute("INSERT INTO email_batches (rule_id, created_at, ready_at) VALUES (?, ?, ?)", (rule_id, stamp, ready_at)).lastrowid
                self._conn.execute("INSERT INTO email_deliveries (event_id, rule_id, batch_id, rule_type_at_creation) VALUES (?, ?, ?, ?)", (event_id, rule_id, batch_id, rule["rule_type"]))
            return event_id
        return 0

    def _apply_recovery_barrier(self, rule_id: int, monitor_id: int) -> None:
        batches = self._conn.execute("SELECT id, blocked_monitors_json FROM email_batches WHERE rule_id = ? AND closed = 0 AND ready_at > ?", (rule_id, now_iso())).fetchall()
        for batch in batches:
            members = self.email_batch_members(batch["id"])
            if any(json.loads(member["payload_json"])["monitor"]["id"] == monitor_id for member in members):
                self._conn.execute("UPDATE email_batches SET closed = 1 WHERE id = ?", (batch["id"],))
            else:
                blocked = set(json.loads(batch["blocked_monitors_json"]))
                blocked.add(monitor_id)
                self._conn.execute("UPDATE email_batches SET blocked_monitors_json = ? WHERE id = ?", (json.dumps(sorted(blocked)), batch["id"]))

    def queue_summary(self, rule_id: int, slot: str, report: dict[str, Any]) -> int:
        with self._lock, self._conn:
            rule = self._conn.execute("SELECT * FROM email_rules WHERE id = ? AND enabled = 1 AND rule_type = 'daily_summary'", (rule_id,)).fetchone()
            if not rule:
                return 0
            return self._queue_event(f"summary:{rule_id}:{slot}", "daily_summary", {"report": report}, [rule_id])

    def record_check_result(self, monitor_id: int, result: Any) -> bool:
        status = "up" if result.ok else "down"
        result.error_type = result_category(result)
        result.classification_state = result.classification_state or ("not_applicable" if result.ok else ("undetermined" if result.error_type == "unknown" else "confirmed"))
        if not result.ok and result.error_type == "unknown":
            result.classification_state = "undetermined"
        with self._lock, self._conn:
            row = self._conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
            if row is None or not row["enabled"]:
                return False
            monitor = dict(row)
            decoded_monitor = self._monitor_row_to_dict(row)
            if not result.ok and result.classification_state == "confirmed" and not result.evidence:
                if result.status_code is not None and result.error_type in {"http_error", "auth_credentials"}:
                    result.evidence = {"status_code": result.status_code, "expected_status": monitor["expected_status"]}
                    result.evidence_source = result.evidence_source or "http"
                elif result.details.get("exception_kind"):
                    result.evidence = {"exception_kind": result.details["exception_kind"]}
                    result.evidence_source = result.evidence_source or "transport"
                else:
                    result.classification_state = "undetermined"
            if not result.ok and result.classification_state != "confirmed":
                result.error_type = "unknown"
            sanitize_result(result, decoded_monitor)
            cursor = self._conn.execute(
                """INSERT INTO logs (monitor_id, monitor_name, status, ok, response_ms, status_code,
                    error, attempts, checked_at, detail_json, error_type, classification_state, reason_code, phase, evidence_source, evidence_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (monitor_id, sanitize(monitor["name"], decoded_monitor), status, int(result.ok), result.response_ms, result.status_code,
                 result.error, result.attempts, result.checked_at, result.detail_json(), result.error_type, result.classification_state, result.reason_code, result.phase, result.evidence_source, json.dumps(result.evidence, ensure_ascii=False)),
            )
            self._conn.execute(
                """UPDATE monitors SET last_status = ?, last_status_code = ?, last_response_ms = ?,
                    last_error = ?, last_error_type = ?, last_checked_at = ?, last_classification_state = ?, last_reason_code = ?, last_phase = ?, updated_at = ? WHERE id = ?""",
                (status, result.status_code, result.response_ms, result.error, result.error_type, result.checked_at, result.classification_state, result.reason_code, result.phase, now_iso(), monitor_id),
            )
            old = monitor["last_status"]
            smtp_setting = self._conn.execute("SELECT value FROM settings WHERE key = 'smtp_enabled'").fetchone()
            alerts_enabled = smtp_setting and smtp_setting["value"] == "1"
            rules = self._conn.execute("SELECT * FROM email_rules WHERE rule_type != 'daily_summary'").fetchall()
            for rule_row in rules:
                rule = dict(rule_row)
                state = self._conn.execute("SELECT * FROM email_incident_state WHERE rule_id = ? AND monitor_id = ?", (rule["id"], monitor_id)).fetchone()
                queued = bool(state and state["down_queued"] and old == "down")
                cause = state["error_type"] if state and old == "down" else monitor["last_error_type"]
                diagnosis = {"reason_code": state["reason_code"], "phase": state["phase"], "evidence_source": state["evidence_source"], "evidence": json.loads(state["evidence_json"])} if state and old == "down" else {"reason_code": "", "phase": "", "evidence_source": "", "evidence": {}}
                excluded = decoded_exclusions(rule)
                kind = ""
                if result.ok:
                    if old == "down" and ((rule["rule_type"] == "incident" and queued) or (rule["rule_type"] == "recovery_only" and cause and cause != "unknown" and cause not in excluded)):
                        kind = "recovery"
                    self._conn.execute("DELETE FROM email_incident_state WHERE rule_id = ? AND monitor_id = ?", (rule["id"], monitor_id))
                else:
                    if not queued:
                        if result.classification_state == "confirmed" and result.error_type != "unknown":
                            cause = result.error_type
                            diagnosis = {"reason_code": result.reason_code, "phase": result.phase, "evidence_source": result.evidence_source, "evidence": result.evidence}
                            if rule["rule_type"] == "incident" and cause not in excluded:
                                kind = "down"
                        elif not cause:
                            cause = "unknown"
                    eligible = bool(kind and alerts_enabled and rule["enabled"])
                    self._conn.execute("INSERT OR REPLACE INTO email_incident_state (rule_id, monitor_id, down_queued, error_type, down_event_id, reason_code, phase, evidence_source, evidence_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (rule["id"], monitor_id, int(queued or eligible), cause, state["down_event_id"] if queued else None, diagnosis["reason_code"], diagnosis["phase"], diagnosis["evidence_source"], json.dumps(diagnosis["evidence"], ensure_ascii=False)))
                if kind and alerts_enabled and rule["enabled"]:
                    safe_monitor = sanitize({key: monitor[key] for key in ("id", "name", "url", "monitor_type", "language", "web_server")}, decoded_monitor)
                    payload = {"monitor": safe_monitor, "result": {
                        "ok": result.ok, "status": status, "response_ms": result.response_ms,
                        "status_code": result.status_code, "error": result.error,
                        "attempts": result.attempts, "checked_at": result.checked_at,
                        "error_type": cause if result.ok else result.error_type,
                        "classification_state": "confirmed", **diagnosis,
                    }}
                    event_id = self._queue_event(f"log:{cursor.lastrowid}:{kind}:rule:{rule['id']}", kind, payload, [rule["id"]])
                    if kind == "down":
                        self._conn.execute("UPDATE email_incident_state SET down_event_id = ? WHERE rule_id = ? AND monitor_id = ?", (event_id, rule["id"], monitor_id))
            return True

    def pending_email_deliveries(self, now: datetime | None = None) -> list[dict[str, Any]]:
        cutoff = ((now or datetime.now()) - timedelta(minutes=1)).isoformat(timespec="seconds")
        with self._lock:
            rows = self._conn.execute(
                """SELECT d.id AS delivery_id, d.event_id, d.attempts, d.batch_id, d.remaining_recipients_json, e.kind, e.payload_json, r.*
                   FROM email_deliveries d JOIN notification_events e ON e.id = d.event_id
                   JOIN email_rules r ON r.id = d.rule_id
                   LEFT JOIN email_batches b ON b.id = d.batch_id
                   WHERE r.enabled = 1 AND d.status IN ('pending', 'failed')
                     AND (d.last_attempt_at IS NULL OR d.last_attempt_at <= ?)
                     AND (b.ready_at IS NULL OR b.ready_at <= ?)
                     AND NOT EXISTS (
                         SELECT 1 FROM email_deliveries prior WHERE prior.rule_id = d.rule_id
                           AND prior.event_id < d.event_id AND prior.status NOT IN ('sent', 'suppressed', 'held')
                     )
                   ORDER BY d.event_id, d.id LIMIT 100""", (cutoff, (now or datetime.now()).isoformat(timespec="seconds")),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_delivery_attempt(self, delivery_id: int) -> bool:
        with self._lock, self._conn:
            eligible = self._conn.execute("SELECT d.id, e.kind, e.payload_json FROM email_deliveries d JOIN email_rules r ON r.id = d.rule_id JOIN notification_events e ON e.id = d.event_id WHERE d.id = ? AND r.enabled = 1 AND d.status IN ('pending', 'failed')", (delivery_id,)).fetchone()
            if not eligible:
                return False
            members = self._conn.execute("SELECT d.id, d.event_id, d.rule_id, e.kind, e.payload_json FROM email_deliveries d JOIN notification_events e ON e.id = d.event_id WHERE d.status IN ('pending', 'failed') AND (d.id = ? OR d.batch_id = (SELECT batch_id FROM email_deliveries WHERE id = ?))", (delivery_id, delivery_id)).fetchall()
            leader_held = False
            for member in members:
                if member["kind"] not in {"down", "recovery"}:
                    continue
                result = json.loads(member["payload_json"]).get("result", {})
                if not _has_classified_evidence(result):
                    self._conn.execute("UPDATE email_deliveries SET status = 'held', error = 'Cause not classified' WHERE id = ?", (member["id"],))
                    self._conn.execute("UPDATE email_incident_state SET down_queued = 0 WHERE rule_id = ? AND down_event_id = ?", (member["rule_id"], member["event_id"]))
                    leader_held |= member["id"] == delivery_id
            if leader_held:
                return False
            self._conn.execute("UPDATE email_batches SET closed = 1 WHERE id = (SELECT batch_id FROM email_deliveries WHERE id = ?)", (delivery_id,))
            self._conn.execute("UPDATE email_deliveries SET status = 'sending', attempts = attempts + 1, last_attempt_at = ? WHERE status IN ('pending', 'failed') AND (id = ? OR batch_id = (SELECT batch_id FROM email_deliveries WHERE id = ?))", (now_iso(), delivery_id, delivery_id))
            return True

    def set_delivery_recipients(self, delivery_id: int, recipients: list[str]) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE email_deliveries SET remaining_recipients_json = ? WHERE status = 'sending' AND (id = ? OR batch_id = (SELECT batch_id FROM email_deliveries WHERE id = ?))", (json.dumps(recipients), delivery_id, delivery_id))

    def finish_email_delivery(self, delivery_id: int, sent: bool, error: str = "") -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE email_deliveries SET status = ?, sent_at = ?, error = ? WHERE status = 'sending' AND (id = ? OR batch_id = (SELECT batch_id FROM email_deliveries WHERE id = ?))",
                ("sent" if sent else ("delivery_uncertain" if error.startswith("delivery_uncertain:") else "failed"), now_iso() if sent else None, "" if sent else error, delivery_id, delivery_id),
            )

    def retry_uncertain_delivery(self, delivery_id: int) -> None:
        with self._lock, self._conn:
            row = self._conn.execute("SELECT e.kind, e.payload_json FROM email_deliveries d JOIN notification_events e ON e.id = d.event_id WHERE d.id = ? AND d.status = 'delivery_uncertain'", (delivery_id,)).fetchone()
            if not row:
                raise ValueError("Uncertain delivery not found")
            if row["kind"] in {"down", "recovery"} and not _has_classified_evidence(json.loads(row["payload_json"]).get("result", {})):
                raise ValueError("Cannot retry an unclassified incident")
            self._conn.execute("UPDATE email_deliveries SET status = 'pending', last_attempt_at = NULL, error = '' WHERE status = 'delivery_uncertain' AND (id = ? OR batch_id = (SELECT batch_id FROM email_deliveries WHERE id = ?))", (delivery_id, delivery_id))

    def email_batch_members(self, batch_id: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT e.kind, e.payload_json FROM email_deliveries d JOIN notification_events e ON e.id = d.event_id WHERE d.batch_id = ? AND d.status NOT IN ('suppressed', 'held') ORDER BY e.id", (batch_id,)).fetchall()
        return [dict(row) for row in rows]

    def email_delivery_counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute("SELECT status, COUNT(*) AS total FROM email_deliveries GROUP BY status").fetchall()
        return {row["status"]: row["total"] for row in rows}

    def list_problem_deliveries(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT d.id, d.status, e.kind, e.payload_json, r.name AS rule_name FROM email_deliveries d JOIN notification_events e ON e.id = d.event_id JOIN email_rules r ON r.id = d.rule_id WHERE d.status IN ('held', 'delivery_uncertain') ORDER BY d.id").fetchall()
        result = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            item = payload.get("monitor", {})
            monitor = self.get_monitor(item.get("id")) if item.get("id") else None
            result.append({"id": row["id"], "status": row["status"], "kind": row["kind"], "rule_name": row["rule_name"], "monitor_name": sanitize(item.get("name", "Summary"), monitor or {}), "error_type": payload.get("result", {}).get("error_type", "")})
        return result
