#!/usr/bin/env python3
"""Export .pt checkpoint → JSON for Brain ML filter (run once on VPS after training)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    p = argparse.ArgumentParser(description="Export PyTorch .pt → Brain JSON weights")
    p.add_argument(
        "--pt",
        default="ml_models/signal_EURUSD_XAUUSD_2000bars.pt",
        help="Path to .pt checkpoint",
    )
    p.add_argument("--json", default="", help="Output JSON path (default: same name .json)")
    args = p.parse_args()

    from ml.inference import export_torch_to_json

    pt = Path(args.pt)
    if not pt.is_file():
        print(f"ERROR: not found: {pt}")
        sys.exit(1)

    out = export_torch_to_json(pt, args.json or None)
    print(f"Exported: {out}")


if __name__ == "__main__":
    main()
