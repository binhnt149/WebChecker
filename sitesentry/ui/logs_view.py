from __future__ import annotations

import csv
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk


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
        self.status_filter = tk.StringVar(value="all")
        ctk.CTkOptionMenu(toolbar, values=["all", "up", "down"], variable=self.status_filter, command=lambda _: self.refresh()).grid(row=0, column=1, padx=6)
        ctk.CTkButton(toolbar, text="Export CSV", command=self._export_csv, width=100).grid(row=0, column=2, padx=6)
        ctk.CTkButton(toolbar, text="Clear", command=self._clear_logs, width=80, fg_color="#991b1b", hover_color="#7f1d1d").grid(row=0, column=3, padx=6)
        ctk.CTkButton(toolbar, text="Refresh", command=self.refresh, width=90).grid(row=0, column=4, padx=(6, 0))

        self.table = ctk.CTkScrollableFrame(self, corner_radius=8)
        self.table.grid(row=1, column=0, padx=20, pady=(8, 20), sticky="nsew")
        self.table.grid_columnconfigure(0, weight=1)
        self.refresh()

    def refresh(self) -> None:
        for child in self.table.winfo_children():
            child.destroy()
        logs = self.app.db.list_logs(limit=500, status_filter=self.status_filter.get())
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

    def _export_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Export logs",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        logs = self.app.db.list_logs(limit=100000, status_filter=self.status_filter.get())
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
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
                ],
            )
            writer.writeheader()
            writer.writerows(logs)

    def _clear_logs(self) -> None:
        if not messagebox.askyesno("Clear logs", "Delete all log rows?", parent=self):
            return
        self.app.db.clear_logs()
        self.refresh()
