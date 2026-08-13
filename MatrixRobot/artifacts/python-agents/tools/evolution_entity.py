"""
Evolution Entity — autonomous continuous self-development on the VPS (cloud).

This is an independent background organism living inside Brain:
  • Runs 24/7 on ForexVPS (not laptop-only)
  • Every N minutes: harvest closed losses → investigate → change thinking
  • Consolidates lessons, escalates stubborn patterns to APE
  • Emits advice for code/config when humans must intervene
  • Advances a generation counter so progress is visible over time

Laptop RTX remains for HEAVY neural training only.
Live evolution / post-mortem / thinking change happens HERE on the cloud.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("matrix.evolution_entity")

_STATE_DIR = Path(__file__).parent.parent / ".state"
_FILE = _STATE_DIR / "evolution_entity.json"

_task: asyncio.Task | None = None
_running_tick = False
_last_tick: str | None = None
_last_result: dict | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _settings():
    from config import get_settings
    return get_settings()


def is_enabled(settings=None) -> bool:
    s = settings or _settings()
    return bool(getattr(s, "evolution_entity_enabled", True))


def _default() -> dict:
    return {
        "generation": 1,
        "ticks": 0,
        "investigations_done": 0,
        "lessons_consolidated": 0,
        "advice_emitted": 0,
        "last_tick_at": None,
        "last_digest_at": None,
        "processed_trade_ids": [],
        "progress_log": [],
        "started_at": None,
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
        logger.warning("evolution_entity load failed: %s", e)
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
        logger.error("evolution_entity save failed: %s", e)


def _trade_key(o: dict) -> str:
    tid = o.get("trade_id") or o.get("ticket")
    if tid is not None:
        return str(tid)
    return f"{o.get('symbol')}|{o.get('side')}|{o.get('closed_at') or o.get('ts')}|{o.get('pnl')}"


async def _harvest_unseen_losses(state: dict, limit: int = 30) -> list[dict]:
    from tools import memory

    outcomes = memory.get_recent_outcomes(limit=limit) or []
    seen = set(state.get("processed_trade_ids") or [])
    fresh = []
    for o in outcomes:
        try:
            pnl = float(o.get("pnl"))
        except (TypeError, ValueError):
            continue
        if pnl >= 0:
            continue
        key = _trade_key(o)
        if key in seen:
            continue
        fresh.append(o)
    return fresh


async def _investigate_batch(losses: list[dict], settings) -> list[dict]:
    from tools import loss_investigator

    results = []
    for o in losses:
        try:
            # Prefer async path (optional LLM narrative on cloud)
            r = await loss_investigator.investigate_loss_async(
                symbol=str(o.get("symbol") or ""),
                side=o.get("side"),
                pnl=float(o.get("pnl")),
                reason=o.get("close_reason") or o.get("reason"),
                trade_id=str(o.get("trade_id") or o.get("ticket") or ""),
                outcome=o,
                settings=settings,
            )
            results.append(r)
        except Exception as e:
            logger.warning("evolution investigate failed: %s", e)
            results.append({"error": str(e)})
        await asyncio.sleep(0.05)
    return results


def _consolidate(settings) -> dict:
    """Merge stubborn patterns → stronger APE / self_learning escalation."""
    from tools import loss_investigator, self_learning, adaptive_policy as ape

    biases = loss_investigator.get_thinking_biases()
    penalties = biases.get("symbol_side_penalty") or {}
    escalated = []
    for key, pen in list(penalties.items()):
        try:
            pen_f = float(pen)
        except Exception:
            continue
        if pen_f < 0.15:
            continue
        if ":" not in key:
            continue
        sym, side = key.split(":", 1)
        lesson = f"Evolution Entity gen-escalate: stubborn losses on {key} (penalty={pen_f})"
        try:
            ape.apply_adaptation(
                adaptation_type="PAUSE_SYMBOL",
                reason=lesson,
                trigger_data={"bias_key": key, "penalty": pen_f},
                expected_benefit="Stop repeating a proven failing setup",
                rollback_condition="Expires; human may resume after review",
                value=sym,
                expires_hours=18,
                applied_by="evolution_entity",
            )
            self_learning.record_event(
                layer="trade",
                kind="trade_loss",
                symbol=sym,
                side=side,
                reason=lesson,
                severity="critical",
                settings=settings,
            )
            escalated.append(key)
        except Exception as e:
            logger.debug("escalate %s failed: %s", key, e)
    return {"escalated": escalated, "penalty_keys": len(penalties)}


async def _maybe_digest(state: dict, settings, tick_result: dict) -> None:
    """Telegram digest so humans see continuous progress (not a silent loop)."""
    hours = float(getattr(settings, "evolution_digest_hours", 6))
    last = state.get("last_digest_at")
    if last:
        try:
            if _now() - datetime.fromisoformat(last) < timedelta(hours=hours):
                return
        except Exception:
            pass
    if not getattr(settings, "has_telegram", False):
        state["last_digest_at"] = _now_iso()
        return

    from tools import loss_investigator, self_learning, telegram_alerts

    li = loss_investigator.get_snapshot(settings)
    sl = self_learning.get_snapshot(settings)
    advice = (li.get("pending_advice") or [])[-5:]
    lines = [
        f"Evolution Entity — Generation {state.get('generation', 1)}",
        f"Ticks: {state.get('ticks', 0)} | Investigations: {state.get('investigations_done', 0)}",
        f"This tick: investigated={tick_result.get('investigated', 0)} "
        f"escalated={len((tick_result.get('consolidate') or {}).get('escalated') or [])}",
        f"Self-learning prevented: {(sl.get('stats') or {}).get('prevented', 0)}",
        f"Active blocks: {len(sl.get('active_blocks') or [])}",
    ]
    if advice:
        lines.append("Advice awaiting you:")
        for a in advice:
            lines.append(f"  [{a.get('type')}] {a.get('text')}")
    try:
        await telegram_alerts.send("\n".join(lines), level="info")
        state["advice_emitted"] = int(state.get("advice_emitted", 0)) + len(advice)
    except Exception as e:
        logger.debug("evolution digest telegram failed: %s", e)
    state["last_digest_at"] = _now_iso()


async def run_tick(force: bool = False) -> dict:
    """One evolution cycle — safe to call manually or from background loop."""
    global _running_tick, _last_tick, _last_result
    s = _settings()
    if not is_enabled(s) and not force:
        return {"ok": False, "reason": "evolution_entity_disabled"}
    if _running_tick:
        return {"ok": False, "reason": "tick_already_running"}

    _running_tick = True
    state = _load()
    if not state.get("started_at"):
        state["started_at"] = _now_iso()

    try:
        losses = await _harvest_unseen_losses(state)
        investigated = await _investigate_batch(losses, s) if losses else []

        for o, r in zip(losses, investigated):
            if r.get("error"):
                continue
            key = _trade_key(o)
            seen = state.setdefault("processed_trade_ids", [])
            if key not in seen:
                seen.append(key)
            state["processed_trade_ids"] = seen[-500:]

        ok_n = sum(1 for r in investigated if r.get("case") or r.get("enabled"))
        state["investigations_done"] = int(state.get("investigations_done", 0)) + ok_n

        consolidate = _consolidate(s)
        if consolidate.get("escalated"):
            state["lessons_consolidated"] = int(state.get("lessons_consolidated", 0)) + len(
                consolidate["escalated"]
            )

        state["ticks"] = int(state.get("ticks", 0)) + 1
        # Generation advances every 20 productive ticks or any escalation
        if state["ticks"] % 20 == 0 or consolidate.get("escalated"):
            state["generation"] = int(state.get("generation", 1)) + 1

        state["last_tick_at"] = _now_iso()
        tick_result = {
            "ok": True,
            "generation": state["generation"],
            "investigated": ok_n,
            "losses_seen": len(losses),
            "consolidate": consolidate,
            "ts": state["last_tick_at"],
        }
        state.setdefault("progress_log", []).append({
            "ts": state["last_tick_at"],
            "generation": state["generation"],
            "investigated": ok_n,
            "escalated": consolidate.get("escalated") or [],
        })
        state["progress_log"] = state["progress_log"][-80:]

        await _maybe_digest(state, s, tick_result)
        _save(state)

        _last_tick = state["last_tick_at"]
        _last_result = tick_result
        logger.info(
            "Evolution Entity tick gen=%s investigated=%s escalated=%s",
            state["generation"], ok_n, consolidate.get("escalated"),
        )
        return tick_result
    except Exception as e:
        _last_result = {"ok": False, "error": str(e)}
        logger.exception("Evolution Entity tick failed")
        return _last_result
    finally:
        _running_tick = False


async def _loop() -> None:
    s = _settings()
    # First tick soon after boot so cloud learning starts immediately
    await asyncio.sleep(20)
    while True:
        s = _settings()
        minutes = max(5, int(getattr(s, "evolution_entity_interval_minutes", 15)))
        if is_enabled(s):
            await run_tick()
        await asyncio.sleep(minutes * 60)


def start_background() -> None:
    global _task
    s = _settings()
    if not is_enabled(s):
        logger.info("Evolution Entity disabled")
        return
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    logger.info(
        "Evolution Entity started on CLOUD — every %s min (continuous self-development)",
        getattr(s, "evolution_entity_interval_minutes", 15),
    )


async def stop_background() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None


def get_snapshot(settings=None) -> dict:
    s = settings or _settings()
    state = _load()
    return {
        "enabled": is_enabled(s),
        "runs_on": "vps_cloud_brain",
        "laptop_role": "heavy_pytorch_training_only",
        "generation": state.get("generation", 1),
        "ticks": state.get("ticks", 0),
        "investigations_done": state.get("investigations_done", 0),
        "lessons_consolidated": state.get("lessons_consolidated", 0),
        "advice_emitted": state.get("advice_emitted", 0),
        "started_at": state.get("started_at"),
        "last_tick_at": state.get("last_tick_at") or _last_tick,
        "last_digest_at": state.get("last_digest_at"),
        "last_result": _last_result,
        "interval_minutes": int(getattr(s, "evolution_entity_interval_minutes", 15)),
        "tick_running": _running_tick,
        "background_alive": bool(_task and not _task.done()),
        "recent_progress": (state.get("progress_log") or [])[-15:],
        "mission_ar": (
            "كيان مستقل على السحابة يطوّر نفسه باستمرار: يحقق في الخسائر، "
            "يغيّر تفكير الروبوت، يمنع التكرار، ويرسل نصائح عند الحاجة — "
            "حتى لا ندور في حلقة مفرغة."
        ),
    }
