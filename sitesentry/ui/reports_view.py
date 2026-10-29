from __future__ import annotations

from datetime import datetime, time
from tkinter import filedialog, messagebox, ttk
from typing import Any

import customtkinter as ctk

from sitesentry.core.diagnostics import error_label
from sitesentry.core.report_export import create_report_template
from sitesentry.core.reports import build_report, export_report, format_duration
from .background import run_background
from .datetime_picker import DateTimePicker
from .theme import BAD, BLUE, MUTED, TEXT, WARNING, fit_wrap, metric, table_scrollers


class ReportsView(ctk.CTkFrame):
    def __init__(self, master: Any, app: Any) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.report: dict[str, Any] | None = None
        self._busy = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=20, pady=(20, 12), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Statistics", font=ctk.CTkFont(size=23, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="Template", width=96, command=self._template).grid(row=0, column=1, padx=8)
        self.export_button = ctk.CTkButton(header, text="Export Excel", command=self._export, state="disabled", width=120)
        self.export_button.grid(row=0, column=2)
        filters = ctk.CTkFrame(self, fg_color="transparent")
        filters.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="ew")
        filters.grid_columnconfigure((0, 1), weight=1)
        now = datetime.now().replace(microsecond=0)
        self.start_picker = DateTimePicker(filters, "From", datetime.combine(now.date(), time.min))
        self.start_picker.grid(row=0, column=0, padx=(0, 12), sticky="ew")
        self.end_picker = DateTimePicker(filters, "To", now, end_of_day=True)
        self.end_picker.grid(row=0, column=1, padx=(0, 12), sticky="ew")
        self.generate_button = ctk.CTkButton(filters, text="Generate", width=100, command=self._generate)
        self.generate_button.grid(row=0, column=2)
        metrics = ctk.CTkFrame(self, fg_color="transparent")
        metrics.grid(row=2, column=0, padx=20, pady=(0, 8), sticky="ew")
        self.metrics = [metric(metrics, title, index, tone) for index, (title, tone) in enumerate([
            ("DOWN checks", BAD), ("Incidents", TEXT), ("Total DOWN", BLUE), ("Average DOWN", TEXT), ("Open incidents", WARNING),
        ])]
        self.tabs = ctk.CTkTabview(self, corner_radius=6)
        self.tabs.grid(row=3, column=0, padx=20, pady=(0, 8), sticky="nsew")
        self.table = self._table("Monitors", ("name", "checks", "incidents", "total", "average", "open", "status", "error", "classification", "reason", "phase", "language", "server"),
            ["Monitor", "DOWN checks", "Incidents", "Total DOWN", "Average DOWN", "Open", "Status", "Error category", "Classification", "Reason", "Phase", "Language", "Web server"],
            [220, 110, 90, 120, 120, 64, 86, 250, 130, 150, 110, 120, 140])
        self.incident_table = self._table("Incidents", ("name", "start", "end", "recovered", "duration", "open", "error"),
            ["Monitor", "Counted from", "Counted until", "Recovered at", "Duration", "Open", "Error categories"],
            [220, 170, 170, 170, 120, 70, 360])
        self.error_table = self._table("Error categories", ("name", "code", "category", "checks", "classification", "reason", "phase"),
            ["Monitor", "Error code", "Error category", "DOWN checks", "Classification", "Reason", "Phase"], [220, 190, 330, 120, 130, 150, 110])
        self.summary = ctk.CTkLabel(self, text="", text_color=MUTED, anchor="w", wraplength=820, justify="left")
        self.summary.grid(row=4, column=0, padx=20, pady=(0, 16), sticky="ew")
        self.bind("<Configure>", lambda event: fit_wrap(self.summary, event.width - 40))
        self._generate()

    def _table(self, name: str, columns: tuple[str, ...], titles: list[str], widths: list[int]) -> ttk.Treeview:
        tab = self.tabs.add(name)
        table = ttk.Treeview(tab, columns=columns, show="headings")
        for column, title, width in zip(columns, titles, widths):
            table.heading(column, text=title)
            table.column(column, width=width, minwidth=60, anchor="e" if column in {"checks", "incidents", "total", "average", "duration", "open"} else "w")
        table_scrollers(tab, table)
        return table

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
        for table in (self.table, self.incident_table, self.error_table):
            children = table.get_children()
            if children:
                table.delete(*children)
        for index, row in enumerate(report["rows"]):
            self.table.insert("", "end", values=(row["monitor_name"], row["down_count"], row["incident_count"], format_duration(row["downtime_seconds"]), format_duration(row["average_down_seconds"]), row["open_incidents"], row["last_status"].upper(), error_label(row["last_error_type"]), row["last_classification_state"], row["last_reason_code"], row["last_phase"], row["language"], row["web_server"]), tags=(row["last_status"], "stripe") if index % 2 else (row["last_status"],))
            for detail in row["diagnostic_counts"]:
                self.error_table.insert("", "end", values=(row["monitor_name"], detail["error_type"], error_label(detail["error_type"]), detail["count"], detail["classification_state"], detail["reason_code"], detail["phase"]))
        for index, incident in enumerate(report["incidents"]):
            self.incident_table.insert("", "end", values=(incident["monitor_name"], incident["counted_from"].replace("T", " "), incident["counted_until"].replace("T", " "), (incident["recovered_at"] or "-").replace("T", " "), format_duration(incident["duration_seconds"]), "Yes" if incident["open"] else "No", ", ".join(error_label(code) for code in incident["error_types"])), tags=("stripe",) if index % 2 else ())
        incidents = sum(row["incident_count"] for row in report["rows"])
        open_count = sum(row["open_incidents"] for row in report["rows"])
        values = [report["down_count"], incidents, format_duration(report["downtime_seconds"]), format_duration(report["downtime_seconds"] / incidents if incidents else 0), open_count]
        for label, value in zip(self.metrics, values):
            label.configure(text=str(value))
        self.summary.configure(text=f"From {report['start_at'].replace('T', ' ')} to {report['end_at'].replace('T', ' ')}   Observed through {report['as_of'].replace('T', ' ')}")
        self._busy = False
        self.generate_button.configure(state="normal")
        self.export_button.configure(state="normal")

    def _error(self, message: str) -> None:
        self._busy = False
        self.generate_button.configure(state="normal")
        self.summary.configure(text=message)

    def _template(self) -> None:
        path = filedialog.asksaveasfilename(parent=self, title="Report template", initialfile="sitesentry_report_template.xlsx", defaultextension=".xlsx", filetypes=[("Excel workbook", "*.xlsx")])
        if path:
            start, end = self.start_picker.get(), self.end_picker.get()
            run_background(self.app, self, lambda: create_report_template(path, start, end), lambda _: messagebox.showinfo("Report template", "Template exported.", parent=self))

    def _export(self) -> None:
        if self.report is None:
            return
        path = filedialog.asksaveasfilename(parent=self, title="Export statistics", initialfile=f"sitesentry_statistics_{self.report['start_at'][:10]}_{self.report['end_at'][:10]}.xlsx", defaultextension=".xlsx", filetypes=[("Excel workbook", "*.xlsx")])
        if path:
            report = self.report
            run_background(self.app, self, lambda: export_report(report, path), lambda _: messagebox.showinfo("Statistics", "Excel report exported.", parent=self))
