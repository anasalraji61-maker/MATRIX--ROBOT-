"""V11 Full Power Demo profile — 55 symbols, 24/5, council + scalping."""
from __future__ import annotations

from typing import Any

from tools.scalping_guard import is_demo_account


def _set(s, key: str, value: Any) -> None:
    object.__setattr__(s, key, value)


def _env_file_has(key: str) -> bool:
    """True if .env explicitly sets key (pydantic reads .env; os.environ may not)."""
    from pathlib import Path

    p = Path(".env")
    if not p.is_file():
        return False
    target = key.strip().upper()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.split("=", 1)[0].strip().upper() == target:
            return True
    return False


def apply_trading_mode_profile(settings) -> None:
    profile = str(getattr(settings, "trading_mode_profile", "") or "").strip().upper()
    if not profile or profile in ("", "DEFAULT", "V10", "CONSERVATIVE"):
        _apply_demo_guards(settings)
        return

    if profile == "FULL_POWER_DEMO":
        _apply_full_power_demo(settings)
    _apply_demo_guards(settings)


def _apply_full_power_demo(s) -> None:
    from tools.symbol_registry import DEFAULT_SYMBOLS_CSV

    preserved_full_analysis = getattr(s, "full_analysis_all_symbols", False)

    _set(s, "symbols", DEFAULT_SYMBOLS_CSV)
    _set(s, "symbol_universe_mode", "full_55")
    _set(s, "run_24h_full_analysis", True)
    _set(s, "run_24h_all_systems", True)
    # Pydantic loads .env before model_post_init; os.environ may lack the key.
    # Respect explicit .env when user sets FULL_ANALYSIS_ALL_SYMBOLS=false.
    if _env_file_has("FULL_ANALYSIS_ALL_SYMBOLS"):
        _set(s, "full_analysis_all_symbols", preserved_full_analysis)
    else:
        _set(s, "full_analysis_all_symbols", True)
    _set(s, "scanner_universe_use_full_registry", True)

    # 24/5 — scalping + intraday + swing + SMALL/NORMAL all hours
    _set(s, "session_filter_mode", "24h")
    _set(s, "allow_24h_scalping", True)
    _set(s, "allow_24h_intraday", True)
    _set(s, "allow_24h_swing", True)
    _set(s, "allow_24h_normal_trades", True)
    _set(s, "allow_24h_small_trades", True)
    _set(s, "smart_watcher_enabled", True)
    _set(s, "smart_watcher_execute_off_session_small", True)
    _set(s, "phase5_session_require_killzone", False)
    _set(s, "phase5_block_low_liquidity", False)
    _set(s, "allow_off_session_small_trades", True)
    _set(s, "off_session_allowed_assets", "ALL")
    _set(s, "off_session_max_open_trades", 12)
    _set(s, "off_session_max_trades_per_day", 60)
    _set(s, "off_session_24h_max_open_trades", 12)
    _set(s, "off_session_24h_max_trades_per_day", 60)
    _set(s, "tiered_block_metals_outside_kz", False)
    _set(s, "tiered_block_oil_outside_kz", False)

    _set(s, "scheduler_interval_minutes", 10)
    _set(s, "phase5_scheduler_high_liq_minutes", 10)
    _set(s, "phase5_scheduler_medium_liq_minutes", 12)
    _set(s, "phase5_scheduler_low_liq_minutes", 15)

    _set(s, "mtf_max_symbols", int(getattr(s, "deep_analysis_top_n", 15)))
    _set(s, "deep_analysis_top_n", 15)
    _set(s, "council_top_n", 8)
    _set(s, "council_top_candidates", 8)

    _set(s, "max_trades_per_day", 80)
    _set(s, "max_concurrent_positions", 15)
    _set(s, "intraday_max_trades_per_day", 25)
    _set(s, "swing_max_trades_per_day", 8)
    _set(s, "small_trade_max_open", 10)
    _set(s, "small_trade_max_per_day", 35)

    _set(s, "scalping_enabled", True)
    _set(s, "scalping_demo_only", True)
    _set(s, "scalping_max_trades_per_day", 40)
    _set(s, "scalping_max_open_trades", 6)
    _set(s, "scalping_risk_multiplier", 0.08)
    _set(s, "scalping_min_strength", 0.58)
    _set(s, "scalping_min_rr", 1.05)
    _set(s, "scalping_use_trailing", True)
    _set(s, "scalping_use_breakeven", True)

    _set(s, "council_enabled", True)

    # Demo Full Power — enforce (not shadow) when broker is demo
    if is_demo_account(s):
        _set(s, "scalping_mode", "enforce")
        _set(s, "council_mode", "enforce")
    elif not getattr(s, "council_mode", None) or s.council_mode == "":
        _set(s, "council_mode", "shadow")

    _set(s, "max_same_currency_exposure", 4)
    _set(s, "max_correlated_trades", 3)
    _set(s, "correlation_guard_enabled", True)

    _set(s, "cheap_scan_top_deep", 15)
    _set(s, "full_power_llm_top_n", 15)


def _apply_demo_guards(s) -> None:
    """Auto-disable aggressive modes on non-demo unless explicit ack."""
    if is_demo_account(s):
        return
    if not getattr(s, "i_understand_real_risk", False):
        if getattr(s, "scalping_enabled", False) and getattr(s, "scalping_demo_only", True):
            _set(s, "scalping_enabled", False)
        cm = str(getattr(s, "council_mode", "shadow") or "shadow").lower()
        if cm == "enforce":
            _set(s, "council_mode", "advisory")
        sm = str(getattr(s, "scalping_mode", "shadow") or "shadow").lower()
        if sm == "enforce":
            _set(s, "scalping_mode", "shadow")
        if str(getattr(s, "trading_mode_profile", "")).upper() == "FULL_POWER_DEMO":
            _set(s, "trading_mode_profile", "")
