from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .database import now_iso


@dataclass
class CheckResult:
    ok: bool
    status: str
    response_ms: int | None = None
    status_code: int | None = None
    error: str = ""
    attempts: int = 1
    checked_at: str = field(default_factory=now_iso)
    details: dict[str, Any] = field(default_factory=dict)

    def detail_json(self) -> str:
        try:
            return json.dumps(self.details, ensure_ascii=False)
        except TypeError:
            return "{}"


def headers_from_json(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Headers JSON is invalid: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Headers JSON must be an object")
    return {str(key): str(value) for key, value in parsed.items()}


def extract_json_path(payload: Any, path: str) -> Any:
    current = payload
    for part in [piece for piece in path.strip().split(".") if piece]:
        name = part
        index: int | None = None
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


class SiteChecker:
    def __init__(self, user_agent: str = "SiteSentry Desktop/1.0") -> None:
        self.user_agent = user_agent

    async def check_monitor(self, monitor: dict[str, Any]) -> CheckResult:
        retry_count = max(1, int(monitor.get("retry_count") or 1))
        retry_delay = max(0.0, float(monitor.get("retry_delay_seconds") or 0.0))
        last_result: CheckResult | None = None

        for attempt in range(1, retry_count + 1):
            result = await self._check_once(monitor)
            result.attempts = attempt
            if result.ok:
                return result
            last_result = result
            if attempt < retry_count and retry_delay:
                await asyncio.sleep(retry_delay)

        return last_result or CheckResult(False, "down", error="No check attempts were executed")

    async def _check_once(self, monitor: dict[str, Any]) -> CheckResult:
        monitor_type = monitor.get("monitor_type") or "simple_web"
        try:
            if monitor_type == "auth_web":
                return await self._check_auth_web(monitor)
            if monitor_type == "api":
                return await self._check_api(monitor)
            return await self._check_simple_web(monitor)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError, ValueError, KeyError) as exc:
            return CheckResult(False, "down", error=str(exc))
        except Exception as exc:  # Defensive boundary for background jobs.
            return CheckResult(False, "down", error=f"{type(exc).__name__}: {exc}")

    def _timeout(self, monitor: dict[str, Any]) -> httpx.Timeout:
        seconds = max(1.0, float(monitor.get("timeout_seconds") or 10.0))
        return httpx.Timeout(seconds, connect=seconds)

    def _base_headers(self, monitor: dict[str, Any]) -> dict[str, str]:
        headers = {"User-Agent": self.user_agent}
        headers.update(headers_from_json(monitor.get("headers_json")))
        return headers

    async def _check_simple_web(self, monitor: dict[str, Any]) -> CheckResult:
        headers = self._base_headers(monitor)
        start = time.perf_counter()
        async with httpx.AsyncClient(http2=True, timeout=self._timeout(monitor), follow_redirects=True) as client:
            response = await client.get(str(monitor.get("url") or ""), headers=headers)
        response_ms = int((time.perf_counter() - start) * 1000)
        return self._assert_response(monitor, response, response_ms)

    async def _check_auth_web(self, monitor: dict[str, Any]) -> CheckResult:
        headers = self._base_headers(monitor)
        login_url = monitor.get("auth_login_url") or monitor.get("url")
        verify_url = monitor.get("auth_verify_url") or monitor.get("url")
        username_field = monitor.get("auth_username_field") or "username"
        password_field = monitor.get("auth_password_field") or "password"
        form_data: dict[str, str] = {
            username_field: str(monitor.get("auth_username") or ""),
            password_field: str(monitor.get("auth_password") or ""),
        }

        raw_extra = monitor.get("auth_extra_fields") or ""
        if raw_extra:
            extra = json.loads(raw_extra)
            if not isinstance(extra, dict):
                raise ValueError("Extra login fields must be a JSON object")
            form_data.update({str(key): str(value) for key, value in extra.items()})

        start = time.perf_counter()
        async with httpx.AsyncClient(http2=True, timeout=self._timeout(monitor), follow_redirects=True) as client:
            login_response = await client.post(str(login_url), data=form_data, headers=headers)
            if login_response.status_code >= 400:
                response_ms = int((time.perf_counter() - start) * 1000)
                return CheckResult(
                    False,
                    "down",
                    response_ms=response_ms,
                    status_code=login_response.status_code,
                    error=f"Login failed with HTTP {login_response.status_code}",
                    details={"phase": "login"},
                )
            verify_response = await client.get(str(verify_url), headers=headers)

        response_ms = int((time.perf_counter() - start) * 1000)
        result = self._assert_response(monitor, verify_response, response_ms)
        verify_text = monitor.get("auth_verify_text") or ""
        if result.ok and verify_text and verify_text not in verify_response.text:
            return CheckResult(
                False,
                "down",
                response_ms=response_ms,
                status_code=verify_response.status_code,
                error="Authentication DOM/text verification failed",
                details={"phase": "verify", "missing_text": verify_text},
            )
        result.details["phase"] = "verify"
        return result

    async def _check_api(self, monitor: dict[str, Any]) -> CheckResult:
        headers = self._base_headers(monitor)
        token = monitor.get("api_token") or ""
        if token:
            token_header = monitor.get("api_token_header") or "Authorization"
            prefix = (monitor.get("api_token_prefix") or "Bearer").strip()
            headers[token_header] = f"{prefix} {token}".strip() if prefix else token

        content = monitor.get("body") or None
        method = str(monitor.get("method") or "GET").upper()
        start = time.perf_counter()
        async with httpx.AsyncClient(http2=True, timeout=self._timeout(monitor), follow_redirects=True) as client:
            response = await client.request(method, str(monitor.get("url") or ""), headers=headers, content=content)
        response_ms = int((time.perf_counter() - start) * 1000)
        result = self._assert_response(monitor, response, response_ms)
        if not result.ok:
            return result

        path = monitor.get("expected_json_path") or ""
        if path:
            try:
                actual = extract_json_path(response.json(), path)
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                return CheckResult(
                    False,
                    "down",
                    response_ms=response_ms,
                    status_code=response.status_code,
                    error=f"JSON assertion path failed: {exc}",
                )
            expected = monitor.get("expected_json_value") or ""
            if expected and str(actual) != expected:
                return CheckResult(
                    False,
                    "down",
                    response_ms=response_ms,
                    status_code=response.status_code,
                    error=f"JSON assertion failed at {path}: expected {expected!r}, got {actual!r}",
                    details={"json_path": path, "actual": actual},
                )
            result.details["json_path"] = path
            result.details["json_value"] = actual
        return result

    def _assert_response(self, monitor: dict[str, Any], response: httpx.Response, response_ms: int) -> CheckResult:
        expected_status = int(monitor.get("expected_status") or 200)
        if response.status_code != expected_status:
            return CheckResult(
                False,
                "down",
                response_ms=response_ms,
                status_code=response.status_code,
                error=f"Expected HTTP {expected_status}, got {response.status_code}",
            )

        expected_text = monitor.get("expected_text") or ""
        if expected_text and expected_text not in response.text:
            return CheckResult(
                False,
                "down",
                response_ms=response_ms,
                status_code=response.status_code,
                error="Expected text was not found in the response",
                details={"missing_text": expected_text},
            )

        return CheckResult(True, "up", response_ms=response_ms, status_code=response.status_code)
