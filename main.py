from __future__ import annotations

import platform
import os
import sys

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

import tkinter as tk
from tkinter import messagebox


MIN_PYTHON = (3, 10)


def _runtime_error_message() -> str:
    current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    return (
        "SiteSentry Desktop requires Python 3.10 or newer.\n\n"
        f"Current runtime: Python {current}\n"
        "The Apple CommandLineTools Python 3.9 runtime can open a Tk window but does not "
        "render CustomTkinter controls correctly on this machine, which results in a blank app window.\n\n"
        "Install Python 3.10+ from python.org or another framework build, then run:\n"
        "python3.10 -m pip install -r requirements.txt\n"
        "python3.10 main.py"
    )


def ensure_supported_runtime() -> None:
    if sys.version_info >= MIN_PYTHON:
        return

    message = _runtime_error_message()
    print(message, file=sys.stderr)
    if platform.system() == "Darwin" and os.environ.get("SITESENTRY_NO_MESSAGEBOX") != "1":
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("SiteSentry Desktop runtime", message)
            root.destroy()
        except tk.TclError:
            pass
    raise SystemExit(1)


def main() -> None:
    ensure_supported_runtime()
    from sitesentry.ui.main_window import SiteSentryApp

    app = SiteSentryApp()
    app.mainloop()


if __name__ == "__main__":
    main()
