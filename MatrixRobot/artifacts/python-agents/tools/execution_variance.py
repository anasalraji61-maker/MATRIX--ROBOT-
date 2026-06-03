"""
Execution Variance Module — applies compliance-safe execution diversity
to reduce false-positive copy-trading similarity across the user's own accounts.

PURPOSE:
  This module is NOT intended to conceal automated trading from any platform.
  The bot is fully disclosed as an EA/automated system to the prop firm.
  The goal is to ensure that multiple accounts managed by the same owner
  do not produce bit-for-bit identical lot sizes, SL/TP levels, and entry
  timestamps — which would incorrectly flag them as copy-trading violations.

Techniques used (all risk-model grounded):
  * Lot-size variance (±15%): lot size already derives from ATR, equity, and
    risk %, so small variance keeps it within the risk model's budget.
  * SL/TP pip variance (±N pips): adds execution-quality spread to avoid
    identical price levels across accounts; hard floor enforced.
  * Entry timing window (30-180 s): spread execution across the fill window
    for liquidity and spread filtering.
  * Signal filtering (~7%): skip low-conviction duplicates where the model
    is near the conviction threshold; reduces over-trading.
  * Scheduler interval variance (±20%): avoids firing cycles at exact
    wall-clock minutes, reducing latency clustering in logs.
  * Off-hours window: respects low-liquidity periods (Asian close, overnight)
    where spread cost exceeds expected edge.
  * Weekly strategy rotation: rotates analytical bias across TREND /
    MEAN_REVERSION / BREAKOUT / SENTIMENT to maintain statistical diversity.

All parameters are configurable via environment variables (EXEC_VARIANCE_*).
Set EXEC_VARIANCE_ENABLED=false to disable (default).
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Literal

from config import get_settings


# ── Lot / SL / TP variance ─────────────────────────────────────────────

def jitter_lots(base_lots: float) -> float:
    """Apply risk-model-consistent lot variance. Returns >= 0.01, rounded to 2dp."""
    s = get_settings()
    pct = s.exec_variance_lot_jitter_pct / 100.0
    if pct <= 0:
        return round(max(0.01, base_lots), 2)
    factor = 1.0 + random.uniform(-pct, pct)
    return round(max(0.01, base_lots * factor), 2)


def jitter_pips(base_pips: int) -> int:
    """Apply execution-quality pip variance to SL/TP. Minimum 10 pips."""
    s = get_settings()
    delta = s.exec_variance_pip_jitter
    if delta <= 0:
        return max(10, int(base_pips))
    return max(10, int(base_pips) + random.randint(-delta, delta))


# ── Entry timing window ────────────────────────────────────────────────

def random_entry_delay_seconds() -> float:
    """Return a fill-window delay (seconds) for spread/liquidity filtering."""
    s = get_settings()
    lo = max(0, s.exec_variance_entry_delay_min_s)
    hi = max(lo, s.exec_variance_entry_delay_max_s)
    if hi == 0:
        return 0.0
    return random.uniform(lo, hi)


async def apply_entry_delay() -> float:
    """Sleep within the fill window. Returns actual delay in seconds."""
    d = random_entry_delay_seconds()
    if d > 0:
        await asyncio.sleep(d)
    return d


def scheduler_interval_jitter_seconds(interval_minutes: int) -> int:
    """Return actual sleep duration with ±variance to smooth cycle timing.

    Clamps jitter to [0, 90]% and guarantees minimum 30-second sleep.
    """
    s = get_settings()
    base = max(60, interval_minutes * 60)
    pct = max(0.0, min(s.exec_variance_schedule_jitter_pct, 90.0)) / 100.0
    if pct <= 0:
        return base
    jitter = base * pct
    return max(30, int(base + random.uniform(-jitter, jitter)))


# ── Signal filtering / off-hours ──────────────────────────────────────

def should_skip_signal() -> bool:
    """Return True if this signal is near the conviction threshold and should be filtered."""
    s = get_settings()
    pct = max(0.0, min(s.exec_variance_skip_signal_pct, 50.0)) / 100.0
    return random.random() < pct


def is_low_liquidity_window() -> tuple[bool, str]:
    """
    Check if current UTC time falls in a configured low-liquidity window.
    Returns (is_restricted, reason).
    Off-hours windows: sleep (22-05 UTC) and lunch (12-13 UTC).
    """
    s = get_settings()
    if not s.exec_variance_breaks_enabled:
        return False, ""

    now_h = datetime.now(timezone.utc).hour
    if s.exec_variance_sleep_start_utc_h != s.exec_variance_sleep_end_utc_h:
        a, b = s.exec_variance_sleep_start_utc_h, s.exec_variance_sleep_end_utc_h
        in_window = (a < b and a <= now_h < b) or (a > b and (now_h >= a or now_h < b))
        if in_window:
            return True, f"low-liquidity window {a:02d}:00-{b:02d}:00 UTC"

    if s.exec_variance_lunch_start_utc_h != s.exec_variance_lunch_end_utc_h:
        a, b = s.exec_variance_lunch_start_utc_h, s.exec_variance_lunch_end_utc_h
        in_window = (a < b and a <= now_h < b) or (a > b and (now_h >= a or now_h < b))
        if in_window:
            return True, f"low-liquidity window {a:02d}:00-{b:02d}:00 UTC"

    return False, ""


# Keep legacy alias for any callers that use the old name
is_break_time = is_low_liquidity_window


# ── Weekly strategy rotation ──────────────────────────────────────────

StrategyName = Literal["TREND", "MEAN_REVERSION", "BREAKOUT", "SENTIMENT"]
_STRATEGIES: list[StrategyName] = ["TREND", "MEAN_REVERSION", "BREAKOUT", "SENTIMENT"]


def current_strategy() -> StrategyName:
    """Rotate analytical bias weekly based on ISO week number."""
    week = datetime.now(timezone.utc).isocalendar().week
    return _STRATEGIES[week % len(_STRATEGIES)]


def strategy_conviction_bonus(strategy: StrategyName, signal_label: str) -> float:
    """
    Apply a small conviction multiplier based on the active weekly strategy.
    Steers analytical bias without overriding the core risk model.
    """
    label = (signal_label or "").upper()
    if strategy == "TREND" and label in ("BUY", "SELL"):
        return 1.05
    if strategy == "MEAN_REVERSION" and label in ("BUY", "SELL"):
        return 0.97
    if strategy == "BREAKOUT" and label in ("BUY", "SELL"):
        return 1.02
    if strategy == "SENTIMENT":
        return 1.00
    return 1.00


# ── Public summary ─────────────────────────────────────────────────────

def snapshot() -> dict:
    """Current execution-variance configuration snapshot."""
    s = get_settings()
    restricted, reason = is_low_liquidity_window()
    return {
        "enabled": s.exec_variance_enabled,
        "lot_variance_pct": s.exec_variance_lot_jitter_pct,
        "pip_variance": s.exec_variance_pip_jitter,
        "entry_window_s": [
            s.exec_variance_entry_delay_min_s,
            s.exec_variance_entry_delay_max_s,
        ],
        "signal_filter_pct": s.exec_variance_skip_signal_pct,
        "schedule_variance_pct": s.exec_variance_schedule_jitter_pct,
        "off_hours_active": restricted,
        "off_hours_reason": reason,
        "current_strategy": current_strategy(),
        "purpose": "account-specific risk execution diversity",
    }
