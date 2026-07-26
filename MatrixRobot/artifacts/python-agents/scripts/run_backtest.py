#!/usr/bin/env python3
"""Run deterministic backtests (no LLM). Uses Twelve Data when key set, else mock bars."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Allow running from repo root or python-agents/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtest.engine import run_backtest


async def main() -> None:
    p = argparse.ArgumentParser(description="Matrix Robot deterministic backtest")
    p.add_argument(
        "--symbols",
        default="EURUSD,XAUUSD,GBPUSD",
        help="Comma-separated symbols",
    )
    p.add_argument("--bars", type=int, default=500, help="H1 bars to fetch")
    args = p.parse_args()

    for sym in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
        result = await run_backtest(sym, bars_limit=args.bars, timeframe="H1")
        print(f"\n=== {sym} ({result.bars_count} bars) ===")
        print(json.dumps(result.stats, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
