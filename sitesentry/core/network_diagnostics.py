from __future__ import annotations

import asyncio
from concurrent.futures import Future
from datetime import datetime
import json
import re
import threading
import time
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import httpx


SECRET_QUERY = re.compile(r"(?:token|secret|pass(?:word)?|auth|api[_-]?key|session|csrf|captcha|signature|code)", re.IGNORECASE)


def validate_profile(data: dict[str, Any]) -> dict[str, Any]:
    name = str(data.get("name") or "").strip()
    scope = data.get("scope", "custom")
    if not name or name == "__CLEAR__" or len(name) > 100:
        raise ValueError("Network profile needs a valid name")
    if scope not in {"internet", "intranet_vpn", "custom"}:
        raise ValueError("Invalid network profile scope")
    targets = data.get("targets", [])
    if not isinstance(targets, list) or len(targets) > 2:
        raise ValueError("A network profile supports at most 2 targets")
    cleaned = []
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError("Invalid reference target")
        url = str(target.get("url") or "").strip()
        parts = urlsplit(url)
        try:
            valid_url = parts.scheme in {"http", "https"} and bool(parts.hostname) and parts.port != 0
        except ValueError:
            valid_url = False
        if not valid_url or parts.username is not None or parts.password is not None or parts.fragment:
            raise ValueError("Reference URL must be HTTP(S) without userinfo or fragment")
        if any(SECRET_QUERY.search(key) for key, _ in parse_qsl(parts.query, keep_blank_values=True)):
            raise ValueError("Reference URL must not contain secret query parameters")
        method = str(target.get("method") or "HEAD").upper()
        if method not in {"GET", "HEAD"}:
            raise ValueError("Reference method must be GET or HEAD")
        try:
            timeout = float(target.get("timeout_seconds", 2))
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid reference timeout") from exc
        if not 0.1 <= timeout <= 30:
            raise ValueError("Reference timeout must be between 0.1 and 30 seconds")
        cleaned.append({"url": url, "method": method, "timeout_seconds": timeout})
    enabled = data.get("enabled", True)
    if type(enabled) is not bool:
        raise ValueError("Network profile enabled must be true or false")
    return {"name": name, "scope": scope, "enabled": enabled, "targets": cleaned}


class NetworkDiagnostics:
    """Share bounded, credential-free reference checks across monitor workers."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, cache_seconds: int = 60) -> None:
        self.transport = transport
        self.cache_seconds = cache_seconds
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, str, dict[str, Any]]] = {}
        self._running: dict[str, tuple[str, Future]] = {}

    async def probe(self, raw_profile: dict[str, Any]) -> dict[str, Any]:
        profile = validate_profile(raw_profile)
        if not profile["enabled"] or not profile["targets"]:
            return {"profile": profile["name"], "scope": profile["scope"], "targets": []}
        name = profile["name"]
        fingerprint = json.dumps(profile, sort_keys=True)
        while True:
            with self._lock:
                cached = self._cache.get(name)
                if cached and cached[1] == fingerprint and time.monotonic() - cached[0] < self.cache_seconds:
                    return cached[2]
                running = self._running.get(name)
                if running is None:
                    future = Future()
                    self._running[name] = (fingerprint, future)
                    break
            previous = await asyncio.shield(asyncio.wrap_future(running[1]))
            if running[0] == fingerprint:
                return previous
        try:
            result = await self._probe_targets(profile)
        except BaseException as exc:
            future.set_exception(exc)
            raise
        else:
            with self._lock:
                self._cache[name] = (time.monotonic(), fingerprint, result)
            future.set_result(result)
            return result
        finally:
            with self._lock:
                self._running.pop(name, None)

    async def _probe_targets(self, profile: dict[str, Any]) -> dict[str, Any]:
        results = []
        async with httpx.AsyncClient(transport=self.transport, follow_redirects=False, trust_env=False) as client:
            for target in profile["targets"]:
                parts = urlsplit(target["url"])
                display_url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
                try:
                    response = await client.request(target["method"], target["url"], timeout=target["timeout_seconds"])
                except httpx.HTTPError as exc:
                    results.append({"url": display_url, "reachable": False, "exception_kind": type(exc).__name__})
                else:
                    results.append({"url": display_url, "reachable": True, "http_status": response.status_code})
        return {"profile": profile["name"], "scope": profile["scope"], "checked_at": datetime.now().isoformat(timespec="seconds"), "targets": results}
