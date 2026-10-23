from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Any, Callable

import customtkinter as ctk

from sitesentry.core.email_rules import RULE_TYPES, WEEKDAYS, normalize_rule
from .focus import bind_focus_on_click


class EmailRuleDialog(ctk.CTkToplevel):
    def __init__(self, master: Any, rule: dict[str, Any] | None, on_save: Callable[[dict[str, Any]], None]) -> None:
        super().__init__(master)
        self.title("Email schedule")
        self.geometry("740x730")
        self.minsize(640, 570)
        self.transient(master.winfo_toplevel())
        self.on_save = on_save
        data = rule or {}
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        form = ctk.CTkScrollableFrame(self, fg_color="transparent")
        form.grid(row=0, column=0, padx=16, pady=16, sticky="nsew")
        form.grid_columnconfigure((0, 1), weight=1)
        self.name = tk.StringVar(value=data.get("name", ""))
        self.kind = tk.StringVar(value=RULE_TYPES[data.get("rule_type", "incident")])
        self.enabled = tk.BooleanVar(value=bool(data.get("enabled", 1)))
        self.hour = tk.StringVar(value=str(data.get("hour", 18)))
        self.minute = tk.StringVar(value=str(data.get("minute", 0)))
        self.period = tk.StringVar(value=data.get("report_period", "today"))
        self.subject = tk.StringVar(value=data.get("subject_template", ""))
        self.details = tk.BooleanVar(value=bool(data.get("include_details", 1)))
        self._entry(form, "Schedule name *", self.name, 0, 0)
        ctk.CTkCheckBox(form, text="Enabled", variable=self.enabled).grid(row=1, column=1, padx=12, sticky="w")
        ctk.CTkLabel(form, text="Event").grid(row=2, column=0, padx=8, pady=(12, 0), sticky="w")
        ctk.CTkOptionMenu(form, values=list(RULE_TYPES.values()), variable=self.kind, command=lambda _: self._toggle_schedule()).grid(row=3, column=0, columnspan=2, padx=8, sticky="ew")
        self.schedule = ctk.CTkFrame(form, fg_color="transparent")
        self.schedule.grid(row=4, column=0, columnspan=2, sticky="ew", pady=8)
        ctk.CTkLabel(self.schedule, text="Send time (local)").grid(row=0, column=0, padx=8, sticky="w")
        tk.Spinbox(self.schedule, from_=0, to=23, textvariable=self.hour, state="readonly", width=4, wrap=True).grid(row=0, column=1, padx=4)
        tk.Spinbox(self.schedule, from_=0, to=59, textvariable=self.minute, state="readonly", width=4, wrap=True).grid(row=0, column=2, padx=4)
        ctk.CTkOptionMenu(self.schedule, values=["today", "yesterday"], variable=self.period, width=140).grid(row=0, column=3, padx=12)
        days = ctk.CTkFrame(self.schedule, fg_color="transparent")
        days.grid(row=1, column=0, columnspan=4, pady=12, sticky="ew")
        selected_days = data.get("weekdays", ",".join(WEEKDAYS)).split(",")
        self.days: dict[str, tk.BooleanVar] = {}
        for index, day in enumerate(WEEKDAYS):
            variable = tk.BooleanVar(value=day in selected_days)
            self.days[day] = variable
            ctk.CTkCheckBox(days, text=day.title(), variable=variable, width=76, checkbox_width=18, checkbox_height=18).grid(row=0, column=index, padx=3)
        ctk.CTkLabel(form, text="Recipients (blank = SMTP recipients)").grid(row=5, column=0, columnspan=2, padx=8, pady=(10, 0), sticky="w")
        self.recipients = bind_focus_on_click(ctk.CTkTextbox(form, height=68))
        self.recipients.grid(row=6, column=0, columnspan=2, padx=8, sticky="ew")
        self.recipients.insert("1.0", data.get("recipients", ""))
        self._entry(form, "Subject", self.subject, 7, 0, span=2)
        ctk.CTkLabel(form, text="Message").grid(row=9, column=0, padx=8, pady=(12, 0), sticky="w")
        self.body = bind_focus_on_click(ctk.CTkTextbox(form, height=150))
        self.body.grid(row=10, column=0, columnspan=2, padx=8, sticky="ew")
        self.body.insert("1.0", data.get("body_template", ""))
        ctk.CTkCheckBox(form, text="Include default HTML report", variable=self.details).grid(row=11, column=0, columnspan=2, padx=8, pady=16, sticky="w")
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=1, column=0, padx=24, pady=(0, 16), sticky="ew")
        ctk.CTkButton(actions, text="Save", width=96, command=self._save).pack(side="right")
        ctk.CTkButton(actions, text="Cancel", width=96, fg_color="#52525b", command=self.destroy).pack(side="right", padx=10)
        self._toggle_schedule()
        self.after(100, self.lift)

    def _entry(self, parent: Any, label: str, variable: tk.StringVar, row: int, column: int, span: int = 1) -> None:
        ctk.CTkLabel(parent, text=label).grid(row=row, column=column, columnspan=span, padx=8, pady=(12, 0), sticky="w")
        bind_focus_on_click(ctk.CTkEntry(parent, textvariable=variable)).grid(row=row + 1, column=column, columnspan=span, padx=8, sticky="ew")

    def _toggle_schedule(self) -> None:
        if self.kind.get() == RULE_TYPES["daily_summary"]:
            self.schedule.grid()
        else:
            self.schedule.grid_remove()

    def _save(self) -> None:
        try:
            payload = normalize_rule({
                "name": self.name.get(), "enabled": self.enabled.get(),
                "rule_type": next(key for key, value in RULE_TYPES.items() if value == self.kind.get()),
                "hour": self.hour.get(), "minute": self.minute.get(),
                "weekdays": ",".join(day for day, variable in self.days.items() if variable.get()),
                "report_period": self.period.get(), "recipients": self.recipients.get("1.0", "end-1c"),
                "subject_template": self.subject.get(), "body_template": self.body.get("1.0", "end-1c"),
                "include_details": self.details.get(),
            })
            self.on_save(payload)
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Email schedule", str(exc), parent=self)
            return
        self.destroy()
