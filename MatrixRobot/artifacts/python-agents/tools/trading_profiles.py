"""Trading style profiles — conservative | aggressive | scalp.

Set TRADING_PROFILE in .env. Applied in config.model_post_init after env load.
"""
from __future__ import annotations

from typing import Any


def _set(s, key: str, value: Any) -> None:
    object.__setattr__(s, key, value)


def apply_trading_profile(settings) -> None:
    profile = str(getattr(settings, "trading_profile", "conservative") or "conservative").lower().strip()
    if profile in ("", "conservative", "v10", "default"):
        return

    from tools.symbol_registry import DEFAULT_SYMBOLS_CSV

    if profile == "aggressive":
        _apply_aggressive(settings, DEFAULT_SYMBOLS_CSV)
    elif profile == "scalp":
        _apply_scalp(settings, DEFAULT_SYMBOLS_CSV)
    else:
        return


def _apply_aggressive(s, symbols_csv: str) -> None:
    """24h full brain, 55 symbols, more trades — intraday (H1), not tick scalping."""
    _set(s, "symbols", symbols_csv)
    _set(s, "smart_watcher_enabled", False)
    _set(s, "smart_watcher_execute_off_session_small", True)
    _set(s, "session_filter_mode", "off")
    _set(s, "phase5_session_require_killzone", False)
    _set(s, "phase5_block_low_liquidity", False)
    _set(s, "ict_killzones_only", False)
    _set(s, "phase5_scheduler_high_liq_minutes", 12)
    _set(s, "phase5_scheduler_medium_liq_minutes", 12)
    _set(s, "phase5_scheduler_low_liq_minutes", 12)
    _set(s, "scheduler_interval_minutes", 12)
    _set(s, "primary_timeframe", "H1")
    _set(s, "normal_trade_min_strength", 0.58)
    _set(s, "small_trade_min_strength", 0.52)
    _set(s, "min_conviction_threshold", 0.52)
    _set(s, "off_session_min_strength", 0.62)
    _set(s, "off_session_escalation_min_strength", 0.62)
    _set(s, "off_session_max_open_trades", 4)
    _set(s, "off_session_max_trades_per_day", 15)
    _set(s, "off_session_scan_fx_only", False)
    _set(s, "off_session_allowed_assets", "ALL")
    _set(s, "small_trade_max_per_day", 25)
    _set(s, "small_trade_max_open", 8)
    _set(s, "max_trades_per_day", 50)
    _set(s, "max_concurrent_positions", 10)
    _set(s, "correlation_guard_enabled", False)
    _set(s, "mtf_max_symbols", 20)
    _set(s, "min_position_hold_seconds", 0)
    _set(s, "phase5_max_hold_hours", 6.0)


def _apply_scalp(s, symbols_csv: str) -> None:
    """Faster cycles + M5 bars — more signals, higher API/LLM cost."""
    _apply_aggressive(s, symbols_csv)
    _set(s, "primary_timeframe", "M5")
    _set(s, "phase5_scheduler_high_liq_minutes", 8)
    _set(s, "phase5_scheduler_medium_liq_minutes", 8)
    _set(s, "phase5_scheduler_low_liq_minutes", 8)
    _set(s, "scheduler_interval_minutes", 8)
    _set(s, "normal_trade_min_strength", 0.55)
    _set(s, "small_trade_min_strength", 0.50)
    _set(s, "min_conviction_threshold", 0.50)
    _set(s, "off_session_min_strength", 0.58)
    _set(s, "phase5_max_hold_hours", 2.0)
    _set(s, "phase5_sl_atr_mult_high", 0.75)
    _set(s, "phase5_sl_atr_mult_medium", 0.9)
    _set(s, "phase5_sl_atr_mult_low", 1.0)
    _set(s, "phase5_tp_rr_high", 1.2)
    _set(s, "phase5_tp_rr_medium", 1.3)
    _set(s, "phase5_tp_rr_low", 1.5)
    _set(s, "phase5_max_spread_pips_fx", 2.5)
