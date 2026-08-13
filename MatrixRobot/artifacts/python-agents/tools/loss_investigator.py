"""
Loss Investigator — post-mortem on losing trades.

This is the layer the user actually asked for:
  1. Reconstruct WHY the robot entered the losing trade (brain reasoning)
  2. Diagnose root causes (session, strength, SL, news, flip-flop, …)
  3. Change future THINKING (biases the brain + risk must respect)
  4. Emit human advice when CODE / CONFIG changes are needed

The fingerprint blocker in self_learning.py is only the immune system
(stop bleeding). This module is the doctor (diagnose + change behaviour).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("matrix.loss_investigator")

_STATE_DIR = Path(__file__).parent.parent / ".state"
_FILE = _STATE_DIR / "loss_investigations.json"
_BIASES_FILE = _STATE_DIR / "thinking_biases.json"
_MAX_CASES = 100
_MAX_ADVICE = 50


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _settings():
    from config import get_settings
    return get_settings()


def is_enabled(settings=None) -> bool:
    s = settings or _settings()
    return bool(getattr(s, "loss_investigator_enabled", True))


def _default_store() -> dict:
    return {"cases": [], "advice": [], "stats": {"investigated": 0, "biases_updated": 0}}


def _default_biases() -> dict:
    return {
        "symbol_side_penalty": {},   # "EURUSD:BUY" -> extra strength required
        "avoid_patterns": [],        # list of {pattern, reason, until}
        "global_notes": [],          # short notes injected into brain prompt
        "updated_at": None,
    }


def _load_json(path: Path, default: dict) -> dict:
    _STATE_DIR.mkdir(exist_ok=True)
    if not path.exists():
        return dict(default)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        out = dict(default)
        out.update(data or {})
        return out
    except Exception as e:
        logger.warning("load %s failed: %s", path, e)
        return dict(default)


def _save_json(path: Path, data: dict) -> None:
    _STATE_DIR.mkdir(exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(dir=_STATE_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
    except Exception as e:
        logger.error("save %s failed: %s", path, e)


def get_thinking_biases() -> dict:
    return _load_json(_BIASES_FILE, _default_biases())


def brain_context_notes(symbol: str | None = None, limit: int = 8) -> str:
    """Text injected into the brain so it CHANGES how it thinks."""
    biases = get_thinking_biases()
    lines: list[str] = ["LESSONS FROM PAST LOSING TRADES (must respect):"]
    for note in (biases.get("global_notes") or [])[-limit:]:
        lines.append(f"- {note}")
    sym = (symbol or "").upper()
    if sym:
        for key, pen in (biases.get("symbol_side_penalty") or {}).items():
            if key.startswith(sym + ":"):
                lines.append(
                    f"- Require +{float(pen):.2f} extra strength for {key} "
                    f"(repeated losses on this setup)."
                )
    for p in (biases.get("avoid_patterns") or [])[-limit:]:
        lines.append(f"- Avoid: {p.get('pattern')} — {p.get('reason')}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def _find_brain_decision(symbol: str, side: str | None) -> dict | None:
    hist: list = []
    try:
        from tools.memory import get_recent_decisions
        hist = get_recent_decisions(symbol=symbol, limit=20)
    except Exception:
        try:
            from tools.memory import retrieve
            hist = [
                h for h in (retrieve("brain_decisions") or [])
                if str(h.get("symbol", "")).upper() == symbol.upper()
            ][-20:]
        except Exception:
            hist = []

    side_u = (side or "").upper()
    for h in reversed(hist or []):
        sig = str(h.get("signal") or "").upper()
        if side_u and sig == side_u:
            return h
    return (hist or [None])[-1] if hist else None


def _diagnose(outcome: dict, brain: dict | None) -> dict[str, Any]:
    """Rule-based root-cause analysis of a losing trade."""
    causes: list[str] = []
    thinking_errors: list[str] = []
    code_advice: list[str] = []
    config_advice: list[str] = []

    symbol = str(outcome.get("symbol") or "").upper()
    side = str(outcome.get("side") or "").upper()
    pnl = float(outcome.get("pnl") or 0)
    reason = str(outcome.get("close_reason") or outcome.get("reason") or "").lower()
    strength = float(outcome.get("strength") or (brain or {}).get("strength") or 0)
    hold = outcome.get("hold_minutes")
    spread = outcome.get("spread_pips") or outcome.get("spread_at_entry")
    entry_reason = str(outcome.get("entry_reason") or (brain or {}).get("llm_analysis") or "")
    brain_reasons = list((brain or {}).get("reasons") or [])

    # --- Diagnose ---
    if "stop" in reason or reason in ("stop_loss", "sl"):
        causes.append("Closed by stop-loss — entry timing or SL distance failed.")
        thinking_errors.append("Accepted an entry that did not leave room for noise.")
        if hold is not None and float(hold) < 20:
            causes.append(f"Very short hold ({hold} min) — likely noise / bad session entry.")
            thinking_errors.append("Entered too early or during choppy conditions.")
            config_advice.append(
                "Consider raising off_session_min_strength or blocking this session window."
            )

    if strength and strength < 0.70:
        causes.append(f"Entry strength was only {strength:.2f} (marginal conviction).")
        thinking_errors.append("Robot treated a weak signal as tradeable.")
        config_advice.append(
            "Raise small_trade / min conviction thresholds, or keep FULL_POWER less aggressive."
        )

    if spread is not None:
        try:
            if float(spread) > 2.5 and symbol not in ("XAUUSD", "XAGUSD"):
                causes.append(f"Wide spread at entry ({spread}).")
                thinking_errors.append("Ignored liquidity cost.")
                code_advice.append(
                    "Tighten phase5_max_spread_pips_fx or fail closed on wide spread in ACTIVE."
                )
        except Exception:
            pass

    if brain_reasons:
        joined = " ".join(str(r) for r in brain_reasons).lower()
        if "against" in joined or "conflict" in joined or "mixed" in joined:
            causes.append("Brain itself noted conflicting evidence but still entered.")
            thinking_errors.append("Failed to HOLD when tools disagreed.")
            code_advice.append(
                "In agentic_brain prompt: force HOLD when MTF/ICT/sentiment conflict."
            )

    if entry_reason and any(w in entry_reason.lower() for w in ("maybe", "possible", "weak", "unclear")):
        causes.append("Language of reasoning was uncertain.")
        thinking_errors.append("Acted on uncertain narrative.")

    if abs(pnl) >= 30:
        causes.append(f"Large single loss ({pnl:.2f}) — sizing or DD guard may be too loose.")
        config_advice.append("Lower risk_per_trade or enable stricter APE after first big loss.")
        code_advice.append("Verify risk_sizing caps and max concurrent positions under FULL_POWER_DEMO.")

    if not causes:
        causes.append("Loss without a clear logged structural flaw — need richer entry snapshots.")
        code_advice.append(
            "Persist full indicator/MTF/ICT snapshot on open so post-mortems can diagnose better."
        )

    # Lesson for future thinking
    lesson = (
        f"On {symbol} {side}: do not repeat this setup. "
        + " ".join(thinking_errors[:2])
    )
    bias_key = f"{symbol}:{side}" if symbol and side in ("BUY", "SELL") else None
    extra_strength = 0.08 if strength and strength < 0.75 else 0.05

    return {
        "causes": causes,
        "thinking_errors": thinking_errors,
        "lesson": lesson,
        "bias_key": bias_key,
        "extra_strength": extra_strength,
        "code_advice": code_advice,
        "config_advice": config_advice,
        "brain_snapshot": {
            "signal": (brain or {}).get("signal"),
            "strength": (brain or {}).get("strength"),
            "reasons": brain_reasons[:8],
            "llm_analysis": str((brain or {}).get("llm_analysis") or "")[:500],
            "source": (brain or {}).get("source"),
        },
    }


async def _llm_deepen(case: dict, settings) -> str | None:
    """Optional deeper narrative via OpenRouter/OpenAI — never blocks the close path."""
    if not getattr(settings, "loss_investigator_use_llm", True):
        return None
    if not getattr(settings, "has_llm", False):
        return None
    try:
        from tools import llm_circuit
        prompt = (
            "You are a trading-system auditor. Given this losing-trade postmortem JSON, "
            "write 5-8 Arabic lines: (1) why the robot's thinking failed, "
            "(2) how it must think differently next time, "
            "(3) one concrete code or config change if needed. No fluff.\n\n"
            + json.dumps(case, ensure_ascii=False, default=str)[:3500]
        )
        if settings.effective_openrouter_key and llm_circuit.is_openrouter_available():
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=settings.primary_model,
                openai_api_key=settings.effective_openrouter_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.2,
                max_tokens=500,
                max_retries=0,
            )
            msg = await llm.ainvoke(prompt)
            return str(getattr(msg, "content", msg))[:1200]
    except Exception as e:
        logger.debug("LLM deepen skipped: %s", e)
    return None


def _apply_thinking_change(diagnosis: dict) -> None:
    biases = get_thinking_biases()
    key = diagnosis.get("bias_key")
    if key:
        pens = biases.setdefault("symbol_side_penalty", {})
        prev = float(pens.get(key, 0.0))
        pens[key] = round(min(0.25, prev + float(diagnosis.get("extra_strength") or 0.05)), 3)
    note = diagnosis.get("lesson")
    if note:
        notes = biases.setdefault("global_notes", [])
        if note not in notes:
            notes.append(note)
        biases["global_notes"] = notes[-40:]
    for pattern in diagnosis.get("thinking_errors") or []:
        biases.setdefault("avoid_patterns", []).append({
            "pattern": pattern,
            "reason": diagnosis.get("lesson"),
            "ts": _now_iso(),
        })
    biases["avoid_patterns"] = (biases.get("avoid_patterns") or [])[-40:]
    biases["updated_at"] = _now_iso()
    _save_json(_BIASES_FILE, biases)


def investigate_loss(
    *,
    symbol: str,
    side: str | None,
    pnl: float | None,
    reason: str | None = None,
    trade_id: str | None = None,
    outcome: dict | None = None,
    settings=None,
) -> dict[str, Any]:
    """Synchronous investigate path used from close_logger / self_learning."""
    s = settings or _settings()
    if not is_enabled(s):
        return {"enabled": False, "skipped": True}
    if pnl is None or float(pnl) >= 0:
        return {"enabled": True, "skipped": True, "reason": "not_a_loss"}

    outcome_d = dict(outcome or {})
    outcome_d.setdefault("symbol", symbol)
    outcome_d.setdefault("side", side)
    outcome_d.setdefault("pnl", pnl)
    outcome_d.setdefault("close_reason", reason)
    outcome_d.setdefault("trade_id", trade_id)

    brain = _find_brain_decision(symbol, side)
    diagnosis = _diagnose(outcome_d, brain)
    _apply_thinking_change(diagnosis)

    case = {
        "ts": _now_iso(),
        "trade_id": trade_id,
        "symbol": symbol,
        "side": side,
        "pnl": float(pnl),
        "close_reason": reason,
        "diagnosis": diagnosis,
        "llm_narrative": None,
        "human_summary_ar": _summary_ar(symbol, side, pnl, diagnosis),
    }

    store = _load_json(_FILE, _default_store())
    store.setdefault("cases", []).append(case)
    store["cases"] = store["cases"][-_MAX_CASES:]
    store["stats"]["investigated"] = int(store.get("stats", {}).get("investigated", 0)) + 1
    store["stats"]["biases_updated"] = int(store.get("stats", {}).get("biases_updated", 0)) + 1

    for adv in diagnosis.get("code_advice") or []:
        store.setdefault("advice", []).append({
            "ts": _now_iso(), "type": "code", "text": adv, "symbol": symbol,
        })
    for adv in diagnosis.get("config_advice") or []:
        store.setdefault("advice", []).append({
            "ts": _now_iso(), "type": "config", "text": adv, "symbol": symbol,
        })
    store["advice"] = store["advice"][-_MAX_ADVICE:]
    _save_json(_FILE, store)

    logger.info(
        "Loss investigated %s %s pnl=%.2f — %s",
        symbol, side, float(pnl), diagnosis.get("lesson"),
    )
    return {"enabled": True, "case": case}


def _summary_ar(symbol: str, side: str | None, pnl: float, diagnosis: dict) -> str:
    lines = [
        f"تحقيق خسارة: {symbol} {side or ''} — PnL={pnl:.2f}",
        "أخطاء التفكير:",
    ]
    for e in diagnosis.get("thinking_errors") or []:
        lines.append(f"  • {e}")
    lines.append("الأسباب:")
    for c in diagnosis.get("causes") or []:
        lines.append(f"  • {c}")
    if diagnosis.get("config_advice"):
        lines.append("نصيحة إعدادات:")
        for a in diagnosis["config_advice"]:
            lines.append(f"  • {a}")
    if diagnosis.get("code_advice"):
        lines.append("نصيحة برمجية:")
        for a in diagnosis["code_advice"]:
            lines.append(f"  • {a}")
    lines.append(f"الدرس للمستقبل: {diagnosis.get('lesson')}")
    return "\n".join(lines)


async def investigate_loss_async(**kwargs) -> dict:
    """Async wrapper — adds optional LLM narrative."""
    result = investigate_loss(**kwargs)
    if result.get("skipped") or not result.get("case"):
        return result
    s = kwargs.get("settings") or _settings()
    narrative = await _llm_deepen(result["case"], s)
    if narrative:
        result["case"]["llm_narrative"] = narrative
        store = _load_json(_FILE, _default_store())
        if store.get("cases"):
            store["cases"][-1]["llm_narrative"] = narrative
            _save_json(_FILE, store)
        try:
            from tools import telegram_alerts
            if s.has_telegram:
                await telegram_alerts.send(
                    f"تحقيق خسارة\n{result['case'].get('human_summary_ar', '')}\n\n{narrative[:800]}",
                    level="warning",
                )
        except Exception:
            pass
    return result


def strength_penalty(symbol: str, side: str) -> float:
    """Extra conviction the brain/risk must demand after repeated losses."""
    biases = get_thinking_biases()
    key = f"{(symbol or '').upper()}:{(side or '').upper()}"
    return float((biases.get("symbol_side_penalty") or {}).get(key, 0.0))


def get_snapshot(settings=None) -> dict:
    s = settings or _settings()
    store = _load_json(_FILE, _default_store())
    biases = get_thinking_biases()
    return {
        "enabled": is_enabled(s),
        "stats": store.get("stats") or {},
        "recent_cases": (store.get("cases") or [])[-10:],
        "pending_advice": (store.get("advice") or [])[-15:],
        "thinking_biases": {
            "symbol_side_penalty": biases.get("symbol_side_penalty"),
            "global_notes": (biases.get("global_notes") or [])[-10:],
            "avoid_patterns": (biases.get("avoid_patterns") or [])[-10:],
            "updated_at": biases.get("updated_at"),
        },
        "explainer_ar": (
            "هذه الطبقة تحقق في الصفقات الخاسرة: لماذا قرر العقل الدخول، "
            "ما خطأ التفكير، كيف يتغيّر التفكير لاحقاً، وما النصائح البرمجية/الإعدادية."
        ),
    }
