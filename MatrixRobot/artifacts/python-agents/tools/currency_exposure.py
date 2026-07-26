"""V11 currency exposure + correlation hardening."""
from __future__ import annotations

from config import get_settings
from tools import memory
from tools.symbol_registry import asset_class


_CURRENCIES = ("USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD", "XAU", "XAG", "OIL")


def _symbol_currencies(symbol: str) -> tuple[str, str]:
    sym = symbol.upper()
    if sym in ("XAUUSD",):
        return "XAU", "USD"
    if sym in ("XAGUSD",):
        return "XAG", "USD"
    if sym in ("USOIL", "UKOIL"):
        return "OIL", "USD"
    if len(sym) >= 6:
        return sym[:3], sym[3:6]
    return sym, ""


def exposure_for_position(symbol: str, action: str) -> dict[str, float]:
    """Long base / short quote exposure for BUY; inverse for SELL."""
    base, quote = _symbol_currencies(symbol)
    act = action.upper()
    exp: dict[str, float] = {c: 0.0 for c in _CURRENCIES}
    if act == "BUY":
        exp[base] = exp.get(base, 0) + 1.0
        exp[quote] = exp.get(quote, 0) - 1.0
    elif act == "SELL":
        exp[base] = exp.get(base, 0) - 1.0
        exp[quote] = exp.get(quote, 0) + 1.0
    return {k: v for k, v in exp.items() if abs(v) > 0}


def build_exposure_report(
    open_positions: list[dict] | None = None,
    pending: list[dict] | None = None,
) -> dict:
    settings = get_settings()
    positions = list(open_positions or memory.retrieve("open_positions") or [])
    pending = pending or []
    all_trades = positions + pending

    by_currency: dict[str, int] = {c: 0 for c in _CURRENCIES}
    for p in all_trades:
        sym = str(p.get("symbol") or "")
        act = str(p.get("action") or p.get("signal") or "")
        for cur, val in exposure_for_position(sym, act).items():
            if val > 0:
                by_currency[cur] = by_currency.get(cur, 0) + 1
            elif val < 0:
                by_currency[cur] = by_currency.get(cur, 0) + 1

    max_exp = int(getattr(settings, "max_same_currency_exposure", 3))
    overloaded = {c: n for c, n in by_currency.items() if n > max_exp}

    from tools.correlation import build_report, is_blocked
    corr = build_report(positions)
    correlated = [g.name for g in corr.groups if g.open_direction]

    return {
        "exposure_by_currency": {k: v for k, v in by_currency.items() if v},
        "max_same_currency_exposure": max_exp,
        "overloaded_currencies": overloaded,
        "correlated_positions": correlated,
        "correlation_groups": [g.model_dump() for g in corr.groups],
    }


def check_exposure_allowed(
    symbol: str,
    action: str,
    open_positions: list[dict] | None = None,
    settings=None,
) -> tuple[bool, str]:
    s = settings or get_settings()
    positions = list(open_positions or memory.retrieve("open_positions") or [])
    max_exp = int(getattr(s, "max_same_currency_exposure", 3))
    max_corr = int(getattr(s, "max_correlated_trades", 2))

    report = build_exposure_report(positions, [{"symbol": symbol, "action": action}])
    overloaded = report.get("overloaded_currencies") or {}
    if overloaded:
        cur = next(iter(overloaded))
        return False, f"currency exposure: {cur} would exceed {max_exp}"

    from tools.correlation import build_report, is_blocked
    corr = build_report(positions)
    blocked, reason = is_blocked(symbol, action.upper(), corr)
    if blocked:
        open_same_dir = sum(
            1 for p in positions
            if p.get("action") == action.upper()
        )
        if open_same_dir >= max_corr:
            return False, reason

    ac = asset_class(symbol)
    if ac == "indices":
        return False, "indices disabled until MT5 symbol verified"

    return True, ""
