"""V11 Trading Council — unified brain + meta judge schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BrainOutput(BaseModel):
    brain: str
    symbol: str
    signal: Literal["buy", "sell", "hold", "reject"] = "hold"
    score: float = Field(ge=-1.0, le=1.0, default=0.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    suggested_strategy: str = "no_trade"
    suggested_tier: str = "watch"
    veto: bool = False
    veto_reason: str = ""
    short_reason: str = ""
    risk_notes: list[str] = Field(default_factory=list)


class MetaJudgeOutput(BaseModel):
    symbol: str
    final_action: Literal["BUY", "SELL", "HOLD"] = "HOLD"
    trade_style: Literal["SCALP", "INTRADAY", "SWING", "NONE"] = "NONE"
    tier: Literal["WATCH", "MICRO", "SMALL", "NORMAL"] = "WATCH"
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    meta_score: float = Field(ge=-1.0, le=1.0, default=0.0)
    selected_strategy: str = ""
    entry_reason: str = ""
    rejection_reason: str = ""
    vetoes: list[str] = Field(default_factory=list)
    approved_by: list[str] = Field(default_factory=list)
    rejected_by: list[str] = Field(default_factory=list)
    recommended_sl: float = 0.0
    recommended_tp: float = 0.0
    expected_hold_minutes: int = 0
    brains: list[BrainOutput] = Field(default_factory=list)
