#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN=""
for candidate in ./scripts/python3.10 python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
    then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  cat >&2 <<'EOF'
SiteSentry Desktop needs Python 3.10 or newer.

This machine does not currently expose python3.10, python3.11, python3.12, or python3.13.
Install Python 3.10+ from python.org, then run this script again:

  ./run.sh

On macOS, avoid the Apple CommandLineTools Python 3.9 runtime for this GUI app.
EOF
  exit 1
fi

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import apscheduler
import cryptography
import customtkinter
import httpx
import openpyxl
import pystray
from PIL import Image
PY
then
  "$PYTHON_BIN" -m pip install -r requirements.txt
fi
"$PYTHON_BIN" main.py
