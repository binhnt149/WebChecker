from __future__ import annotations

import shutil
import subprocess
import os
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ICON = ROOT / "sitesentry" / "assets" / "icon.png"
ICONSET = ROOT / "build" / "icon.iconset"
OUTPUT_ICON = ROOT / "sitesentry" / "assets" / "icon.icns"
FALLBACK_PNG = ROOT / "build" / "icon_1024.png"
FALLBACK_ICNS = Path("/private/tmp/sitesentry-desktop-icon.icns")


def main() -> None:
    if not SOURCE_ICON.exists():
        raise SystemExit(f"Missing source icon: {SOURCE_ICON}")

    if ICONSET.exists():
        shutil.rmtree(ICONSET)
    ICONSET.mkdir(parents=True, exist_ok=True)

    image = Image.open(SOURCE_ICON).convert("RGBA")
    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for size, filename in sizes:
        image.resize((size, size), Image.LANCZOS).save(ICONSET / filename)

    if OUTPUT_ICON.exists():
        OUTPUT_ICON.unlink()

    try:
        subprocess.run(["iconutil", "-c", "icns", str(ICONSET), "-o", str(OUTPUT_ICON)], check=True)
    except subprocess.CalledProcessError:
        env = os.environ.copy()
        env["TMPDIR"] = "/private/tmp"
        subprocess.run(["sips", "-s", "format", "icns", str(SOURCE_ICON), "--out", str(FALLBACK_ICNS)], check=True, env=env)
        shutil.copyfile(FALLBACK_ICNS, OUTPUT_ICON)
    print(f"Created {OUTPUT_ICON}")


if __name__ == "__main__":
    main()
