#!/usr/bin/env python3
"""Train Matrix signal win/loss classifier — PyTorch + MLflow (CUDA when available)."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from ml.dataset import (
    Dataset,
    build_from_backtest,
    build_from_postgres,
    build_from_trade_outcomes,
)
from ml.trainer import default_mlflow_uri, train_classifier


async def _build_dataset(symbols: list[str], bars: int, timeframe: str, source: str):
    if source == "outcomes":
        ds = build_from_trade_outcomes()
        if ds is not None and ds.n_samples >= 8:
            return ds, symbols or sorted({s.symbol for s in ds.samples if s.symbol})
        print("Trade outcomes too few — falling back to backtest replay.")

    if source == "postgres":
        ds = build_from_postgres()
        if ds is not None and ds.n_samples >= 8:
            return ds, symbols
        print("Postgres dataset too small — falling back to backtest replay.")

    import numpy as np
    from ml.features import feature_dim
    from ml.dataset import LabeledSample

    all_samples: list[LabeledSample] = []
    for sym in symbols:
        ds = await build_from_backtest(sym, bars_limit=bars, timeframe=timeframe)
        all_samples.extend(ds.samples)
        print(f"  {sym}: {ds.n_samples} trades (WR {ds.to_dict()['win_rate']:.1%})")

    if not all_samples:
        return Dataset(
            X=np.zeros((0, feature_dim()), dtype=np.float32),
            y=np.zeros(0, dtype=np.float32),
        ), symbols

    X = np.array([s.features for s in all_samples], dtype=np.float32)
    y = np.array([s.label for s in all_samples], dtype=np.float32)
    return Dataset(X=X, y=y, samples=all_samples), symbols


async def main() -> None:
    p = argparse.ArgumentParser(description="Matrix Robot — ML signal trainer")
    p.add_argument("--symbols", default="EURUSD,XAUUSD,GBPUSD,USDJPY", help="Comma-separated")
    p.add_argument("--bars", type=int, default=2000, help="H1 bars per symbol")
    p.add_argument("--timeframe", default="H1")
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--hidden", type=int, default=32)
    p.add_argument(
        "--source",
        choices=("backtest", "postgres", "outcomes"),
        default="backtest",
    )
    p.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    p.add_argument(
        "--heavy",
        action="store_true",
        help="Laptop lab profile: more bars/epochs/hidden (uses RTX if present)",
    )
    p.add_argument(
        "--mlflow-uri",
        default=default_mlflow_uri(),
        help="Default: sqlite:///C:/MatrixML/mlflow.db",
    )
    p.add_argument("--experiment", default="matrix_signal_classifier")
    args = p.parse_args()

    if args.heavy:
        args.bars = max(args.bars, 3000)
        args.epochs = max(args.epochs, 80)
        args.hidden = max(args.hidden, 64)
        args.symbols = args.symbols or "EURUSD,XAUUSD,GBPUSD,USDJPY,USDCAD"
        os.environ["MATRIX_ML_DEVICE"] = args.device
        print("HEAVY lab mode — bars=%s epochs=%s hidden=%s device=%s" % (
            args.bars, args.epochs, args.hidden, args.device,
        ))

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    print(f"Building dataset ({args.source}) — {', '.join(symbols)} @ {args.bars} bars...")
    dataset, symbols = await _build_dataset(symbols, args.bars, args.timeframe, args.source)

    result = train_classifier(
        dataset,
        symbols=symbols,
        bars=args.bars,
        timeframe=args.timeframe,
        epochs=args.epochs,
        lr=args.lr,
        hidden=args.hidden,
        mlflow_uri=args.mlflow_uri,
        experiment=args.experiment,
        run_name=f"{'_'.join(symbols[:4])}_{args.bars}b",
        device=args.device,
    )

    print("\n=== Training result ===")
    print(json.dumps(result, indent=2))
    if result.get("ok"):
        print(f"\nDevice: {result.get('device')}")
        print(f"MLflow UI: mlflow ui --backend-store-uri {args.mlflow_uri} --host 127.0.0.1 --port 5000")
        print(f"Model PT:   {result['checkpoint']}")
        print(f"Model JSON: {result['model_json']}  ← copy this to VPS ml_models/")
        # Also write a stable name for VPS deploy
        stable = Path("ml_models") / "signal_deploy.json"
        try:
            import shutil
            shutil.copy2(result["model_json"], stable)
            print(f"Stable:     {stable}")
        except Exception as e:
            print(f"(stable copy skipped: {e})")


if __name__ == "__main__":
    asyncio.run(main())
