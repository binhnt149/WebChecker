from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from sitesentry.core.excel_importer import create_monitor_template, import_monitors_from_excel

from .monitor_dialog import MonitorDialog


STATUS_COLORS = {
    "up": "#16a34a",
    "down": "#dc2626",
    "unknown": "#64748b",
}


class DashboardView(ctk.CTkFrame):
    def __init__(self, master: Any, app: Any) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 8))
        self.header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.header, text="Dashboard", font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(self.header, text="Add Monitor", command=self._add_monitor, width=120).grid(row=0, column=1, padx=6)
        ctk.CTkButton(self.header, text="Import Excel", command=self._import_excel, width=110).grid(row=0, column=2, padx=6)
        ctk.CTkButton(self.header, text="Template", command=self._save_template, width=90).grid(row=0, column=3, padx=6)
        ctk.CTkButton(self.header, text="Run All", command=self.app.scheduler.run_all_now, width=90).grid(row=0, column=4, padx=6)
        ctk.CTkButton(self.header, text="Refresh", command=self.refresh, width=90).grid(row=0, column=5, padx=(6, 0))

        self.kpi_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.kpi_frame.grid(row=1, column=0, padx=20, pady=8, sticky="ew")
        for column in range(5):
            self.kpi_frame.grid_columnconfigure(column, weight=1)

        self.list_frame = ctk.CTkScrollableFrame(self, corner_radius=8)
        self.list_frame.grid(row=2, column=0, padx=20, pady=(8, 20), sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)
        self.refresh()

    def refresh(self) -> None:
        monitors = self.app.db.list_monitors(include_disabled=True)
        for child in self.kpi_frame.winfo_children():
            child.destroy()
        for child in self.list_frame.winfo_children():
            child.destroy()

        total = len(monitors)
        up = sum(1 for monitor in monitors if monitor.get("last_status") == "up")
        down = sum(1 for monitor in monitors if monitor.get("last_status") == "down")
        unknown = sum(1 for monitor in monitors if monitor.get("last_status") == "unknown")
        response_values = [monitor.get("last_response_ms") for monitor in monitors if monitor.get("last_response_ms") is not None]
        avg_ms = int(sum(response_values) / len(response_values)) if response_values else 0

        self._kpi("Total", str(total), 0)
        self._kpi("Up", str(up), 1, "#16a34a")
        self._kpi("Down", str(down), 2, "#dc2626")
        self._kpi("Unknown", str(unknown), 3, "#64748b")
        self._kpi("Avg ms", str(avg_ms), 4, "#2563eb")

        if not monitors:
            self._empty_state()
            return

        for row, monitor in enumerate(monitors):
            self._monitor_row(row, monitor)

    def _kpi(self, label: str, value: str, column: int, color: str | None = None) -> None:
        card = ctk.CTkFrame(self.kpi_frame, corner_radius=8)
        card.grid(row=0, column=column, padx=6, sticky="ew")
        ctk.CTkLabel(card, text=label, text_color="#94a3b8").pack(anchor="w", padx=14, pady=(10, 0))
        ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=26, weight="bold"), text_color=color).pack(anchor="w", padx=14, pady=(0, 10))

    def _empty_state(self) -> None:
        frame = ctk.CTkFrame(self.list_frame, corner_radius=8)
        frame.grid(row=0, column=0, padx=8, pady=18, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text="No monitors configured", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, padx=18, pady=(18, 4), sticky="w")
        ctk.CTkLabel(
            frame,
            text="Dashboard is ready. Add a monitor to start collecting status, response time, logs, and alerts.",
            text_color="#94a3b8",
            wraplength=680,
            justify="left",
        ).grid(row=1, column=0, padx=18, pady=(0, 12), sticky="w")
        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.grid(row=2, column=0, padx=12, pady=(0, 18), sticky="w")
        ctk.CTkButton(actions, text="Add Monitor", command=self._add_monitor, width=120).grid(row=0, column=0, padx=6)
        ctk.CTkButton(actions, text="Import Excel", command=self._import_excel, width=120).grid(row=0, column=1, padx=6)
        ctk.CTkButton(actions, text="Template", command=self._save_template, width=100, fg_color="#475569").grid(row=0, column=2, padx=6)

    def _monitor_row(self, row: int, monitor: dict[str, Any]) -> None:
        frame = ctk.CTkFrame(self.list_frame, corner_radius=8)
        frame.grid(row=row, column=0, padx=4, pady=6, sticky="ew")
        frame.grid_columnconfigure(1, weight=1)

        status = monitor.get("last_status") or "unknown"
        status_color = STATUS_COLORS.get(status, "#64748b")
        dot = ctk.CTkLabel(frame, text="●", text_color=status_color, font=ctk.CTkFont(size=18))
        dot.grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=10)

        name = monitor.get("name") or "Untitled"
        ctk.CTkLabel(frame, text=name, font=ctk.CTkFont(size=15, weight="bold")).grid(row=0, column=1, sticky="w", pady=(10, 0))
        meta = self._meta_text(monitor)
        ctk.CTkLabel(frame, text=meta, text_color="#94a3b8").grid(row=1, column=1, sticky="w", pady=(0, 10))

        enabled_text = "Disable" if monitor.get("enabled") else "Enable"
        ctk.CTkButton(frame, text="Run", width=66, command=lambda mid=monitor["id"]: self.app.scheduler.run_now(int(mid))).grid(row=0, column=2, rowspan=2, padx=4)
        ctk.CTkButton(frame, text="Edit", width=66, command=lambda m=monitor: self._edit_monitor(m)).grid(row=0, column=3, rowspan=2, padx=4)
        ctk.CTkButton(frame, text=enabled_text, width=76, command=lambda m=monitor: self._toggle_monitor(m)).grid(row=0, column=4, rowspan=2, padx=4)
        ctk.CTkButton(frame, text="Delete", width=76, fg_color="#991b1b", hover_color="#7f1d1d", command=lambda m=monitor: self._delete_monitor(m)).grid(row=0, column=5, rowspan=2, padx=(4, 12))

    def _meta_text(self, monitor: dict[str, Any]) -> str:
        pieces = [
            str(monitor.get("monitor_type") or "web"),
            str(monitor.get("url") or ""),
            f"every {monitor.get('interval_seconds') or 60}s",
        ]
        if monitor.get("last_checked_at"):
            pieces.append(f"last {monitor.get('last_checked_at')}")
        if monitor.get("last_response_ms") is not None:
            pieces.append(f"{monitor.get('last_response_ms')} ms")
        if monitor.get("last_error") and monitor.get("last_status") == "down":
            pieces.append(str(monitor.get("last_error")))
        return "  |  ".join(pieces)

    def _add_monitor(self) -> None:
        MonitorDialog(self.app, on_save=self.refresh)

    def _save_template(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save monitor template",
            initialfile="sitesentry_monitors_template.xlsx",
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
        )
        if not path:
            return
        try:
            create_monitor_template(path)
        except Exception as exc:
            messagebox.showerror("Template", f"Could not save template:\n{exc}", parent=self)
            return
        messagebox.showinfo("Template", f"Template saved:\n{path}", parent=self)

    def _import_excel(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Import monitors from Excel",
            filetypes=[("Excel workbook", "*.xlsx"), ("All files", "*.*")],
        )
        if not path:
            return
        self._set_busy(True)

        def worker() -> None:
            try:
                result = import_monitors_from_excel(self.app.db, path)
                self.app.scheduler.sync_jobs()
            except Exception as exc:
                self.after(0, lambda: self._finish_import_error(exc))
                return
            self.after(0, lambda: self._finish_import(result.summary(), result.ok))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_import(self, summary: str, ok: bool) -> None:
        self._set_busy(False)
        self.refresh()
        self.app._update_status_text()
        if ok:
            messagebox.showinfo("Import Excel", summary, parent=self)
        else:
            messagebox.showwarning("Import Excel", summary, parent=self)

    def _finish_import_error(self, exc: Exception) -> None:
        self._set_busy(False)
        messagebox.showerror("Import Excel", f"Import failed:\n{exc}", parent=self)

    def _set_busy(self, busy: bool) -> None:
        cursor = "watch" if busy else ""
        self.configure(cursor=cursor)
        self.app.configure(cursor=cursor)

    def _edit_monitor(self, monitor: dict[str, Any]) -> None:
        fresh = self.app.db.get_monitor(int(monitor["id"])) or monitor
        MonitorDialog(self.app, monitor=fresh, on_save=self.refresh)

    def _toggle_monitor(self, monitor: dict[str, Any]) -> None:
        self.app.db.set_monitor_enabled(int(monitor["id"]), not bool(monitor.get("enabled")))
        self.app.scheduler.sync_jobs()
        self.refresh()

    def _delete_monitor(self, monitor: dict[str, Any]) -> None:
        if not messagebox.askyesno("Delete monitor", f"Delete {monitor.get('name')}?", parent=self):
            return
        self.app.db.delete_monitor(int(monitor["id"]))
        self.app.scheduler.sync_jobs()
        self.refresh()
