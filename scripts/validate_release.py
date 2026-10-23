from __future__ import annotations

import os
from pathlib import Path
import re
from runpy import run_path


ROOT = Path(__file__).resolve().parent.parent


def app_version() -> str:
    version = run_path(str(ROOT / "sitesentry" / "__init__.py"))["__version__"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("App version must have the form X.Y.Z")
    return version


def validate_ref(ref: str, version: str) -> None:
    if ref.startswith("refs/tags/") and ref != f"refs/tags/v{version}":
        raise ValueError(f"Release tag must match app version: v{version}")


if __name__ == "__main__":
    version = app_version()
    validate_ref(os.environ.get("GITHUB_REF", ""), version)
    print(f"SiteSentry Desktop {version}")
