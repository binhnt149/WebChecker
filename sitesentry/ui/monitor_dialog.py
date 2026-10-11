from __future__ import annotations

import asyncio
import json
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Any, Callable

import customtkinter as ctk

from .focus import bind_focus_on_click


SaveCallback = Callable[[], None]


TYPE_TO_TAB = {
    "simple_web": "Web",
    "auth_web": "Auth Web",
    "api": "API",
}

TAB_TO_TYPE = {value: key for key, value in TYPE_TO_TAB.items()}

REQUIRED_COLOR = "#f59e0b"
ERROR_COLOR = "#ef4444"
SUCCESS_COLOR = "#22c55e"
INFO_COLOR = "#94a3b8"


class MonitorDialog(ctk.CTkToplevel):
    def __init__(self, master: Any, monitor: dict[str, Any] | None = None, on_save: SaveCallback | None = None) -> None:
        super().__init__(master)
        self.app = master
        self.monitor = monitor or {}
        self.on_save = on_save
        self._first_focus_widget: ctk.CTkEntry | None = None
        self.title("Monitor")
        self.geometry("860x720")
        self.minsize(760, 620)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_common()
        self._build_tabs()
        self._build_actions()
        self._load_monitor()
        self.after(100, self._activate_dialog)

    def _activate_dialog(self) -> None:
        try:
            self.deiconify()
            self.lift()
            self.focus_set()
        except tk.TclError:
            pass
        self.after(50, self._focus_first_input)

    def _focus_first_input(self) -> None:
        focus_target = self._first_focus_widget or self
        try:
            focus_target.focus_set()
        except tk.TclError:
            pass

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def _build_common(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=8)
        frame.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        for column in range(6):
            frame.grid_columnconfigure(column, weight=1)

        self.name_var = tk.StringVar()
        self.enabled_var = tk.BooleanVar(value=True)
        self.interval_var = tk.StringVar(value="60")
        self.timeout_var = tk.StringVar(value="10")
        self.expected_status_var = tk.StringVar(value="200")
        self.retry_count_var = tk.StringVar(value="3")
        self.retry_delay_var = tk.StringVar(value="2")
        self.cooldown_var = tk.StringVar(value="30")

        self._entry(
            frame,
            "Name",
            self.name_var,
            0,
            0,
            columnspan=3,
            required=True,
            placeholder="Homepage, Login portal, Health API...",
        )
        self._entry(
            frame,
            "Expected HTTP",
            self.expected_status_var,
            0,
            3,
            required=True,
            placeholder="200",
        )
        ctk.CTkCheckBox(frame, text="Enabled", variable=self.enabled_var).grid(row=0, column=4, padx=8, pady=8, sticky="w")

        self._entry(frame, "Interval (sec)", self.interval_var, 1, 0, required=True, placeholder="60")
        self._entry(frame, "Timeout (sec)", self.timeout_var, 1, 1, required=True, placeholder="10")
        self._entry(frame, "Retries", self.retry_count_var, 1, 2, required=True, placeholder="3")
        self._entry(frame, "Retry delay", self.retry_delay_var, 1, 3, required=True, placeholder="2")
        self._entry(frame, "Cooldown (min)", self.cooldown_var, 1, 4, required=True, placeholder="30")

        self.expected_text = bind_focus_on_click(ctk.CTkTextbox(frame, height=62))
        ctk.CTkLabel(frame, text="Expected text").grid(row=4, column=0, padx=8, pady=(6, 0), sticky="w")
        self.expected_text.grid(row=5, column=0, columnspan=6, padx=8, pady=(0, 8), sticky="ew")
        ctk.CTkLabel(
            frame,
            text=(
                "* Required. Web: URL. Auth Web: Protected URL, Login URL, Username, Password, form field names. "
                "API: Endpoint URL, Method."
            ),
            anchor="w",
            justify="left",
            text_color=REQUIRED_COLOR,
            wraplength=780,
        ).grid(row=6, column=0, columnspan=6, padx=8, pady=(0, 8), sticky="ew")

    def _build_tabs(self) -> None:
        self.tabs = ctk.CTkTabview(self, corner_radius=8)
        self.tabs.grid(row=1, column=0, padx=16, pady=8, sticky="nsew")
        self.web_tab = self.tabs.add("Web")
        self.auth_tab = self.tabs.add("Auth Web")
        self.api_tab = self.tabs.add("API")
        self._build_web_tab()
        self._build_auth_tab()
        self._build_api_tab()

    def _build_web_tab(self) -> None:
        self.web_tab.grid_columnconfigure(1, weight=1)
        self.web_url_var = tk.StringVar()
        self._entry(
            self.web_tab,
            "URL",
            self.web_url_var,
            0,
            0,
            columnspan=2,
            required=True,
            placeholder="https://example.com",
        )
        ctk.CTkLabel(self.web_tab, text="Headers JSON").grid(row=2, column=0, padx=8, pady=(10, 0), sticky="nw")
        self.web_headers = bind_focus_on_click(ctk.CTkTextbox(self.web_tab, height=160))
        self.web_headers.grid(row=3, column=1, padx=8, pady=(10, 8), sticky="nsew")
        self.web_tab.grid_rowconfigure(3, weight=1)

    def _build_auth_tab(self) -> None:
        self.auth_tab.grid_columnconfigure(0, weight=1)
        self.auth_tab.grid_rowconfigure(0, weight=1)
        auth_frame = ctk.CTkScrollableFrame(self.auth_tab, fg_color="transparent", corner_radius=0)
        auth_frame.grid(row=0, column=0, sticky="nsew")
        for column in range(4):
            auth_frame.grid_columnconfigure(column, weight=1)
        self.auth_url_var = tk.StringVar()
        self.auth_login_url_var = tk.StringVar()
        self.auth_verify_url_var = tk.StringVar()
        self.auth_username_var = tk.StringVar()
        self.auth_password_var = tk.StringVar()
        self.auth_username_field_var = tk.StringVar(value="username")
        self.auth_password_field_var = tk.StringVar(value="password")
        self.auth_verify_text_var = tk.StringVar()

        self._entry(
            auth_frame,
            "Protected URL",
            self.auth_url_var,
            0,
            0,
            columnspan=4,
            required=True,
            placeholder="https://example.com/account",
        )
        self._entry(
            auth_frame,
            "Login URL",
            self.auth_login_url_var,
            1,
            0,
            columnspan=4,
            required=True,
            placeholder="https://example.com/login",
        )
        self._entry(
            auth_frame,
            "Verify URL",
            self.auth_verify_url_var,
            2,
            0,
            columnspan=4,
            placeholder="Optional, defaults to Protected URL",
        )
        self._entry(
            auth_frame,
            "Username",
            self.auth_username_var,
            3,
            0,
            columnspan=2,
            required=True,
            placeholder="user@example.com",
        )
        self._entry(
            auth_frame,
            "Password",
            self.auth_password_var,
            3,
            2,
            columnspan=2,
            show="*",
            required=True,
            placeholder="Login password",
        )
        self._entry(
            auth_frame,
            "Username field",
            self.auth_username_field_var,
            4,
            0,
            columnspan=2,
            required=True,
            placeholder="username",
        )
        self._entry(
            auth_frame,
            "Password field",
            self.auth_password_field_var,
            4,
            2,
            columnspan=2,
            required=True,
            placeholder="password",
        )
        self._entry(
            auth_frame,
            "Verify text",
            self.auth_verify_text_var,
            5,
            0,
            columnspan=4,
            placeholder="Optional text after login",
        )

        ctk.CTkLabel(auth_frame, text="Extra login fields JSON").grid(row=12, column=0, padx=8, pady=(10, 0), sticky="nw")
        self.auth_extra_fields = bind_focus_on_click(ctk.CTkTextbox(auth_frame, height=100))
        self.auth_extra_fields.grid(row=13, column=1, columnspan=3, padx=8, pady=(10, 8), sticky="nsew")
        ctk.CTkLabel(auth_frame, text="Headers JSON").grid(row=14, column=0, padx=8, pady=(10, 0), sticky="nw")
        self.auth_headers = bind_focus_on_click(ctk.CTkTextbox(auth_frame, height=100))
        self.auth_headers.grid(row=15, column=1, columnspan=3, padx=8, pady=(10, 8), sticky="nsew")

    def _build_api_tab(self) -> None:
        for column in range(4):
            self.api_tab.grid_columnconfigure(column, weight=1)
        self.api_url_var = tk.StringVar()
        self.method_var = tk.StringVar(value="GET")
        self.api_token_var = tk.StringVar()
        self.api_token_header_var = tk.StringVar(value="Authorization")
        self.api_token_prefix_var = tk.StringVar(value="Bearer")
        self.json_path_var = tk.StringVar()
        self.json_value_var = tk.StringVar()

        self._entry(
            self.api_tab,
            "Endpoint URL",
            self.api_url_var,
            0,
            0,
            columnspan=4,
            required=True,
            placeholder="https://api.example.com/health",
        )
        ctk.CTkLabel(self.api_tab, text="Method *", text_color=REQUIRED_COLOR).grid(
            row=2,
            column=0,
            padx=8,
            pady=(8, 0),
            sticky="w",
        )
        ctk.CTkOptionMenu(
            self.api_tab,
            values=["GET", "POST", "PUT", "PATCH", "DELETE"],
            variable=self.method_var,
        ).grid(row=3, column=1, padx=8, pady=(0, 8), sticky="ew")
        self._entry(self.api_tab, "Token header", self.api_token_header_var, 1, 2, placeholder="Authorization")
        self._entry(self.api_tab, "Token prefix", self.api_token_prefix_var, 1, 3, placeholder="Bearer")
        self._entry(self.api_tab, "API token", self.api_token_var, 2, 0, columnspan=4, show="*", placeholder="Optional token")
        self._entry(self.api_tab, "JSON path", self.json_path_var, 3, 0, columnspan=2, placeholder="data.status")
        self._entry(self.api_tab, "Expected JSON value", self.json_value_var, 3, 2, columnspan=2, placeholder="ok")

        ctk.CTkLabel(self.api_tab, text="Headers JSON").grid(row=8, column=0, padx=8, pady=(10, 0), sticky="nw")
        self.api_headers = bind_focus_on_click(ctk.CTkTextbox(self.api_tab, height=110))
        self.api_headers.grid(row=9, column=1, columnspan=3, padx=8, pady=(10, 8), sticky="nsew")
        ctk.CTkLabel(self.api_tab, text="Body").grid(row=10, column=0, padx=8, pady=(10, 0), sticky="nw")
        self.api_body = bind_focus_on_click(ctk.CTkTextbox(self.api_tab, height=150))
        self.api_body.grid(row=11, column=1, columnspan=3, padx=8, pady=(10, 8), sticky="nsew")
        self.api_tab.grid_rowconfigure(11, weight=1)

    def _build_actions(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=2, column=0, padx=16, pady=(8, 16), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)
        self.result_label = ctk.CTkLabel(frame, text="Fields marked * are required.", anchor="w", text_color=INFO_COLOR)
        self.result_label.grid(row=0, column=0, padx=0, pady=0, sticky="ew")
        ctk.CTkButton(frame, text="Test Run", command=self._test_run, width=110).grid(row=0, column=1, padx=6)
        ctk.CTkButton(frame, text="Cancel", command=self._close, width=90, fg_color="#475569").grid(row=0, column=2, padx=6)
        ctk.CTkButton(frame, text="Save", command=self._save, width=90).grid(row=0, column=3, padx=(6, 0))

    def _entry(
        self,
        parent: Any,
        label: str,
        variable: tk.StringVar,
        row: int,
        column: int,
        columnspan: int = 1,
        show: str | None = None,
        required: bool = False,
        placeholder: str = "",
    ) -> ctk.CTkEntry:
        label_text = f"{label} *" if required else label
        label_kwargs = {"text_color": REQUIRED_COLOR} if required else {}
        ctk.CTkLabel(parent, text=label_text, **label_kwargs).grid(
            row=row * 2,
            column=column,
            columnspan=columnspan,
            padx=8,
            pady=(8, 0),
            sticky="w",
        )
        entry = bind_focus_on_click(ctk.CTkEntry(parent, textvariable=variable, show=show, placeholder_text=placeholder))
        entry.grid(row=row * 2 + 1, column=column, columnspan=columnspan, padx=8, pady=(0, 8), sticky="ew")
        if self._first_focus_widget is None:
            self._first_focus_widget = entry
        return entry

    def _load_monitor(self) -> None:
        monitor = self.monitor
        if not monitor:
            self.web_headers.insert("1.0", "{}")
            self.auth_headers.insert("1.0", "{}")
            self.auth_extra_fields.insert("1.0", "{}")
            self.api_headers.insert("1.0", "{}")
            return

        self.name_var.set(str(monitor.get("name") or ""))
        self.enabled_var.set(bool(monitor.get("enabled", True)))
        self.interval_var.set(str(monitor.get("interval_seconds") or 60))
        self.timeout_var.set(str(monitor.get("timeout_seconds") or 10))
        self.expected_status_var.set(str(monitor.get("expected_status") or 200))
        self.retry_count_var.set(str(monitor.get("retry_count") or 3))
        self.retry_delay_var.set(str(monitor.get("retry_delay_seconds") or 2))
        self.cooldown_var.set(str(monitor.get("cooldown_minutes") or 30))
        self.expected_text.insert("1.0", str(monitor.get("expected_text") or ""))

        headers = monitor.get("headers_json") or "{}"
        monitor_type = monitor.get("monitor_type") or "simple_web"
        self.tabs.set(TYPE_TO_TAB.get(monitor_type, "Web"))
        if monitor_type == "auth_web":
            self.auth_url_var.set(str(monitor.get("url") or ""))
            self.auth_login_url_var.set(str(monitor.get("auth_login_url") or ""))
            self.auth_verify_url_var.set(str(monitor.get("auth_verify_url") or ""))
            self.auth_username_var.set(str(monitor.get("auth_username") or ""))
            self.auth_password_var.set(str(monitor.get("auth_password") or ""))
            self.auth_username_field_var.set(str(monitor.get("auth_username_field") or "username"))
            self.auth_password_field_var.set(str(monitor.get("auth_password_field") or "password"))
            self.auth_verify_text_var.set(str(monitor.get("auth_verify_text") or ""))
            self.auth_extra_fields.insert("1.0", monitor.get("auth_extra_fields") or "{}")
            self.auth_headers.insert("1.0", headers)
        elif monitor_type == "api":
            self.api_url_var.set(str(monitor.get("url") or ""))
            self.method_var.set(str(monitor.get("method") or "GET"))
            self.api_token_var.set(str(monitor.get("api_token") or ""))
            self.api_token_header_var.set(str(monitor.get("api_token_header") or "Authorization"))
            self.api_token_prefix_var.set(str(monitor.get("api_token_prefix") or "Bearer"))
            self.json_path_var.set(str(monitor.get("expected_json_path") or ""))
            self.json_value_var.set(str(monitor.get("expected_json_value") or ""))
            self.api_headers.insert("1.0", headers)
            self.api_body.insert("1.0", monitor.get("body") or "")
        else:
            self.web_url_var.set(str(monitor.get("url") or ""))
            self.web_headers.insert("1.0", headers)

    def _textbox(self, widget: ctk.CTkTextbox) -> str:
        return widget.get("1.0", "end").strip()

    def _selected_type(self) -> str:
        return TAB_TO_TYPE.get(self.tabs.get(), "simple_web")

    def _payload(self) -> dict[str, Any]:
        monitor_type = self._selected_type()
        headers = "{}"
        url = ""
        body = ""
        if monitor_type == "auth_web":
            url = self.auth_url_var.get().strip()
            headers = self._textbox(self.auth_headers)
        elif monitor_type == "api":
            url = self.api_url_var.get().strip()
            headers = self._textbox(self.api_headers)
            body = self._textbox(self.api_body)
        else:
            url = self.web_url_var.get().strip()
            headers = self._textbox(self.web_headers)

        data: dict[str, Any] = {
            "id": self.monitor.get("id"),
            "name": self.name_var.get().strip(),
            "enabled": self.enabled_var.get(),
            "monitor_type": monitor_type,
            "url": url,
            "headers_json": headers,
            "body": body,
            "method": self.method_var.get(),
            "interval_seconds": self.interval_var.get(),
            "timeout_seconds": self.timeout_var.get(),
            "expected_status": self.expected_status_var.get(),
            "expected_text": self._textbox(self.expected_text),
            "expected_json_path": self.json_path_var.get().strip(),
            "expected_json_value": self.json_value_var.get().strip(),
            "api_token": self.api_token_var.get(),
            "api_token_header": self.api_token_header_var.get().strip(),
            "api_token_prefix": self.api_token_prefix_var.get().strip(),
            "auth_login_url": self.auth_login_url_var.get().strip(),
            "auth_username": self.auth_username_var.get().strip(),
            "auth_password": self.auth_password_var.get(),
            "auth_username_field": self.auth_username_field_var.get().strip(),
            "auth_password_field": self.auth_password_field_var.get().strip(),
            "auth_extra_fields": self._textbox(self.auth_extra_fields),
            "auth_verify_url": self.auth_verify_url_var.get().strip(),
            "auth_verify_text": self.auth_verify_text_var.get().strip(),
            "retry_count": self.retry_count_var.get(),
            "retry_delay_seconds": self.retry_delay_var.get(),
            "cooldown_minutes": self.cooldown_var.get(),
        }
        return data

    def _collect_validation_errors(self, data: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        monitor_type = str(data.get("monitor_type") or "simple_web")

        def require_text(key: str, label: str) -> None:
            if not str(data.get(key) or "").strip():
                errors.append(f"{label} is required.")

        def validate_url(key: str, label: str) -> None:
            value = str(data.get(key) or "").strip()
            if not value:
                errors.append(f"{label} is required.")
                return
            if not value.startswith(("http://", "https://")):
                errors.append(f"{label} must start with http:// or https://.")

        def validate_int(key: str, label: str, minimum: int | None = None, maximum: int | None = None) -> None:
            value = str(data.get(key) or "").strip()
            if not value:
                errors.append(f"{label} is required.")
                return
            try:
                parsed = int(value)
            except ValueError:
                errors.append(f"{label} must be a whole number.")
                return
            if minimum is not None and parsed < minimum:
                errors.append(f"{label} must be at least {minimum}.")
            if maximum is not None and parsed > maximum:
                errors.append(f"{label} must be at most {maximum}.")

        def validate_float(key: str, label: str, minimum: float | None = None) -> None:
            value = str(data.get(key) or "").strip()
            if not value:
                errors.append(f"{label} is required.")
                return
            try:
                parsed = float(value)
            except ValueError:
                errors.append(f"{label} must be a number.")
                return
            if minimum is not None and parsed < minimum:
                errors.append(f"{label} must be at least {minimum:g}.")

        require_text("name", "Name")
        validate_url("url", "URL")
        validate_int("expected_status", "Expected HTTP", minimum=100, maximum=599)
        validate_int("interval_seconds", "Interval (sec)", minimum=10)
        validate_float("timeout_seconds", "Timeout (sec)", minimum=1)
        validate_int("retry_count", "Retries", minimum=1)
        validate_float("retry_delay_seconds", "Retry delay", minimum=0)
        validate_int("cooldown_minutes", "Cooldown (min)", minimum=0)

        if monitor_type == "auth_web":
            validate_url("auth_login_url", "Login URL")
            require_text("auth_username", "Username")
            require_text("auth_password", "Password")
            require_text("auth_username_field", "Username field")
            require_text("auth_password_field", "Password field")
            verify_url = str(data.get("auth_verify_url") or "").strip()
            if verify_url and not verify_url.startswith(("http://", "https://")):
                errors.append("Verify URL must start with http:// or https://.")
        elif monitor_type == "api":
            method = str(data.get("method") or "").upper()
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                errors.append("Method is required.")
            if str(data.get("expected_json_value") or "").strip() and not str(data.get("expected_json_path") or "").strip():
                errors.append("JSON path is required when Expected JSON value is filled.")

        json_fields = [(data.get("headers_json"), "Headers JSON")]
        if monitor_type == "auth_web":
            json_fields.append((data.get("auth_extra_fields"), "Extra login fields JSON"))
        for raw, label in json_fields:
            if raw:
                try:
                    parsed = json.loads(str(raw))
                except json.JSONDecodeError as exc:
                    errors.append(f"{label} is invalid: {exc}.")
                    continue
                if not isinstance(parsed, dict):
                    errors.append(f"{label} must be a JSON object.")

        return errors

    def _validate(self, data: dict[str, Any]) -> bool:
        errors = self._collect_validation_errors(data)
        if errors:
            message = "\n".join(f"- {error}" for error in errors)
            self.result_label.configure(text=f"Please fix {len(errors)} field(s) before continuing.", text_color=ERROR_COLOR)
            messagebox.showerror("Missing or invalid information", message, parent=self)
            return False
        self.result_label.configure(text="Ready to save or test.", text_color=SUCCESS_COLOR)
        return True

    def _save(self) -> None:
        data = self._payload()
        if not self._validate(data):
            return
        self.app.db.save_monitor(data)
        self.app.scheduler.sync_jobs()
        if self.on_save:
            self.on_save()
        self._close()

    def _test_run(self) -> None:
        data = self._payload()
        if not self._validate(data):
            return
        self.result_label.configure(text="Running test...", text_color=INFO_COLOR)

        def worker() -> None:
            result = asyncio.run(self.app.checker.check_monitor(data))
            message = "UP" if result.ok else f"DOWN: {result.error}"
            suffix = f"HTTP {result.status_code}, {result.response_ms} ms, attempts {result.attempts}"
            color = SUCCESS_COLOR if result.ok else ERROR_COLOR
            self.after(0, lambda: self.result_label.configure(text=f"{message} ({suffix})", text_color=color))

        threading.Thread(target=worker, daemon=True).start()
