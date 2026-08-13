"""Phase 5C — spread / liquidity guard before opening new trades."""
from __future__ import annotations

from tools.symbol_specs import pip_size_for


def _max_spread_pips(symbol: str, settings) -> float:
    sym = symbol.upper()
    if sym == "XAUUSD":
        return float(settings.phase5_max_spread_pips_xau)
    if sym == "XAGUSD":
        return float(settings.phase5_max_spread_pips_xau) * 0.5
    if sym in ("USOIL", "UKOIL"):
        return float(getattr(settings, "phase5_max_spread_pips_oil", 8.0))
    if sym in ("US30", "US500", "USTEC") or sym.isdigit():
        return float(settings.phase5_max_spread_pips_index)
    return float(settings.phase5_max_spread_pips_fx)


def spread_pips(symbol: str, quote: dict | None) -> float | None:
    if not quote:
        return None
    bid = float(quote.get("bid") or 0)
    ask = float(quote.get("ask") or 0)
    if bid <= 0 or ask <= 0:
        return None
    pip = pip_size_for(symbol)
    return (ask - bid) / pip


def check_spread(symbol: str, quote: dict | None, settings) -> tuple[bool, str]:
    """Return (allowed, reason). allowed=False blocks the new entry."""
    if not getattr(settings, "phase5_liquidity_guard_enabled", True):
        return True, ""
    if not getattr(settings, "phase5_intraday_enabled", True):
        return True, ""

    sp = spread_pips(symbol, quote)
    if sp is None:
        return True, ""  # no quote — do not block sizing path

    cap = _max_spread_pips(symbol, settings)
    if sp > cap:
        return False, f"Spread {sp:.1f} pips > cap {cap:.1f} for {symbol}"
    return True, ""
