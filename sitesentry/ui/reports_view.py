from __future__ import annotations

from datetime import datetime, time
from tkinter import filedialog, messagebox, ttk
from typing import Any

import customtkinter as ctk

from sitesentry.core.reports import build_report, export_report, format_duration
from .background import run_background
from .datetime_picker import DateTimePicker


class ReportsView(ctk.CTkFrame):
    def __init__(self, master: Any, app: Any) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.report: dict[str, Any] | None = None
        self._busy = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=20, pady=(18, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Statistics", font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0, sticky="w")
        self.export_button = ctk.CTkButton(header, text="Export Excel", command=self._export, state="disabled", width=120)
        self.export_button.grid(row=0, column=1)
        filters = ctk.CTkFrame(self, fg_color="transparent")
        filters.grid(row=1, column=0, padx=20, pady=8, sticky="ew")
        filters.grid_columnconfigure((0, 1), weight=1)
        now = datetime.now().replace(microsecond=0)
        self.start_picker = DateTimePicker(filters, "From", datetime.combine(now.date(), time.min))
        self.start_picker.grid(row=0, column=0, padx=(0, 12), sticky="ew")
        self.end_picker = DateTimePicker(filters, "To", now, end_of_day=True)
        self.end_picker.grid(row=0, column=1, padx=(0, 12), sticky="ew")
        self.generate_button = ctk.CTkButton(filters, text="Generate", width=100, command=self._generate)
        self.generate_button.grid(row=0, column=2)
        self.summary = ctk.CTkLabel(self, text="", anchor="w", wraplength=820, justify="left")
        self.summary.grid(row=2, column=0, padx=20, pady=8, sticky="ew")
        table_frame = ctk.CTkFrame(self, fg_color="transparent")
        table_frame.grid(row=3, column=0, padx=20, pady=(8, 20), sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        columns = ("name", "checks", "incidents", "total", "average", "open", "language", "server")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", style="SiteSentry.Treeview")
        for column, title, width in zip(columns, ["Monitor name", "DOWN count", "Incidents", "Total DOWN", "Average DOWN", "Open", "Language", "Web server"], [220, 110, 90, 130, 130, 60, 120, 140]):
            self.table.heading(column, text=title)
            self.table.column(column, width=width, minwidth=60, anchor="w" if column in {"name", "language", "server"} else "e")
        dark = ctk.get_appearance_mode() == "Dark"
        style = ttk.Style(self)
        style.configure("SiteSentry.Treeview", rowheight=30, font=("Arial", 12), background="#242424" if dark else "#ffffff", fieldbackground="#242424" if dark else "#ffffff", foreground="#eeeeee" if dark else "#222222")
        style.configure("SiteSentry.Treeview.Heading", font=("Arial", 12, "bold"))
        self.table.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.table.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        self._generate()

    def _generate(self) -> None:
        if self._busy:
            return
        start, end = self.start_picker.get(), self.end_picker.get()
        if start is None or end is None or start > end:
            messagebox.showerror("Statistics", "Select a valid From / To period.", parent=self)
            return
        self._busy = True
        self.generate_button.configure(state="disabled")
        self.export_button.configure(state="disabled")
        self.summary.configure(text="Generating...")
        run_background(self.app, self, lambda: build_report(self.app.db, start, end), self._show_report, self._error)

    def _show_report(self, report: dict[str, Any]) -> None:
        self.report = report
        for item in self.table.get_children():
            self.table.delete(item)
        for row in report["rows"]:
            self.table.insert("", "end", values=(row["monitor_name"], row["down_count"], row["incident_count"], format_duration(row["downtime_seconds"]), format_duration(row["average_down_seconds"]), row["open_incidents"], row["language"], row["web_server"]))
        incidents = sum(row["incident_count"] for row in report["rows"])
        self.summary.configure(text=f"DOWN checks: {report['down_count']}    Incidents: {incidents}    Total DOWN: {format_duration(report['downtime_seconds'])}    As of: {report['as_of']}")
        self._busy = False
        self.generate_button.configure(state="normal")
        self.export_button.configure(state="normal")

    def _error(self, message: str) -> None:
        self._busy = False
        self.generate_button.configure(state="normal")
        self.summary.configure(text=message)

    def _export(self) -> None:
        if self.report is None:
            return
        path = filedialog.asksaveasfilename(parent=self, title="Export statistics", initialfile=f"sitesentry_statistics_{self.report['start_at'][:10]}_{self.report['end_at'][:10]}.xlsx", defaultextension=".xlsx", filetypes=[("Excel workbook", "*.xlsx")])
        if path:
            report = self.report
            run_background(self.app, self, lambda: export_report(report, path), lambda _: messagebox.showinfo("Statistics", "Excel report exported.", parent=self))
