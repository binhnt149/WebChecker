from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

import httpx

from .diagnostics import ERROR_TYPES, visible_text


PHASES = {"login_page", "login_submit", "verify", "response", "assertion"}
OPERATORS = {"http_status": {"equals", "range"}, "visible_text": {"equals", "contains"}, "json": {"equals", "not_equals"}}


def extract_json_path(payload: Any, path: str) -> Any:
    current = payload
    for part in [piece for piece in path.strip().split(".") if piece]:
        name, index = part, None
        if part.endswith("]") and "[" in part:
            name, index_part = part[:-1].split("[", 1)
            index = int(index_part)
        if name:
            if not isinstance(current, dict) or name not in current:
                raise KeyError(path)
            current = current[name]
        if index is not None:
            if not isinstance(current, list):
                raise KeyError(path)
            current = current[index]
    return current


def validate_rules(raw: Any) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        return []
    try:
        rules = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Diagnostic rules must be valid JSON") from exc
    if not isinstance(rules, list) or len(rules) > 20:
        raise ValueError("Diagnostic rules must be a list of at most 20 rules")
    ids = set()
    for item in rules:
        if not isinstance(item, dict):
            raise ValueError("Each diagnostic rule must be an object")
        rule_id, priority, phase = item.get("id"), item.get("priority"), item.get("phase")
        if not isinstance(rule_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", rule_id) or rule_id in ids:
            raise ValueError("Rule ID must be unique and contain 1–64 letters, numbers, _ or -")
        ids.add(rule_id)
        if type(item.get("enabled")) is not bool or type(priority) is not int or phase not in PHASES:
            raise ValueError(f"Rule {rule_id}: invalid enabled, priority or phase")
        result, conditions = item.get("result"), item.get("conditions")
        if not isinstance(result, dict) or result.get("error_type") not in ERROR_TYPES or result.get("error_type") in {"unknown", "network_offline"}:
            raise ValueError(f"Rule {rule_id}: invalid error category")
        reason = result.get("reason_code", "")
        if not isinstance(reason, str) or (reason and not re.fullmatch(r"[a-z0-9_]{1,64}", reason)):
            raise ValueError(f"Rule {rule_id}: invalid reason code")
        if not isinstance(conditions, list) or not conditions or len(conditions) > 20:
            raise ValueError(f"Rule {rule_id}: conditions must be a nonempty list of at most 20 items")
        for condition in conditions:
            if not isinstance(condition, dict):
                raise ValueError(f"Rule {rule_id}: condition must be an object")
            source, operator = condition.get("source"), condition.get("operator")
            if source not in OPERATORS or operator not in OPERATORS[source] or "value" not in condition:
                raise ValueError(f"Rule {rule_id}: invalid condition source, operator or value")
            value = condition["value"]
            if len(json.dumps(value, ensure_ascii=False)) > 1024:
                raise ValueError(f"Rule {rule_id}: condition value exceeds 1024 characters")
            if source == "http_status":
                valid_code = lambda code: type(code) is int and 100 <= code <= 599
                if operator == "equals" and not valid_code(value):
                    raise ValueError(f"Rule {rule_id}: invalid HTTP status")
                if operator == "range" and not (isinstance(value, list) and len(value) == 2 and all(valid_code(v) for v in value) and value[0] <= value[1]):
                    raise ValueError(f"Rule {rule_id}: invalid HTTP range")
            elif source == "visible_text":
                if not isinstance(value, str) or not value or type(condition.get("case_sensitive", False)) is not bool:
                    raise ValueError(f"Rule {rule_id}: invalid visible text")
            elif not isinstance(condition.get("path"), str) or not re.fullmatch(r"(?:[^.\[\]\s]+(?:\[\d+\])?|\[\d+\])(?:\.(?:[^.\[\]\s]+(?:\[\d+\])?|\[\d+\]))*", condition["path"]):
                raise ValueError(f"Rule {rule_id}: invalid JSON path")
    return rules


def _typed_equal(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return actual == expected
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(_typed_equal(a, b) for a, b in zip(actual, expected))
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(_typed_equal(actual[key], expected[key]) for key in actual)
    return actual == expected


def _condition_matches(condition: dict[str, Any], response: httpx.Response) -> bool:
    source, operator, value = condition["source"], condition["operator"], condition["value"]
    if source == "http_status":
        return response.status_code == value if operator == "equals" else value[0] <= response.status_code <= value[1]
    if source == "visible_text":
        actual = " ".join(unicodedata.normalize("NFC", visible_text(response.text)).split())
        expected = " ".join(unicodedata.normalize("NFC", value).split())
        if not condition.get("case_sensitive", False):
            actual, expected = actual.casefold(), expected.casefold()
        return actual == expected if operator == "equals" else expected in actual
    try:
        actual = extract_json_path(response.json(), condition["path"])
    except (KeyError, IndexError, TypeError, ValueError):
        return False
    equal = _typed_equal(actual, value)
    return equal if operator == "equals" else not equal


def match_rules(rules: list[dict[str, Any]], response: httpx.Response, phase: str) -> dict[str, Any] | None:
    matches = []
    for item in rules:
        if not item["enabled"] or item["phase"] != phase or response.status_code >= 500:
            continue
        if response.status_code in {401, 403, 429}:
            sources = {condition["source"] for condition in item["conditions"]}
            if "http_status" not in sources or not sources.intersection({"json", "visible_text"}):
                continue
        if all(_condition_matches(condition, response) for condition in item["conditions"]):
            matches.append(item)
    if not matches:
        return None
    priority = max(item["priority"] for item in matches)
    winners = sorted((item for item in matches if item["priority"] == priority), key=lambda item: item["id"])
    ids = [item["id"] for item in winners]
    if len({item["result"]["error_type"] for item in winners}) > 1:
        return {"error_type": "unknown", "reason_code": "conflicting_evidence", "rule_ids": ids}
    return {**winners[0]["result"], "rule_id": winners[0]["id"], "rule_ids": ids}
