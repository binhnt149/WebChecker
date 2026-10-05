from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox
from typing import Any

import customtkinter as ctk

from .focus import bind_focus_on_click


class SettingsView(ctk.CTkFrame):
    def __init__(self, master: Any, app: Any) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=20, pady=(18, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Settings", font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="Save", command=self._save, width=90).grid(row=0, column=1, padx=6)
        ctk.CTkButton(header, text="Test Email", command=self._test_email, width=110).grid(row=0, column=2, padx=(6, 0))

        form = ctk.CTkFrame(self, corner_radius=8)
        form.grid(row=1, column=0, padx=20, pady=8, sticky="ew")
        for column in range(4):
            form.grid_columnconfigure(column, weight=1)

        self.smtp_enabled = tk.BooleanVar(value=False)
        self.tls_enabled = tk.BooleanVar(value=True)
        self.host_var = tk.StringVar()
        self.port_var = tk.StringVar(value="587")
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.from_var = tk.StringVar()
        self.to_var = tk.StringVar()
        self.cooldown_var = tk.StringVar(value="30")
        self.theme_var = tk.StringVar(value="System")

        ctk.CTkCheckBox(form, text="Enable SMTP alerts", variable=self.smtp_enabled).grid(row=0, column=0, padx=10, pady=10, sticky="w")
        ctk.CTkCheckBox(form, text="Use STARTTLS", variable=self.tls_enabled).grid(row=0, column=1, padx=10, pady=10, sticky="w")
        self._entry(form, "SMTP host", self.host_var, 1, 0, columnspan=2)
        self._entry(form, "Port", self.port_var, 1, 2)
        self._entry(form, "Username", self.username_var, 2, 0, columnspan=2)
        self._entry(form, "Password", self.password_var, 2, 2, columnspan=2, show="*")
        self._entry(form, "From email", self.from_var, 3, 0, columnspan=2)
        self._entry(form, "Recipients", self.to_var, 3, 2, columnspan=2)
        self._entry(form, "Default cooldown minutes", self.cooldown_var, 4, 0)
        ctk.CTkLabel(form, text="Appearance").grid(row=10, column=1, padx=10, pady=(10, 0), sticky="w")
        ctk.CTkOptionMenu(form, values=["System", "Dark", "Light"], variable=self.theme_var).grid(row=11, column=1, padx=10, pady=(0, 10), sticky="ew")

        self.status_label = ctk.CTkLabel(self, text="", text_color="#94a3b8")
        self.status_label.grid(row=2, column=0, padx=20, pady=8, sticky="w")
        self._load()

    def _entry(
        self,
        parent: Any,
        label: str,
        variable: tk.StringVar,
        row: int,
        column: int,
        columnspan: int = 1,
        show: str | None = None,
    ) -> None:
        ctk.CTkLabel(parent, text=label).grid(row=row * 2, column=column, columnspan=columnspan, padx=10, pady=(10, 0), sticky="w")
        entry = bind_focus_on_click(ctk.CTkEntry(parent, textvariable=variable, show=show))
        entry.grid(row=row * 2 + 1, column=column, columnspan=columnspan, padx=10, pady=(0, 10), sticky="ew")

    def _load(self) -> None:
        settings = self.app.db.get_settings()
        self.smtp_enabled.set(settings.get("smtp_enabled", "0") == "1")
        self.tls_enabled.set(settings.get("smtp_use_tls", "1") == "1")
        self.host_var.set(settings.get("smtp_host", ""))
        self.port_var.set(settings.get("smtp_port", "587"))
        self.username_var.set(settings.get("smtp_username", ""))
        self.password_var.set(settings.get("smtp_password", ""))
        self.from_var.set(settings.get("smtp_from", ""))
        self.to_var.set(settings.get("smtp_to", ""))
        self.cooldown_var.set(settings.get("alert_cooldown_minutes", "30"))
        self.theme_var.set(settings.get("appearance", "System"))

    def _save(self) -> None:
        db = self.app.db
        db.set_setting("smtp_enabled", "1" if self.smtp_enabled.get() else "0")
        db.set_setting("smtp_use_tls", "1" if self.tls_enabled.get() else "0")
        db.set_setting("smtp_host", self.host_var.get().strip())
        db.set_setting("smtp_port", self.port_var.get().strip())
        db.set_setting("smtp_username", self.username_var.get().strip())
        db.set_setting("smtp_password", self.password_var.get(), secret=True)
        db.set_setting("smtp_from", self.from_var.get().strip())
        db.set_setting("smtp_to", self.to_var.get().strip())
        db.set_setting("alert_cooldown_minutes", self.cooldown_var.get().strip())
        db.set_setting("appearance", self.theme_var.get())
        ctk.set_appearance_mode(self.theme_var.get())
        self.status_label.configure(text="Settings saved")

    def _test_email(self) -> None:
        self._save()
        self.status_label.configure(text="Sending test email...")

        def worker() -> None:
            ok, message = self.app.notifier.send_test_email()
            color = "#16a34a" if ok else "#dc2626"
            self.after(0, lambda: self.status_label.configure(text=message, text_color=color))
            if not ok:
                self.after(0, lambda: messagebox.showerror("Test email", message, parent=self))

        threading.Thread(target=worker, daemon=True).start()
