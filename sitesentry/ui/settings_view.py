from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Any

import customtkinter as ctk

from sitesentry.core.email_rules import RULE_TYPES, parse_recipients
from .background import run_background
from .email_rule_dialog import EmailRuleDialog
from .focus import bind_focus_on_click


class SettingsView(ctk.CTkFrame):
    def __init__(self, master: Any, app: Any) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._dialog: EmailRuleDialog | None = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=20, pady=(18, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Settings", font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="Save", command=self._save, width=90).grid(row=0, column=1, padx=6)
        self.test_button = ctk.CTkButton(header, text="Test Email", command=self._test_email, width=110)
        self.test_button.grid(row=0, column=2, padx=(6, 0))
        tabs = ctk.CTkTabview(self, corner_radius=8)
        self.tabs = tabs
        tabs.grid(row=1, column=0, padx=20, pady=8, sticky="nsew")
        smtp = tabs.add("SMTP")
        schedules = tabs.add("Email schedules")
        smtp.grid_columnconfigure(0, weight=1)
        smtp.grid_rowconfigure(0, weight=1)
        form = ctk.CTkScrollableFrame(smtp, fg_color="transparent")
        form.grid(row=0, column=0, sticky="nsew")
        form.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.smtp_enabled = tk.BooleanVar(value=False)
        self.tls_enabled = tk.BooleanVar(value=True)
        self.host_var = tk.StringVar()
        self.port_var = tk.StringVar(value="587")
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.from_var = tk.StringVar()
        self.theme_var = tk.StringVar(value="System")
        ctk.CTkCheckBox(form, text="Enable SMTP alerts", variable=self.smtp_enabled).grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="w")
        ctk.CTkCheckBox(form, text="Use STARTTLS", variable=self.tls_enabled).grid(row=0, column=2, columnspan=2, padx=10, pady=10, sticky="w")
        self._entry(form, "SMTP host", self.host_var, 1, 0, 3)
        self._entry(form, "Port", self.port_var, 1, 3)
        self._entry(form, "Username", self.username_var, 2, 0, 2)
        self._entry(form, "Password", self.password_var, 2, 2, 2, show="*")
        self._entry(form, "From email", self.from_var, 3, 0, 4)
        ctk.CTkLabel(form, text="Recipients").grid(row=8, column=0, padx=10, pady=(10, 0), sticky="w")
        self.to_box = bind_focus_on_click(ctk.CTkTextbox(form, height=80))
        self.to_box.grid(row=9, column=0, columnspan=4, padx=10, pady=(0, 10), sticky="ew")
        ctk.CTkLabel(form, text="Appearance").grid(row=10, column=0, padx=10, pady=(10, 0), sticky="w")
        ctk.CTkOptionMenu(form, values=["System", "Dark", "Light"], variable=self.theme_var).grid(row=11, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
        schedules.grid_columnconfigure(0, weight=1)
        schedules.grid_rowconfigure(1, weight=1)
        ctk.CTkButton(schedules, text="Add schedule", command=lambda: self._edit_rule(None), width=130).grid(row=0, column=0, padx=8, pady=8, sticky="e")
        self.rules_list = ctk.CTkScrollableFrame(schedules, fg_color="transparent")
        self.rules_list.grid(row=1, column=0, sticky="nsew")
        self.rules_list.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(self, text="", anchor="w", wraplength=760)
        self.status_label.grid(row=2, column=0, padx=20, pady=(0, 12), sticky="ew")
        self._load()
        self._refresh_rules()

    def _entry(self, parent: Any, label: str, variable: tk.StringVar, row: int, column: int, span: int = 1, show: str | None = None) -> None:
        ctk.CTkLabel(parent, text=label).grid(row=row * 2, column=column, columnspan=span, padx=10, pady=(10, 0), sticky="w")
        bind_focus_on_click(ctk.CTkEntry(parent, textvariable=variable, show=show)).grid(row=row * 2 + 1, column=column, columnspan=span, padx=10, pady=(0, 10), sticky="ew")

    def _load(self) -> None:
        data = self.app.db.get_settings()
        self.smtp_enabled.set(data.get("smtp_enabled", "0") == "1")
        self.tls_enabled.set(data.get("smtp_use_tls", "1") == "1")
        for variable, key, default in [(self.host_var, "smtp_host", ""), (self.port_var, "smtp_port", "587"), (self.username_var, "smtp_username", ""), (self.password_var, "smtp_password", ""), (self.from_var, "smtp_from", ""), (self.theme_var, "appearance", "System")]:
            variable.set(data.get(key, default))
        self.to_box.insert("1.0", data.get("smtp_to", ""))

    def _save(self) -> bool:
        try:
            port = int(self.port_var.get())
            if not 1 <= port <= 65535:
                raise ValueError("SMTP port must be between 1 and 65535")
            recipients = self.to_box.get("1.0", "end-1c").strip()
            parse_recipients(recipients)
            sender = self.from_var.get().strip()
            if sender and (len(parse_recipients(sender)) != 1 or any(char in sender for char in "\r\n")):
                raise ValueError("Enter one valid From email")
            if self.smtp_enabled.get() and not self.host_var.get().strip():
                raise ValueError("SMTP host is required")
        except ValueError as exc:
            messagebox.showerror("Settings", str(exc), parent=self)
            return False
        data = {"smtp_enabled": "1" if self.smtp_enabled.get() else "0", "smtp_use_tls": "1" if self.tls_enabled.get() else "0", "smtp_host": self.host_var.get().strip(), "smtp_port": str(port), "smtp_username": self.username_var.get().strip(), "smtp_from": sender, "smtp_to": recipients, "appearance": self.theme_var.get()}
        for key, value in data.items():
            self.app.db.set_setting(key, value)
        self.app.db.set_setting("smtp_password", self.password_var.get(), secret=True)
        ctk.set_appearance_mode(self.theme_var.get())
        self.app.notifier.wake()
        self.status_label.configure(text="Settings saved")
        return True

    def _test_email(self) -> None:
        if not self._save():
            return
        self.test_button.configure(state="disabled")
        self.status_label.configure(text="Sending test email...")

        def done(result: tuple[bool, str]) -> None:
            ok, message = result
            self.test_button.configure(state="normal")
            self.status_label.configure(text=message, text_color="#16a34a" if ok else "#dc2626")

        def failed(message: str) -> None:
            self.test_button.configure(state="normal")
            self.status_label.configure(text=message, text_color="#dc2626")

        run_background(self.app, self, self.app.notifier.send_test_email, done, failed)

    def _refresh_rules(self) -> None:
        for child in self.rules_list.winfo_children():
            child.destroy()
        rules = self.app.db.list_email_rules()
        counts = self.app.db.email_delivery_counts()
        if not rules:
            ctk.CTkLabel(self.rules_list, text="No email schedules").grid(row=0, column=0, pady=40)
        for index, rule in enumerate(rules):
            row = ctk.CTkFrame(self.rules_list, fg_color="transparent")
            row.grid(row=index, column=0, padx=8, pady=10, sticky="ew")
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=rule["name"], font=ctk.CTkFont(weight="bold"), anchor="w", wraplength=330).grid(row=0, column=0, sticky="ew")
            description = RULE_TYPES[rule["rule_type"]]
            if rule["rule_type"] == "daily_summary":
                description += f" | {rule['hour']:02d}:{rule['minute']:02d} | {rule['weekdays']} | {rule['report_period']}"
            description += " | Enabled" if rule["enabled"] else " | Disabled"
            ctk.CTkLabel(row, text=description, anchor="w", wraplength=500, justify="left").grid(row=1, column=0, columnspan=4, sticky="ew")
            ctk.CTkLabel(row, text=rule["recipients"] or "SMTP recipients", anchor="w", wraplength=500, justify="left").grid(row=2, column=0, columnspan=4, sticky="ew")
            if rule["rule_type"] == "daily_summary":
                ctk.CTkButton(row, text="Send now", width=86, command=lambda value=rule["id"]: self._send_summary(value)).grid(row=0, column=1, padx=4)
            ctk.CTkButton(row, text="Edit", width=60, command=lambda value=rule: self._edit_rule(value)).grid(row=0, column=2, padx=4)
            ctk.CTkButton(row, text="Delete", width=64, fg_color="#991b1b", command=lambda value=rule["id"]: self._delete_rule(value)).grid(row=0, column=3, padx=4)
        self.status_label.configure(text="Email queue: " + ", ".join(f"{key}: {value}" for key, value in counts.items()) if counts else "No email deliveries yet")

    def _edit_rule(self, rule: dict[str, Any] | None) -> None:
        if self._dialog is not None and self._dialog.winfo_exists():
            self._dialog.lift()
            return

        def save(payload: dict[str, Any]) -> None:
            if rule:
                payload["id"] = rule["id"]
            self.app.db.save_email_rule(payload)
            self.app.scheduler.sync_email_jobs()
            self.app.notifier.wake()
            self._refresh_rules()

        self._dialog = EmailRuleDialog(self, rule, save)

    def _delete_rule(self, rule_id: int) -> None:
        if messagebox.askyesno("Delete schedule", "Delete this schedule and its email queue?", parent=self):
            self.app.db.delete_email_rule(rule_id)
            self.app.scheduler.sync_email_jobs()
            self._refresh_rules()

    def _send_summary(self, rule_id: int) -> None:
        if not self._save():
            return
        run_background(self.app, self, lambda: self.app.scheduler.queue_daily_summary(rule_id, manual=True), lambda queued: self.status_label.configure(text="Summary queued" if queued else "Summary not queued: check SMTP and schedule status"))
