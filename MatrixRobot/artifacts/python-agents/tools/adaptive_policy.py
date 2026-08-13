"""
Adaptive Policy Envelope (APE) — lets the brain autonomously apply
defensive adaptations without human approval.

ALLOWED (brain can do autonomously):
  ✓ Reduce risk multiplier (0.3 – 1.0)   → smaller position sizes
  ✓ Pause a symbol temporarily (max 24h)  → skip that symbol's signals
  ✓ Tighten conviction threshold          → require stronger signal
  ✓ Skip next session                     → sit out bad conditions
  ✓ Reset any of the above (with guardrails) → restore to baseline

NOT ALLOWED (requires human action via Replit Secrets / .env):
  ✗ Increase risk above baseline (multiplier > 1.0)
  ✗ Enable live trading / change ALLOW_LIVE_TRADING
  ✗ Change DD limits (max_daily_drawdown_pct, max_total_drawdown_pct)
  ✗ Use HFT / scalping / grid / martingale / copy trading
  ✗ Add new symbols or change core strategy family

Hardening (post-ChatGPT review):
  • SKIP_SESSION uses skip_session_until timestamp — not cleared per-symbol
  • TIGHTEN_CONVICTION has conviction_expires_at (max 24h)
  • RESET_RISK requires: cooldown 2h + consecutive_losses == 0
  • RESUME_SYMBOL requires: symbol was paused >= 1h
  • Symbols validated against VALID_SYMBOLS universe
  • Anti-flapping: max 3 APE changes per 24h, min 30min between same type
  • Atomic writes: tempfile + os.replace
  • Corrupted state: backup + restore defaults + critical log
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# Lazy import of memory to avoid circular imports at module load time.
# Used only inside _get_trusted_daily_dd() to read last known account state.
def _memory():
    from tools import memory as _m
    return _m

logger = logging.getLogger("matrix.adaptive_policy")

_STATE_DIR = Path(__file__).parent.parent / ".state"
_APE_FILE = _STATE_DIR / "adaptive_policy.json"

_MIN_RISK_MULTIPLIER = 0.3
_MAX_RISK_MULTIPLIER = 1.0
_MAX_PAUSE_HOURS = 24
_MAX_CONVICTION_HOURS = 24
_MAX_SKIP_HOURS = 3
_MAX_LOG_ENTRIES = 100
_RESET_RISK_COOLDOWN_HOURS = 2
_MIN_PAUSE_BEFORE_RESUME_HOURS = 1
_MAX_APE_CHANGES_PER_24H = 3
_MIN_SAME_TYPE_COOLDOWN_MINUTES = 30

VALID_SYMBOLS: frozenset[str] = frozenset({
    "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCHF", "USDCAD", "USDJPY",
    "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "CHFJPY", "CADJPY", "NZDJPY",
    "EURAUD", "EURCHF", "GBPCHF", "AUDCAD", "AUDNZD",
    "XAUUSD", "XAGUSD", "US30", "US500", "USTEC",
})

ALLOWED_TYPES = {
    "REDUCE_RISK",
    "RESET_RISK",
    "PAUSE_SYMBOL",
    "RESUME_SYMBOL",
    "TIGHTEN_CONVICTION",
    "RESET_CONVICTION",
    "SKIP_SESSION",
}

FORBIDDEN_TYPES = {
    "INCREASE_RISK",
    "ENABLE_LIVE",
    "CHANGE_DRAWDOWN_LIMITS",
    "USE_HFT",
    "USE_MARTINGALE",
    "USE_GRID",
    "COPY_TRADING",
    "CHANGE_CORE_STRATEGY",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _get_trusted_daily_dd() -> Optional[float]:
    """Read daily drawdown % from the last known cycle state (trusted internal source).
    Returns None if no data available — callers must treat None as 'data unavailable'
    and reject operations that require a trusted drawdown figure.
    """
    try:
        mem = _memory()
        # Try agent_state first (most recent snapshot)
        state = mem.get_state() or {}
        dd = state.get("daily_drawdown_pct")
        if dd is not None:
            return float(dd)
        # Fall back to last cycle
        cycle = mem.get_last_cycle() or {}
        acct = cycle.get("account") or {}
        dd2 = acct.get("daily_drawdown_pct")
        if dd2 is not None:
            return float(dd2)
        return None
    except Exception as e:
        logger.warning(f"APE: could not read trusted daily DD: {e}")
        return None


def _default_state() -> dict:
    return {
        "risk_multiplier": 1.0,
        "risk_multiplier_reason": None,
        "risk_multiplier_expires_at": None,
        "last_risk_change_ts": None,
        "paused_symbols": {},
        "conviction_override": None,
        "conviction_reason": None,
        "conviction_expires_at": None,
        "conviction_set_at": None,       # track when TIGHTEN_CONVICTION was applied
        # SKIP_SESSION: now uses a timestamp, NOT a boolean flag.
        # This prevents "only first symbol gets skipped" bug when risk_agent
        # is called per-symbol. Flag is active while now < skip_session_until.
        "skip_session_until": None,
        "skip_reason": None,
        "consecutive_losses": 0,
        "adaptation_log": [],
        # Anti-flapping: track recent change timestamps per type
        "recent_changes": [],
    }


def _load() -> dict:
    _STATE_DIR.mkdir(exist_ok=True)
    if not _APE_FILE.exists():
        return _default_state()
    try:
        with open(_APE_FILE) as f:
            data = json.load(f)
        # Migrate old boolean flag to new timestamp format
        if "skip_next_session" in data:
            if data.pop("skip_next_session", False):
                if not data.get("skip_session_until"):
                    data["skip_session_until"] = (_now() + timedelta(hours=2)).isoformat()
            data.setdefault("skip_session_until", None)
        return data
    except Exception as e:
        logger.critical(f"APE state corrupted ({e}) — backing up and restoring defaults")
        _backup_corrupted()
        return _default_state()


def _backup_corrupted() -> None:
    if _APE_FILE.exists():
        ts = _now().strftime("%Y%m%dT%H%M%S")
        backup = _APE_FILE.with_name(f"adaptive_policy.corrupted.{ts}.json")
        try:
            shutil.copy2(_APE_FILE, backup)
            logger.critical(f"APE: corrupted state backed up to {backup}")
        except Exception as be:
            logger.error(f"APE: could not back up corrupted state: {be}")


def _save(state: dict) -> None:
    """Atomic write: write to temp file then os.replace to avoid JSON corruption
    if two processes or threads write simultaneously."""
    _STATE_DIR.mkdir(exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=_STATE_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp_path, _APE_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            raise
    except Exception as e:
        logger.error(f"APE: could not save state: {e}")


def _expire_stale(state: dict) -> dict:
    now = _now()

    # Risk multiplier expiry
    exp = state.get("risk_multiplier_expires_at")
    if exp:
        try:
            if datetime.fromisoformat(exp) <= now:
                state["risk_multiplier"] = 1.0
                state["risk_multiplier_reason"] = None
                state["risk_multiplier_expires_at"] = None
                logger.info("APE: risk_multiplier expired → reset to 1.0")
        except Exception:
            pass

    # Symbol pause expiry
    active: dict = {}
    for sym, info in (state.get("paused_symbols") or {}).items():
        exp2 = info.get("expires_at")
        if exp2:
            try:
                if datetime.fromisoformat(exp2) > now:
                    active[sym] = info
                else:
                    logger.info(f"APE: pause on {sym} expired → resumed")
            except Exception:
                active[sym] = info
        else:
            active[sym] = info
    state["paused_symbols"] = active

    # Conviction override expiry (new: uses conviction_expires_at)
    conv_exp = state.get("conviction_expires_at")
    if conv_exp:
        try:
            if datetime.fromisoformat(conv_exp) <= now:
                state["conviction_override"] = None
                state["conviction_reason"] = None
                state["conviction_expires_at"] = None
                logger.info("APE: conviction_override expired → reset to default")
        except Exception:
            pass

    # Skip session expiry (timestamp-based, no boolean flag)
    skip_until = state.get("skip_session_until")
    if skip_until:
        try:
            if datetime.fromisoformat(skip_until) <= now:
                state["skip_session_until"] = None
                state["skip_reason"] = None
                logger.info("APE: skip_session_until expired → session active again")
        except Exception:
            pass

    # Prune recent_changes older than 24h
    changes = state.get("recent_changes") or []
    cutoff = (now - timedelta(hours=24)).isoformat()
    state["recent_changes"] = [c for c in changes if c.get("ts", "") >= cutoff]

    return state


def get_state() -> dict:
    state = _load()
    state = _expire_stale(state)
    _save(state)
    return state


def get_risk_multiplier() -> float:
    return float(get_state().get("risk_multiplier", 1.0))


def is_symbol_paused(symbol: str) -> tuple[bool, str]:
    state = get_state()
    info = (state.get("paused_symbols") or {}).get(symbol.upper())
    if info:
        return True, info.get("reason", "paused by adaptive policy")
    return False, ""


def get_conviction_override() -> Optional[float]:
    return get_state().get("conviction_override")


def should_skip_session() -> tuple[bool, str]:
    """
    Returns (True, reason) if the current time is within an active SKIP_SESSION
    window. Does NOT clear any state — the timestamp expires naturally, so this
    is safe to call once per symbol without the 'only first symbol gets skipped' bug.
    """
    state = get_state()
    skip_until = state.get("skip_session_until")
    if skip_until:
        try:
            if _now() < datetime.fromisoformat(skip_until):
                return True, state.get("skip_reason", "skipped by adaptive policy")
        except Exception:
            pass
    return False, ""


def increment_consecutive_losses() -> int:
    state = _load()
    state["consecutive_losses"] = int(state.get("consecutive_losses", 0)) + 1
    _save(state)
    return state["consecutive_losses"]


def reset_consecutive_losses() -> None:
    state = _load()
    state["consecutive_losses"] = 0
    _save(state)


def _check_rate_limit(state: dict, adaptation_type: str) -> Optional[str]:
    """Check anti-flapping limits. Returns error string if blocked, None if ok."""
    now = _now()
    changes = state.get("recent_changes") or []

    # Max 3 APE changes per 24h (all types combined)
    recent_24h = [c for c in changes if c.get("ts", "") >= (now - timedelta(hours=24)).isoformat()]
    if len(recent_24h) >= _MAX_APE_CHANGES_PER_24H:
        return (
            f"Anti-flapping: max {_MAX_APE_CHANGES_PER_24H} APE changes per 24h reached "
            f"({len(recent_24h)} already applied). Wait until older changes expire."
        )

    # Min 30 min between same type
    min_cutoff = (now - timedelta(minutes=_MIN_SAME_TYPE_COOLDOWN_MINUTES)).isoformat()
    same_type_recent = [
        c for c in changes
        if c.get("type") == adaptation_type and c.get("ts", "") >= min_cutoff
    ]
    if same_type_recent:
        return (
            f"Anti-flapping: {adaptation_type} was already applied within the last "
            f"{_MIN_SAME_TYPE_COOLDOWN_MINUTES} minutes. Wait before repeating."
        )

    return None


def _record_change(state: dict, adaptation_type: str) -> None:
    state.setdefault("recent_changes", []).append({
        "ts": _now_iso(),
        "type": adaptation_type,
    })
    state["recent_changes"] = state["recent_changes"][-50:]


def apply_adaptation(
    adaptation_type: str,
    reason: str,
    trigger_data: dict,
    expected_benefit: str,
    rollback_condition: str,
    fn_compliance_note: str = "Defensive only — no FundedNext rules violated",
    value: float | str | None = None,
    expires_hours: int | None = None,
    daily_dd_pct: float = 0.0,
    applied_by: str = "brain",
) -> dict:
    """
    Apply a defensive adaptation (brain tool or mistake_learner).
    Returns a result dict (success or error).

    daily_dd_pct: optionally pass current daily drawdown % for RESET_RISK guardrail.
    """
    if adaptation_type in FORBIDDEN_TYPES:
        return {
            "error": f"'{adaptation_type}' is in the FORBIDDEN list — requires human approval via Replit Secrets.",
            "forbidden_types": sorted(FORBIDDEN_TYPES),
            "allowed_types": sorted(ALLOWED_TYPES),
        }

    if adaptation_type not in ALLOWED_TYPES:
        return {
            "error": f"Unknown adaptation type '{adaptation_type}'.",
            "allowed_types": sorted(ALLOWED_TYPES),
        }

    state = _load()
    state = _expire_stale(state)
    now = _now()
    result_msg = ""

    # ── Anti-flapping check (skip for RESET_* which are less dangerous) ──────
    if adaptation_type not in {"RESET_RISK", "RESET_CONVICTION", "RESUME_SYMBOL"}:
        rate_err = _check_rate_limit(state, adaptation_type)
        if rate_err:
            return {"error": rate_err}

    # ────────────────────────────────────────────────────────────────
    if adaptation_type == "REDUCE_RISK":
        requested = float(value or 0.5)
        clamped = max(_MIN_RISK_MULTIPLIER, min(requested, _MAX_RISK_MULTIPLIER))
        current = float(state.get("risk_multiplier", 1.0))
        if clamped >= current:
            return {
                "error": "REDUCE_RISK rejected: requested value is not lower than current multiplier.",
                "current_multiplier": current,
                "requested": requested,
                "hint": "To raise risk you need human approval. Brain may only reduce.",
            }
        hours = min(expires_hours or 24, _MAX_PAUSE_HOURS)
        exp_iso = (now + timedelta(hours=hours)).isoformat()
        state["risk_multiplier"] = clamped
        state["risk_multiplier_reason"] = reason
        state["risk_multiplier_expires_at"] = exp_iso
        state["last_risk_change_ts"] = now.isoformat()
        result_msg = f"risk_multiplier → {clamped:.2f} (was {current:.2f}), expires {exp_iso}"

    elif adaptation_type == "RESET_RISK":
        # Guardrail 1: cooldown since last risk change
        last_change = state.get("last_risk_change_ts")
        if last_change:
            try:
                elapsed_h = (now - datetime.fromisoformat(last_change)).total_seconds() / 3600
                if elapsed_h < _RESET_RISK_COOLDOWN_HOURS:
                    return {
                        "error": (
                            f"RESET_RISK blocked: cooldown active. "
                            f"Must wait {_RESET_RISK_COOLDOWN_HOURS}h after last risk change "
                            f"({elapsed_h:.1f}h elapsed). Conditions must stabilise first."
                        ),
                        "last_change_ts": last_change,
                        "cooldown_hours": _RESET_RISK_COOLDOWN_HOURS,
                    }
            except Exception:
                pass
        # Guardrail 2: no active loss streak
        consecutive = int(state.get("consecutive_losses", 0))
        if consecutive > 0:
            return {
                "error": (
                    f"RESET_RISK blocked: {consecutive} consecutive loss(es) recorded. "
                    "Risk reset requires 0 consecutive losses. Wait for a winning trade "
                    "before restoring baseline risk."
                ),
                "consecutive_losses": consecutive,
            }
        # Guardrail 3: daily DD from TRUSTED INTERNAL SOURCE (not LLM-provided).
        # The LLM-passed daily_dd_pct parameter is intentionally ignored here.
        # We read from memory so the LLM cannot bypass this check by passing 0.0.
        trusted_dd = _get_trusted_daily_dd()
        if trusted_dd is None:
            return {
                "error": (
                    "RESET_RISK blocked: trusted daily drawdown data is unavailable "
                    "(no completed cycle yet). Run at least one full cycle before "
                    "resetting risk."
                ),
            }
        if trusted_dd >= 3.0:
            return {
                "error": (
                    f"RESET_RISK blocked: daily drawdown {trusted_dd:.2f}% >= 3.0% "
                    "(internal source — not LLM-provided). "
                    "Do not restore baseline risk when daily loss is elevated."
                ),
                "trusted_daily_dd_pct": trusted_dd,
            }
        state["risk_multiplier"] = 1.0
        state["risk_multiplier_reason"] = None
        state["risk_multiplier_expires_at"] = None
        state["last_risk_change_ts"] = now.isoformat()
        result_msg = f"risk_multiplier → 1.0 (baseline restored; verified daily DD={trusted_dd:.2f}% < 3%)"

    elif adaptation_type == "PAUSE_SYMBOL":
        sym = str(value or "").strip().upper()
        if not sym:
            return {"error": "PAUSE_SYMBOL requires value=<SYMBOL>"}
        if sym not in VALID_SYMBOLS:
            return {
                "error": f"PAUSE_SYMBOL rejected: '{sym}' is not in the approved trading universe.",
                "valid_symbols": sorted(VALID_SYMBOLS),
            }
        hours = min(expires_hours or 12, _MAX_PAUSE_HOURS)
        exp_iso = (now + timedelta(hours=hours)).isoformat()
        state.setdefault("paused_symbols", {})[sym] = {
            "reason": reason,
            "expires_at": exp_iso,
            "paused_at": now.isoformat(),
        }
        result_msg = f"{sym} paused for {hours}h (until {exp_iso})"

    elif adaptation_type == "RESUME_SYMBOL":
        sym = str(value or "").strip().upper()
        if not sym:
            return {"error": "RESUME_SYMBOL requires value=<SYMBOL>"}
        if sym not in VALID_SYMBOLS:
            return {
                "error": f"RESUME_SYMBOL rejected: '{sym}' is not in the approved trading universe.",
                "valid_symbols": sorted(VALID_SYMBOLS),
            }
        pause_info = (state.get("paused_symbols") or {}).get(sym)
        if pause_info:
            # Guard 1: minimum pause duration
            paused_at_str = pause_info.get("paused_at")
            if paused_at_str:
                try:
                    elapsed_h = (now - datetime.fromisoformat(paused_at_str)).total_seconds() / 3600
                    if elapsed_h < _MIN_PAUSE_BEFORE_RESUME_HOURS:
                        return {
                            "error": (
                                f"RESUME_SYMBOL blocked: {sym} was paused only {elapsed_h:.1f}h ago. "
                                f"Minimum pause duration is {_MIN_PAUSE_BEFORE_RESUME_HOURS}h. "
                                "Let the cooling-off period pass first."
                            ),
                            "paused_at": paused_at_str,
                            "elapsed_hours": round(elapsed_h, 2),
                        }
                except Exception:
                    pass
            # Guard 2: no active loss streak
            consecutive = int(state.get("consecutive_losses", 0))
            if consecutive > 0:
                return {
                    "error": (
                        f"RESUME_SYMBOL blocked: {consecutive} consecutive loss(es) still active. "
                        f"Clear loss streak before resuming {sym}."
                    ),
                    "consecutive_losses": consecutive,
                }
            # Guard 3: daily DD from trusted internal source
            trusted_dd = _get_trusted_daily_dd()
            if trusted_dd is not None and trusted_dd >= 2.0:
                return {
                    "error": (
                        f"RESUME_SYMBOL blocked: daily drawdown {trusted_dd:.2f}% >= 2.0%. "
                        f"Do not resume {sym} when daily loss is elevated."
                    ),
                    "trusted_daily_dd_pct": trusted_dd,
                }
            state.setdefault("paused_symbols", {}).pop(sym, None)
            result_msg = f"{sym} resumed after all safety checks passed"
        else:
            result_msg = f"{sym} was not paused"

    elif adaptation_type == "TIGHTEN_CONVICTION":
        requested = float(value or 0.70)
        clamped = max(0.55, min(requested, 0.85))
        hours = min(expires_hours or 12, _MAX_CONVICTION_HOURS)
        exp_iso = (now + timedelta(hours=hours)).isoformat()
        state["conviction_override"] = clamped
        state["conviction_reason"] = reason
        state["conviction_expires_at"] = exp_iso
        state["conviction_set_at"] = now.isoformat()   # track for RESET_CONVICTION cooldown
        result_msg = f"conviction_override → {clamped:.2f}, expires {exp_iso}"

    elif adaptation_type == "RESET_CONVICTION":
        # Guard 1: minimum cooldown since TIGHTEN_CONVICTION was applied (1h = ~1 cycle)
        conviction_set_at = state.get("conviction_set_at")
        if conviction_set_at:
            try:
                elapsed_h = (now - datetime.fromisoformat(conviction_set_at)).total_seconds() / 3600
                if elapsed_h < 1.0:
                    return {
                        "error": (
                            f"RESET_CONVICTION blocked: conviction was tightened only {elapsed_h:.1f}h ago. "
                            "Minimum cooldown is 1h (~1 full cycle). Wait before removing this guard."
                        ),
                        "conviction_set_at": conviction_set_at,
                        "elapsed_hours": round(elapsed_h, 2),
                    }
            except Exception:
                pass
        # Guard 2: no active loss streak
        consecutive = int(state.get("consecutive_losses", 0))
        if consecutive > 0:
            return {
                "error": (
                    f"RESET_CONVICTION blocked: {consecutive} consecutive loss(es) still active. "
                    "Clear loss streak before removing conviction tightening."
                ),
                "consecutive_losses": consecutive,
            }
        # Guard 3: daily DD check (soft — only block if elevated)
        trusted_dd = _get_trusted_daily_dd()
        if trusted_dd is not None and trusted_dd >= 2.0:
            return {
                "error": (
                    f"RESET_CONVICTION blocked: daily drawdown {trusted_dd:.2f}% >= 2.0%. "
                    "Keep conviction tightened until daily loss recovers."
                ),
                "trusted_daily_dd_pct": trusted_dd,
            }
        state["conviction_override"] = None
        state["conviction_reason"] = None
        state["conviction_expires_at"] = None
        state["conviction_set_at"] = None
        result_msg = "conviction_override cleared (safety checks passed)"

    elif adaptation_type == "SKIP_SESSION":
        # Use skip_session_until timestamp — safe to call per-symbol without clearing early.
        # Default: skip for current + next cycle window (2h covers one 60-min cycle with buffer).
        hours = min(expires_hours or 2, _MAX_SKIP_HOURS)
        skip_until_iso = (now + timedelta(hours=hours)).isoformat()
        state["skip_session_until"] = skip_until_iso
        state["skip_reason"] = reason
        result_msg = f"session skipped until {skip_until_iso} ({hours}h window)"

    # Record the change and log it
    _record_change(state, adaptation_type)

    log_entry = {
        "ts": now.isoformat(),
        "type": adaptation_type,
        "reason": reason,
        "trigger_data": trigger_data,
        "expected_benefit": expected_benefit,
        "rollback_condition": rollback_condition,
        "fn_compliance_note": fn_compliance_note,
        "result": result_msg,
        "applied_by": applied_by or "brain",
    }
    state.setdefault("adaptation_log", []).append(log_entry)
    state["adaptation_log"] = state["adaptation_log"][-_MAX_LOG_ENTRIES:]
    _save(state)

    logger.info(f"APE applied: {adaptation_type} — {result_msg}")
    return {
        "success": True,
        "adaptation_type": adaptation_type,
        "result": result_msg,
        "fn_compliance_note": fn_compliance_note,
        "current_state": {
            "risk_multiplier": state.get("risk_multiplier"),
            "paused_symbols": list((state.get("paused_symbols") or {}).keys()),
            "conviction_override": state.get("conviction_override"),
            "conviction_expires_at": state.get("conviction_expires_at"),
            "skip_session_until": state.get("skip_session_until"),
        },
    }


def get_snapshot() -> dict:
    state = get_state()
    now = _now()

    # Compute skip_session_active from timestamp
    skip_active = False
    skip_until = state.get("skip_session_until")
    if skip_until:
        try:
            skip_active = now < datetime.fromisoformat(skip_until)
        except Exception:
            pass

    changes_24h = len([
        c for c in (state.get("recent_changes") or [])
        if c.get("ts", "") >= (now - timedelta(hours=24)).isoformat()
    ])

    return {
        "risk_multiplier": state.get("risk_multiplier", 1.0),
        "risk_multiplier_reason": state.get("risk_multiplier_reason"),
        "risk_multiplier_expires_at": state.get("risk_multiplier_expires_at"),
        "paused_symbols": state.get("paused_symbols", {}),
        "conviction_override": state.get("conviction_override"),
        "conviction_reason": state.get("conviction_reason"),
        "conviction_expires_at": state.get("conviction_expires_at"),
        "skip_session_active": skip_active,
        "skip_session_until": skip_until,
        "skip_reason": state.get("skip_reason"),
        "consecutive_losses": state.get("consecutive_losses", 0),
        "ape_changes_last_24h": changes_24h,
        "ape_changes_remaining_24h": max(0, _MAX_APE_CHANGES_PER_24H - changes_24h),
        "adaptation_log": (state.get("adaptation_log") or [])[-20:],
        "allowed_adaptations": sorted(ALLOWED_TYPES),
        "forbidden_adaptations": sorted(FORBIDDEN_TYPES),
        "valid_symbols": sorted(VALID_SYMBOLS),
    }
