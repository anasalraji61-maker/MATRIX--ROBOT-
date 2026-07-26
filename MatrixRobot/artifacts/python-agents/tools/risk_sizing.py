"""Shared position sizing — used by risk, execution, prop_rules."""

from tools.symbol_specs import get_spec, pip_size_for, pip_value_for, PIP_VALUE



_FALLBACK_EQUITY = 10_000.0

_MAX_LOTS = 5.0





def quantize_lot(raw: float, min_lot: float, step: float) -> float:

    """Round lot down to broker min/step; return 0 if below minimum."""

    if raw < min_lot:

        return 0.0

    if step <= 0:

        return round(raw, 4)

    steps = int((raw - min_lot) / step)

    return round(min_lot + steps * step, 4)





def compute_safe_sizing(

    symbol: str,

    strength: float,

    atr: float,

    equity: float,

    starting_balance: float,

    current_open_risk_pct: float,

    prop_status: dict | None,

    settings,

    vol_mult: float = 1.0,

    adaptive_risk_multiplier: float = 1.0,

    max_risk_pct_override: float | None = None,

    trade_tier: str = "NORMAL",

    session_profile: dict | None = None,

) -> dict:

    spec = get_spec(symbol)

    min_lot = float(spec.volume_min or 0.01)

    lot_step = float(spec.volume_step or 0.01)

    pip = pip_size_for(symbol)

    sl_atr_mult = 1.5

    tp_rr_base = 2.0

    if session_profile and session_profile.get("enabled"):

        sl_atr_mult = float(session_profile.get("sl_atr_mult", sl_atr_mult))

        tp_rr_base = float(session_profile.get("tp_rr_ratio", tp_rr_base))

    sl_pips = max(int(atr * (1.0 / pip) * sl_atr_mult), 15)

    tp_pips = max(int(sl_pips * tp_rr_base), 30)

    pip_val = pip_value_for(symbol)

    rr = round(tp_pips / max(sl_pips, 1), 2)



    safety = float(getattr(settings, "sizing_safety_buffer_pct", 0.3))

    ps = prop_status or {}

    daily_dd_now = float(ps.get("daily_loss_pct", 0.0) or 0.0)

    total_dd_now = float(ps.get("total_loss_pct", 0.0) or 0.0)



    eq = max(equity, 1.0)

    sb = max(starting_balance, 1.0)

    ape_mult = max(0.3, min(float(adaptive_risk_multiplier or 1.0), 1.0))

    strength_scale = min(float(strength or 0.0), 1.0)

    risk_at_min_lot_usd = sl_pips * pip_val * min_lot



    account_profile = str(getattr(settings, "account_profile", "")).upper()

    if (

        account_profile == "REAL"

        and eq <= float(getattr(settings, "real_micro_equity_threshold", 100.0))

    ):

        strength_scale = max(

            strength_scale,

            float(getattr(settings, "real_micro_strength_floor_for_sizing", 0.8)),

        )

        required_max_risk_pct = (

            risk_at_min_lot_usd / max(eq * strength_scale * ape_mult, 1e-9)

        ) * 100.0

        effective_max_risk_pct = min(

            max(float(settings.max_risk_per_trade_pct), required_max_risk_pct),

            float(getattr(settings, "real_micro_max_risk_per_trade_pct", 3.5)),

        )

        per_trade_usd = eq * (effective_max_risk_pct / 100.0) * strength_scale * ape_mult

    else:

        tier_risk_pct = float(settings.max_risk_per_trade_pct)

        if max_risk_pct_override is not None:

            tier_risk_pct = min(tier_risk_pct, float(max_risk_pct_override))

        per_trade_usd = eq * (tier_risk_pct / 100.0) * strength_scale * ape_mult



    daily_room_usd = sb * max(0.0, settings.max_daily_drawdown_pct - daily_dd_now - safety) / 100.0

    total_room_usd = sb * max(0.0, settings.max_total_drawdown_pct - total_dd_now - safety) / 100.0

    portfolio_room_usd = sb * max(0.0, settings.max_total_open_risk_pct - current_open_risk_pct) / 100.0



    caps_usd = [

        (per_trade_usd, "per-trade cap"),

        (daily_room_usd, "daily DD buffer to internal target"),

        (total_room_usd, "total DD buffer to internal target"),

        (portfolio_room_usd, "portfolio open-risk cap"),

    ]

    risk_budget_usd, cap_reason = min(caps_usd, key=lambda c: c[0])

    binding_pct = (risk_budget_usd / sb) * 100.0



    if risk_budget_usd <= 0.0:

        return {

            "lots": 0.0, "sl_pips": sl_pips, "tp_pips": tp_pips, "rr": rr,

            "pip": pip, "pip_val": pip_val,

            "min_lot": min_lot, "lot_step": lot_step,

            "risk_usd": 0.0, "risk_pct_of_starting": 0.0,

            "budget_usd": 0.0, "budget_pct": 0.0,

            "cap_reason": cap_reason, "rejected": True,

            "reject_reason": (

                f"No room left under '{cap_reason}' "

                f"(daily {daily_dd_now:.2f}%, total {total_dd_now:.2f}%, "

                f"open {current_open_risk_pct:.2f}%)"

            ),

            "trade_tier": trade_tier,

        }



    if risk_at_min_lot_usd > risk_budget_usd:

        return {

            "lots": 0.0, "sl_pips": sl_pips, "tp_pips": tp_pips, "rr": rr,

            "pip": pip, "pip_val": pip_val,

            "min_lot": min_lot, "lot_step": lot_step,

            "risk_usd": 0.0, "risk_pct_of_starting": 0.0,

            "budget_usd": round(risk_budget_usd, 2),

            "budget_pct": round(binding_pct, 3),

            "cap_reason": cap_reason, "rejected": True,

            "reject_reason": (

                f"Minimum lot {min_lot} would risk ${risk_at_min_lot_usd:.2f} "

                f"> budget ${risk_budget_usd:.2f} under '{cap_reason}'"

            ),

            "trade_tier": trade_tier,

        }



    raw_lots = risk_budget_usd / max(sl_pips * pip_val, 1.0)

    try:
        from tools.surgical_filters import xagusd_risk_multiplier
        vol_mult = vol_mult * xagusd_risk_multiplier(symbol, settings)
    except Exception:
        pass

    raw_lots = raw_lots * max(0.1, min(vol_mult, 1.0))

    lots = quantize_lot(min(raw_lots, _MAX_LOTS), min_lot, lot_step)



    if lots <= 0.0:

        return {

            "lots": 0.0, "sl_pips": sl_pips, "tp_pips": tp_pips, "rr": rr,

            "pip": pip, "pip_val": pip_val,

            "min_lot": min_lot, "lot_step": lot_step,

            "risk_usd": 0.0, "risk_pct_of_starting": 0.0,

            "budget_usd": round(risk_budget_usd, 2),

            "budget_pct": round(binding_pct, 3),

            "cap_reason": cap_reason, "rejected": True,

            "reject_reason": (

                f"Quantized lot below minimum {min_lot} under '{cap_reason}'"

            ),

            "trade_tier": trade_tier,

        }



    actual_risk_usd = sl_pips * pip_val * lots

    max_xag_loss = float(getattr(settings, "xagusd_max_single_loss_usd", 0) or 0)
    if symbol.upper() == "XAGUSD" and max_xag_loss > 0 and actual_risk_usd > max_xag_loss:
        capped = quantize_lot(max_xag_loss / max(sl_pips * pip_val, 1.0), min_lot, lot_step)
        if capped <= 0:
            return {
                "lots": 0.0, "sl_pips": sl_pips, "tp_pips": tp_pips, "rr": rr,
                "pip": pip, "pip_val": pip_val,
                "min_lot": min_lot, "lot_step": lot_step,
                "risk_usd": 0.0, "risk_pct_of_starting": 0.0,
                "budget_usd": round(risk_budget_usd, 2),
                "budget_pct": round(binding_pct, 3),
                "cap_reason": cap_reason, "rejected": True,
                "reject_reason": f"XAGUSD max loss ${max_xag_loss:.0f} — lot too small",
                "trade_tier": trade_tier,
            }
        lots = capped
        actual_risk_usd = sl_pips * pip_val * lots

    if actual_risk_usd > risk_budget_usd and lots > min_lot:

        reduced = quantize_lot(risk_budget_usd / max(sl_pips * pip_val, 1.0), min_lot, lot_step)

        if reduced > 0:

            lots = reduced

            actual_risk_usd = sl_pips * pip_val * lots



    actual_risk_pct = (actual_risk_usd / sb) * 100.0



    if actual_risk_usd > risk_budget_usd:

        return {

            "lots": 0.0, "sl_pips": sl_pips, "tp_pips": tp_pips, "rr": rr,

            "pip": pip, "pip_val": pip_val,

            "min_lot": min_lot, "lot_step": lot_step,

            "risk_usd": 0.0, "risk_pct_of_starting": 0.0,

            "budget_usd": round(risk_budget_usd, 2),

            "budget_pct": round(binding_pct, 3),

            "cap_reason": cap_reason, "rejected": True,

            "reject_reason": (

                f"Final guard: risk ${actual_risk_usd:.2f} > budget "

                f"${risk_budget_usd:.2f} under '{cap_reason}'"

            ),

            "trade_tier": trade_tier,

        }



    return {

        "lots": lots, "sl_pips": sl_pips, "tp_pips": tp_pips, "rr": rr,

        "pip": pip, "pip_val": pip_val,

        "min_lot": min_lot, "lot_step": lot_step,

        "risk_usd": round(actual_risk_usd, 2),

        "risk_pct_of_starting": round(actual_risk_pct, 3),

        "budget_usd": round(risk_budget_usd, 2),

        "budget_pct": round(binding_pct, 3),

        "cap_reason": cap_reason,

        "rejected": False,

        "reject_reason": "",

        "trade_tier": trade_tier,

    }

