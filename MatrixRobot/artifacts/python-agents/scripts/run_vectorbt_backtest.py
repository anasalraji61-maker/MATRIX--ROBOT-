#!/usr/bin/env python3
"""VectorBT backtest CLI — richer metrics (Sharpe, max DD %, total return)."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtest.vectorbt_engine import run_vectorbt_backtest


async def main() -> None:
    p = argparse.ArgumentParser(description="Matrix Robot — VectorBT backtest")
    p.add_argument("--symbols", default="EURUSD,XAUUSD", help="Comma-separated symbols")
    p.add_argument("--bars", type=int, default=500, help="H1 bars (500≈3wk, 2000≈3mo)")
    p.add_argument("--timeframe", default="H1", help="M15, H1, H4, D1")
    p.add_argument("--no-compare", action="store_true", help="Skip builtin engine comparison")
    args = p.parse_args()

    for sym in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
        result = await run_vectorbt_backtest(
            sym,
            bars_limit=args.bars,
            timeframe=args.timeframe,
            compare_builtin=not args.no_compare,
        )
        print(f"\n=== {sym} VectorBT ({result.bars_count} bars) ===")
        print(json.dumps(result.stats, indent=2))
        if result.compare_engine:
            print("\n--- compare (builtin engine) ---")
            print(json.dumps(result.compare_engine.get("stats", {}), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
