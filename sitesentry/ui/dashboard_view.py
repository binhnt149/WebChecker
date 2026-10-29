from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

import customtkinter as ctk

from sitesentry.core.diagnostics import ERROR_TYPES, error_label
from sitesentry.core.privacy import sanitize
from sitesentry.core.excel_importer import create_monitor_template, import_monitors_from_excel
from .background import run_background
from .focus import bind_focus_on_click
from .monitor_dialog import MonitorDialog
from .theme import BAD, BLUE, GOOD, MUTED, TEXT, fit_wrap, metric, table_scrollers


TYPE_LABELS = {"simple_web": "Web", "auth_web": "Auth Web", "api": "API"}


class DashboardView(ctk.CTkFrame):
    def __init__(self, master: Any, app: Any) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._busy = False
        self._refresh_again = False
        self._monitors: dict[int, dict[str, Any]] = {}
        self._dialog: MonitorDialog | None = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=20, pady=(20, 12), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Dashboard", font=ctk.CTkFont(size=23, weight="bold")).grid(row=0, column=0, sticky="w")
        for column, (label, command, width) in enumerate([
            ("Import Excel", self._import_excel, 104), ("Template", self._save_template, 84),
            ("Run all", self.app.scheduler.run_all_now, 82), ("Add monitor", self._add_monitor, 112),
        ], start=1):
            ctk.CTkButton(header, text=label, command=command, width=width).grid(row=0, column=column, padx=(8, 0))
        metrics = ctk.CTkFrame(self, fg_color="transparent")
        metrics.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="ew")
        self.metrics = [metric(metrics, title, column, tone) for column, (title, tone) in enumerate([
            ("Monitors", TEXT), ("UP", GOOD), ("DOWN", BAD), ("Unknown", MUTED), ("Avg response", BLUE),
        ])]
        filters = ctk.CTkFrame(self, fg_color="transparent")
        filters.grid(row=2, column=0, padx=20, pady=(0, 12), sticky="ew")
        filters.grid_columnconfigure(0, weight=1)
        self.search = tk.StringVar()
        self.status = tk.StringVar(value="All states")
        self.monitor_type = tk.StringVar(value="All types")
        self.category = tk.StringVar(value="All errors")
        self.classification = tk.StringVar(value="All classifications")
        bind_focus_on_click(ctk.CTkEntry(filters, textvariable=self.search, placeholder_text="Search monitor, URL or error", height=32)).grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ctk.CTkOptionMenu(filters, values=["All states", "UP", "DOWN", "Unknown", "Paused"], variable=self.status, width=122, command=lambda _: self._render()).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkOptionMenu(filters, values=["All types", *TYPE_LABELS.values()], variable=self.monitor_type, width=120, command=lambda _: self._render()).grid(row=0, column=2, padx=(0, 8))
        ctk.CTkButton(filters, text="Refresh", width=82, command=self.refresh).grid(row=0, column=3)
        ctk.CTkOptionMenu(filters, values=["All errors", *ERROR_TYPES.values()], variable=self.category, width=250, command=lambda _: self._render()).grid(row=1, column=0, pady=(8, 0), sticky="w")
        ctk.CTkOptionMenu(filters, values=["All classifications", "confirmed", "undetermined", "legacy", "not_applicable"], variable=self.classification, width=180, command=lambda _: self._render()).grid(row=1, column=1, columnspan=2, padx=8, pady=(8, 0), sticky="w")
        self.search.trace_add("write", lambda *_: self._render())
        table_frame = ctk.CTkFrame(self, fg_color="transparent")
        table_frame.grid(row=3, column=0, padx=20, sticky="nsew")
        columns = ("name", "type", "status", "error", "classification", "reason", "phase", "response", "checked", "url")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        for column, title, width in zip(columns, ["Monitor", "Type", "Status", "Error category", "Classification", "Reason", "Phase", "Response", "Last checked", "URL"], [210, 90, 86, 250, 130, 160, 120, 100, 170, 320]):
            self.table.heading(column, text=title)
            self.table.column(column, width=width, minwidth=70, stretch=column == "name")
        table_scrollers(table_frame, self.table)
        self.table.bind("<<TreeviewSelect>>", lambda _: self._selection_changed())
        self.table.bind("<Double-1>", lambda _: self._edit_selected())
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, padx=20, pady=(12, 16), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        self.selection_label = ctk.CTkLabel(footer, text="No monitor selected", anchor="w", text_color=MUTED, wraplength=280, justify="left")
        self.selection_label.grid(row=0, column=0, sticky="ew")
        actions = ctk.CTkFrame(footer, fg_color="transparent")
        actions.grid(row=0, column=1)
        self.actions = []
        for label, command in [("Run", self._run_selected), ("Edit", self._edit_selected), ("Pause", self._toggle_selected), ("Delete", self._delete_selected)]:
            button = ctk.CTkButton(actions, text=label, width=70, command=command, state="disabled")
            button.pack(side="left", padx=(6, 0))
            self.actions.append(button)
        self.detail = ctk.CTkLabel(footer, text="", anchor="w", justify="left", text_color=MUTED, wraplength=700, height=40)
        self.detail.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        footer.bind("<Configure>", lambda event: fit_wrap(self.detail, event.width - 12))
        self.refresh()

    def refresh(self) -> None:
        if not self.winfo_exists():
            return
        if self._busy:
            self._refresh_again = True
            return
        self._busy = True
        def done(monitors: list[dict[str, Any]]) -> None:
            self._busy = False
            self._monitors = {item["id"]: item for item in monitors}
            responses = [item["last_response_ms"] for item in monitors if item["last_response_ms"] is not None]
            values = [len(monitors), sum(item["last_status"] == "up" for item in monitors),
                      sum(item["last_status"] == "down" for item in monitors), sum(item["last_status"] == "unknown" for item in monitors),
                      f"{round(sum(responses) / len(responses))} ms" if responses else "-"]
            for label, value in zip(self.metrics, values):
                label.configure(text=str(value))
            self._render()
            if self._refresh_again:
                self._refresh_again = False
                self.refresh()
        def failed(message: str) -> None:
            self._busy = False
            self.detail.configure(text=message)
        run_background(self.app, self, lambda: self.app.db.list_monitors(include_disabled=True), done, failed)

    def _render(self) -> None:
        if not hasattr(self, "table"):
            return
        query = self.search.get().casefold()
        selected = self.table.selection()
        wanted = set()
        index = 0
        for monitor in self._monitors.values():
            state = monitor["last_status"]
            type_label = TYPE_LABELS.get(monitor["monitor_type"], monitor["monitor_type"])
            if self.status.get() != "All states" and not (self.status.get() == "Paused" and not monitor["enabled"]) and self.status.get().lower() != state:
                continue
            if self.monitor_type.get() not in {"All types", type_label}:
                continue
            category = error_label(monitor.get("last_error_type", "")) if state == "down" else "-"
            if self.category.get() != "All errors" and category != self.category.get():
                continue
            if self.classification.get() != "All classifications" and monitor.get("last_classification_state") != self.classification.get():
                continue
            if query not in f"{monitor['name']} {monitor['url']} {category} {monitor['last_error']}".casefold():
                continue
            iid = str(monitor["id"])
            wanted.add(iid)
            checked = str(monitor.get("last_checked_at") or "Never").replace("T", " ")
            response = f"{monitor['last_response_ms']} ms" if monitor["last_response_ms"] is not None else "-"
            values = (sanitize(monitor["name"], monitor), type_label, state.upper() if monitor["enabled"] else "PAUSED", category, monitor.get("last_classification_state", ""), monitor.get("last_reason_code", ""), monitor.get("last_phase", ""), response, checked, sanitize(monitor["url"], monitor))
            tags = (state, "stripe") if index % 2 else (state,)
            if self.table.exists(iid):
                self.table.item(iid, values=values, tags=tags)
                self.table.move(iid, "", index)
            else:
                self.table.insert("", index, iid=iid, values=values, tags=tags)
            index += 1
        for iid in self.table.get_children():
            if iid not in wanted:
                self.table.delete(iid)
        if selected and selected[0] in wanted:
            self.table.selection_set(selected[0])
        self._selection_changed()

    def _selected(self) -> dict[str, Any] | None:
        items = self.table.selection()
        return self._monitors.get(int(items[0])) if items else None

    def _selection_changed(self) -> None:
        monitor = self._selected()
        for button in self.actions:
            button.configure(state="normal" if monitor else "disabled")
        self.actions[2].configure(text="Pause" if monitor and monitor["enabled"] else "Enable")
        if monitor:
            self.selection_label.configure(text=sanitize(str(monitor["name"]), monitor))
            detail = monitor["last_error"] if monitor["last_status"] == "down" else monitor["url"]
            if monitor.get("last_classification_state") == "legacy" and monitor["last_status"] == "down":
                detail = "Legacy diagnostic details withheld"
            self.detail.configure(text=sanitize(detail, monitor))
        else:
            self.selection_label.configure(text=f"{len(self.table.get_children())} monitor(s)")
            self.detail.configure(text="No monitors" if not self._monitors else "")

    def _open_dialog(self, monitor: dict[str, Any] | None = None) -> None:
        if self._dialog is not None and self._dialog.winfo_exists():
            self._dialog.lift()
            return
        self._dialog = MonitorDialog(self.app, monitor=monitor, on_save=self.refresh)

    def _add_monitor(self) -> None:
        self._open_dialog()

    def _edit_selected(self) -> None:
        monitor = self._selected()
        if monitor:
            self._open_dialog(self.app.db.get_monitor(monitor["id"]))

    def _run_selected(self) -> None:
        monitor = self._selected()
        if monitor:
            self.app.scheduler.run_now(monitor["id"])

    def _toggle_selected(self) -> None:
        monitor = self._selected()
        if monitor:
            self.app.db.set_monitor_enabled(monitor["id"], not monitor["enabled"])
            self.app.scheduler.sync_jobs()
            self.refresh()

    def _delete_selected(self) -> None:
        monitor = self._selected()
        if monitor and messagebox.askyesno("Delete monitor", f"Delete {monitor['name']}?", parent=self):
            self.app.db.delete_monitor(monitor["id"])
            self.app.scheduler.sync_jobs()
            self.refresh()

    def _save_template(self) -> None:
        path = filedialog.asksaveasfilename(parent=self, title="Monitor template", initialfile="sitesentry_monitors_template.xlsx", defaultextension=".xlsx", filetypes=[("Excel workbook", "*.xlsx")])
        if path:
            run_background(self.app, self, lambda: create_monitor_template(path), lambda _: messagebox.showinfo("Template", "Template exported.", parent=self))

    def _import_excel(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Import monitors", filetypes=[("Excel workbook", "*.xlsx")])
        if not path:
            return
        def work():
            result = import_monitors_from_excel(self.app.db, path)
            self.app.scheduler.sync_jobs()
            return result
        def done(result):
            self.refresh()
            self.app._update_status_text()
            (messagebox.showinfo if result.ok else messagebox.showwarning)("Import Excel", result.summary(), parent=self)
        run_background(self.app, self, work, done)
