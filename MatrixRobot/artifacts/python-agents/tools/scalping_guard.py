"""V11 scalping safety — demo-only, FX-only, auto-disable on real/funded."""
from __future__ import annotations

from config import get_settings
from tools.symbol_registry import DEFAULT_SYMBOLS_CSV, asset_class


def is_demo_account(settings=None) -> bool:
    s = settings or get_settings()
    server = (s.mt5_server or "").lower()
    if "demo" in server:
        return True
    if str(s.account_profile or "").upper() == "REAL":
        return False
    return False


def scalping_asset_allowed(symbol: str, settings=None) -> bool:
    s = settings or get_settings()
    allowed = str(getattr(s, "scalping_allowed_assets", "FX_ONLY") or "FX_ONLY").upper()
    sym = (symbol or "").upper()
    if allowed == "FX_ONLY":
        return asset_class(sym) == "fx"
    return True


def scalping_effective_enabled(mode: str = "", settings=None) -> tuple[bool, str]:
    """Return (enabled, reason_if_disabled)."""
    s = settings or get_settings()
    if not getattr(s, "scalping_enabled", False):
        return False, "SCALPING_ENABLED=false"
    if getattr(s, "scalping_demo_only", True):
        if not is_demo_account(s):
            return False, "demo-only guard — not a demo broker"
        if str(mode or s.trading_state).upper() == "ACTIVE" and not is_demo_account(s):
            return False, "demo-only guard — ACTIVE on non-demo"
    return True, ""


def scanner_universe(settings=None) -> list[str]:
    """55-symbol cheap-scan universe (independent of V10 cycle symbol list)."""
    s = settings or get_settings()
    if getattr(s, "scanner_universe_use_full_registry", True):
        raw = DEFAULT_SYMBOLS_CSV
    else:
        raw = s.symbols
    disabled = s.active_disabled_symbol_set
    out: list[str] = []
    for part in raw.split(","):
        sym = part.strip().upper()
        if not sym or sym in disabled:
            continue
        if scalping_asset_allowed(sym, s):
            out.append(sym)
    return out
