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
from .vi import CLASSIFICATIONS, PHASES, STATES, label, message as vi_message
from .theme import BAD, BLUE, CANVAS, GOOD, MUTED, TEXT, WARNING, color, fit_wrap, metric, table_scrollers


TYPE_LABELS = {"simple_web": "Web", "auth_web": "Auth Web", "api": "API"}


def summarize_monitor_states(monitors: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"up": 0, "down": 0, "unknown": 0, "paused": 0}
    for item in monitors:
        state = item.get("last_status") if item.get("enabled") else "paused"
        counts[state if state in counts else "unknown"] += 1
    return counts


class DashboardView(ctk.CTkFrame):
    def __init__(self, master: Any, app: Any) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._busy = False
        self._refresh_again = False
        self._monitors: dict[int, dict[str, Any]] = {}
        self._dialog: MonitorDialog | None = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=20, pady=(20, 12), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Tổng quan", font=ctk.CTkFont(size=23, weight="bold")).grid(row=0, column=0, sticky="w")
        for column, (label, command, width) in enumerate([
            ('Nhập Excel', self._import_excel, 104), ('Mẫu Excel', self._save_template, 84),
            ('Kiểm tra tất cả', self.app.scheduler.run_all_now, 82), ('Thêm monitor', self._add_monitor, 112),
        ], start=1):
            ctk.CTkButton(header, text=label, command=command, width=width).grid(row=0, column=column, padx=(8, 0))
        metrics = ctk.CTkFrame(self, fg_color="transparent")
        metrics.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="ew")
        self.metrics = [metric(metrics, title, column, tone) for column, (title, tone) in enumerate([
            ('Monitor', TEXT), ("UP", GOOD), ("DOWN", BAD), ('Chưa rõ', MUTED), ('Phản hồi TB', BLUE),
        ])]
        chart = ctk.CTkFrame(self, fg_color="transparent")
        chart.grid(row=2, column=0, padx=20, pady=(0, 8), sticky="ew")
        chart.grid_columnconfigure(0, weight=1)
        self.chart_title = ctk.CTkLabel(chart, text="Tình hình hoạt động hiện tại", anchor="w", font=ctk.CTkFont(size=13, weight="bold"))
        self.chart_title.grid(row=0, column=0, sticky="ew")
        self.internet_label = ctk.CTkLabel(chart, text="Internet: chưa cấu hình", anchor="e", text_color=MUTED)
        self.internet_label.grid(row=0, column=1, padx=(12, 0), sticky="e")
        self.chart_canvas = tk.Canvas(chart, height=20, highlightthickness=0, bd=0)
        self.chart_canvas.grid(row=1, column=0, pady=(4, 0), sticky="ew")
        self.chart_legend = ctk.CTkLabel(chart, text="Chưa có monitor", anchor="w", text_color=MUTED)
        self.chart_legend.grid(row=2, column=0, sticky="ew")
        self.chart_canvas.bind("<Configure>", lambda _: self._render_chart())
        filters = ctk.CTkFrame(self, fg_color="transparent")
        filters.grid(row=3, column=0, padx=20, pady=(0, 12), sticky="ew")
        filters.grid_columnconfigure(0, weight=1)
        self.search = tk.StringVar()
        self.status = tk.StringVar(value='Mọi trạng thái')
        self.monitor_type = tk.StringVar(value='Mọi loại')
        self.category = tk.StringVar(value='Mọi nhóm lỗi')
        self.classification = tk.StringVar(value='Mọi phân loại')
        bind_focus_on_click(ctk.CTkEntry(filters, textvariable=self.search, placeholder_text='Tìm monitor, URL hoặc lỗi', height=32)).grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ctk.CTkOptionMenu(filters, values=['Mọi trạng thái', "UP", "DOWN", 'Chưa rõ', 'Tạm dừng'], variable=self.status, width=122, command=lambda _: self._render()).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkOptionMenu(filters, values=['Mọi loại', *TYPE_LABELS.values()], variable=self.monitor_type, width=120, command=lambda _: self._render()).grid(row=0, column=2, padx=(0, 8))
        ctk.CTkButton(filters, text='Làm mới', width=82, command=self.refresh).grid(row=0, column=3)
        ctk.CTkOptionMenu(filters, values=['Mọi nhóm lỗi', *ERROR_TYPES.values()], variable=self.category, width=250, command=lambda _: self._render()).grid(row=1, column=0, pady=(8, 0), sticky="w")
        ctk.CTkOptionMenu(filters, values=['Mọi phân loại', *CLASSIFICATIONS.values()], variable=self.classification, width=180, command=lambda _: self._render()).grid(row=1, column=1, columnspan=2, padx=8, pady=(8, 0), sticky="w")
        self.search.trace_add("write", lambda *_: self._render())
        table_frame = ctk.CTkFrame(self, fg_color="transparent")
        table_frame.grid(row=4, column=0, padx=20, sticky="nsew")
        columns = ("name", "type", "status", "error", "classification", "reason", "phase", "response", "checked", "url")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        for column, title, width in zip(columns, ['Monitor', 'Loại', 'Trạng thái', 'Nhóm lỗi', 'Phân loại', 'Mã lý do', 'Giai đoạn', 'Phản hồi', 'Kiểm tra gần nhất', "URL"], [210, 90, 86, 250, 130, 160, 120, 100, 170, 320]):
            self.table.heading(column, text=title)
            self.table.column(column, width=width, minwidth=70, stretch=column == "name")
        table_scrollers(table_frame, self.table)
        self.table.bind("<<TreeviewSelect>>", lambda _: self._selection_changed())
        self.table.bind("<Double-1>", lambda _: self._edit_selected())
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=5, column=0, padx=20, pady=(12, 16), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        self.selection_label = ctk.CTkLabel(footer, text='Chưa chọn monitor', anchor="w", text_color=MUTED, wraplength=280, justify="left")
        self.selection_label.grid(row=0, column=0, sticky="ew")
        actions = ctk.CTkFrame(footer, fg_color="transparent")
        actions.grid(row=0, column=1)
        self.actions = []
        for label, command in [('Kiểm tra', self._run_selected), ('Sửa', self._edit_selected), ('Tạm dừng', self._toggle_selected), ('Xóa', self._delete_selected)]:
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
        def done(data: tuple[list[dict[str, Any]], str, dict[str, Any] | None, list[dict[str, Any]]]) -> None:
            monitors, profile, profile_data, events = data
            self._busy = False
            self._monitors = {item["id"]: item for item in monitors}
            valid_profile = bool(profile_data and profile_data.get("enabled") and profile_data.get("scope") == "internet" and profile_data.get("targets"))
            latest = events[0] if valid_profile and events and events[0]["profile"] == profile else None
            internet_text = "chưa cấu hình" if not profile else "profile không khả dụng" if not valid_profile else "chưa kiểm tra" if not latest else {"reachable": "điểm tham chiếu phản hồi", "reference_unreachable": "điểm tham chiếu không phản hồi", "network_offline": "mạng máy giám sát không khả dụng"}.get(latest["state"], "chưa xác định")
            when = f" ({(latest['last_seen_at'] or latest['checked_at']).replace('T', ' ')})" if latest else ""
            self.internet_label.configure(text=f"Internet: {internet_text}{when}", text_color=BAD if latest and latest["state"] != "reachable" else MUTED)
            responses = [item["last_response_ms"] for item in monitors if item["last_response_ms"] is not None]
            counts = summarize_monitor_states(monitors)
            values = [len(monitors), counts["up"], counts["down"], counts["unknown"],
                      f"{round(sum(responses) / len(responses))} ms" if responses else "-"]
            for label, value in zip(self.metrics, values):
                label.configure(text=str(value))
            self._render_chart()
            self._render()
            if self._refresh_again:
                self._refresh_again = False
                self.refresh()
        def failed(message: str) -> None:
            self._busy = False
            self.detail.configure(text=message)
        def work() -> tuple[list[dict[str, Any]], str, dict[str, Any] | None, list[dict[str, Any]]]:
            profile = self.app.db.get_setting("internet_profile", "")
            return self.app.db.list_monitors(include_disabled=True), profile, self.app.db.get_network_profile(profile) if profile else None, self.app.db.list_network_events(limit=1)
        run_background(self.app, self, work, done, failed)

    def _render_chart(self) -> None:
        if not self.winfo_exists():
            return
        counts = summarize_monitor_states(list(self._monitors.values()))
        total = sum(counts.values())
        self.chart_canvas.configure(bg=color(CANVAS))
        self.chart_canvas.delete("all")
        width = max(1, self.chart_canvas.winfo_width())
        x = 0.0
        for key, tone in (("up", GOOD), ("down", BAD), ("unknown", WARNING), ("paused", MUTED)):
            next_x = x + width * counts[key] / total if total else x
            if next_x > x:
                self.chart_canvas.create_rectangle(x, 2, next_x, 18, fill=color(tone), outline="")
            x = next_x
        self.chart_legend.configure(text=(f"Hoạt động: {counts['up']}   •   Sự cố: {counts['down']}   •   Chưa rõ: {counts['unknown']}   •   Tạm dừng: {counts['paused']}" if total else "Chưa có monitor để thống kê"))

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
            shown_state = state if monitor["enabled"] else "paused"
            if self.status.get() != 'Mọi trạng thái' and self.status.get() != label(STATES, shown_state):
                continue
            if self.monitor_type.get() not in {'Mọi loại', type_label}:
                continue
            category = error_label(monitor.get("last_error_type", "")) if state == "down" else "-"
            if self.category.get() != 'Mọi nhóm lỗi' and category != self.category.get():
                continue
            if self.classification.get() != 'Mọi phân loại' and label(CLASSIFICATIONS, monitor.get("last_classification_state", "")) != self.classification.get():
                continue
            if query not in f"{monitor['name']} {monitor['url']} {category} {monitor['last_error']}".casefold():
                continue
            iid = str(monitor["id"])
            wanted.add(iid)
            checked = str(monitor.get("last_checked_at") or 'Chưa kiểm tra').replace("T", " ")
            response = f"{monitor['last_response_ms']} ms" if monitor["last_response_ms"] is not None else "-"
            values = (sanitize(monitor["name"], monitor), type_label, label(STATES, shown_state), category, label(CLASSIFICATIONS, monitor.get("last_classification_state", "")), monitor.get("last_reason_code", ""), label(PHASES, monitor.get("last_phase", "")), response, checked, sanitize(monitor["url"], monitor))
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
        self.actions[2].configure(text='Tạm dừng' if monitor and monitor["enabled"] else 'Bật')
        if monitor:
            self.selection_label.configure(text=sanitize(str(monitor["name"]), monitor))
            detail = monitor["last_error"] if monitor["last_status"] == "down" else monitor["url"]
            if monitor.get("last_classification_state") == "legacy" and monitor["last_status"] == "down":
                detail = 'Chi tiết chẩn đoán cũ được ẩn'
            self.detail.configure(text=vi_message(sanitize(detail, monitor)))
        else:
            self.selection_label.configure(text=f"{len(self.table.get_children())} monitor")
            self.detail.configure(text='Chưa có monitor' if not self._monitors else "")

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
        if monitor and messagebox.askyesno('Xóa monitor', f"Xóa {monitor['name']}?", parent=self):
            self.app.db.delete_monitor(monitor["id"])
            self.app.scheduler.sync_jobs()
            self.refresh()

    def _save_template(self) -> None:
        path = filedialog.asksaveasfilename(parent=self, title='Mẫu monitor', initialfile="sitesentry_monitors_template.xlsx", defaultextension=".xlsx", filetypes=[('Tệp Excel', "*.xlsx")])
        if path:
            run_background(self.app, self, lambda: create_monitor_template(path), lambda _: messagebox.showinfo('Mẫu Excel', 'Đã xuất file mẫu.', parent=self))

    def _import_excel(self) -> None:
        path = filedialog.askopenfilename(parent=self, title='Nhập danh sách monitor', filetypes=[('Tệp Excel', "*.xlsx")])
        if not path:
            return
        def work():
            result = import_monitors_from_excel(self.app.db, path)
            self.app.scheduler.sync_jobs()
            return result
        def done(result):
            self.refresh()
            self.app._update_status_text()
            summary = f"Đã tạo: {result.created}\nĐã cập nhật: {result.updated}\nĐã bỏ qua: {result.skipped}"
            if result.errors:
                summary += "\nLỗi:\n" + "\n".join(f"- {vi_message(error)}" for error in result.errors[:12])
                if len(result.errors) > 12:
                    summary += f"\n- và {len(result.errors) - 12} lỗi khác"
            (messagebox.showinfo if result.ok else messagebox.showwarning)('Nhập Excel', summary, parent=self)
        run_background(self.app, self, work, done)
