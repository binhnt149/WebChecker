from __future__ import annotations

import asyncio
import html
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import httpx

from .database import now_iso
from .diagnostic_rules import extract_json_path, match_rules, validate_rules
from .diagnostics import exception_category, has_login_rejection, result_category
from .network_diagnostics import NetworkDiagnostics, validate_profile
from .privacy import sanitize_result


WHITESPACE_RE = re.compile(r"\s+")
PREVIEW_CHARS = 500


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
    error_type: str = ""
    classification_state: str = ""
    reason_code: str = ""
    phase: str = ""
    evidence_source: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def detail_json(self) -> str:
        try:
            return json.dumps(self.details, ensure_ascii=False)
        except TypeError:
            return "{}"


class LoginFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self._current_form: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}
        if tag.lower() == "form":
            self._current_form = {"attrs": attr_map, "inputs": []}
            return
        if tag.lower() == "input" and self._current_form is not None:
            self._current_form["inputs"].append(attr_map)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form" and self._current_form is not None:
            self.forms.append(self._current_form)
            self._current_form = None

    def close(self) -> None:
        super().close()
        if self._current_form is not None:
            self.forms.append(self._current_form)
            self._current_form = None


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


def normalize_assertion_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).replace("\xa0", " ")
    return WHITESPACE_RE.sub(" ", normalized).strip()


def contains_expected_text(response_text: str, expected_text: str) -> bool:
    if expected_text in response_text:
        return True
    expected_normalized = normalize_assertion_text(expected_text)
    if not expected_normalized:
        return True
    response_normalized = normalize_assertion_text(response_text)
    return expected_normalized.casefold() in response_normalized.casefold()


def response_preview(response_text: str) -> str:
    without_assets = re.sub(r"<(script|style)\b.*?</\1>", " ", response_text, flags=re.IGNORECASE | re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", " ", without_assets)
    return normalize_assertion_text(html.unescape(without_tags))[:PREVIEW_CHARS]


def parse_login_forms(response_text: str) -> list[dict[str, Any]]:
    parser = LoginFormParser()
    parser.feed(response_text)
    parser.close()
    return parser.forms


class SiteChecker:
    def __init__(self, user_agent: str = "SiteSentry Desktop/1.0", profile_resolver: Callable[[str], dict[str, Any] | None] | None = None, network_diagnostics: NetworkDiagnostics | None = None, internet_profile_resolver: Callable[[], dict[str, Any] | None] | None = None) -> None:
        self.user_agent = user_agent
        self.profile_resolver = profile_resolver
        self.network_diagnostics = network_diagnostics or NetworkDiagnostics()
        self.internet_profile_resolver = internet_profile_resolver

    async def check_monitor(self, monitor: dict[str, Any]) -> CheckResult:
        try:
            retry_count = max(1, int(monitor.get("retry_count") or 1))
            retry_delay = max(0.0, float(monitor.get("retry_delay_seconds") or 0.0))
        except (ValueError, TypeError):
            return CheckResult(False, "down", error="Invalid retry configuration", error_type="configuration_error", classification_state="confirmed", reason_code="invalid_retry", phase="configuration", evidence_source="configuration", evidence={"field": "retry"})
        internet_check = None
        if self.internet_profile_resolver:
            try:
                profile = self.internet_profile_resolver()
                if profile and profile.get("scope") == "internet" and profile.get("enabled") and profile.get("targets"):
                    internet_check = await self.network_diagnostics.probe(profile)
                    targets = internet_check["targets"]
                    state = "reachable" if any(t["reachable"] for t in targets) else "network_offline" if any(t.get("error_type") == "network_offline" for t in targets) else "reference_unreachable"
                    internet_check = {**internet_check, "state": state}
            except (ValueError, httpx.HTTPError, OSError):
                internet_check = {"state": "unconfigured", "targets": []}
        last_result: CheckResult | None = None

        for attempt in range(1, retry_count + 1):
            result = await self._check_once(monitor)
            result.error_type = result_category(result)
            result.classification_state = "not_applicable" if result.ok else ("undetermined" if result.error_type == "unknown" else "confirmed")
            result.phase = result.phase or result.details.get("phase", "response")
            if not result.ok and not result.reason_code:
                if result.status_code is not None and result.error_type == "http_error":
                    result.reason_code = f"http_{result.status_code}"
                elif result.error_type == "auth_credentials":
                    result.reason_code = "auth_rejected"
                elif result.error_type == "auth_verification":
                    result.reason_code = "session_unverified"
            if not result.evidence_source and not result.ok:
                result.evidence_source = "assertion" if result.error_type == "assertion_failed" else ("http" if result.status_code is not None else "transport")
            if not result.evidence and not result.ok:
                result.evidence = {key: value for key, value in {"status_code": result.status_code, "exception_kind": result.details.get("exception_kind")}.items() if value is not None}
            result.attempts = attempt
            if result.ok or result.error_type in {"auth_credentials", "configuration_error"}:
                if internet_check is not None:
                    result.evidence["internet_check"] = internet_check
                return await self._finalize(monitor, result)
            last_result = result
            if attempt < retry_count and retry_delay:
                await asyncio.sleep(retry_delay)

        result = last_result or CheckResult(False, "down", error="No check attempts were executed", error_type="unknown", classification_state="undetermined")
        if internet_check is not None:
            result.evidence["internet_check"] = internet_check
        return await self._finalize(monitor, result)

    async def _finalize(self, monitor: dict[str, Any], result: CheckResult) -> CheckResult:
        profile_name = str(monitor.get("network_profile") or "")
        if not result.ok and result.error_type in {"timeout", "dns_error", "target_unreachable"} and profile_name and self.profile_resolver:
            profile = self.profile_resolver(profile_name)
            if profile:
                try:
                    result.evidence["network_probe"] = await self.network_diagnostics.probe(profile)
                except (ValueError, httpx.HTTPError) as exc:
                    result.evidence["network_probe"] = {"profile": profile_name, "exception_kind": type(exc).__name__}
        sanitize_result(result, monitor)
        return result

    async def _check_once(self, monitor: dict[str, Any]) -> CheckResult:
        monitor_type = monitor.get("monitor_type") or "simple_web"
        try:
            validate_rules(monitor.get("diagnostic_rules_json"))
            profile_name = str(monitor.get("network_profile") or "")
            if profile_name:
                profile = self.profile_resolver(profile_name) if self.profile_resolver else None
                if profile is None:
                    raise ValueError("Network profile does not exist")
                validate_profile(profile)
            if monitor_type == "auth_web":
                return await self._check_auth_web(monitor)
            if monitor_type == "api":
                return await self._check_api(monitor)
            return await self._check_simple_web(monitor)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError, ValueError, KeyError) as exc:
            return self._transport_failure(exc, str(exc))
        except Exception as exc:  # Defensive boundary for background jobs.
            return self._transport_failure(exc, f"{type(exc).__name__}: {exc}")

    def _transport_failure(self, exc: Exception, message: str, details: dict[str, Any] | None = None) -> CheckResult:
        reasons = {httpx.ConnectTimeout: "connect_timeout", httpx.ReadTimeout: "read_timeout", httpx.WriteTimeout: "write_timeout", httpx.PoolTimeout: "pool_timeout"}
        category = exception_category(exc)
        reason = next((name for typ, name in reasons.items() if isinstance(exc, typ)), "")
        if not reason:
            reason = {"dns_error": "dns_resolution_failed", "tls_error": "tls_handshake_failed", "network_offline": "local_interface_down", "configuration_error": "invalid_configuration"}.get(category, "")
        phase = (details or {}).get("phase") or {"dns_error": "resolve", "tls_error": "tls", "configuration_error": "configuration"}.get(category, "connect" if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)) else "request")
        return CheckResult(False, "down", error=message, error_type=category, reason_code=reason, phase=phase, evidence_source="configuration" if category == "configuration_error" else "transport", details={"exception_kind": type(exc).__name__, **(details or {})})

    def _rule_result(self, monitor: dict[str, Any], response: httpx.Response, response_ms: int, phase: str) -> CheckResult | None:
        match = match_rules(validate_rules(monitor.get("diagnostic_rules_json")), response, phase)
        if match is None:
            return None
        return CheckResult(False, "down", response_ms=response_ms, status_code=response.status_code,
            error="Conflicting diagnostic rules" if match["error_type"] == "unknown" else "Diagnostic rule matched",
            error_type=match["error_type"], reason_code=match.get("reason_code", ""), phase=phase,
            evidence_source="response_rule", evidence={"status_code": response.status_code, **{key: match[key] for key in ("rule_id", "rule_ids") if key in match}})

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
        # PrimeFaces AJAX headers belong on the login POST only. Sending them on
        # the page GETs can make JSF return a short partial-response XML instead
        # of the HTML needed for login form parsing or Verify text assertions.
        ajax_header_names = {"faces-request", "x-requested-with"}
        page_headers = {
            key: value for key, value in headers.items()
            if key.lower() not in ajax_header_names
        }
        login_url = monitor.get("auth_login_url") or monitor.get("url")
        verify_url = monitor.get("auth_verify_url") or monitor.get("url")
        username_field = monitor.get("auth_username_field") or "username"
        password_field = monitor.get("auth_password_field") or "password"

        extra_fields: dict[str, str] = {}
        raw_extra = monitor.get("auth_extra_fields") or ""
        if raw_extra:
            extra = json.loads(raw_extra)
            if not isinstance(extra, dict):
                raise ValueError("Extra login fields must be a JSON object")
            extra_fields = {str(key): str(value) for key, value in extra.items()}

        start = time.perf_counter()
        async with httpx.AsyncClient(http2=True, timeout=self._timeout(monitor), follow_redirects=True) as client:
            try:
                login_page_response = await client.get(str(login_url), headers=page_headers)
            except (httpx.HTTPError, httpx.InvalidURL) as exc:
                return self._transport_failure(exc, f"Login page failed: could not open Login URL {login_url}: {exc}", {"phase": "login_page", "login_url": str(login_url)})
            page_rule = self._rule_result(monitor, login_page_response, int((time.perf_counter() - start) * 1000), "login_page")
            if page_rule:
                return page_rule
            if login_page_response.status_code >= 400:
                return CheckResult(False, "down", status_code=login_page_response.status_code, error=f"Login page failed: Login URL {login_url} returned HTTP {login_page_response.status_code}", details={"phase": "login_page", "login_url": str(login_page_response.url)})
            login_page_url = str(login_page_response.url)
            form_data, post_url, form_details = self._auth_form_payload(
                login_page_response,
                login_url=str(login_url),
                username_field=str(username_field),
                password_field=str(password_field),
                username=str(monitor.get("auth_username") or ""),
                password=str(monitor.get("auth_password") or ""),
                extra_fields=extra_fields,
            )
            post_headers = dict(headers)
            if str(form_data.get("javax.faces.partial.ajax") or "").lower() == "true":
                if not any(key.lower() == "faces-request" for key in post_headers):
                    post_headers["Faces-Request"] = "partial/ajax"
                if not any(key.lower() == "x-requested-with" for key in post_headers):
                    post_headers["X-Requested-With"] = "XMLHttpRequest"
            post_headers.setdefault("Referer", str(login_page_response.url))
            try:
                login_response = await client.post(post_url, data=form_data, headers=post_headers)
            except (httpx.HTTPError, httpx.InvalidURL) as exc:
                return self._transport_failure(exc, f"Login failed: could not submit credentials to {post_url}: {exc}", {"phase": "login_submit", **form_details})
            login_rule = self._rule_result(monitor, login_response, int((time.perf_counter() - start) * 1000), "login_submit")
            if login_rule:
                return login_rule
            credential_fields = {str(username_field), str(password_field)}
            still_has_login_form = any(credential_fields.issubset({item.get("name") for item in form.get("inputs", [])}) for form in parse_login_forms(login_response.text))
            if login_response.status_code == 401 or (200 <= login_response.status_code < 300 and has_login_rejection(login_response.text) and still_has_login_form):
                return CheckResult(False, "down", status_code=login_response.status_code, error="Login rejected: the server rejected the account/password or authentication token.", error_type="auth_credentials", details={"phase": "login_submit", **form_details})
            login_redirect = next(
                (
                    str(response.headers["location"])
                    for response in login_response.history
                    if "location" in response.headers
                ),
                "",
            )
            login_post_cookie_names = sorted(
                {
                    raw_cookie.split("=", 1)[0].strip()
                    for response in [*login_response.history, login_response]
                    for raw_cookie in response.headers.get_list("set-cookie")
                    if "=" in raw_cookie
                }
            )
            login_post_status = login_response.status_code
            login_post_final_url = str(login_response.url)
            login_post_field_names = sorted(form_data)
            login_post_preview = response_preview(login_response.text)[:240]
            if login_response.status_code >= 400:
                response_ms = int((time.perf_counter() - start) * 1000)
                return CheckResult(
                    False,
                    "down",
                    response_ms=response_ms,
                    status_code=login_response.status_code,
                    error=f"Login failed: submitting credentials to {post_url} returned HTTP {login_response.status_code}",
                    details={"phase": "login_submit", **form_details},
                )
            try:
                verify_response = await client.get(str(verify_url), headers=page_headers)
            except (httpx.HTTPError, httpx.InvalidURL) as exc:
                return self._transport_failure(exc, f"Verify failed: could not open Verify URL {verify_url}: {exc}", {"phase": "verify", "verify_url": str(verify_url), **form_details})

        response_ms = int((time.perf_counter() - start) * 1000)
        result = self._assert_response(monitor, verify_response, response_ms, phase="verify")
        if not result.ok:
            if result.error_type == "assertion_failed" and self._is_login_page(verify_response.url, str(login_url), login_page_url):
                result.error_type = "auth_verification"
            result.error = f"Verify failed: Verify URL {verify_url} returned HTTP {result.status_code}. {result.error}"
            result.details.update(
                {
                    "phase": "verify",
                    "verify_url": str(verify_response.url),
                    "login_post_redirect": login_redirect,
                    "login_post_status": login_post_status,
                    "login_post_final_url": login_post_final_url,
                    "login_post_cookie_names": login_post_cookie_names,
                    "login_post_field_names": login_post_field_names,
                    "login_post_preview": login_post_preview,
                    **form_details,
                }
            )
            return result
        verify_text = monitor.get("auth_verify_text") or ""
        if result.ok and not verify_text and self._is_login_page(verify_response.url, str(login_url), login_page_url):
            return CheckResult(
                False,
                "down",
                response_ms=response_ms,
                status_code=verify_response.status_code,
                error=f"Login failed: Verify URL {verify_url} still shows the login page. Check the credentials or set Verify text to confirm a successful login.",
                error_type="auth_verification",
                details={
                    **self._response_details(verify_response, phase="verify"),
                    "login_post_redirect": login_redirect,
                    "login_post_status": login_post_status,
                    "login_post_final_url": login_post_final_url,
                    "login_post_cookie_names": login_post_cookie_names,
                    "login_post_field_names": login_post_field_names,
                    "login_post_preview": login_post_preview,
                    **form_details,
                },
            )
        if result.ok and verify_text and not contains_expected_text(verify_response.text, str(verify_text)):
            return CheckResult(
                False,
                "down",
                response_ms=response_ms,
                status_code=verify_response.status_code,
                error="Verify failed: " + self._missing_text_error("Verify text was not found", verify_response, str(verify_text)),
                error_type="auth_verification" if self._is_login_page(verify_response.url, str(login_url), login_page_url) else "assertion_failed",
                details={
                    **self._response_details(verify_response, missing_text=str(verify_text), phase="verify"),
                    "login_post_redirect": login_redirect,
                    "login_post_status": login_post_status,
                    "login_post_final_url": login_post_final_url,
                    "login_post_cookie_names": login_post_cookie_names,
                    "login_post_field_names": login_post_field_names,
                    "login_post_preview": login_post_preview,
                    **form_details,
                },
            )
        result.details["phase"] = "verify"
        result.details.update(form_details)
        return result

    def _is_login_page(self, response_url: httpx.URL, configured_login_url: str, discovered_login_url: str) -> bool:
        final = urlparse(str(response_url))
        candidates = [urlparse(configured_login_url), urlparse(discovered_login_url)]
        final_path = final.path.rstrip("/") or "/"
        for candidate in candidates:
            candidate_path = candidate.path.rstrip("/") or "/"
            if final.netloc == candidate.netloc and final_path == candidate_path:
                return True
        return False

    def _auth_form_payload(
        self,
        login_response: httpx.Response,
        login_url: str,
        username_field: str,
        password_field: str,
        username: str,
        password: str,
        extra_fields: dict[str, str],
    ) -> tuple[dict[str, str], str, dict[str, Any]]:
        form = self._select_login_form(login_response.text, username_field, password_field)
        post_url = str(login_response.url if login_response.status_code < 400 else login_url)
        form_data: dict[str, str] = {}
        form_details: dict[str, Any] = {
            "login_form_url": str(login_response.url),
            "login_form_status": login_response.status_code,
            "login_hidden_fields": [],
        }

        if form is not None:
            action = str(form.get("attrs", {}).get("action") or "")
            post_url = urljoin(str(login_response.url), action) if action else str(login_response.url)
            hidden_names: list[str] = []
            for input_attrs in form.get("inputs", []):
                field_name = str(input_attrs.get("name") or "")
                if not field_name:
                    continue
                field_type = str(input_attrs.get("type") or "text").lower()
                if field_type == "hidden":
                    form_data[field_name] = str(input_attrs.get("value") or "")
                    hidden_names.append(field_name)
            form_details["login_form_action"] = post_url
            form_details["login_hidden_fields"] = hidden_names

        form_data.update(extra_fields)
        form_data[username_field] = username
        form_data[password_field] = password
        return form_data, post_url, form_details

    def _select_login_form(
        self,
        response_text: str,
        username_field: str,
        password_field: str,
    ) -> dict[str, Any] | None:
        forms = parse_login_forms(response_text)
        if not forms:
            return None
        wanted = {username_field, password_field}
        for form in forms:
            names = {str(input_attrs.get("name") or "") for input_attrs in form.get("inputs", [])}
            if wanted & names:
                return form
        return forms[0]

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
                    error_type="assertion_failed",
                )
            expected = monitor.get("expected_json_value") or ""
            if expected and str(actual) != expected:
                return CheckResult(
                    False,
                    "down",
                    response_ms=response_ms,
                    status_code=response.status_code,
                    error=f"JSON assertion failed at {path}: value did not match",
                    error_type="assertion_failed",
                    details={"json_path": path, "actual": actual},
                )
            result.details["json_path"] = path
            result.details["json_value"] = actual
        return result

    def _assert_response(self, monitor: dict[str, Any], response: httpx.Response, response_ms: int, phase: str = "response") -> CheckResult:
        rule_result = self._rule_result(monitor, response, response_ms, phase)
        if rule_result is not None:
            return rule_result
        expected_status = int(monitor.get("expected_status") or 200)
        if response.status_code != expected_status:
            return CheckResult(
                False,
                "down",
                response_ms=response_ms,
                status_code=response.status_code,
                error=f"Expected HTTP {expected_status}, got {response.status_code}",
                error_type="auth_credentials" if response.status_code == 401 else "http_error",
            )

        assertion_rule = self._rule_result(monitor, response, response_ms, "assertion")
        if assertion_rule is not None:
            return assertion_rule

        expected_text = str(monitor.get("expected_text") or "")
        if expected_text and not contains_expected_text(response.text, expected_text):
            return CheckResult(
                False,
                "down",
                response_ms=response_ms,
                status_code=response.status_code,
                error=self._missing_text_error("Expected text was not found in the response", response, expected_text),
                error_type="assertion_failed",
                details=self._response_details(response, missing_text=expected_text),
            )

        return CheckResult(True, "up", response_ms=response_ms, status_code=response.status_code)

    def _missing_text_error(self, message: str, response: httpx.Response, expected_text: str) -> str:
        return f"{message} (final URL: {response.url}, response chars: {len(response.text)})"

    def _response_details(
        self,
        response: httpx.Response,
        missing_text: str = "",
        phase: str | None = None,
    ) -> dict[str, Any]:
        details: dict[str, Any] = {
            "final_url": str(response.url),
            "content_type": response.headers.get("content-type", ""),
            "response_chars": len(response.text),
            "response_preview": response_preview(response.text),
        }
        if missing_text:
            details["missing_text"] = missing_text
            details["missing_text_normalized"] = normalize_assertion_text(missing_text)
        if phase:
            details["phase"] = phase
        return details
