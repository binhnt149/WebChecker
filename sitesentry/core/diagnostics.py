from __future__ import annotations

import errno
from html.parser import HTMLParser
import socket
import ssl
from typing import Any

import httpx


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []
        self.lines: list[str] = []
        self.parts: list[str] = []

    def _flush(self) -> None:
        text = " ".join("".join(self.parts).split())
        if text:
            self.lines.append(text)
        self.parts.clear()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"p", "div", "li", "form", "section", "article", "table", "tr", "td", "h1", "h2", "h3", "h4", "br", "hr"}:
            self._flush()
        if tag in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            return
        attributes = dict(attrs)
        style = str(attributes.get("style") or "").replace(" ", "").casefold()
        hidden = (bool(self.stack and self.stack[-1][1]) or tag in {"script", "style", "template", "noscript"} or "hidden" in attributes or attributes.get("aria-hidden") == "true" or "display:none" in style or "visibility:hidden" in style)
        self.stack.append((tag, hidden))

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "li", "form", "section", "article", "table", "tr", "td", "h1", "h2", "h3", "h4"}:
            self._flush()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if not self.stack or not self.stack[-1][1]:
            self.parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush()


def has_login_rejection(response_text: str) -> bool:
    parser = _VisibleText()
    parser.feed(response_text)
    parser.close()
    markers = {"invalid username or password", "incorrect username or password", "invalid credentials", "authentication failed", "sai tên đăng nhập", "sai mật khẩu", "tài khoản hoặc mật khẩu không đúng", "tên đăng nhập hoặc mật khẩu không đúng"}
    return any(" ".join(line.split()).casefold().rstrip(".! ") in markers for line in parser.lines)


def visible_text(response_text: str) -> str:
    parser = _VisibleText()
    parser.feed(response_text)
    parser.close()
    return " ".join(parser.lines)


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
    if transport and any(getattr(item, "errno", None) in {errno.ENETDOWN, 10050} for item in chain):
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
