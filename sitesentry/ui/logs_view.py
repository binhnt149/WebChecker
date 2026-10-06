from __future__ import annotations

import csv
from datetime import datetime, time
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .focus import bind_focus_on_click


EXPORT_FIELDS = [
    "id",
    "monitor_id",
    "monitor_name",
    "status",
    "ok",
    "response_ms",
    "status_code",
    "error",
    "attempts",
    "checked_at",
    "detail_json",
]


class LogsView(ctk.CTkFrame):
    def __init__(self, master: Any, app: Any) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=0, column=0, padx=20, pady=(18, 8), sticky="ew")
        toolbar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(toolbar, text="Logs", font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0, sticky="w")

        filters = ctk.CTkFrame(toolbar, fg_color="transparent")
        filters.grid(row=1, column=0, columnspan=6, sticky="ew", pady=(14, 0))
        filters.grid_columnconfigure(7, weight=1)
        self.status_filter = tk.StringVar(value="all")
        self.start_var = tk.StringVar()
        self.end_var = tk.StringVar()
        ctk.CTkLabel(filters, text="Status").grid(row=0, column=0, padx=(0, 6), sticky="w")
        ctk.CTkOptionMenu(filters, values=["all", "up", "down"], variable=self.status_filter, command=lambda _: self.refresh(), width=100).grid(row=0, column=1, padx=(0, 12), sticky="w")
        ctk.CTkLabel(filters, text="From").grid(row=0, column=2, padx=(0, 6), sticky="w")
        bind_focus_on_click(ctk.CTkEntry(filters, textvariable=self.start_var, placeholder_text="YYYY-MM-DD", width=130)).grid(row=0, column=3, padx=(0, 12), sticky="w")
        ctk.CTkLabel(filters, text="To").grid(row=0, column=4, padx=(0, 6), sticky="w")
        bind_focus_on_click(ctk.CTkEntry(filters, textvariable=self.end_var, placeholder_text="YYYY-MM-DD", width=130)).grid(row=0, column=5, padx=(0, 12), sticky="w")
        ctk.CTkButton(filters, text="Apply", command=self.refresh, width=82).grid(row=0, column=6, padx=(0, 6))
        ctk.CTkButton(filters, text="Export Excel", command=self._export_excel, width=120).grid(row=0, column=8, padx=6)
        ctk.CTkButton(filters, text="Export CSV", command=self._export_csv, width=110, fg_color="#475569").grid(row=0, column=9, padx=6)
        ctk.CTkButton(filters, text="Clear", command=self._clear_logs, width=80, fg_color="#991b1b", hover_color="#7f1d1d").grid(row=0, column=10, padx=6)
        ctk.CTkButton(filters, text="Refresh", command=self.refresh, width=90).grid(row=0, column=11, padx=(6, 0))

        self.table = ctk.CTkScrollableFrame(self, corner_radius=8)
        self.table.grid(row=1, column=0, padx=20, pady=(8, 20), sticky="nsew")
        self.table.grid_columnconfigure(0, weight=1)
        self.summary_label = ctk.CTkLabel(self, text="", text_color="#94a3b8")
        self.summary_label.grid(row=2, column=0, padx=20, pady=(0, 12), sticky="w")
        self.refresh()

    def refresh(self) -> None:
        for child in self.table.winfo_children():
            child.destroy()
        range_values = self._date_range()
        if range_values is None:
            return
        start_at, end_at = range_values
        logs = self.app.db.list_logs(limit=500, status_filter=self.status_filter.get(), start_at=start_at, end_at=end_at)
        self.summary_label.configure(text=f"Showing {len(logs)} latest log row(s)")
        if not logs:
            ctk.CTkLabel(self.table, text="No logs", text_color="#94a3b8").grid(row=0, column=0, pady=48)
            return
        for row, item in enumerate(logs):
            self._row(row, item)

    def _row(self, row: int, item: dict[str, Any]) -> None:
        frame = ctk.CTkFrame(self.table, corner_radius=8)
        frame.grid(row=row, column=0, padx=4, pady=5, sticky="ew")
        frame.grid_columnconfigure(1, weight=1)
        color = "#16a34a" if item.get("ok") else "#dc2626"
        ctk.CTkLabel(frame, text=str(item.get("status", "")).upper(), text_color=color, width=70).grid(row=0, column=0, padx=10, pady=8)
        title = f"{item.get('monitor_name')}  |  {item.get('checked_at')}"
        ctk.CTkLabel(frame, text=title, anchor="w").grid(row=0, column=1, sticky="ew", pady=(8, 0))
        details = f"HTTP {item.get('status_code') or '-'}  |  {item.get('response_ms') or '-'} ms  |  attempts {item.get('attempts') or 1}  |  {item.get('error') or ''}"
        ctk.CTkLabel(frame, text=details, text_color="#94a3b8", anchor="w").grid(row=1, column=1, sticky="ew", pady=(0, 8))

    def _date_range(self) -> tuple[str | None, str | None] | None:
        start_text = self.start_var.get().strip()
        end_text = self.end_var.get().strip()
        try:
            start_at = self._parse_boundary(start_text, is_end=False) if start_text else None
            end_at = self._parse_boundary(end_text, is_end=True) if end_text else None
        except ValueError as exc:
            messagebox.showerror("Log date filter", str(exc), parent=self)
            return None
        if start_at and end_at and start_at > end_at:
            messagebox.showerror("Log date filter", "From date must be before To date.", parent=self)
            return None
        return start_at, end_at

    def _parse_boundary(self, value: str, is_end: bool) -> str:
        formats = ["%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"]
        parsed: datetime | None = None
        for date_format in formats:
            try:
                parsed = datetime.strptime(value, date_format)
                if date_format == "%Y-%m-%d":
                    parsed = datetime.combine(parsed.date(), time.max if is_end else time.min).replace(microsecond=0)
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValueError("Date must use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS.")
        return parsed.isoformat(timespec="seconds")

    def _filtered_logs(self, limit: int) -> list[dict[str, Any]] | None:
        range_values = self._date_range()
        if range_values is None:
            return None
        start_at, end_at = range_values
        return self.app.db.list_logs(limit=limit, status_filter=self.status_filter.get(), start_at=start_at, end_at=end_at)

    def _export_excel(self) -> None:
        logs = self._filtered_logs(limit=100000)
        if logs is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export logs to Excel",
            initialfile=self._default_export_name("xlsx"),
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
        )
        if not path:
            return

        wb = Workbook()
        ws = wb.active
        ws.title = "Logs"
        ws.append(EXPORT_FIELDS)
        for item in logs:
            ws.append([item.get(field, "") for field in EXPORT_FIELDS])

        header_fill = PatternFill("solid", fgColor="1F2937")
        header_font = Font(color="FFFFFF", bold=True)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{ws.cell(row=1, column=len(EXPORT_FIELDS)).coordinate}"
        widths = {
            "A": 8,
            "B": 12,
            "C": 26,
            "D": 12,
            "E": 8,
            "F": 14,
            "G": 14,
            "H": 42,
            "I": 10,
            "J": 22,
            "K": 42,
        }
        for column_cells in ws.columns:
            letter = column_cells[0].column_letter
            ws.column_dimensions[letter].width = widths.get(letter, 18)
            for cell in column_cells:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
        wb.save(path)
        messagebox.showinfo("Export Excel", f"Exported {len(logs)} log row(s).", parent=self)

    def _export_csv(self) -> None:
        logs = self._filtered_logs(limit=100000)
        if logs is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export logs",
            initialfile=self._default_export_name("csv"),
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=EXPORT_FIELDS,
            )
            writer.writeheader()
            writer.writerows(logs)
        messagebox.showinfo("Export CSV", f"Exported {len(logs)} log row(s).", parent=self)

    def _default_export_name(self, extension: str) -> str:
        start = self.start_var.get().strip().replace(" ", "_").replace(":", "")
        end = self.end_var.get().strip().replace(" ", "_").replace(":", "")
        if start or end:
            suffix = f"{start or 'begin'}_{end or 'now'}"
        else:
            suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"sitesentry_logs_{suffix}.{extension}"

    def _clear_logs(self) -> None:
        if not messagebox.askyesno("Clear logs", "Delete all log rows?", parent=self):
            return
        self.app.db.clear_logs()
        self.refresh()
