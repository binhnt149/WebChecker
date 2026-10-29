from __future__ import annotations

import asyncio
import json
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

import customtkinter as ctk

from sitesentry.core.diagnostic_rules import PHASES, validate_rules
from sitesentry.core.diagnostics import ERROR_TYPES
from sitesentry.core.network_diagnostics import validate_profile
from .background import run_background
from .focus import bind_focus_on_click
from .theme import polish, table_scrollers


class MonitorDiagnosticsDialog(ctk.CTkToplevel):
    def __init__(self, master: Any, profile: str, rules: str, on_save: Callable[[str, str], None]) -> None:
        super().__init__(master)
        self.app = master.app
        self.on_save = on_save
        self.rules = validate_rules(rules)
        self.title("Monitor diagnostics")
        self.geometry("760x540")
        self.minsize(650, 450)
        self.transient(master)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=18, pady=12, sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(top, text="Network profile").grid(row=0, column=0, padx=(0, 10))
        self.profile_var = tk.StringVar(value=profile or "None")
        self.profile_menu = ctk.CTkOptionMenu(top, variable=self.profile_var, values=["None"])
        self.profile_menu.grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(top, text="Manage profiles", width=140, command=self._manage_profiles).grid(row=0, column=2, padx=(10, 0))
        ctk.CTkLabel(self, text="Rules evaluate only configured evidence; unclassified incidents do not send email.", anchor="w", wraplength=680, justify="left").grid(row=1, column=0, padx=18, sticky="ew")
        table_frame = ctk.CTkFrame(self, fg_color="transparent")
        table_frame.grid(row=2, column=0, padx=18, pady=10, sticky="nsew")
        self.table = ttk.Treeview(table_frame, columns=("id", "phase", "category", "priority", "enabled"), show="headings", selectmode="browse")
        for column, title, width in [("id", "Rule", 160), ("phase", "Phase", 120), ("category", "Category", 180), ("priority", "Priority", 80), ("enabled", "Enabled", 75)]:
            self.table.heading(column, text=title)
            self.table.column(column, width=width, minwidth=60)
        table_scrollers(table_frame, self.table)
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=3, column=0, padx=18, pady=6, sticky="ew")
        for label, command in [("Add rule", lambda: self._edit_rule(None)), ("Edit", self._edit_selected), ("Enable / disable", self._toggle), ("Remove", self._remove)]:
            ctk.CTkButton(actions, text=label, width=100, command=command).pack(side="left", padx=(0, 6))
        ctk.CTkButton(actions, text="Save", width=90, command=self._save).pack(side="right")
        ctk.CTkButton(actions, text="Cancel", width=90, command=self.destroy).pack(side="right", padx=6)
        self._refresh_profiles()
        self._render()
        polish(self)

    def _refresh_profiles(self) -> None:
        values = ["None", *(profile["name"] for profile in self.app.db.list_network_profiles())]
        self.profile_menu.configure(values=values)
        if self.profile_var.get() not in values:
            self.profile_var.set("None")

    def _render(self) -> None:
        self.table.delete(*self.table.get_children())
        for item in self.rules:
            self.table.insert("", "end", iid=item["id"], values=(item["id"], item["phase"], item["result"]["error_type"], item["priority"], "Yes" if item["enabled"] else "No"))

    def _selected(self) -> dict[str, Any] | None:
        selected = self.table.selection()
        return next((item for item in self.rules if item["id"] == selected[0]), None) if selected else None

    def _edit_selected(self) -> None:
        item = self._selected()
        if item:
            self._edit_rule(item)

    def _edit_rule(self, item: dict[str, Any] | None) -> None:
        def save(value: dict[str, Any]) -> None:
            updated = [rule for rule in self.rules if not item or rule["id"] != item["id"]] + [value]
            validate_rules(updated)
            self.rules = updated
            self._render()
        self._rule_dialog = DiagnosticRuleDialog(self, item, save)

    def _toggle(self) -> None:
        item = self._selected()
        if item:
            item["enabled"] = not item["enabled"]
            self._render()

    def _remove(self) -> None:
        item = self._selected()
        if item:
            self.rules = [rule for rule in self.rules if rule["id"] != item["id"]]
            self._render()

    def _manage_profiles(self) -> None:
        self._profiles_dialog = NetworkProfilesDialog(self, self.app, self._refresh_profiles)

    def _save(self) -> None:
        try:
            validate_rules(self.rules)
            profile = "" if self.profile_var.get() == "None" else self.profile_var.get()
            if profile and not self.app.db.get_network_profile(profile):
                raise ValueError("Selected network profile no longer exists")
            self.on_save(profile, json.dumps(self.rules, ensure_ascii=False))
        except ValueError as exc:
            messagebox.showerror("Diagnostics", str(exc), parent=self)
            return
        self.destroy()


class DiagnosticRuleDialog(ctk.CTkToplevel):
    def __init__(self, master: Any, item: dict[str, Any] | None, on_save: Callable[[dict[str, Any]], None]) -> None:
        super().__init__(master)
        self.on_save = on_save
        self.title("Diagnostic rule")
        self.geometry("700x640")
        self.transient(master)
        item = item or {"id": "api-failure", "enabled": True, "priority": 100, "phase": "response", "conditions": [{"source": "json", "path": "success", "operator": "equals", "value": False}], "result": {"error_type": "assertion_failed", "reason_code": "business_rule_match"}}
        self.id_var = tk.StringVar(value=item["id"])
        self.priority_var = tk.StringVar(value=str(item["priority"]))
        self.phase_var = tk.StringVar(value=item["phase"])
        self.enabled_var = tk.BooleanVar(value=item["enabled"])
        self.category_var = tk.StringVar(value=item["result"]["error_type"])
        self.reason_var = tk.StringVar(value=item["result"].get("reason_code", ""))
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        form = ctk.CTkScrollableFrame(self)
        form.grid(row=0, column=0, padx=16, pady=12, sticky="nsew")
        form.grid_columnconfigure((0, 1), weight=1)
        for row, (label, variable) in enumerate([("Rule ID", self.id_var), ("Priority", self.priority_var), ("Reason code", self.reason_var)]):
            ctk.CTkLabel(form, text=label).grid(row=row * 2, column=0, padx=8, sticky="w")
            bind_focus_on_click(ctk.CTkEntry(form, textvariable=variable)).grid(row=row * 2 + 1, column=0, padx=8, pady=(0, 8), sticky="ew")
        ctk.CTkLabel(form, text="Phase").grid(row=0, column=1, padx=8, sticky="w")
        ctk.CTkOptionMenu(form, variable=self.phase_var, values=sorted(PHASES)).grid(row=1, column=1, padx=8, sticky="ew")
        ctk.CTkLabel(form, text="Error category").grid(row=2, column=1, padx=8, sticky="w")
        ctk.CTkOptionMenu(form, variable=self.category_var, values=[code for code in ERROR_TYPES if code not in {"unknown", "network_offline"}]).grid(row=3, column=1, padx=8, sticky="ew")
        ctk.CTkCheckBox(form, text="Enabled", variable=self.enabled_var).grid(row=5, column=1, padx=8, sticky="w")
        ctk.CTkLabel(form, text="Conditions JSON (all conditions must match)").grid(row=6, column=0, columnspan=2, padx=8, pady=(12, 0), sticky="w")
        self.conditions = bind_focus_on_click(ctk.CTkTextbox(form, height=170))
        self.conditions.grid(row=7, column=0, columnspan=2, padx=8, pady=8, sticky="ew")
        self.conditions.insert("1.0", json.dumps(item["conditions"], ensure_ascii=False, indent=2))
        ctk.CTkLabel(form, text="Sources: http_status, visible_text, json. JSON values retain their type; see checker-spec.md §7.", wraplength=600, justify="left").grid(row=8, column=0, columnspan=2, padx=8, sticky="w")
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="e")
        ctk.CTkButton(actions, text="Cancel", width=90, command=self.destroy).pack(side="left", padx=6)
        ctk.CTkButton(actions, text="Save rule", width=100, command=self._save).pack(side="left")
        polish(self)

    def _save(self) -> None:
        try:
            payload = {"id": self.id_var.get().strip(), "enabled": self.enabled_var.get(), "priority": int(self.priority_var.get()), "phase": self.phase_var.get(), "conditions": json.loads(self.conditions.get("1.0", "end-1c")), "result": {"error_type": self.category_var.get(), "reason_code": self.reason_var.get().strip()}}
            validate_rules([payload])
            self.on_save(payload)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Diagnostic rule", str(exc), parent=self)
            return
        self.destroy()


class NetworkProfilesDialog(ctk.CTkToplevel):
    def __init__(self, master: Any, app: Any, on_change: Callable[[], None]) -> None:
        super().__init__(master)
        self.app, self.on_change = app, on_change
        self.title("Network profiles")
        self.geometry("680x440")
        self.transient(master)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self, text="Reference checks only verify the configured endpoint.", wraplength=600).grid(row=0, column=0, padx=16, pady=12, sticky="w")
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=1, column=0, padx=16, sticky="nsew")
        self.table = ttk.Treeview(frame, columns=("name", "scope", "targets", "enabled"), show="headings", selectmode="browse")
        for column, title, width in [("name", "Name", 190), ("scope", "Scope", 160), ("targets", "Targets", 90), ("enabled", "Enabled", 90)]:
            self.table.heading(column, text=title)
            self.table.column(column, width=width)
        table_scrollers(frame, self.table)
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=2, column=0, padx=16, pady=12, sticky="ew")
        ctk.CTkButton(actions, text="Add", width=90, command=lambda: self._edit_profile(None)).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="Edit", width=90, command=self._edit_selected).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="Delete", width=90, command=self._delete).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="Close", width=90, command=self.destroy).pack(side="right")
        self._refresh()
        polish(self)

    def _refresh(self) -> None:
        self.table.delete(*self.table.get_children())
        for item in self.app.db.list_network_profiles():
            self.table.insert("", "end", iid=item["name"], values=(item["name"], item["scope"], len(item["targets"]), "Yes" if item["enabled"] else "No"))
        self.on_change()

    def _edit_selected(self) -> None:
        selected = self.table.selection()
        if selected:
            self._edit_profile(self.app.db.get_network_profile(selected[0]))

    def _edit_profile(self, profile: dict[str, Any] | None) -> None:
        self._profile_dialog = NetworkProfileEditor(self, self.app, profile, self._refresh)

    def _delete(self) -> None:
        selected = self.table.selection()
        if not selected:
            return
        try:
            self.app.db.delete_network_profile(selected[0])
        except ValueError as exc:
            messagebox.showerror("Network profiles", str(exc), parent=self)
        else:
            self._refresh()


class NetworkProfileEditor(ctk.CTkToplevel):
    def __init__(self, master: Any, app: Any, profile: dict[str, Any] | None, on_save: Callable[[], None]) -> None:
        super().__init__(master)
        self.app, self.original, self.on_save = app, profile, on_save
        self.title("Network profile")
        self.geometry("700x520")
        self.transient(master)
        profile = profile or {"name": "", "scope": "custom", "enabled": True, "targets": []}
        self.name_var = tk.StringVar(value=profile["name"])
        self.scope_var = tk.StringVar(value=profile["scope"])
        self.enabled_var = tk.BooleanVar(value=profile["enabled"])
        self.target_vars = []
        self.grid_columnconfigure(0, weight=1)
        form = ctk.CTkFrame(self)
        form.grid(row=0, column=0, padx=16, pady=12, sticky="nsew")
        form.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(form, text="Profile name *").grid(row=0, column=0, padx=8, sticky="w")
        name = bind_focus_on_click(ctk.CTkEntry(form, textvariable=self.name_var))
        name.grid(row=1, column=0, padx=8, sticky="ew")
        if self.original:
            name.configure(state="disabled")
        ctk.CTkOptionMenu(form, variable=self.scope_var, values=["internet", "intranet_vpn", "custom"]).grid(row=1, column=1, padx=8)
        ctk.CTkCheckBox(form, text="Enabled", variable=self.enabled_var).grid(row=2, column=0, padx=8, pady=8, sticky="w")
        for index in range(2):
            target = profile["targets"][index] if index < len(profile["targets"]) else {}
            url, method, timeout = tk.StringVar(value=target.get("url", "")), tk.StringVar(value=target.get("method", "HEAD")), tk.StringVar(value=str(target.get("timeout_seconds", 2)))
            self.target_vars.append((url, method, timeout))
            ctk.CTkLabel(form, text=f"Reference URL {index + 1}").grid(row=3 + index * 2, column=0, padx=8, sticky="w")
            bind_focus_on_click(ctk.CTkEntry(form, textvariable=url, placeholder_text="https://reference.example/health")).grid(row=4 + index * 2, column=0, padx=8, pady=6, sticky="ew")
            ctk.CTkOptionMenu(form, variable=method, values=["HEAD", "GET"], width=90).grid(row=4 + index * 2, column=1, padx=6)
            bind_focus_on_click(ctk.CTkEntry(form, textvariable=timeout, width=60)).grid(row=4 + index * 2, column=2, padx=6)
        self.status = ctk.CTkLabel(form, text="Probe does not include monitor credentials and only checks this endpoint.", wraplength=620, justify="left")
        self.status.grid(row=7, column=0, columnspan=3, padx=8, pady=14, sticky="w")
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=1, column=0, padx=16, pady=10, sticky="ew")
        ctk.CTkButton(actions, text="Test profile", command=self._test).pack(side="left")
        ctk.CTkButton(actions, text="Save", width=90, command=self._save).pack(side="right")
        ctk.CTkButton(actions, text="Cancel", width=90, command=self.destroy).pack(side="right", padx=8)
        polish(self)

    def _payload(self) -> dict[str, Any]:
        targets = [{"url": url.get().strip(), "method": method.get(), "timeout_seconds": timeout.get()} for url, method, timeout in self.target_vars if url.get().strip()]
        return validate_profile({"name": self.name_var.get(), "scope": self.scope_var.get(), "enabled": self.enabled_var.get(), "targets": targets})

    def _save(self) -> None:
        try:
            payload = self._payload()
            if not self.original and self.app.db.get_network_profile(payload["name"]):
                raise ValueError("A profile with this name already exists")
            self.app.db.save_network_profile(payload)
            self.on_save()
        except ValueError as exc:
            messagebox.showerror("Network profile", str(exc), parent=self)
            return
        self.destroy()

    def _test(self) -> None:
        try:
            profile = self._payload()
        except ValueError as exc:
            messagebox.showerror("Network profile", str(exc), parent=self)
            return
        self.status.configure(text="Checking reference endpoints...")
        run_background(self.app, self, lambda: asyncio.run(self.app.checker.network_diagnostics.probe(profile)), lambda result: self.status.configure(text=json.dumps(result, ensure_ascii=False)), lambda error: self.status.configure(text=error))
