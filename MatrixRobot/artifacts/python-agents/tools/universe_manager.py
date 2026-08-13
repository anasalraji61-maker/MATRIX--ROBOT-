"""V11 symbol universe — full 55 registry, disabled symbols, asset counts."""
from __future__ import annotations

from config import get_settings
from tools.symbol_registry import (
    ALL_SYMBOLS,
    DEFAULT_SYMBOLS_CSV,
    asset_class,
)


def is_full_power(settings=None) -> bool:
    s = settings or get_settings()
    profile = str(getattr(s, "trading_mode_profile", "") or "").upper()
    return profile in ("FULL_POWER_DEMO", "FULL_POWER")


def configured_symbols(settings=None) -> list[str]:
    s = settings or get_settings()
    if is_full_power(s) or str(getattr(s, "symbol_universe_mode", "")).lower() == "full_55":
        raw = DEFAULT_SYMBOLS_CSV
    elif (s.symbols or "").strip():
        raw = s.symbols
    else:
        from tools.symbol_registry import DEMO_SYMBOLS_CSV
        raw = DEMO_SYMBOLS_CSV
    disabled = s.active_disabled_symbol_set
    return [sym.strip().upper() for sym in raw.split(",") if sym.strip() and sym.strip().upper() not in disabled]


def active_symbols(settings=None) -> list[str]:
    return configured_symbols(settings)


def universe_status(settings=None) -> dict:
    s = settings or get_settings()
    configured = configured_symbols(s)
    disabled = sorted(s.active_disabled_symbol_set)
    counts: dict[str, int] = {"fx": 0, "metals": 0, "oil": 0, "indices": 0}
    for sym in configured:
        ac = asset_class(sym)
        if ac in counts:
            counts[ac] += 1
        else:
            counts["fx"] += 1
    return {
        "trading_mode_profile": getattr(s, "trading_mode_profile", ""),
        "symbol_universe_mode": getattr(s, "symbol_universe_mode", ""),
        "configured_symbols_count": len(configured) + len(disabled),
        "active_symbols_count": len(configured),
        "disabled_symbols": disabled,
        "asset_class_counts": counts,
        "active_symbols": configured,
        "registry_total": len(ALL_SYMBOLS),
    }
