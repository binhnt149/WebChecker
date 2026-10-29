from __future__ import annotations

import calendar
from datetime import date, datetime, time
import tkinter as tk
from typing import Any

import customtkinter as ctk
from .theme import polish


class DateTimePicker(ctk.CTkFrame):
    def __init__(self, master: Any, label: str, value: datetime | None = None, end_of_day: bool = False) -> None:
        super().__init__(master, fg_color="transparent")
        self.value = value
        self.end_of_day = end_of_day
        self._popup: DateTimeDialog | None = None
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=label).grid(row=0, column=0, padx=(0, 8))
        self.button = ctk.CTkButton(self, text="", command=self._open, width=178)
        self.button.grid(row=0, column=1, sticky="ew")
        self.set(value)

    def get(self) -> datetime | None:
        return self.value

    def set(self, value: datetime | None) -> None:
        self.value = value
        self.button.configure(text=value.strftime("%Y-%m-%d %H:%M:%S") if value else 'Mọi ngày')

    def _open(self) -> None:
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.lift()
            return
        self._popup = DateTimeDialog(self)


class DateTimeDialog(ctk.CTkToplevel):
    def __init__(self, picker: DateTimePicker) -> None:
        super().__init__(picker)
        self.picker = picker
        self.title('Ngày và giờ')
        self.geometry("390x410")
        self.resizable(False, False)
        self.transient(picker.winfo_toplevel())
        initial = picker.get() or datetime.combine(date.today(), time(23, 59, 59) if picker.end_of_day else time.min)
        self.selected = initial.date()
        self.year = tk.StringVar(value=str(initial.year))
        self.month = tk.StringVar(value=str(initial.month))
        self.hour = tk.StringVar(value=f"{initial.hour:02d}")
        self.minute = tk.StringVar(value=f"{initial.minute:02d}")
        self.second = tk.StringVar(value=f"{initial.second:02d}")
        self.grid_columnconfigure(0, weight=1)
        navigation = ctk.CTkFrame(self, fg_color="transparent")
        navigation.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        navigation.grid_columnconfigure(2, weight=1)
        ctk.CTkButton(navigation, text="<", width=30, command=lambda: self._shift(-1)).grid(row=0, column=0, padx=(0, 8))
        self._spin(navigation, self.month, 1, 12, self._render).grid(row=0, column=1)
        self._spin(navigation, self.year, 1, 9999, self._render, width=6).grid(row=0, column=2)
        ctk.CTkButton(navigation, text=">", width=30, command=lambda: self._shift(1)).grid(row=0, column=3, padx=(8, 0))
        self.days = ctk.CTkFrame(self, fg_color="transparent")
        self.days.grid(row=1, column=0, padx=16, pady=8, sticky="nsew")
        for column in range(7):
            self.days.grid_columnconfigure(column, weight=1, uniform="days")
        clock = ctk.CTkFrame(self, fg_color="transparent")
        clock.grid(row=2, column=0, padx=16, pady=8, sticky="w")
        for column, (label, variable, maximum) in enumerate([('Giờ', self.hour, 23), ('Phút', self.minute, 59), ('Giây', self.second, 59)]):
            ctk.CTkLabel(clock, text=label).grid(row=0, column=column, padx=8)
            self._spin(clock, variable, 0, maximum).grid(row=1, column=column, padx=8)
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=3, column=0, padx=16, pady=12, sticky="ew")
        ctk.CTkButton(actions, text='Hôm nay', width=72, command=self._today).pack(side="left", padx=(0, 6))
        ctk.CTkButton(actions, text='Xóa', width=72, command=self._clear).pack(side="left")
        ctk.CTkButton(actions, text='Áp dụng', width=90, command=self._apply).pack(side="right")
        self._render()
        polish(self)
        self.after(50, self.lift)

    def _spin(self, parent: Any, variable: tk.StringVar, minimum: int, maximum: int, command: Any = None, width: int = 4) -> tk.Spinbox:
        dark = ctk.get_appearance_mode() == "Dark"
        return tk.Spinbox(
            parent, from_=minimum, to=maximum, textvariable=variable, command=command,
            width=width, state="readonly", wrap=True, font=("Arial", 12),
            readonlybackground="#333333" if dark else "#ffffff", fg="#ffffff" if dark else "#222222",
            buttonbackground="#555555" if dark else "#dddddd", relief="flat", highlightthickness=1,
        )

    def _render(self) -> None:
        for child in self.days.winfo_children():
            child.destroy()
        year, month = int(self.year.get()), int(self.month.get())
        self.selected = date(year, month, min(self.selected.day, calendar.monthrange(year, month)[1]))
        for column, day in enumerate(["T2", "T3", "T4", "T5", "T6", "T7", "CN"]):
            ctk.CTkLabel(self.days, text=day, height=24).grid(row=0, column=column)
        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
        for row in range(6):
            self.days.grid_rowconfigure(row + 1, minsize=32)
            for column in range(7):
                day = weeks[row][column] if row < len(weeks) else 0
                if day:
                    selected = self.selected == date(year, month, day)
                    ctk.CTkButton(
                        self.days, text=str(day), width=36, height=28,
                        fg_color="#2563eb" if selected else ("#dddddd", "#444444"),
                        text_color="white" if selected else ("#222222", "#eeeeee"),
                        command=lambda value=day: self._select(value),
                    ).grid(row=row + 1, column=column, padx=2, pady=2)

    def _select(self, day: int) -> None:
        self.selected = date(int(self.year.get()), int(self.month.get()), day)
        self._render()

    def _shift(self, delta: int) -> None:
        index = int(self.year.get()) * 12 + int(self.month.get()) - 1 + delta
        year, month_index = divmod(index, 12)
        if 1 <= year <= 9999:
            self.year.set(str(year))
            self.month.set(str(month_index + 1))
            self._render()

    def _today(self) -> None:
        self.selected = date.today()
        self.year.set(str(self.selected.year))
        self.month.set(str(self.selected.month))
        self._render()

    def _clear(self) -> None:
        self.picker.set(None)
        self.destroy()

    def _apply(self) -> None:
        self.picker.set(datetime.combine(self.selected, time(int(self.hour.get()), int(self.minute.get()), int(self.second.get()))))
        self.destroy()
