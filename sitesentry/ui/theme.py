from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

import customtkinter as ctk


CANVAS = ("#f3f6f8", "#111719")
SURFACE = ("#ffffff", "#1b2428")
TEXT = ("#18252c", "#edf3f5")
MUTED = ("#52616b", "#a9bac3")
BORDER = ("#d6e0e5", "#39494f")
ACCENT = ("#087d72", "#0d7c72")
ACCENT_HOVER = ("#08665e", "#09675f")
SELECTION = ("#dbf4ef", "#234a45")
GOOD = ("#137449", "#65dda2")
BAD = ("#b42332", "#ff8792")
WARNING = ("#8b5700", "#f8cc70")
BLUE = ("#205fbb", "#87b7ff")


def fit_wrap(label: ctk.CTkLabel, width: int) -> None:
    width = max(200, width)
    if label.cget("wraplength") != width:
        label.configure(wraplength=width)


def color(value: tuple[str, str]) -> str:
    return value[ctk.get_appearance_mode() == "Dark"]


def polish(widget: Any) -> None:
    """Apply the desktop palette to existing CTk forms without rebuilding them."""
    if isinstance(widget, (ctk.CTk, ctk.CTkToplevel)):
        widget.configure(fg_color=CANVAS)
    elif isinstance(widget, ctk.CTkFrame) and widget.cget("fg_color") != "transparent":
        widget.configure(fg_color=SURFACE, corner_radius=6)
    elif isinstance(widget, (ctk.CTkEntry, ctk.CTkTextbox)):
        widget.configure(fg_color=SURFACE, text_color=TEXT, border_color=BORDER, border_width=1, corner_radius=5)
    elif isinstance(widget, ctk.CTkSegmentedButton):
        widget.configure(fg_color=CANVAS, selected_color=SELECTION, selected_hover_color=SELECTION, unselected_color=SURFACE, unselected_hover_color=CANVAS, text_color=TEXT)
        return
    elif isinstance(widget, ctk.CTkLabel):
        current = widget.cget("text_color")
        if isinstance(current, str) and current in {"#94a3b8", "#64748b"}:
            widget.configure(text_color=MUTED)
        elif isinstance(current, str) and current in {"#f59e0b", "#ff9900"}:
            widget.configure(text_color=WARNING)
        elif isinstance(current, str) and current in {"#dc2626", "#ef4444", "#f87171"}:
            widget.configure(text_color=BAD)
        elif isinstance(current, str) and current in {"#16a34a", "#22c55e"}:
            widget.configure(text_color=GOOD)
        elif isinstance(current, str) and current in {"gray10", "gray90"}:
            widget.configure(text_color=TEXT)
        elif not isinstance(current, str) and tuple(current) not in {TEXT, MUTED, GOOD, BAD, WARNING, BLUE}:
            widget.configure(text_color=TEXT)
    elif isinstance(widget, ctk.CTkButton):
        current = widget.cget("fg_color")
        default_blue = not isinstance(current, str) and tuple(code.lower() for code in current) in {("#3b8ed0", "#1f6aa5"), ("#3a7ebf", "#1f538d")}
        if default_blue or (isinstance(current, str) and current.lower() in {"#3b8ed0", "#1f6aa5", "#2563eb"}):
            widget.configure(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white")
        widget.configure(corner_radius=5, height=32)
    elif isinstance(widget, (ctk.CTkCheckBox, ctk.CTkSwitch)):
        widget.configure(fg_color=ACCENT, text_color=TEXT)
    elif isinstance(widget, ctk.CTkOptionMenu):
        widget.configure(fg_color=ACCENT, button_color=ACCENT_HOVER, button_hover_color=ACCENT_HOVER, text_color="white")
    for child in widget.winfo_children():
        polish(child)


def configure_table(table: ttk.Treeview) -> None:
    style = ttk.Style(table)
    if style.theme_use() != "clam":
        style.theme_use("clam")
    style.configure("Sentry.Treeview", background=color(SURFACE), fieldbackground=color(SURFACE), foreground=color(TEXT), rowheight=34, font=("Arial", 12), borderwidth=0)
    style.configure("Sentry.Treeview.Heading", background=color(CANVAS), foreground=color(MUTED), font=("Arial", 11, "bold"), padding=(10, 10), relief="flat")
    style.map("Sentry.Treeview", background=[("selected", color(SELECTION))], foreground=[("selected", color(TEXT))])
    style.map("Sentry.Treeview.Heading", background=[("active", color(SELECTION))])
    table.configure(style="Sentry.Treeview")
    table.tag_configure("down", foreground=color(BAD))
    table.tag_configure("up", foreground=color(GOOD))
    table.tag_configure("stripe", background=color(CANVAS))


def table_scrollers(parent: Any, table: ttk.Treeview) -> None:
    parent.grid_columnconfigure(0, weight=1)
    parent.grid_rowconfigure(0, weight=1)
    table.grid(row=0, column=0, sticky="nsew")
    vertical = ttk.Scrollbar(parent, orient="vertical", command=table.yview)
    horizontal = ttk.Scrollbar(parent, orient="horizontal", command=table.xview)
    vertical.grid(row=0, column=1, sticky="ns")
    horizontal.grid(row=1, column=0, sticky="ew")
    table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    configure_table(table)


def metric(parent: Any, title: str, column: int, tone: tuple[str, str] = TEXT) -> ctk.CTkLabel:
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    frame.grid(row=0, column=column, padx=(0, 20), pady=8, sticky="ew")
    parent.grid_columnconfigure(column, weight=1, uniform="metrics")
    ctk.CTkLabel(frame, text=title, text_color=MUTED, font=ctk.CTkFont(size=12)).pack(anchor="w")
    value = ctk.CTkLabel(frame, text="-", text_color=tone, font=ctk.CTkFont(size=24, weight="bold"))
    value.pack(anchor="w")
    return value
