from __future__ import annotations

import threading
from tkinter import messagebox
from typing import Any, Callable
from .vi import message as vi_message


def run_background(app: Any, owner: Any, work: Callable[[], Any], on_success: Callable[[Any], None], on_error: Callable[[str], None] | None = None) -> None:
    def publish(callback: Callable[[], None]) -> None:
        app._queue_ui_action(lambda: callback() if owner.winfo_exists() else None)

    def worker() -> None:
        try:
            result = work()
        except Exception as exc:
            message = vi_message(f"{type(exc).__name__}: {exc}")
            publish(lambda: on_error(message) if on_error else messagebox.showerror("SiteSentry", message, parent=owner))
        else:
            publish(lambda: on_success(result))

    threading.Thread(target=worker, daemon=True).start()
