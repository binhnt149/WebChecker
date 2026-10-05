from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


APP_NAME = "SiteSentry Desktop"
APP_SLUG = "sitesentry-desktop"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[2]


def user_data_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if system == "Windows":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME

    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / APP_SLUG
    return Path.home() / ".local" / "share" / APP_SLUG


def config_path() -> Path:
    if is_frozen():
        return user_data_dir() / "config.json"
    return resource_root() / "config.json"


def bundled_config_path() -> Path:
    return resource_root() / "config.json"


def resolve_app_path(value: object | None, default: str) -> Path:
    raw = str(value or default)
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    base = user_data_dir() if is_frozen() else resource_root()
    return base / path


def asset_path(filename: str) -> Path:
    return resource_root() / "sitesentry" / "assets" / filename
