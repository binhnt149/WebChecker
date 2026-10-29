from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .security import SecurityManager
from .notification_store import NotificationStore
from .diagnostic_rules import validate_rules
from .network_diagnostics import validate_profile


SECRET_MONITOR_FIELDS = {
    "headers_json": "headers_enc",
    "body": "body_enc",
    "api_token": "api_token_enc",
    "auth_password": "auth_password_enc",
    "auth_extra_fields": "auth_extra_fields_enc",
    "diagnostic_rules_json": "diagnostic_rules_enc",
}

SCHEMA_VERSION = 2


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


class Database(NotificationStore):
    def __init__(
        self,
        db_path: str | Path = "data/sitesentry.db",
        security: SecurityManager | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.security = security or SecurityManager()
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self.init_schema()

    def init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS monitors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    monitor_type TEXT NOT NULL DEFAULT 'simple_web',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    url TEXT NOT NULL,
                    method TEXT NOT NULL DEFAULT 'GET',
                    interval_seconds INTEGER NOT NULL DEFAULT 60,
                    timeout_seconds REAL NOT NULL DEFAULT 10,
                    expected_status INTEGER NOT NULL DEFAULT 200,
                    expected_text TEXT DEFAULT '',
                    expected_json_path TEXT DEFAULT '',
                    expected_json_value TEXT DEFAULT '',
                    headers_enc TEXT DEFAULT '',
                    body_enc TEXT DEFAULT '',
                    api_token_enc TEXT DEFAULT '',
                    api_token_header TEXT DEFAULT 'Authorization',
                    api_token_prefix TEXT DEFAULT 'Bearer',
                    auth_login_url TEXT DEFAULT '',
                    auth_username TEXT DEFAULT '',
                    auth_password_enc TEXT DEFAULT '',
                    auth_username_field TEXT DEFAULT 'username',
                    auth_password_field TEXT DEFAULT 'password',
                    auth_extra_fields_enc TEXT DEFAULT '',
                    auth_verify_url TEXT DEFAULT '',
                    auth_verify_text TEXT DEFAULT '',
                    retry_count INTEGER NOT NULL DEFAULT 3,
                    retry_delay_seconds REAL NOT NULL DEFAULT 2,
                    cooldown_minutes INTEGER NOT NULL DEFAULT 30,
                    last_status TEXT NOT NULL DEFAULT 'unknown',
                    last_status_code INTEGER,
                    last_response_ms INTEGER,
                    last_checked_at TEXT,
                    last_error TEXT DEFAULT '',
                    last_alert_at TEXT,
                    last_recovery_alert_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    monitor_id INTEGER,
                    monitor_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    response_ms INTEGER,
                    status_code INTEGER,
                    error TEXT DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 1,
                    checked_at TEXT NOT NULL,
                    detail_json TEXT DEFAULT '',
                    FOREIGN KEY (monitor_id) REFERENCES monitors(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT DEFAULT '',
                    is_secret INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_logs_checked_at ON logs(checked_at DESC);
                CREATE INDEX IF NOT EXISTS idx_logs_monitor_id ON logs(monitor_id);
                CREATE INDEX IF NOT EXISTS idx_monitors_enabled ON monitors(enabled);

                CREATE TABLE IF NOT EXISTS network_profiles (
                    name TEXT PRIMARY KEY,
                    definition_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS network_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile TEXT NOT NULL,
                    state TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL DEFAULT '',
                    evidence_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS email_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    rule_type TEXT NOT NULL DEFAULT 'incident',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    recipients TEXT NOT NULL DEFAULT '',
                    hour INTEGER NOT NULL DEFAULT 18,
                    minute INTEGER NOT NULL DEFAULT 0,
                    weekdays TEXT NOT NULL DEFAULT 'mon,tue,wed,thu,fri,sat,sun',
                    report_period TEXT NOT NULL DEFAULT 'today',
                    subject_template TEXT NOT NULL DEFAULT '[SiteSentry] {status}: {monitor_name}',
                    body_template TEXT NOT NULL DEFAULT '',
                    include_details INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notification_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_key TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS email_deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL REFERENCES notification_events(id) ON DELETE CASCADE,
                    rule_id INTEGER NOT NULL REFERENCES email_rules(id) ON DELETE CASCADE,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_attempt_at TEXT,
                    sent_at TEXT,
                    remaining_recipients_json TEXT,
                    error TEXT NOT NULL DEFAULT '',
                    UNIQUE(event_id, rule_id)
                );
                CREATE INDEX IF NOT EXISTS idx_deliveries_status ON email_deliveries(status, last_attempt_at);
                """
            )
            columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(monitors)")}
            network_columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(network_events)")}
            if "last_seen_at" not in network_columns:
                self._conn.execute("ALTER TABLE network_events ADD COLUMN last_seen_at TEXT NOT NULL DEFAULT ''")
            for column in ("language", "web_server"):
                if column not in columns:
                    self._conn.execute(f"ALTER TABLE monitors ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
            if "last_error_type" not in columns:
                self._conn.execute("ALTER TABLE monitors ADD COLUMN last_error_type TEXT NOT NULL DEFAULT ''")
                self._conn.execute("UPDATE monitors SET last_error_type = 'unknown' WHERE last_status = 'down'")
            for name, definition in {
                "network_profile": "TEXT NOT NULL DEFAULT ''",
                "diagnostic_rules_enc": "TEXT NOT NULL DEFAULT ''",
                "last_classification_state": "TEXT NOT NULL DEFAULT 'legacy'",
                "last_reason_code": "TEXT NOT NULL DEFAULT ''",
                "last_phase": "TEXT NOT NULL DEFAULT ''",
            }.items():
                if name not in columns:
                    self._conn.execute(f"ALTER TABLE monitors ADD COLUMN {name} {definition}")
            log_columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(logs)")}
            if "error_type" not in log_columns:
                self._conn.execute("ALTER TABLE logs ADD COLUMN error_type TEXT NOT NULL DEFAULT ''")
                self._conn.execute("UPDATE logs SET error_type = 'unknown' WHERE status = 'down'")
            for name, definition in {
                "classification_state": "TEXT NOT NULL DEFAULT 'legacy'",
                "reason_code": "TEXT NOT NULL DEFAULT ''",
                "phase": "TEXT NOT NULL DEFAULT ''",
                "evidence_source": "TEXT NOT NULL DEFAULT ''",
                "evidence_json": "TEXT NOT NULL DEFAULT '{}'",
            }.items():
                if name not in log_columns:
                    self._conn.execute(f"ALTER TABLE logs ADD COLUMN {name} {definition}")
            delivery_columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(email_deliveries)")}
            if "remaining_recipients_json" not in delivery_columns:
                self._conn.execute("ALTER TABLE email_deliveries ADD COLUMN remaining_recipients_json TEXT")
            initialized = self._conn.execute("SELECT 1 FROM settings WHERE key = 'email_rules_initialized'").fetchone()
            if not initialized:
                stamp = now_iso()
                self._conn.execute(
                    "INSERT INTO email_rules (name, created_at, updated_at) VALUES (?, ?, ?)",
                    ("Incident alerts", stamp, stamp),
                )
                self._conn.execute(
                    "INSERT INTO settings (key, value, updated_at) VALUES ('email_rules_initialized', '1', ?)", (stamp,),
                )
            self.init_notification_features()
            version = self._conn.execute("PRAGMA user_version").fetchone()[0]
            if version < SCHEMA_VERSION:
                self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def list_network_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM network_events ORDER BY id DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        return [dict(row) for row in rows]

    def _monitor_row_to_dict(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        for plain_key, column in SECRET_MONITOR_FIELDS.items():
            data[plain_key] = self.security.decrypt(data.get(column))
            data.pop(column, None)
        data["diagnostic_rules_json"] = data["diagnostic_rules_json"] or "[]"
        return data

    def _monitor_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "name": str(data.get("name") or "Untitled monitor").strip(),
            "monitor_type": str(data.get("monitor_type") or "simple_web"),
            "enabled": 1 if data.get("enabled", True) else 0,
            "url": str(data.get("url") or "").strip(),
            "language": str(data.get("language") or "").strip(),
            "web_server": str(data.get("web_server") or "").strip(),
            "network_profile": str(data.get("network_profile") or "").strip(),
            "method": str(data.get("method") or "GET").upper(),
            "interval_seconds": max(10, as_int(data.get("interval_seconds"), 60)),
            "timeout_seconds": max(1.0, as_float(data.get("timeout_seconds"), 10.0)),
            "expected_status": as_int(data.get("expected_status"), 200),
            "expected_text": str(data.get("expected_text") or ""),
            "expected_json_path": str(data.get("expected_json_path") or ""),
            "expected_json_value": str(data.get("expected_json_value") or ""),
            "api_token_header": str(data.get("api_token_header") or "Authorization"),
            "api_token_prefix": str(data.get("api_token_prefix") or "Bearer"),
            "auth_login_url": str(data.get("auth_login_url") or ""),
            "auth_username": str(data.get("auth_username") or ""),
            "auth_username_field": str(data.get("auth_username_field") or "username"),
            "auth_password_field": str(data.get("auth_password_field") or "password"),
            "auth_verify_url": str(data.get("auth_verify_url") or ""),
            "auth_verify_text": str(data.get("auth_verify_text") or ""),
            "retry_count": max(1, as_int(data.get("retry_count"), 3)),
            "retry_delay_seconds": max(0.0, as_float(data.get("retry_delay_seconds"), 2.0)),
            "cooldown_minutes": max(0, as_int(data.get("cooldown_minutes"), 30)),
        }
        rules = json.dumps(validate_rules(data.get("diagnostic_rules_json")), ensure_ascii=False)
        for plain_key, column in SECRET_MONITOR_FIELDS.items():
            payload[column] = self.security.encrypt(rules if plain_key == "diagnostic_rules_json" else data.get(plain_key) or "")
        return payload

    def list_network_profiles(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT definition_json FROM network_profiles ORDER BY name COLLATE NOCASE").fetchall()
        return [json.loads(row[0]) for row in rows]

    def get_network_profile(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT definition_json FROM network_profiles WHERE name = ?", (name,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_network_profile(self, data: dict[str, Any]) -> str:
        profile = validate_profile(data)
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO network_profiles (name, definition_json) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET definition_json = excluded.definition_json", (profile["name"], json.dumps(profile, ensure_ascii=False)))
        return profile["name"]

    def delete_network_profile(self, name: str) -> None:
        with self._lock, self._conn:
            if self._conn.execute("SELECT 1 FROM monitors WHERE network_profile = ? LIMIT 1", (name,)).fetchone():
                raise ValueError("Network profile is used by a monitor")
            self._conn.execute("DELETE FROM network_profiles WHERE name = ?", (name,))

    def list_monitors(self, include_disabled: bool = True) -> list[dict[str, Any]]:
        sql = "SELECT * FROM monitors"
        params: tuple[Any, ...] = ()
        if not include_disabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY enabled DESC, name COLLATE NOCASE"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._monitor_row_to_dict(row) for row in rows if row is not None]

    def get_monitor(self, monitor_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
        return self._monitor_row_to_dict(row)

    def find_monitor_by_name_url(self, name: str, url: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM monitors WHERE name = ? AND url = ? LIMIT 1",
                (name, url),
            ).fetchone()
        return self._monitor_row_to_dict(row)

    def save_monitor(self, data: dict[str, Any]) -> int:
        stamp = now_iso()
        monitor_id = data.get("id")
        with self._lock, self._conn:
            data = dict(data)
            if monitor_id:
                existing = self._monitor_row_to_dict(self._conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone())
                if existing:
                    for field in ("language", "web_server", "network_profile", "diagnostic_rules_json"):
                        data.setdefault(field, existing[field])
            payload = self._monitor_payload(data)
            if payload["network_profile"] and not self._conn.execute("SELECT 1 FROM network_profiles WHERE name = ?", (payload["network_profile"],)).fetchone():
                raise ValueError("network_profile: profile does not exist")
            if monitor_id:
                payload["updated_at"] = stamp
                assignments = ", ".join(f"{key} = ?" for key in payload)
                values = list(payload.values()) + [monitor_id]
                self._conn.execute(f"UPDATE monitors SET {assignments} WHERE id = ?", values)
                return int(monitor_id)

            payload["created_at"] = stamp
            payload["updated_at"] = stamp
            columns = ", ".join(payload)
            placeholders = ", ".join("?" for _ in payload)
            cur = self._conn.execute(
                f"INSERT INTO monitors ({columns}) VALUES ({placeholders})",
                list(payload.values()),
            )
            return int(cur.lastrowid)

    def delete_monitor(self, monitor_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM monitors WHERE id = ?", (monitor_id,))

    def set_monitor_enabled(self, monitor_id: int, enabled: bool) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE monitors SET enabled = ?, updated_at = ? WHERE id = ?",
                (1 if enabled else 0, now_iso(), monitor_id),
            )

    def set_monitor_result(
        self,
        monitor_id: int,
        status: str,
        status_code: int | None,
        response_ms: int | None,
        error: str,
        checked_at: str | None = None,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE monitors
                SET last_status = ?,
                    last_status_code = ?,
                    last_response_ms = ?,
                    last_error = ?,
                    last_checked_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (status, status_code, response_ms, error, checked_at or now_iso(), now_iso(), monitor_id),
            )

    def mark_alert_sent(self, monitor_id: int, kind: str) -> None:
        column = "last_recovery_alert_at" if kind == "recovery" else "last_alert_at"
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE monitors SET {column} = ?, updated_at = ? WHERE id = ?",
                (now_iso(), now_iso(), monitor_id),
            )

    def add_log(
        self,
        monitor_id: int | None,
        monitor_name: str,
        status: str,
        ok: bool,
        response_ms: int | None,
        status_code: int | None,
        error: str = "",
        attempts: int = 1,
        detail_json: str = "",
        checked_at: str | None = None,
        error_type: str = "",
    ) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO logs (
                    monitor_id, monitor_name, status, ok, response_ms, status_code,
                    error, attempts, checked_at, detail_json, error_type, classification_state
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    monitor_id,
                    monitor_name,
                    status,
                    1 if ok else 0,
                    response_ms,
                    status_code,
                    error,
                    attempts,
                    checked_at or now_iso(),
                    detail_json,
                    error_type or ("unknown" if status == "down" else ""),
                    "not_applicable" if ok else ("confirmed" if error_type and error_type != "unknown" else "undetermined"),
                ),
            )
            return int(cur.lastrowid)

    def list_logs(
        self,
        limit: int = 500,
        status_filter: str | None = None,
        monitor_id: int | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        error_type: str | None = None,
        classification_state: str | None = None,
        phase: str | None = None,
        monitor_name: str | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if error_type and error_type != "all":
            where.append("error_type = ?")
            params.append(error_type)
        if classification_state and classification_state != "all":
            where.append("classification_state = ?")
            params.append(classification_state)
        if phase and phase != "all":
            where.append("phase = ?")
            params.append(phase)
        if monitor_name:
            where.append("instr(lower(monitor_name), lower(?)) > 0")
            params.append(monitor_name)
        if status_filter and status_filter != "all":
            where.append("status = ?")
            params.append(status_filter)
        if monitor_id:
            where.append("monitor_id = ?")
            params.append(monitor_id)
        if start_at:
            where.append("checked_at >= ?")
            params.append(start_at)
        if end_at:
            where.append("checked_at <= ?")
            params.append(end_at)

        sql = "SELECT * FROM logs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY checked_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            if item["classification_state"] == "legacy":
                item["error"] = "Legacy diagnostic details withheld" if item["error"] else ""
                item["detail_json"] = "{}"
                item["evidence_json"] = "{}"
            result.append(item)
        return result

    def clear_logs(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM logs")

    def report_logs(self, start_at: str, end_at: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                WITH earlier AS (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY CASE WHEN monitor_id IS NULL THEN 'name:' || monitor_name ELSE 'id:' || monitor_id END
                        ORDER BY checked_at DESC, id DESC
                    ) AS position
                    FROM logs WHERE checked_at < ?
                )
                SELECT id, monitor_id, monitor_name, status, checked_at, error_type, classification_state, reason_code, phase FROM earlier WHERE position = 1
                UNION ALL
                SELECT id, monitor_id, monitor_name, status, checked_at, error_type, classification_state, reason_code, phase FROM logs WHERE checked_at >= ? AND checked_at <= ?
                ORDER BY checked_at, id
                """, (start_at, start_at, end_at),
            ).fetchall()
        return [dict(row) for row in rows]


    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute("SELECT value, is_secret FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        value = row["value"] or ""
        if row["is_secret"]:
            return self.security.decrypt(value) or default
        return value

    def set_setting(self, key: str, value: object | None, secret: bool = False) -> None:
        encoded = self.security.encrypt(value) if secret else str(value or "")
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO settings (key, value, is_secret, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    is_secret = excluded.is_secret,
                    updated_at = excluded.updated_at
                """,
                (key, encoded, 1 if secret else 0, now_iso()),
            )

    def get_settings(self) -> dict[str, str]:
        with self._lock:
            rows = self._conn.execute("SELECT key, value, is_secret FROM settings").fetchall()
        settings: dict[str, str] = {}
        for row in rows:
            settings[row["key"]] = self.security.decrypt(row["value"]) if row["is_secret"] else row["value"]
        return settings
