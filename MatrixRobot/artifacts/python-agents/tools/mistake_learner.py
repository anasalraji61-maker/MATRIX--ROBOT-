"""
Mistake Learner — lightweight self-learning from closed-trade errors.

Unlike full ML/RL training (heavy), this module:
  1. Tracks consecutive losses (global + per symbol)
  2. Writes a small lesson journal to .state/
  3. Auto-applies defensive APE actions WITHOUT waiting for the LLM brain

This closes the gap where increment_consecutive_losses existed but was never
called, and APE only fired when the brain remembered to call it.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("matrix.mistake_learner")

_STATE_DIR = Path(__file__).parent.parent / ".state"
_FILE = _STATE_DIR / "mistake_learner.json"
_MAX_LESSONS = 80


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default() -> dict:
    return {
        "enabled": True,
        "consecutive_losses": 0,
        "consecutive_wins": 0,
        "symbol_streaks": {},  # SYM -> {"losses": n, "wins": n, "last_pnl": x}
        "lessons": [],
        "actions_applied": 0,
        "closes_seen": 0,
        "last_close_at": None,
    }


def _load() -> dict:
    _STATE_DIR.mkdir(exist_ok=True)
    if not _FILE.exists():
        return _default()
    try:
        with open(_FILE, encoding="utf-8") as f:
            data = json.load(f)
        base = _default()
        base.update(data or {})
        return base
    except Exception as e:
        logger.warning("mistake_learner load failed: %s", e)
        return _default()


def _save(state: dict) -> None:
    _STATE_DIR.mkdir(exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(dir=_STATE_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp, _FILE)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
    except Exception as e:
        logger.error("mistake_learner save failed: %s", e)


def _settings():
    from config import get_settings
    return get_settings()


def is_enabled(settings=None) -> bool:
    s = settings or _settings()
    return bool(getattr(s, "mistake_learner_enabled", True))


def get_snapshot(settings=None) -> dict:
    s = settings or _settings()
    st = _load()
    return {
        "enabled": is_enabled(s),
        "consecutive_losses": int(st.get("consecutive_losses", 0)),
        "consecutive_wins": int(st.get("consecutive_wins", 0)),
        "symbol_streaks": st.get("symbol_streaks") or {},
        "actions_applied": int(st.get("actions_applied", 0)),
        "closes_seen": int(st.get("closes_seen", 0)),
        "last_close_at": st.get("last_close_at"),
        "thresholds": {
            "pause_after_symbol_losses": int(
                getattr(s, "mistake_learner_pause_after_symbol_losses", 2)
            ),
            "reduce_risk_after": int(getattr(s, "mistake_learner_reduce_risk_after", 3)),
            "tighten_after": int(getattr(s, "mistake_learner_tighten_after", 4)),
            "skip_after": int(getattr(s, "mistake_learner_skip_after", 5)),
        },
        "recent_lessons": (st.get("lessons") or [])[-15:],
    }


def _add_lesson(state: dict, lesson: dict) -> None:
    state.setdefault("lessons", []).append(lesson)
    state["lessons"] = state["lessons"][-_MAX_LESSONS:]


def _apply_ape(
    adaptation_type: str,
    reason: str,
    trigger: dict,
    *,
    value: float | str | None = None,
    expires_hours: int | None = None,
) -> dict:
    from tools import adaptive_policy as ape

    return ape.apply_adaptation(
        adaptation_type=adaptation_type,
        reason=reason,
        trigger_data=trigger,
        expected_benefit="Reduce repeat losses after closed-trade mistakes",
        rollback_condition="Expires automatically or after winning streak",
        fn_compliance_note="Defensive auto-learner — no FN rule change",
        value=value,
        expires_hours=expires_hours,
        applied_by="mistake_learner",
    )


def on_trade_closed(
    *,
    symbol: str,
    side: str | None,
    pnl: float | None,
    reason: str | None = None,
    trade_id: str | None = None,
    settings=None,
) -> dict[str, Any]:
    """Hook from close_logger — update streaks and auto-adapt if needed."""
    s = settings or _settings()
    if not is_enabled(s):
        return {"enabled": False, "skipped": True}

    if pnl is None:
        return {"enabled": True, "skipped": True, "reason": "pnl_missing"}

    sym = (symbol or "").strip().upper()
    pnl_f = float(pnl)
    is_loss = pnl_f < 0
    is_win = pnl_f > 0

    state = _load()
    state["closes_seen"] = int(state.get("closes_seen", 0)) + 1
    state["last_close_at"] = _now_iso()

    streaks = state.setdefault("symbol_streaks", {})
    sym_info = streaks.setdefault(sym or "UNKNOWN", {"losses": 0, "wins": 0, "last_pnl": 0.0})

    actions: list[dict] = []
    lesson_type = "breakeven"

    if is_loss:
        lesson_type = "loss"
        state["consecutive_losses"] = int(state.get("consecutive_losses", 0)) + 1
        state["consecutive_wins"] = 0
        sym_info["losses"] = int(sym_info.get("losses", 0)) + 1
        sym_info["wins"] = 0
        try:
            from tools import adaptive_policy as ape
            ape.increment_consecutive_losses()
        except Exception as e:
            logger.debug("APE consecutive loss bump failed: %s", e)
    elif is_win:
        lesson_type = "win"
        state["consecutive_wins"] = int(state.get("consecutive_wins", 0)) + 1
        state["consecutive_losses"] = 0
        sym_info["wins"] = int(sym_info.get("wins", 0)) + 1
        sym_info["losses"] = 0
        try:
            from tools import adaptive_policy as ape
            ape.reset_consecutive_losses()
        except Exception as e:
            logger.debug("APE consecutive loss reset failed: %s", e)
    else:
        # flat — no streak change beyond journal
        pass

    sym_info["last_pnl"] = pnl_f
    if sym:
        streaks[sym] = sym_info

    consec = int(state.get("consecutive_losses", 0))
    sym_losses = int(sym_info.get("losses", 0)) if is_loss else 0

    pause_after = int(getattr(s, "mistake_learner_pause_after_symbol_losses", 2))
    reduce_after = int(getattr(s, "mistake_learner_reduce_risk_after", 3))
    tighten_after = int(getattr(s, "mistake_learner_tighten_after", 4))
    skip_after = int(getattr(s, "mistake_learner_skip_after", 5))

    trigger = {
        "symbol": sym,
        "side": side,
        "pnl": pnl_f,
        "close_reason": reason,
        "trade_id": trade_id,
        "consecutive_losses": consec,
        "symbol_losses": sym_losses,
    }

    if is_loss and sym and sym_losses >= pause_after:
        r = _apply_ape(
            "PAUSE_SYMBOL",
            f"Mistake learner: {sym} lost {sym_losses} times in a row (pnl={pnl_f:.2f})",
            trigger,
            value=sym,
            expires_hours=12,
        )
        actions.append({"type": "PAUSE_SYMBOL", "result": r})
        if r.get("success"):
            state["actions_applied"] = int(state.get("actions_applied", 0)) + 1

    if is_loss and consec >= reduce_after:
        r = _apply_ape(
            "REDUCE_RISK",
            f"Mistake learner: {consec} consecutive losses — cut size",
            trigger,
            value=0.5,
            expires_hours=24,
        )
        actions.append({"type": "REDUCE_RISK", "result": r})
        if r.get("success"):
            state["actions_applied"] = int(state.get("actions_applied", 0)) + 1

    if is_loss and consec >= tighten_after:
        r = _apply_ape(
            "TIGHTEN_CONVICTION",
            f"Mistake learner: {consec} consecutive losses — raise entry bar",
            trigger,
            value=0.75,
            expires_hours=12,
        )
        actions.append({"type": "TIGHTEN_CONVICTION", "result": r})
        if r.get("success"):
            state["actions_applied"] = int(state.get("actions_applied", 0)) + 1

    if is_loss and consec >= skip_after:
        r = _apply_ape(
            "SKIP_SESSION",
            f"Mistake learner: {consec} consecutive losses — sit out",
            trigger,
            expires_hours=2,
        )
        actions.append({"type": "SKIP_SESSION", "result": r})
        if r.get("success"):
            state["actions_applied"] = int(state.get("actions_applied", 0)) + 1

    lesson = {
        "ts": _now_iso(),
        "type": lesson_type,
        "symbol": sym,
        "side": side,
        "pnl": pnl_f,
        "close_reason": reason,
        "trade_id": trade_id,
        "consecutive_losses": consec,
        "symbol_losses": int(sym_info.get("losses", 0)),
        "actions": [
            {
                "type": a["type"],
                "ok": bool((a.get("result") or {}).get("success")),
                "detail": (a.get("result") or {}).get("result")
                or (a.get("result") or {}).get("error"),
            }
            for a in actions
        ],
    }
    _add_lesson(state, lesson)
    _save(state)

    if actions:
        logger.info(
            "Mistake learner adapted after %s %s pnl=%.2f: %s",
            sym,
            side,
            pnl_f,
            [a["type"] for a in actions],
        )
    else:
        logger.debug(
            "Mistake learner recorded %s %s pnl=%.2f (no auto-action)",
            sym,
            side,
            pnl_f,
        )

    return {
        "enabled": True,
        "lesson_type": lesson_type,
        "consecutive_losses": consec,
        "symbol_losses": int(sym_info.get("losses", 0)),
        "actions": actions,
        "lesson": lesson,
    }
