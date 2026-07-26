"""
Contextual bandit RL — learns per (symbol, side) Q-values from closed trade PnL.

Lightweight online learner (no PyTorch in Brain hot path). Updates on each
trade_outcome; filters weak arms in enforce mode.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("matrix.rl")

_STATE_DIR = Path(__file__).resolve().parents[2] / ".state"
_POLICY_FILE = _STATE_DIR / "rl_policy.json"

_policy: "RLPolicy | None" = None


def _arm_key(symbol: str, signal: str) -> str:
    return f"{(symbol or '').upper()}:{(signal or '').upper()}"


class RLPolicy:
    def __init__(self, learning_rate: float = 0.12, min_samples: int = 3):
        self.learning_rate = learning_rate
        self.min_samples = min_samples
        self.q: dict[str, float] = {}
        self.n: dict[str, int] = {}
        self.total_updates: int = 0

    def q_value(self, symbol: str, signal: str) -> float:
        return float(self.q.get(_arm_key(symbol, signal), 0.0))

    def sample_count(self, symbol: str, signal: str) -> int:
        return int(self.n.get(_arm_key(symbol, signal), 0))

    def score(self, symbol: str, signal: str) -> dict[str, Any]:
        q = self.q_value(symbol, signal)
        n = self.sample_count(symbol, signal)
        return {
            "arm": _arm_key(symbol, signal),
            "q_value": round(q, 4),
            "samples": n,
            "explore": n < self.min_samples,
        }

    def record_outcome(
        self,
        symbol: str,
        signal: str,
        pnl: float,
        *,
        learning_rate: float | None = None,
    ) -> dict[str, Any]:
        key = _arm_key(symbol, signal)
        lr = learning_rate if learning_rate is not None else self.learning_rate
        reward = max(-1.0, min(1.0, float(pnl) / 50.0))
        old_q = float(self.q.get(key, 0.0))
        new_q = old_q + lr * (reward - old_q)
        self.q[key] = round(new_q, 5)
        self.n[key] = self.n.get(key, 0) + 1
        self.total_updates += 1
        self.save()
        return {
            "arm": key,
            "reward": round(reward, 4),
            "q_value": self.q[key],
            "samples": self.n[key],
        }

    def to_dict(self) -> dict:
        return {
            "q": self.q,
            "n": self.n,
            "total_updates": self.total_updates,
            "learning_rate": self.learning_rate,
            "min_samples": self.min_samples,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RLPolicy":
        p = cls(
            learning_rate=float(data.get("learning_rate", 0.12)),
            min_samples=int(data.get("min_samples", 3)),
        )
        p.q = {str(k): float(v) for k, v in (data.get("q") or {}).items()}
        p.n = {str(k): int(v) for k, v in (data.get("n") or {}).items()}
        p.total_updates = int(data.get("total_updates", 0))
        return p

    def save(self) -> None:
        _STATE_DIR.mkdir(exist_ok=True)
        tmp = _POLICY_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        os.replace(tmp, _POLICY_FILE)

    @classmethod
    def load(cls, learning_rate: float = 0.12) -> "RLPolicy":
        if not _POLICY_FILE.exists():
            return cls(learning_rate=learning_rate)
        try:
            with open(_POLICY_FILE, encoding="utf-8") as f:
                data = json.load(f)
            p = cls.from_dict(data)
            p.learning_rate = learning_rate
            return p
        except Exception as e:
            logger.warning("RL policy load failed: %s — starting fresh", e)
            return cls(learning_rate=learning_rate)


def get_policy(settings=None) -> RLPolicy:
    global _policy
    from config import get_settings

    s = settings or get_settings()
    lr = float(getattr(s, "rl_learning_rate", 0.12))
    if _policy is None:
        _policy = RLPolicy.load(lr)
    return _policy
