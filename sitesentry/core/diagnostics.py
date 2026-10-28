from __future__ import annotations

import errno
import socket
import ssl
from typing import Any

import httpx


ERROR_TYPES = {
    "auth_credentials": "Authentication rejected",
    "auth_verification": "Login / session verification",
    "timeout": "Website not responding",
    "target_unreachable": "Server connection failed",
    "network_offline": "Monitoring device network unavailable",
    "dns_error": "Address / DNS resolution failed",
    "tls_error": "TLS / certificate error",
    "http_error": "Unexpected HTTP status",
    "assertion_failed": "Content / API assertion failed",
    "configuration_error": "Invalid monitor configuration",
    "unknown": "Unclassified error",
}


def error_label(code: str) -> str:
    return ERROR_TYPES.get(code, ERROR_TYPES["unknown"]) if code else "-"


def has_local_route() -> bool:
    # UDP connect only asks the OS to select a route; no application data is sent.
    for family, address in [(socket.AF_INET, ("192.0.2.1", 9)), (socket.AF_INET6, ("2001:db8::1", 9))]:
        try:
            with socket.socket(family, socket.SOCK_DGRAM) as client:
                client.connect(address)
                return True
        except OSError:
            continue
    return False


def exception_category(exc: Exception) -> str:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and all(current is not item for item in chain):
        chain.append(current)
        current = current.__cause__ or current.__context__
    text = " ".join(str(item).casefold() for item in chain)
    if any(isinstance(item, ssl.SSLError) for item in chain) or any(marker in text for marker in ("certificate verify failed", "certificate_verify_failed", "ssl:", "tls handshake")):
        return "tls_error"
    if isinstance(exc, (ValueError, KeyError, httpx.InvalidURL, httpx.UnsupportedProtocol)):
        return "configuration_error"
    transport = isinstance(exc, (httpx.TransportError, OSError))
    if transport and (any(getattr(item, "errno", None) in {errno.ENETDOWN, errno.ENETUNREACH, 10050, 10051} for item in chain) or not has_local_route()):
        return "network_offline"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if any(isinstance(item, socket.gaierror) for item in chain) or any(marker in text for marker in ("getaddrinfo", "name or service not known", "nodename nor servname", "name resolution")):
        return "dns_error"
    if transport:
        return "target_unreachable"
    return "unknown"


def result_category(result: Any) -> str:
    if result.ok:
        return ""
    code = getattr(result, "error_type", "")
    if code in ERROR_TYPES:
        return code
    if result.status_code == 401:
        return "auth_credentials"
    if result.status_code is not None and result.status_code >= 400:
        return "http_error"
    return "unknown"


def decoded_exclusions(rule: dict[str, Any]) -> set[str]:
    import json
    raw = rule.get("excluded_error_types", rule.get("excluded_error_types_json", "[]"))
    values = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(values, list) or any(item not in ERROR_TYPES for item in values):
        raise ValueError("Invalid excluded error types")
    return set(values)
