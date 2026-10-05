from __future__ import annotations

from typing import Any

import tkinter as tk


def bind_focus_on_click(widget: Any) -> Any:
    """Make CustomTkinter input widgets focus reliably on the first click."""

    def focus_widget(_event: tk.Event) -> None:
        try:
            widget.focus_set()
        except tk.TclError:
            pass

    try:
        widget.bind("<ButtonPress-1>", focus_widget, add="+")
    except (AttributeError, tk.TclError):
        pass
    return widget
