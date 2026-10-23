from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil

from .validate_release import ROOT, app_version


PLATFORMS = ("Windows-x64", "macOS-x64", "macOS-arm64")


def filenames(version: str, platform: str) -> list[str]:
    if platform not in PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform}")
    base = f"SiteSentry-Desktop-v{version}-{platform}"
    return [f"{base}.exe", f"{base}.zip"] if platform == "Windows-x64" else [f"{base}.dmg"]


def stage(platform: str, source: Path, output: Path, version: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    inputs = ["SiteSentry Desktop.exe", "SiteSentry-Desktop-Windows.zip"] if platform == "Windows-x64" else ["SiteSentry-Desktop-macOS.dmg"]
    for original, name in zip(inputs, filenames(version, platform)):
        path = source / original
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing or empty build output: {path}")
        shutil.copy2(path, output / name)
        print(name)


def verify(output: Path, version: str) -> None:
    expected = sorted(name for platform in PLATFORMS for name in filenames(version, platform))
    actual = sorted(path.name for path in output.iterdir() if path.name != "SHA256SUMS.txt")
    if actual != expected:
        raise ValueError(f"Release files do not match. Expected {expected}, found {actual}")
    checksums = []
    for name in expected:
        path = output / name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing or empty release file: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        checksums.append(f"{digest.hexdigest()}  {name}\n")
    (output / "SHA256SUMS.txt").write_text("".join(checksums), encoding="utf-8")
    print(f"Verified {len(expected)} packages")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify(ROOT / "release", app_version())
    else:
        stage(os.environ["PACKAGE_PLATFORM"], ROOT / "dist", ROOT / "release", app_version())
