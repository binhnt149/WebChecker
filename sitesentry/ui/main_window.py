from __future__ import annotations

import json
import os
import platform
import queue
import sys
import threading

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

import tkinter as tk
from typing import Any

import customtkinter as ctk
from PIL import Image, ImageDraw

from sitesentry.core.checker import SiteChecker
from sitesentry.core.database import Database
from sitesentry.core.notifier import EmailNotifier
from sitesentry.core.paths import asset_path, bundled_config_path, config_path, is_frozen, resolve_app_path
from sitesentry.core.scheduler import MonitorScheduler
from sitesentry.core.security import SecurityManager

from .dashboard_view import DashboardView
from .logs_view import LogsView
from .settings_view import SettingsView


def load_config() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "app_name": "SiteSentry Desktop",
        "database_path": "data/sitesentry.db",
        "fernet_key_path": "data/fernet.key",
        "appearance": "System",
        "enable_system_tray": "auto",
    }
    bundled_config = bundled_config_path()
    user_config = config_path()
    if bundled_config.exists():
        defaults.update(json.loads(bundled_config.read_text(encoding="utf-8")))
    if user_config.exists() and user_config != bundled_config:
        defaults.update(json.loads(user_config.read_text(encoding="utf-8")))
    elif is_frozen():
        user_config.parent.mkdir(parents=True, exist_ok=True)
        user_config.write_text(json.dumps(defaults, indent=2), encoding="utf-8")

    defaults["database_path"] = str(resolve_app_path(defaults.get("database_path"), "data/sitesentry.db"))
    defaults["fernet_key_path"] = str(resolve_app_path(defaults.get("fernet_key_path"), "data/fernet.key"))
    return defaults


def ensure_icon_files() -> None:
    if is_frozen():
        return
    png_path = asset_path("icon.png")
    ico_path = asset_path("icon.ico")
    png_path.parent.mkdir(parents=True, exist_ok=True)
    if png_path.exists() and ico_path.exists():
        return
    image = Image.new("RGBA", (128, 128), "#0f172a")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((12, 12, 116, 116), radius=24, fill="#1d4ed8")
    draw.ellipse((34, 30, 94, 90), fill="#22c55e")
    draw.rectangle((58, 62, 70, 104), fill="#ffffff")
    draw.rectangle((40, 76, 88, 88), fill="#ffffff")
    image.save(png_path)
    image.save(ico_path)


class SiteSentryApp(ctk.CTk):
    def __init__(self) -> None:
        self.config = load_config()
        appearance = self.config.get("appearance", "System")
        ctk.set_appearance_mode(appearance)
        ctk.set_default_color_theme("blue")
        super().__init__()

        ensure_icon_files()
        self.title("SiteSentry Desktop")
        self.geometry("1160x760")
        self.minsize(980, 640)

        self.security = SecurityManager(self.config.get("fernet_key_path", "data/fernet.key"))
        self.db = Database(self.config.get("database_path", "data/sitesentry.db"), security=self.security)
        saved_appearance = self.db.get_setting("appearance", appearance)
        ctk.set_appearance_mode(saved_appearance)
        self.checker = SiteChecker()
        self.notifier = EmailNotifier(self.db)
        self.scheduler = MonitorScheduler(self.db, self.checker, self.notifier, on_result=self._on_monitor_result)

        self._current_view: ctk.CTkFrame | None = None
        self._tray_icon: Any | None = None
        self._tray_enabled = self._should_enable_tray()
        self._closing = False
        self._result_queue: queue.Queue[tuple[dict[str, Any], Any]] = queue.Queue()
        self.status_text = tk.StringVar(value="Starting...")
        self._build_layout()
        self.show_view("Dashboard")
        self.protocol("WM_DELETE_WINDOW", self._handle_close)
        if self._tray_enabled:
            self._start_tray()
        self.scheduler.start()
        self._update_status_text()
        self.after(250, self._drain_result_queue)
        self.after(250, self._show_on_launch)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(5, weight=1)
        ctk.CTkLabel(sidebar, text="SiteSentry", font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0, padx=20, pady=(24, 20), sticky="w")
        ctk.CTkButton(sidebar, text="Dashboard", command=lambda: self.show_view("Dashboard")).grid(row=1, column=0, padx=18, pady=6, sticky="ew")
        ctk.CTkButton(sidebar, text="Logs", command=lambda: self.show_view("Logs")).grid(row=2, column=0, padx=18, pady=6, sticky="ew")
        ctk.CTkButton(sidebar, text="Settings", command=lambda: self.show_view("Settings")).grid(row=3, column=0, padx=18, pady=6, sticky="ew")
        self.status_label = ctk.CTkLabel(sidebar, textvariable=self.status_text, text_color="#94a3b8", justify="left", wraplength=176)
        self.status_label.grid(row=5, column=0, padx=18, pady=12, sticky="sw")
        self.tray_button = ctk.CTkButton(sidebar, text="Hide to Tray", command=self.hide_to_tray, fg_color="#475569")
        self.tray_button.grid(row=6, column=0, padx=18, pady=(6, 18), sticky="ew")
        if not self._tray_enabled:
            self.tray_button.configure(state="disabled", text="Tray unavailable")

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

    def show_view(self, name: str) -> None:
        if self._current_view is not None:
            self._current_view.destroy()
        if name == "Logs":
            view = LogsView(self.content, self)
        elif name == "Settings":
            view = SettingsView(self.content, self)
        else:
            view = DashboardView(self.content, self)
        self._current_view = view
        view.grid(row=0, column=0, sticky="nsew")

    def _on_monitor_result(self, monitor: dict[str, Any], result: Any) -> None:
        self._result_queue.put((monitor, result))

    def _drain_result_queue(self) -> None:
        if self._closing:
            return
        has_updates = False
        while True:
            try:
                self._result_queue.get_nowait()
                has_updates = True
            except queue.Empty:
                break
        if has_updates:
            if self._current_view is not None and hasattr(self._current_view, "refresh"):
                getattr(self._current_view, "refresh")()
            self._update_status_text()
        self.after(250, self._drain_result_queue)

    def _show_on_launch(self) -> None:
        self.deiconify()
        self.lift()
        if self.focus_get() is None:
            try:
                self.focus_set()
            except tk.TclError:
                pass

    def _handle_close(self) -> None:
        if self._tray_icon is not None:
            self.hide_to_tray()
        else:
            self.quit_app()

    def hide_to_tray(self) -> None:
        if self._tray_icon is not None:
            self.withdraw()

    def show_from_tray(self) -> None:
        self.after(0, self.deiconify)
        self.after(0, self.lift)

    def quit_app(self) -> None:
        self._closing = True
        try:
            self.scheduler.stop()
        finally:
            if self._tray_icon is not None:
                self._tray_icon.stop()
            self.quit()

    def _should_enable_tray(self) -> bool:
        configured = str(self.config.get("enable_system_tray", "auto")).strip().lower()
        if configured in {"0", "false", "no", "off", "disabled"}:
            return False
        if configured in {"1", "true", "yes", "on", "enabled"}:
            return True
        if platform.system() == "Darwin":
            return False
        return True

    def _update_status_text(self) -> None:
        monitor_count = len(self.db.list_monitors(include_disabled=True))
        scheduler_state = "running" if self.scheduler.running else "stopped"
        tray_state = "on" if self._tray_icon is not None else "off"
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        self.status_text.set(
            f"Scheduler: {scheduler_state}\n"
            f"Monitors: {monitor_count}\n"
            f"Tray: {tray_state}\n"
            f"Python: {python_version}"
        )

    def _start_tray(self) -> None:
        import pystray

        image = Image.open(asset_path("icon.png"))
        menu = pystray.Menu(
            pystray.MenuItem("Show SiteSentry", lambda: self.show_from_tray()),
            pystray.MenuItem("Run All Now", lambda: self.scheduler.run_all_now()),
            pystray.MenuItem("Quit", lambda: self.after(0, self.quit_app)),
        )
        self._tray_icon = pystray.Icon("sitesentry", image, "SiteSentry Desktop", menu)
        try:
            self._tray_icon.run_detached()
        except (AttributeError, NotImplementedError):
            thread = threading.Thread(target=self._tray_icon.run, daemon=True)
            thread.start()
        except Exception:
            self._tray_icon = None
            self.tray_button.configure(state="disabled", text="Tray unavailable")
        self._update_status_text()
