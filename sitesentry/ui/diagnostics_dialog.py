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
from .vi import message as vi_message
from .focus import bind_focus_on_click
from .theme import polish, table_scrollers
from .vi import PHASES as PHASE_LABELS, label

SCOPES = {"internet": "Internet", "intranet_vpn": "Nội bộ / VPN", "custom": "Tùy chỉnh"}


class MonitorDiagnosticsDialog(ctk.CTkToplevel):
    def __init__(self, master: Any, profile: str, rules: str, on_save: Callable[[str, str], None]) -> None:
        super().__init__(master)
        self.app = master.app
        self.on_save = on_save
        self.rules = validate_rules(rules)
        self.title('Chẩn đoán monitor')
        self.geometry("760x540")
        self.minsize(650, 450)
        self.transient(master)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=18, pady=12, sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(top, text='Profile mạng').grid(row=0, column=0, padx=(0, 10))
        self.profile_var = tk.StringVar(value=profile or "Chưa chọn")
        self.profile_menu = ctk.CTkOptionMenu(top, variable=self.profile_var, values=["Chưa chọn"])
        self.profile_menu.grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(top, text='Quản lý profile', width=140, command=self._manage_profiles).grid(row=0, column=2, padx=(10, 0))
        ctk.CTkLabel(self, text='Quy tắc xét bằng chứng đã cấu hình; sự cố chưa phân loại không gửi email.', anchor="w", wraplength=680, justify="left").grid(row=1, column=0, padx=18, sticky="ew")
        table_frame = ctk.CTkFrame(self, fg_color="transparent")
        table_frame.grid(row=2, column=0, padx=18, pady=10, sticky="nsew")
        self.table = ttk.Treeview(table_frame, columns=("id", "phase", "category", "priority", "enabled"), show="headings", selectmode="browse")
        for column, title, width in [("id", 'Quy tắc', 160), ("phase", 'Giai đoạn', 120), ("category", 'Nhóm lỗi', 180), ("priority", 'Ưu tiên', 80), ("enabled", 'Đang bật', 75)]:
            self.table.heading(column, text=title)
            self.table.column(column, width=width, minwidth=60)
        table_scrollers(table_frame, self.table)
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=3, column=0, padx=18, pady=6, sticky="ew")
        for label, command in [('Thêm quy tắc', lambda: self._edit_rule(None)), ('Sửa', self._edit_selected), ('Bật / tắt', self._toggle), ('Xóa', self._remove)]:
            ctk.CTkButton(actions, text=label, width=100, command=command).pack(side="left", padx=(0, 6))
        ctk.CTkButton(actions, text='Lưu', width=90, command=self._save).pack(side="right")
        ctk.CTkButton(actions, text='Hủy', width=90, command=self.destroy).pack(side="right", padx=6)
        self._refresh_profiles()
        self._render()
        polish(self)

    def _refresh_profiles(self) -> None:
        values = ["Chưa chọn", *(profile["name"] for profile in self.app.db.list_network_profiles())]
        self.profile_menu.configure(values=values)
        if self.profile_var.get() not in values:
            self.profile_var.set("Chưa chọn")

    def _render(self) -> None:
        self.table.delete(*self.table.get_children())
        for item in self.rules:
            self.table.insert("", "end", iid=item["id"], values=(item["id"], label(PHASE_LABELS, item["phase"]), label(ERROR_TYPES, item["result"]["error_type"]), item["priority"], 'Có' if item["enabled"] else 'Không'))

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
            profile = "" if self.profile_var.get() == "Chưa chọn" else self.profile_var.get()
            if profile and not self.app.db.get_network_profile(profile):
                raise ValueError('Profile mạng đã chọn không còn tồn tại')
            self.on_save(profile, json.dumps(self.rules, ensure_ascii=False))
        except ValueError as exc:
            messagebox.showerror('Chẩn đoán', vi_message(exc), parent=self)
            return
        self.destroy()


class DiagnosticRuleDialog(ctk.CTkToplevel):
    def __init__(self, master: Any, item: dict[str, Any] | None, on_save: Callable[[dict[str, Any]], None]) -> None:
        super().__init__(master)
        self.on_save = on_save
        self.title('Quy tắc chẩn đoán')
        self.geometry("700x640")
        self.transient(master)
        item = item or {"id": "api-failure", "enabled": True, "priority": 100, "phase": "response", "conditions": [{"source": "json", "path": "success", "operator": "equals", "value": False}], "result": {"error_type": "assertion_failed", "reason_code": "business_rule_match"}}
        self.id_var = tk.StringVar(value=item["id"])
        self.priority_var = tk.StringVar(value=str(item["priority"]))
        self.phase_var = tk.StringVar(value=PHASE_LABELS[item["phase"]])
        self.enabled_var = tk.BooleanVar(value=item["enabled"])
        self.category_var = tk.StringVar(value=ERROR_TYPES[item["result"]["error_type"]])
        self.reason_var = tk.StringVar(value=item["result"].get("reason_code", ""))
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        form = ctk.CTkScrollableFrame(self)
        form.grid(row=0, column=0, padx=16, pady=12, sticky="nsew")
        form.grid_columnconfigure((0, 1), weight=1)
        for row, (label, variable) in enumerate([('Mã quy tắc', self.id_var), ('Ưu tiên', self.priority_var), ('Mã lý do', self.reason_var)]):
            ctk.CTkLabel(form, text=label).grid(row=row * 2, column=0, padx=8, sticky="w")
            bind_focus_on_click(ctk.CTkEntry(form, textvariable=variable)).grid(row=row * 2 + 1, column=0, padx=8, pady=(0, 8), sticky="ew")
        ctk.CTkLabel(form, text='Giai đoạn').grid(row=0, column=1, padx=8, sticky="w")
        ctk.CTkOptionMenu(form, variable=self.phase_var, values=[PHASE_LABELS[phase] for phase in sorted(PHASES)]).grid(row=1, column=1, padx=8, sticky="ew")
        ctk.CTkLabel(form, text='Nhóm lỗi').grid(row=2, column=1, padx=8, sticky="w")
        ctk.CTkOptionMenu(form, variable=self.category_var, values=[name for code, name in ERROR_TYPES.items() if code not in {"unknown", "network_offline"}]).grid(row=3, column=1, padx=8, sticky="ew")
        ctk.CTkCheckBox(form, text='Đang bật', variable=self.enabled_var).grid(row=5, column=1, padx=8, sticky="w")
        ctk.CTkLabel(form, text='Điều kiện JSON (phải khớp tất cả)').grid(row=6, column=0, columnspan=2, padx=8, pady=(12, 0), sticky="w")
        self.conditions = bind_focus_on_click(ctk.CTkTextbox(form, height=170))
        self.conditions.grid(row=7, column=0, columnspan=2, padx=8, pady=8, sticky="ew")
        self.conditions.insert("1.0", json.dumps(item["conditions"], ensure_ascii=False, indent=2))
        ctk.CTkLabel(form, text='Nguồn: http_status, visible_text, json. Giá trị JSON giữ nguyên kiểu; xem checker-spec.md mục 7.', wraplength=600, justify="left").grid(row=8, column=0, columnspan=2, padx=8, sticky="w")
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="e")
        ctk.CTkButton(actions, text='Hủy', width=90, command=self.destroy).pack(side="left", padx=6)
        ctk.CTkButton(actions, text='Lưu quy tắc', width=100, command=self._save).pack(side="left")
        polish(self)

    def _save(self) -> None:
        try:
            payload = {"id": self.id_var.get().strip(), "enabled": self.enabled_var.get(), "priority": int(self.priority_var.get()), "phase": next(code for code in PHASES if PHASE_LABELS[code] == self.phase_var.get()), "conditions": json.loads(self.conditions.get("1.0", "end-1c")), "result": {"error_type": next(code for code, name in ERROR_TYPES.items() if name == self.category_var.get()), "reason_code": self.reason_var.get().strip()}}
            validate_rules([payload])
            self.on_save(payload)
        except (ValueError, TypeError) as exc:
            messagebox.showerror('Quy tắc chẩn đoán', vi_message(exc), parent=self)
            return
        self.destroy()


class NetworkProfilesDialog(ctk.CTkToplevel):
    def __init__(self, master: Any, app: Any, on_change: Callable[[], None]) -> None:
        super().__init__(master)
        self.app, self.on_change = app, on_change
        self.title('Các profile mạng')
        self.geometry("680x440")
        self.transient(master)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self, text='Kiểm tra tham chiếu chỉ xác minh địa chỉ đã cấu hình.', wraplength=600).grid(row=0, column=0, padx=16, pady=12, sticky="w")
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=1, column=0, padx=16, sticky="nsew")
        self.table = ttk.Treeview(frame, columns=("name", "scope", "targets", "enabled"), show="headings", selectmode="browse")
        for column, title, width in [("name", 'Tên', 190), ("scope", 'Phạm vi', 160), ("targets", 'Điểm tham chiếu', 90), ("enabled", 'Đang bật', 90)]:
            self.table.heading(column, text=title)
            self.table.column(column, width=width)
        table_scrollers(frame, self.table)
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=2, column=0, padx=16, pady=12, sticky="ew")
        ctk.CTkButton(actions, text='Thêm', width=90, command=lambda: self._edit_profile(None)).pack(side="left", padx=4)
        ctk.CTkButton(actions, text='Sửa', width=90, command=self._edit_selected).pack(side="left", padx=4)
        ctk.CTkButton(actions, text='Xóa', width=90, command=self._delete).pack(side="left", padx=4)
        ctk.CTkButton(actions, text='Đóng', width=90, command=self.destroy).pack(side="right")
        self._refresh()
        polish(self)

    def _refresh(self) -> None:
        self.table.delete(*self.table.get_children())
        for item in self.app.db.list_network_profiles():
            self.table.insert("", "end", iid=item["name"], values=(item["name"], label(SCOPES, item["scope"]), len(item["targets"]), 'Có' if item["enabled"] else 'Không'))
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
            messagebox.showerror('Các profile mạng', vi_message(exc), parent=self)
        else:
            self._refresh()


class NetworkProfileEditor(ctk.CTkToplevel):
    def __init__(self, master: Any, app: Any, profile: dict[str, Any] | None, on_save: Callable[[], None]) -> None:
        super().__init__(master)
        self.app, self.original, self.on_save = app, profile, on_save
        self.title('Profile mạng')
        self.geometry("700x520")
        self.transient(master)
        profile = profile or {"name": "", "scope": "custom", "enabled": True, "targets": []}
        self.name_var = tk.StringVar(value=profile["name"])
        self.scope_var = tk.StringVar(value=SCOPES[profile["scope"]])
        self.enabled_var = tk.BooleanVar(value=profile["enabled"])
        self.target_vars = []
        self.grid_columnconfigure(0, weight=1)
        form = ctk.CTkFrame(self)
        form.grid(row=0, column=0, padx=16, pady=12, sticky="nsew")
        form.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(form, text='Tên profile *').grid(row=0, column=0, padx=8, sticky="w")
        name = bind_focus_on_click(ctk.CTkEntry(form, textvariable=self.name_var))
        name.grid(row=1, column=0, padx=8, sticky="ew")
        if self.original:
            name.configure(state="disabled")
        ctk.CTkOptionMenu(form, variable=self.scope_var, values=list(SCOPES.values())).grid(row=1, column=1, padx=8)
        ctk.CTkCheckBox(form, text='Đang bật', variable=self.enabled_var).grid(row=2, column=0, padx=8, pady=8, sticky="w")
        for index in range(2):
            target = profile["targets"][index] if index < len(profile["targets"]) else {}
            url, method, timeout = tk.StringVar(value=target.get("url", "")), tk.StringVar(value=target.get("method", "HEAD")), tk.StringVar(value=str(target.get("timeout_seconds", 2)))
            self.target_vars.append((url, method, timeout))
            ctk.CTkLabel(form, text=f"URL tham chiếu {index + 1}").grid(row=3 + index * 2, column=0, padx=8, sticky="w")
            bind_focus_on_click(ctk.CTkEntry(form, textvariable=url, placeholder_text="https://reference.example/health")).grid(row=4 + index * 2, column=0, padx=8, pady=6, sticky="ew")
            ctk.CTkOptionMenu(form, variable=method, values=["HEAD", "GET"], width=90).grid(row=4 + index * 2, column=1, padx=6)
            bind_focus_on_click(ctk.CTkEntry(form, textvariable=timeout, width=60)).grid(row=4 + index * 2, column=2, padx=6)
        self.status = ctk.CTkLabel(form, text='Kiểm tra không gửi thông tin đăng nhập monitor và chỉ xác minh điểm tham chiếu.', wraplength=620, justify="left")
        self.status.grid(row=7, column=0, columnspan=3, padx=8, pady=14, sticky="w")
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=1, column=0, padx=16, pady=10, sticky="ew")
        ctk.CTkButton(actions, text='Kiểm tra profile', command=self._test).pack(side="left")
        ctk.CTkButton(actions, text='Lưu', width=90, command=self._save).pack(side="right")
        ctk.CTkButton(actions, text='Hủy', width=90, command=self.destroy).pack(side="right", padx=8)
        polish(self)

    def _payload(self) -> dict[str, Any]:
        targets = [{"url": url.get().strip(), "method": method.get(), "timeout_seconds": timeout.get()} for url, method, timeout in self.target_vars if url.get().strip()]
        return validate_profile({"name": self.name_var.get(), "scope": next((key for key, value in SCOPES.items() if value == self.scope_var.get()), ""), "enabled": self.enabled_var.get(), "targets": targets})

    def _save(self) -> None:
        try:
            payload = self._payload()
            if not self.original and self.app.db.get_network_profile(payload["name"]):
                raise ValueError('Đã có profile cùng tên')
            self.app.db.save_network_profile(payload)
            self.on_save()
        except ValueError as exc:
            messagebox.showerror('Profile mạng', vi_message(exc), parent=self)
            return
        self.destroy()

    def _test(self) -> None:
        try:
            profile = self._payload()
        except ValueError as exc:
            messagebox.showerror('Profile mạng', vi_message(exc), parent=self)
            return
        self.status.configure(text='Đang kiểm tra điểm tham chiếu...')
        run_background(self.app, self, lambda: asyncio.run(self.app.checker.network_diagnostics.probe(profile)), lambda result: self.status.configure(text=json.dumps(result, ensure_ascii=False)), lambda error: self.status.configure(text=error))
