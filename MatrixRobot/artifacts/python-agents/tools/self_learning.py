"""
Self-Learning System — unified experience memory across the Matrix robot.

Purpose
-------
Learn from mistakes in EVERY layer (analysis, risk, supervisor, execution,
bridge, LLM, closes) and PREVENT the same fingerprint from repeating.

Design
------
  • Lightweight JSON state under .state/self_learning.json (no PyTorch in hot path)
  • Fingerprint = layer + kind + symbol + side + reason_code
  • After N hits within a time window → active BLOCK (symbol / side / pattern)
  • Blocks expire automatically
  • Delegates closed-trade streak defence to mistake_learner + APE
  • Heavy neural training stays on the laptop ML Lab; this module is the
    always-on immune system for live / paper cycles
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger("matrix.self_learning")

_STATE_DIR = Path(__file__).parent.parent / ".state"
_FILE = _STATE_DIR / "self_learning.json"
_MAX_EVENTS = 400
_MAX_BLOCKS = 80
_MAX_LESSONS = 120

# Layers covering the full robot stack
LAYERS = frozenset({
    "emergency",
    "data",
    "sentiment",
    "analysis",
    "council",
    "risk",
    "supervisor",
    "execution",
    "bridge",
    "llm",
    "trade",
    "session",
    "prop",
    "system",
})

KIND_CODES = frozenset({
    "trade_loss",
    "trade_win",
    "risk_reject",
    "supervisor_hold",
    "execution_fail",
    "bridge_fail",
    "llm_fail",
    "data_fail",
    "emergency_lock",
    "cycle_fail",
    "sl_hit",
    "repeat_blocked",
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _settings():
    from config import get_settings
    return get_settings()


def is_enabled(settings=None) -> bool:
    s = settings or _settings()
    return bool(getattr(s, "self_learning_enabled", True))


def _default() -> dict:
    return {
        "events": [],
        "blocks": [],
        "fingerprints": {},  # fp -> {count, first_ts, last_ts, layer, kind, ...}
        "lessons": [],
        "stats": {
            "events_total": 0,
            "blocks_created": 0,
            "blocks_hit": 0,
            "prevented": 0,
        },
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
        base["stats"] = {**_default()["stats"], **(base.get("stats") or {})}
        return base
    except Exception as e:
        logger.warning("self_learning load failed: %s", e)
        return _default()


def _save(state: dict) -> None:
    _STATE_DIR.mkdir(exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(dir=_STATE_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)
            os.replace(tmp, _FILE)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
    except Exception as e:
        logger.error("self_learning save failed: %s", e)


def _reason_code(message: str | None) -> str:
    raw = (message or "unknown").strip().lower()
    raw = re.sub(r"[0-9]+", "#", raw)
    raw = re.sub(r"\s+", " ", raw)
    return raw[:120]


def fingerprint(
    *,
    layer: str,
    kind: str,
    symbol: str | None = None,
    side: str | None = None,
    reason: str | None = None,
) -> str:
    key = "|".join([
        (layer or "system").lower(),
        (kind or "unknown").lower(),
        (symbol or "*").upper(),
        (side or "*").upper(),
        _reason_code(reason),
    ])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _expire_blocks(state: dict) -> dict:
    now = _now()
    active = []
    for b in state.get("blocks") or []:
        exp = b.get("expires_at")
        if not exp:
            active.append(b)
            continue
        try:
            if datetime.fromisoformat(exp) > now:
                active.append(b)
        except Exception:
            active.append(b)
    state["blocks"] = active[-_MAX_BLOCKS:]
    return state


def _block_match(block: dict, symbol: str | None, side: str | None) -> bool:
    bsym = (block.get("symbol") or "*").upper()
    bside = (block.get("side") or "*").upper()
    sym = (symbol or "").upper()
    sd = (side or "").upper()
    if bsym not in ("*", "") and sym and bsym != sym:
        return False
    if bside not in ("*", "") and sd and bside != sd:
        return False
    return True


def get_active_blocks(symbol: str | None = None, side: str | None = None) -> list[dict]:
    state = _expire_blocks(_load())
    _save(state)
    blocks = state.get("blocks") or []
    if symbol is None and side is None:
        return list(blocks)
    return [b for b in blocks if _block_match(b, symbol, side)]


def is_blocked(
    symbol: str | None = None,
    side: str | None = None,
    *,
    layer: str | None = None,
) -> tuple[bool, str]:
    """Return (blocked, reason) for a candidate symbol/side."""
    if not is_enabled():
        return False, ""
    for b in get_active_blocks(symbol, side):
        if layer and b.get("scope_layer") not in (None, "*", layer):
            continue
        reason = b.get("lesson") or b.get("reason") or "self-learning block"
        return True, str(reason)
    return False, ""


def _create_block(
    state: dict,
    *,
    fp: str,
    layer: str,
    kind: str,
    symbol: str | None,
    side: str | None,
    reason: str,
    hours: float,
    lesson: str,
) -> dict:
    exp = (_now() + timedelta(hours=max(0.5, hours))).isoformat()
    block = {
        "id": fp,
        "fingerprint": fp,
        "layer": layer,
        "kind": kind,
        "symbol": (symbol or "*").upper(),
        "side": (side or "*").upper(),
        "reason": reason,
        "lesson": lesson,
        "created_at": _now_iso(),
        "expires_at": exp,
        "scope_layer": "*",
    }
    # Replace same fingerprint block
    others = [b for b in (state.get("blocks") or []) if b.get("fingerprint") != fp]
    others.append(block)
    state["blocks"] = others[-_MAX_BLOCKS:]
    state["stats"]["blocks_created"] = int(state["stats"].get("blocks_created", 0)) + 1
    state.setdefault("lessons", []).append({
        "ts": _now_iso(),
        "fingerprint": fp,
        "lesson": lesson,
        "symbol": block["symbol"],
        "side": block["side"],
        "layer": layer,
        "kind": kind,
        "expires_at": exp,
    })
    state["lessons"] = state["lessons"][-_MAX_LESSONS:]
    return block


def record_event(
    *,
    layer: str,
    kind: str,
    symbol: str | None = None,
    side: str | None = None,
    reason: str | None = None,
    severity: str = "medium",
    meta: dict | None = None,
    settings=None,
) -> dict[str, Any]:
    """Record a system event; may create a prevention block on repeat."""
    s = settings or _settings()
    if not is_enabled(s):
        return {"enabled": False, "skipped": True}

    layer_n = (layer or "system").lower()
    kind_n = (kind or "unknown").lower()
    sym = (symbol or "").strip().upper() or None
    sd = (side or "").strip().upper() or None
    if sd and sd not in ("BUY", "SELL"):
        sd = None

    fp = fingerprint(layer=layer_n, kind=kind_n, symbol=sym, side=sd, reason=reason)
    state = _expire_blocks(_load())

    event = {
        "ts": _now_iso(),
        "fingerprint": fp,
        "layer": layer_n,
        "kind": kind_n,
        "symbol": sym or "*",
        "side": sd or "*",
        "reason": (reason or "")[:240],
        "severity": severity,
        "meta": meta or {},
    }
    state.setdefault("events", []).append(event)
    state["events"] = state["events"][-_MAX_EVENTS:]
    state["stats"]["events_total"] = int(state["stats"].get("events_total", 0)) + 1

    fp_info = state.setdefault("fingerprints", {}).get(fp) or {
        "count": 0,
        "first_ts": event["ts"],
        "layer": layer_n,
        "kind": kind_n,
        "symbol": sym or "*",
        "side": sd or "*",
        "reason": event["reason"],
    }
    fp_info["count"] = int(fp_info.get("count", 0)) + 1
    fp_info["last_ts"] = event["ts"]
    state["fingerprints"][fp] = fp_info

    threshold = int(getattr(s, "self_learning_repeat_threshold", 2))
    block_hours = float(getattr(s, "self_learning_block_hours", 12))
    if severity == "high":
        threshold = max(1, threshold - 1)
        block_hours = max(block_hours, 18)
    if severity == "critical":
        threshold = 1
        block_hours = max(block_hours, 24)

    created_block = None
    if kind_n not in ("trade_win",) and fp_info["count"] >= threshold:
        lesson = (
            f"Prevent repeat: {layer_n}/{kind_n} on {sym or '*'} {sd or '*'} — "
            f"seen {fp_info['count']}x. Cause: {event['reason'] or 'n/a'}"
        )
        created_block = _create_block(
            state,
            fp=fp,
            layer=layer_n,
            kind=kind_n,
            symbol=sym,
            side=sd,
            reason=event["reason"],
            hours=block_hours,
            lesson=lesson,
        )
        logger.warning("Self-learning BLOCK created: %s", lesson)
        # Escalate to APE for trade/risk/execution repeats
        if layer_n in ("trade", "risk", "execution", "supervisor") and sym:
            try:
                from tools import adaptive_policy as ape
                ape.apply_adaptation(
                    adaptation_type="PAUSE_SYMBOL",
                    reason=lesson,
                    trigger_data={"fingerprint": fp, "count": fp_info["count"]},
                    expected_benefit="Stop repeating the same losing pattern",
                    rollback_condition="Expires with self-learning block",
                    value=sym,
                    expires_hours=int(min(block_hours, 24)),
                    applied_by="self_learning",
                )
            except Exception as e:
                logger.debug("APE escalate skipped: %s", e)

    _save(state)
    return {
        "enabled": True,
        "fingerprint": fp,
        "count": fp_info["count"],
        "block": created_block,
        "event": event,
    }


def filter_analyses(analyses: Iterable[dict], settings=None) -> tuple[list[dict], list[dict]]:
    """Drop analyses blocked by self-learning. Returns (kept, removed)."""
    if not is_enabled(settings):
        return list(analyses), []
    kept, removed = [], []
    for a in analyses or []:
        sym = str(a.get("symbol") or "")
        side = str(a.get("signal") or a.get("side") or "")
        blocked, why = is_blocked(sym, side)
        if blocked and str(a.get("signal", "")).upper() in ("BUY", "SELL"):
            removed.append({**a, "self_learning_block": why})
            state = _load()
            state["stats"]["prevented"] = int(state["stats"].get("prevented", 0)) + 1
            state["stats"]["blocks_hit"] = int(state["stats"].get("blocks_hit", 0)) + 1
            _save(state)
        else:
            kept.append(a)
    return kept, removed


def filter_approved_trades(trades: list, settings=None) -> tuple[list, list[dict]]:
    """Filter ApprovedTrade-like objects or dicts."""
    if not is_enabled(settings):
        return list(trades), []
    kept, removed = [], []
    for t in trades or []:
        if hasattr(t, "symbol"):
            sym, side = t.symbol, t.signal
        else:
            sym = str(t.get("symbol") or "")
            side = str(t.get("signal") or t.get("side") or "")
        blocked, why = is_blocked(sym, side)
        if blocked:
            removed.append({"symbol": sym, "signal": side, "reason": why})
            state = _load()
            state["stats"]["prevented"] = int(state["stats"].get("prevented", 0)) + 1
            state["stats"]["blocks_hit"] = int(state["stats"].get("blocks_hit", 0)) + 1
            _save(state)
        else:
            kept.append(t)
    return kept, removed


def on_trade_closed(
    *,
    symbol: str,
    side: str | None,
    pnl: float | None,
    reason: str | None = None,
    trade_id: str | None = None,
    settings=None,
) -> dict[str, Any]:
    """Closed-trade hook: record + streak learner + prevent repeats."""
    s = settings or _settings()
    out: dict[str, Any] = {"self_learning": None, "mistake_learner": None}
    if pnl is None:
        return out

    if float(pnl) < 0:
        close_kind = "sl_hit" if "stop" in (reason or "").lower() else "trade_loss"
        out["self_learning"] = record_event(
            layer="trade",
            kind=close_kind,
            symbol=symbol,
            side=side,
            reason=reason or f"loss pnl={pnl}",
            severity="high" if abs(float(pnl)) >= 20 else "medium",
            meta={"pnl": pnl, "trade_id": trade_id},
            settings=s,
        )
    elif float(pnl) > 0:
        out["self_learning"] = record_event(
            layer="trade",
            kind="trade_win",
            symbol=symbol,
            side=side,
            reason=reason or f"win pnl={pnl}",
            severity="low",
            meta={"pnl": pnl, "trade_id": trade_id},
            settings=s,
        )

    try:
        from tools import mistake_learner
        out["mistake_learner"] = mistake_learner.on_trade_closed(
            symbol=symbol,
            side=side,
            pnl=pnl,
            reason=reason,
            trade_id=trade_id,
            settings=s,
        )
    except Exception as e:
        logger.warning("mistake_learner via self_learning failed: %s", e)
        out["mistake_learner"] = {"error": str(e)}

    # Deep post-mortem: why did the brain choose this loser? change thinking + advice
    if float(pnl) < 0:
        try:
            from tools import loss_investigator
            out["investigation"] = loss_investigator.investigate_loss(
                symbol=symbol,
                side=side,
                pnl=pnl,
                reason=reason,
                trade_id=trade_id,
                settings=s,
            )
        except Exception as e:
            logger.warning("loss investigator failed: %s", e)
            out["investigation"] = {"error": str(e)}
    return out


def ingest_cycle(final_state: dict, *, cycle_id: str | None = None, settings=None) -> dict:
    """Mine a finished cycle for mistakes across all layers."""
    s = settings or _settings()
    if not is_enabled(s):
        return {"enabled": False}

    recorded: list[dict] = []
    errors = list(final_state.get("errors") or [])
    for err in errors:
        msg = str(err)
        layer = "system"
        kind = "cycle_fail"
        severity = "medium"
        if "llm" in msg.lower() or "openai" in msg.lower() or "401" in msg:
            layer, kind, severity = "llm", "llm_fail", "high"
        elif "bridge" in msg.lower() or "mt5" in msg.lower():
            layer, kind, severity = "bridge", "bridge_fail", "high"
        elif "data" in msg.lower() or "twelve" in msg.lower():
            layer, kind, severity = "data", "data_fail", "medium"
        recorded.append(record_event(
            layer=layer, kind=kind, reason=msg, severity=severity,
            meta={"cycle_id": cycle_id}, settings=s,
        ))

    emergency = final_state.get("emergency") or {}
    if emergency.get("locked"):
        recorded.append(record_event(
            layer="emergency",
            kind="emergency_lock",
            reason=str((emergency.get("lockout") or {}).get("reason") or "locked"),
            severity="critical",
            meta={"cycle_id": cycle_id},
            settings=s,
        ))

    risk = final_state.get("risk") or {}
    for sym, reasons in (risk.get("rejections") or {}).items():
        for r in reasons or []:
            recorded.append(record_event(
                layer="risk",
                kind="risk_reject",
                symbol=sym,
                reason=str(r),
                severity="low",
                meta={"cycle_id": cycle_id},
                settings=s,
            ))

    decision = final_state.get("decision") or {}
    if str(decision.get("action", "")).upper() == "HOLD":
        note = decision.get("risk_note") or decision.get("reasoning") or "hold"
        # Only learn from "failed path" holds, not normal empty markets
        note_l = str(note).lower()
        if any(k in note_l for k in ("fail", "error", "reject", "block", "lock", "quarantine")):
            recorded.append(record_event(
                layer="supervisor",
                kind="supervisor_hold",
                symbol=decision.get("symbol"),
                reason=str(note)[:240],
                severity="medium",
                meta={"cycle_id": cycle_id},
                settings=s,
            ))

    for ex in final_state.get("executions") or []:
        if ex.get("executed"):
            continue
        msg = str(ex.get("message") or "execution failed")
        kind = "bridge_fail" if "bridge" in msg.lower() or "mt5" in msg.lower() else "execution_fail"
        recorded.append(record_event(
            layer="execution",
            kind=kind,
            symbol=ex.get("symbol"),
            side=ex.get("action"),
            reason=msg,
            severity="high",
            meta={"cycle_id": cycle_id},
            settings=s,
        ))
    primary = final_state.get("execution") or {}
    if primary and not primary.get("executed") and primary.get("message"):
        msg = str(primary.get("message"))
        if "hold" not in msg.lower() and "no supervisor" not in msg.lower():
            recorded.append(record_event(
                layer="execution",
                kind="execution_fail",
                symbol=primary.get("symbol"),
                side=primary.get("action"),
                reason=msg,
                severity="medium",
                meta={"cycle_id": cycle_id},
                settings=s,
            ))

    return {
        "enabled": True,
        "recorded": len(recorded),
        "blocks_created": sum(1 for r in recorded if r.get("block")),
    }


def get_snapshot(settings=None) -> dict:
    s = settings or _settings()
    state = _expire_blocks(_load())
    _save(state)
    fps = state.get("fingerprints") or {}
    top = sorted(fps.items(), key=lambda kv: int(kv[1].get("count", 0)), reverse=True)[:15]
    return {
        "enabled": is_enabled(s),
        "stats": state.get("stats") or {},
        "active_blocks": state.get("blocks") or [],
        "recent_events": (state.get("events") or [])[-25:],
        "recent_lessons": (state.get("lessons") or [])[-20:],
        "top_fingerprints": [
            {"fingerprint": k, **v} for k, v in top
        ],
        "thresholds": {
            "repeat_threshold": int(getattr(s, "self_learning_repeat_threshold", 2)),
            "block_hours": float(getattr(s, "self_learning_block_hours", 12)),
        },
        "covers_layers": sorted(LAYERS),
    }
