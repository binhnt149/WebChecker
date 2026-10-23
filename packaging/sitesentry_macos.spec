# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from runpy import run_path

from PyInstaller.utils.hooks import collect_data_files


PROJECT_ROOT = Path(SPECPATH).resolve().parent
VERSION = run_path(str(PROJECT_ROOT / "sitesentry" / "__init__.py"))["__version__"]

datas = [
    (str(PROJECT_ROOT / "config.json"), "."),
    (str(PROJECT_ROOT / "sitesentry" / "assets"), "sitesentry/assets"),
    (str(PROJECT_ROOT / "templates"), "templates"),
]
datas += collect_data_files("customtkinter")

hiddenimports = [
    "PIL._tkinter_finder",
    "apscheduler.executors.pool",
    "apscheduler.jobstores.memory",
    "apscheduler.schedulers.background",
    "apscheduler.triggers.interval",
    "apscheduler.triggers.cron",
    "pystray._base",
    "pystray._darwin",
]


a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SiteSentry Desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SiteSentry Desktop",
)

app = BUNDLE(
    coll,
    name="SiteSentry Desktop.app",
    icon=str(PROJECT_ROOT / "sitesentry" / "assets" / "icon.icns"),
    bundle_identifier="com.sitesentry.desktop",
    info_plist={
        "CFBundleName": "SiteSentry Desktop",
        "CFBundleDisplayName": "SiteSentry Desktop",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSHighResolutionCapable": True,
    },
)
