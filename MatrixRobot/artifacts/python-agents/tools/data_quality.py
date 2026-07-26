"""ACTIVE-mode data integrity — global fail-closed + per-symbol quarantine."""
from __future__ import annotations

from config import get_settings
from tools.symbol_registry import INDICES, METALS, OIL


def _mock_sets(state: dict) -> tuple[list[str], list[str]]:
    dq = (state.get("market_data") or {}).get("data_quality") or {}
    mock_q = [str(s).upper() for s in (dq.get("quotes_mock_symbols") or [])]
    mock_b = [str(s).upper() for s in (dq.get("bars_mock_symbols") or [])]
    return mock_q, mock_b


def compute_data_quarantine(state: dict, mode: str) -> dict:
    """Build per-symbol quarantine map and detect provider-wide failure."""
    settings = get_settings()
    symbols = [str(s).upper() for s in (state.get("symbols_analyzed") or [])]
    if not symbols:
        symbols = list(settings.symbol_list)

    quarantine: dict[str, str] = {}
    mock_q, mock_b = _mock_sets(state)
    mock_all = set(mock_q) | set(mock_b)

    per_symbol = getattr(settings, "active_data_per_symbol_quarantine", True)
    use_quarantine = mode == "ACTIVE" and getattr(settings, "active_fail_closed_data", True)

    if use_quarantine and per_symbol:
        for sym in mock_all:
            reasons: list[str] = []
            if sym in mock_q:
                reasons.append("mock/stale quote")
            if sym in mock_b:
                reasons.append("mock/stale bars")
            quarantine[sym] = "; ".join(reasons)

    if mode == "ACTIVE":
        disabled = settings.active_disabled_symbol_set
        for sym in disabled:
            if sym in symbols or sym in mock_all:
                if sym not in quarantine:
                    quarantine[sym] = "disabled in ACTIVE (demo FX-only)"

    tradable = [s for s in symbols if s not in settings.active_disabled_symbol_set]
    unexpected_bad = [
        s for s in quarantine
        if s not in settings.active_disabled_symbol_set
    ]
    total = max(len(tradable), 1)
    bad_count = len(unexpected_bad)
    ratio = bad_count / total
    threshold = float(getattr(settings, "active_data_global_block_ratio", 0.5))

    global_block = False
    global_reason = ""
    if use_quarantine and not per_symbol:
        ok, global_reason = validate_active_data(state, mode)
        global_block = not ok
    elif use_quarantine and per_symbol:
        md = state.get("market_data") or {}
        qs = str((md.get("data_quality") or {}).get("quotes_source", "unknown")).lower()
        if qs in ("mock", "failed", "none") and len(mock_q) >= total:
            global_block = True
            global_reason = f"Provider-wide quote failure ({qs})"
        elif ratio >= threshold and bad_count > 0:
            global_block = True
            global_reason = (
                f"Too many stale tradable symbols ({bad_count}/{total} >= {threshold:.0%} threshold)"
            )

    return {
        "data_quarantine_symbols": quarantine,
        "global_data_block": global_block,
        "global_data_block_reason": global_reason,
        "quotes_mock_symbols": mock_q,
        "bars_mock_symbols": mock_b,
    }


def symbol_quarantine_reason(symbol: str, state: dict, mode: str) -> str:
    """Non-empty reason if symbol must not trade in this mode."""
    sym = str(symbol).upper()
    from tools.surgical_filters import is_symbol_quarantined

    blocked, q_reason = is_symbol_quarantined(sym)
    if blocked:
        return q_reason
    snap = state.get("data_quarantine") or compute_data_quarantine(state, mode)
    reason = (snap.get("data_quarantine_symbols") or {}).get(sym, "")
    if reason:
        return reason
    if mode == "ACTIVE" and sym in get_settings().active_disabled_symbol_set:
        return "disabled in ACTIVE (demo FX-only)"
    return ""


def validate_active_data(state: dict, mode: str) -> tuple[bool, str]:
    """Global ACTIVE gate — news, account, provider-wide data failure only."""
    settings = get_settings()
    if mode != "ACTIVE":
        return True, ""
    if not getattr(settings, "active_fail_closed_data", True):
        return True, ""

    md = state.get("market_data") or {}
    if getattr(settings, "active_require_live_news", True):
        src = str(md.get("news_source", "unknown")).lower()
        if src in ("mock", "none", "unknown"):
            return False, f"Live news required in ACTIVE (source={src})"

    if getattr(settings, "active_data_per_symbol_quarantine", True):
        snap = state.get("data_quarantine") or compute_data_quarantine(state, mode)
        if snap.get("global_data_block"):
            return False, snap.get("global_data_block_reason") or "Global data integrity block"
    else:
        dq = md.get("data_quality") or {}
        mock_q = dq.get("quotes_mock_symbols") or []
        mock_b = dq.get("bars_mock_symbols") or []
        if mock_q:
            return False, f"Mock/stale quotes in ACTIVE: {', '.join(mock_q[:5])}"
        if mock_b:
            return False, f"Mock/stale bars in ACTIVE: {', '.join(mock_b[:5])}"

    if getattr(settings, "active_fail_closed_no_account", True):
        acct = state.get("account") or {}
        if not acct.get("available"):
            return False, "Account snapshot unavailable — no new trades in ACTIVE"

    return True, ""


def active_data_status(state: dict | None = None, mode: str = "") -> dict:
    """Dashboard snapshot — why ACTIVE may be blocked on data/news."""
    settings = get_settings()
    md = (state or {}).get("market_data") or {}
    src = str(md.get("news_source", "unknown")).lower()
    require_news = getattr(settings, "active_require_live_news", True)
    effective_mode = mode or settings.trading_state
    quarantine = (
        (state or {}).get("data_quarantine")
        or compute_data_quarantine(state or {}, effective_mode)
    )
    ok, reason = (
        validate_active_data(state or {}, effective_mode)
        if effective_mode == "ACTIVE"
        else (True, "")
    )
    return {
        "mode": effective_mode,
        "news_source": src,
        "active_require_live_news": require_news,
        "active_data_per_symbol_quarantine": settings.active_data_per_symbol_quarantine,
        "active_disabled_symbols": sorted(settings.active_disabled_symbol_set),
        "polygon_configured": settings.has_polygon,
        "twelve_data_configured": settings.has_twelve_data,
        "active_blocked": effective_mode == "ACTIVE" and not ok,
        "block_reason": reason if effective_mode == "ACTIVE" and not ok else "",
        "quotes_mock_symbols": quarantine.get("quotes_mock_symbols", []),
        "bars_mock_symbols": quarantine.get("bars_mock_symbols", []),
        "data_quarantine_symbols": quarantine.get("data_quarantine_symbols", {}),
        "global_data_block": quarantine.get("global_data_block", False),
        "global_data_block_reason": quarantine.get("global_data_block_reason", ""),
    }
