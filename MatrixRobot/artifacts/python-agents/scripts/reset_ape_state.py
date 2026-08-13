#!/usr/bin/env python3
"""Reset Adaptive Policy (APE) — clears SKIP_SESSION and conviction override.

Run once on VPS when Brain stops trading due to self-imposed APE locks:
  C:\\MatrixVenv\\Scripts\\python scripts\\reset_ape_state.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

APE_FILE = Path(__file__).resolve().parents[1] / ".state" / "adaptive_policy.json"


def main() -> None:
    from tools.adaptive_policy import _default_state

    APE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = _default_state()
    APE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"APE reset OK: {APE_FILE}")
    print("  conviction_override → cleared")
    print("  skip_session_until → cleared")
    print("  paused_symbols → cleared")


if __name__ == "__main__":
    main()
