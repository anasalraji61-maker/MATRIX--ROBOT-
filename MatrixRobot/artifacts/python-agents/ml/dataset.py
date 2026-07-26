"""Build labeled datasets from backtest replay or live strategy_scores."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backtest.engine import (
    MIN_WARMUP_BARS,
    MAX_BARS_HELD,
    SIGNAL_THRESHOLD,
    Trade,
    _check_exit,
    _open_trade,
    _score_bar,
)
from ml.features import FEATURE_NAMES, extract_features
from tools import indicators as _ind
from tools import ict_smc as _ict
from tools import twelve_data

logger = logging.getLogger("matrix.ml.dataset")


@dataclass
class LabeledSample:
    symbol: str
    side: str
    features: list[float]
    label: int          # 1 = win, 0 = loss/breakeven
    pnl_r: float
    entry_idx: int
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Dataset:
    X: np.ndarray       # (n, n_features)
    y: np.ndarray       # (n,)
    samples: list[LabeledSample] = field(default_factory=list)
    feature_names: tuple[str, ...] = FEATURE_NAMES

    @property
    def n_samples(self) -> int:
        return len(self.y)

    def to_dict(self) -> dict:
        wins = int(self.y.sum())
        return {
            "n_samples": self.n_samples,
            "n_wins": wins,
            "n_losses": self.n_samples - wins,
            "win_rate": round(wins / self.n_samples, 4) if self.n_samples else 0.0,
            "feature_names": list(self.feature_names),
        }


def _samples_to_arrays(samples: list[LabeledSample]) -> Dataset:
    if not samples:
        return Dataset(
            X=np.zeros((0, len(FEATURE_NAMES)), dtype=np.float32),
            y=np.zeros(0, dtype=np.float32),
            samples=[],
        )
    X = np.array([s.features for s in samples], dtype=np.float32)
    y = np.array([s.label for s in samples], dtype=np.float32)
    return Dataset(X=X, y=y, samples=samples)


async def build_from_backtest(
    symbol: str,
    bars_limit: int = 2000,
    timeframe: str = "H1",
) -> Dataset:
    """Replay deterministic backtest and label each entry (win if pnl_r > 0)."""
    symbol = symbol.upper()
    bars = await twelve_data.fetch_historical(symbol, limit=bars_limit, timeframe=timeframe)
    n = len(bars)
    samples: list[LabeledSample] = []
    open_trade: Trade | None = None

    for t in range(MIN_WARMUP_BARS, n):
        if open_trade is not None:
            if _check_exit(open_trade, bars[t], t):
                _append_sample(samples, open_trade, symbol)
                open_trade = None
            elif (t - open_trade.entry_idx) >= MAX_BARS_HELD:
                open_trade.exit_idx = t
                open_trade.exit_price = bars[t]["close"]
                px_diff = open_trade.exit_price - open_trade.entry_price
                if open_trade.side == "SELL":
                    px_diff = -px_diff
                sl_dist = abs(open_trade.entry_price - open_trade.sl)
                open_trade.pnl_r = round(px_diff / sl_dist, 3) if sl_dist > 0 else 0.0
                open_trade.bars_held = t - open_trade.entry_idx
                open_trade.exit_reason = "TIMEOUT"
                _append_sample(samples, open_trade, symbol)
                open_trade = None

        if open_trade is not None:
            continue

        window = bars[: t + 1]
        try:
            ind = _ind.compute_indicators(symbol, window).model_dump()
            ict = _ict.analyze(symbol, window, backtest_mode=True).model_dump()
        except Exception as e:
            logger.debug("features bar %s: %s", t, e)
            continue

        norm = _score_bar(ind, ict)
        atr = ind.get("atr_14") or 0.0
        price = bars[t]["close"]
        if atr <= 0 or price <= 0:
            continue

        side = None
        if norm >= SIGNAL_THRESHOLD:
            side = "BUY"
        elif norm <= -SIGNAL_THRESHOLD:
            side = "SELL"
        if side is None:
            continue

        feats = extract_features(ind, ict, norm, side, price)
        open_trade = _open_trade(symbol, side, t, price, atr)
        open_trade._entry_features = feats  # type: ignore[attr-defined]
        open_trade._entry_norm = norm  # type: ignore[attr-defined]

    if open_trade is not None:
        last_t = n - 1
        open_trade.exit_idx = last_t
        open_trade.exit_price = bars[last_t]["close"]
        sl_dist = abs(open_trade.entry_price - open_trade.sl)
        px_diff = open_trade.exit_price - open_trade.entry_price
        if open_trade.side == "SELL":
            px_diff = -px_diff
        open_trade.pnl_r = round(px_diff / sl_dist, 3) if sl_dist > 0 else 0.0
        open_trade.bars_held = last_t - open_trade.entry_idx
        open_trade.exit_reason = "EOD"
        _append_sample(samples, open_trade, symbol)

    return _samples_to_arrays(samples)


def _append_sample(samples: list[LabeledSample], trade: Trade, symbol: str) -> None:
    feats = getattr(trade, "_entry_features", None)
    if feats is None:
        return
    label = 1 if trade.pnl_r > 0 else 0
    samples.append(
        LabeledSample(
            symbol=symbol,
            side=trade.side,
            features=feats,
            label=label,
            pnl_r=trade.pnl_r,
            entry_idx=trade.entry_idx,
            meta={"exit_reason": trade.exit_reason, "bars_held": trade.bars_held},
        )
    )


def build_from_postgres(min_completed: int = 20) -> Dataset | None:
    """Optional: train from live strategy_scores when enough completed rows exist."""
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return None
    try:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        pool = ConnectionPool(
            conninfo=dsn, min_size=1, max_size=2,
            kwargs={"autocommit": True}, open=True, timeout=5,
        )
        with pool.connection() as conn:
            conn.row_factory = dict_row
            cur = conn.execute(
                """
                SELECT symbol, signal, confidence, outcome, pnl, regime
                FROM strategy_scores
                WHERE outcome IS NOT NULL
                ORDER BY ts DESC
                LIMIT 500
                """
            )
            rows = cur.fetchall()
        pool.close()
    except Exception as e:
        logger.warning("postgres dataset skipped: %s", e)
        return None

    if len(rows) < min_completed:
        return None

    samples: list[LabeledSample] = []
    for i, row in enumerate(rows):
        sig = (row.get("signal") or "HOLD").upper()
        side_val = 1.0 if sig == "BUY" else (-1.0 if sig == "SELL" else 0.0)
        conf = float(row.get("confidence") or 0.5)
        outcome = row.get("outcome")
        label = 1 if outcome == "win" else 0
        pnl = float(row.get("pnl") or 0.0)
        # Minimal feature vector — live rows lack full indicator snapshot
        feats = [0.0] * len(FEATURE_NAMES)
        feats[0] = side_val
        feats[1] = conf if side_val >= 0 else -conf
        samples.append(
            LabeledSample(
                symbol=row.get("symbol") or "",
                side=sig,
                features=feats,
                label=label,
                pnl_r=pnl,
                entry_idx=i,
                meta={"source": "postgres", "regime": row.get("regime")},
            )
        )
    return _samples_to_arrays(samples)
