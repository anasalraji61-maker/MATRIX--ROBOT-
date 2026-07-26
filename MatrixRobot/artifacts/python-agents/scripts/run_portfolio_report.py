#!/usr/bin/env python3
"""Portfolio backtest report — multi-symbol summary (Phase 4A).

Example (VPS, ~15–25 min for 5000 H1 bars × 5 symbols):
  C:\\MatrixVenv\\Scripts\\python scripts\\run_portfolio_report.py --bars 5000
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_SYMBOLS = "EURUSD,XAUUSD,GBPUSD,USDJPY,US500"


async def _run_one_basic(sym: str, bars: int, timeframe: str) -> dict:
    from backtest.engine import run_backtest

    try:
        r = await run_backtest(sym, bars_limit=bars, timeframe=timeframe)
        s = r.stats or {}
        return {
            "symbol": sym,
            "engine": "basic",
            "bars_count": r.bars_count,
            "n_trades": s.get("n_trades", 0),
            "win_rate": s.get("win_rate"),
            "total_r": s.get("total_r"),
            "profit_factor": s.get("profit_factor"),
            "max_dd_r": s.get("max_dd_r"),
            "sharpe_like": s.get("sharpe_like"),
            "expectancy_r": s.get("expectancy_r"),
            "error": s.get("error"),
        }
    except Exception as e:
        return {"symbol": sym, "engine": "basic", "error": f"{type(e).__name__}: {e}"}


async def _run_one_vectorbt(sym: str, bars: int, timeframe: str) -> dict:
    from backtest.vectorbt_engine import run_vectorbt_backtest

    try:
        r = await run_vectorbt_backtest(
            sym, bars_limit=bars, timeframe=timeframe, compare_builtin=False,
        )
        s = r.stats or {}
        return {
            "symbol": sym,
            "engine": "vectorbt",
            "bars_count": r.bars_count,
            "n_trades": s.get("total_trades", 0),
            "win_rate": s.get("win_rate"),
            "total_return_pct": s.get("total_return_pct"),
            "profit_factor": s.get("profit_factor"),
            "max_drawdown_pct": s.get("max_drawdown_pct"),
            "sharpe_ratio": s.get("sharpe_ratio"),
            "error": s.get("error"),
        }
    except Exception as e:
        return {"symbol": sym, "engine": "vectorbt", "error": f"{type(e).__name__}: {e}"}


def _aggregate(rows: list[dict]) -> dict:
    ok = [r for r in rows if not r.get("error")]
    total_trades = sum(int(r.get("n_trades") or 0) for r in ok)
    total_r = sum(float(r.get("total_r") or 0) for r in ok if r.get("total_r") is not None)
    wins = 0
    for r in ok:
        wr = r.get("win_rate")
        nt = int(r.get("n_trades") or 0)
        if wr is not None and nt:
            wins += int(round(wr * nt))
    return {
        "symbols_ok": len(ok),
        "symbols_failed": len(rows) - len(ok),
        "total_trades": total_trades,
        "portfolio_win_rate": round(wins / total_trades, 4) if total_trades else 0.0,
        "total_r": round(total_r, 3) if ok and any(r.get("total_r") is not None for r in ok) else None,
    }


def _print_table(rows: list[dict], engine: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"  PORTFOLIO REPORT — engine={engine}")
    print(f"{'=' * 72}")
    print(f"{'Symbol':<10} {'Trades':>7} {'WR%':>7} {'TotalR':>8} {'PF':>7} {'Sharpe':>8}")
    print("-" * 72)
    for r in rows:
        if r.get("error"):
            print(f"{r['symbol']:<10} {'ERROR':>7}  {r['error'][:40]}")
            continue
        wr = r.get("win_rate")
        wr_s = f"{100 * wr:.1f}" if wr is not None else "—"
        tr = r.get("total_r")
        tr_s = f"{tr:+.2f}" if tr is not None else (
            f"{r.get('total_return_pct', 0):+.1f}%" if r.get("total_return_pct") is not None else "—"
        )
        pf = r.get("profit_factor")
        pf_s = f"{pf:.2f}" if pf is not None else "—"
        sh = r.get("sharpe_like") or r.get("sharpe_ratio")
        sh_s = f"{sh:.2f}" if sh is not None else "—"
        print(
            f"{r['symbol']:<10} {int(r.get('n_trades') or 0):>7} {wr_s:>7} "
            f"{tr_s:>8} {pf_s:>7} {sh_s:>8}"
        )
    print("-" * 72)


async def main() -> None:
    p = argparse.ArgumentParser(description="Matrix Robot — portfolio backtest report")
    p.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    p.add_argument("--bars", type=int, default=5000, help="H1 bars (~7 months @ 5000)")
    p.add_argument("--timeframe", default="H1")
    p.add_argument("--engine", choices=("basic", "vectorbt"), default="basic")
    p.add_argument("--out-dir", default="backtest_reports")
    args = p.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    print(f"Running {args.engine} backtest — {len(symbols)} symbols @ {args.bars} {args.timeframe} bars...")
    print("(This may take 15–30 minutes — do not close PowerShell)\n")

    runner = _run_one_vectorbt if args.engine == "vectorbt" else _run_one_basic
    rows = await asyncio.gather(*[runner(sym, args.bars, args.timeframe) for sym in symbols])
    rows = list(rows)

    _print_table(rows, args.engine)
    overall = _aggregate(rows)
    print(f"\nOverall: {overall['symbols_ok']} OK, {overall['total_trades']} trades, "
          f"WR={100 * overall['portfolio_win_rate']:.1f}%", end="")
    if overall.get("total_r") is not None:
        print(f", total R={overall['total_r']:+.2f}")
    else:
        print()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    out_path = out_dir / f"portfolio_{args.engine}_{args.bars}b_{stamp}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": args.engine,
        "bars": args.bars,
        "timeframe": args.timeframe,
        "symbols": symbols,
        "per_symbol": rows,
        "overall": overall,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nReport saved: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
