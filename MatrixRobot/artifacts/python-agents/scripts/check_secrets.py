#!/usr/bin/env python3
"""Simple secret scanner — run before commit or in CI."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PATTERNS = [
    (re.compile(r"MT5_BRIDGE_SECRET\s*=\s*['\"]?[A-Za-z0-9+/=_-]{16,}"), "MT5_BRIDGE_SECRET"),
    (re.compile(r"TWELVE_DATA_API_KEY\s*=\s*['\"]?[a-f0-9]{20,}"), "TWELVE_DATA_API_KEY"),
    (re.compile(r"MT5_PASSWORD\s*=\s*['\"]?[^\s#'\"]{6,}"), "MT5_PASSWORD"),
    (re.compile(r"telegram_bot_token\s*=\s*['\"]?\d{8,}:[A-Za-z0-9_-]{20,}"), "telegram_bot_token"),
]

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules", ".state"}
SKIP_FILES = {".env"}


def scan_file(path: Path) -> list[str]:
    if path.name in SKIP_FILES:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    hits = []
    for pat, label in PATTERNS:
        for m in pat.finditer(text):
            val = m.group(0)
            if "YOUR_" in val or "PLACEHOLDER" in val.upper() or "PUT_YOUR" in val:
                continue
            hits.append(f"{path.relative_to(ROOT)}: possible {label}")
    return hits


def main() -> int:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        findings.extend(scan_file(path))
    if findings:
        print("SECRET SCAN FAILED:")
        for f in findings:
            print(f"  - {f}")
        return 1
    print("Secret scan OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
