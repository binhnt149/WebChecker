from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit


URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
PRIVATE_DETAIL_KEYS = {"response_preview", "login_post_preview", "missing_text", "missing_text_normalized", "json_value", "actual"}


def safe_url(url: str) -> str:
    try:
        parts = urlsplit(str(url))
        return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", ""))
    except ValueError:
        return "[invalid URL]"


def _secrets(monitor: dict[str, Any]) -> set[str]:
    values = set()
    for key in ("auth_password", "api_token", "body", "auth_username"):
        if monitor.get(key):
            values.add(str(monitor[key]))
    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, str) and value:
            values.add(value)
    try:
        body = json.loads(monitor.get("body") or "null")
        collect(body)
    except (TypeError, ValueError):
        pass
    for key in ("headers_json", "auth_extra_fields"):
        try:
            parsed = json.loads(monitor.get(key) or "{}")
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            values.update(str(value) for value in parsed.values() if isinstance(value, str) and value)
    for key in ("url", "auth_login_url", "auth_verify_url"):
        try:
            parts = urlsplit(str(monitor.get(key) or ""))
            values.update(value for _, value in parse_qsl(parts.query) if value)
            values.update(value for value in (parts.username, parts.password) if value)
        except ValueError:
            continue
    return values


def sanitize(value: Any, monitor: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: sanitize(item, monitor) for key, item in value.items() if key not in PRIVATE_DETAIL_KEYS}
    if isinstance(value, list):
        return [sanitize(item, monitor) for item in value]
    if isinstance(value, str):
        value = URL_PATTERN.sub(lambda match: safe_url(match.group()), value)
        for secret in sorted(_secrets(monitor), key=len, reverse=True):
            value = value.replace(secret, "[redacted]")
        return value[:1000]
    return value


def sanitize_result(result: Any, monitor: dict[str, Any]) -> None:
    result.error = sanitize(result.error, monitor)
    result.details = sanitize(result.details, monitor)
    result.evidence = sanitize(result.evidence, monitor)
    result.reason_code = sanitize(result.reason_code, monitor)
