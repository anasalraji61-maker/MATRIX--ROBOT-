from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


class Quote(BaseModel):
    symbol: str
    bid: float
    ask: float
    mid: float
    change_pct: float
    timestamp: str


class NewsItem(BaseModel):
    title: str
    summary: str
    publisher: str
    published_at: str
    sentiment_hint: Optional[str] = None  # positive | negative | neutral


class Indicators(BaseModel):
    symbol: str
    # Momentum
    rsi_14: Optional[float] = None
    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None
    williams_r: Optional[float] = None
    # Trend
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    ema_200: Optional[float] = None
    adx_14: Optional[float] = None             # trend strength (0-100)
    di_plus: Optional[float] = None
    di_minus: Optional[float] = None
    # Volatility
    bb_upper: Optional[float] = None
    bb_mid: Optional[float] = None
    bb_lower: Optional[float] = None
    bb_width_pct: Optional[float] = None       # (upper-lower)/mid * 100
    atr_14: Optional[float] = None
    # Ichimoku (simplified)
    ichimoku_tenkan: Optional[float] = None
    ichimoku_kijun: Optional[float] = None
    ichimoku_above_cloud: Optional[bool] = None
    # Levels
    pivot: Optional[float] = None              # classic daily pivot
    pivot_r1: Optional[float] = None
    pivot_s1: Optional[float] = None
    pivot_r2: Optional[float] = None
    pivot_s2: Optional[float] = None
    # Swing-based S/R + Fibonacci
    support: Optional[float] = None
    resistance: Optional[float] = None
    fib_382: Optional[float] = None
    fib_500: Optional[float] = None
    fib_618: Optional[float] = None
    # Aggregated
    trend: str = "neutral"  # bullish | bearish | neutral
    momentum: str = "neutral"  # bullish | bearish | neutral
    volatility_regime: str = "normal"  # low | normal | high


class TimeframeTrend(BaseModel):
    timeframe: str  # M15 | H1 | H4 | D1
    trend: str      # bullish | bearish | neutral
    rsi_14: Optional[float] = None
    adx_14: Optional[float] = None


class MultiTimeframeView(BaseModel):
    symbol: str
    timeframes: list[TimeframeTrend] = []
    consensus: str = "neutral"        # bullish | bearish | mixed | neutral
    aligned_count: int = 0            # how many TFs agree
    score: float = 0.0                # -1.0 .. +1.0


class CorrelationGroup(BaseModel):
    name: str
    members: list[str]
    open_direction: Optional[str] = None  # BUY | SELL | None


class CorrelationReport(BaseModel):
    groups: list[CorrelationGroup] = []
    blocked_pairs: list[str] = []         # symbols currently blocked due to existing correlated exposure


class VolatilityRegime(BaseModel):
    symbol: str
    atr_14: Optional[float] = None
    atr_percentile: Optional[float] = None  # 0..100 vs lookback
    regime: str = "normal"                  # low | normal | high
    size_multiplier: float = 1.0            # apply to base lot size


class EconomicEvent(BaseModel):
    title: str
    currency: str
    impact: str  # LOW | MEDIUM | HIGH
    when_iso: str
    minutes_until: int


class EconomicCalendar(BaseModel):
    in_blackout: bool = False
    blackout_reason: str = ""
    affected_currencies: list[str] = []
    upcoming: list[EconomicEvent] = []
    source: str = "internal"


class SentimentResult(BaseModel):
    score: float  # -1.0 to +1.0
    label: str    # POSITIVE | NEGATIVE | NEUTRAL
    confidence: float
    news_count: int
    source: str   # finbert | mock


class AnalysisResult(BaseModel):
    symbol: str
    signal: str         # BUY | SELL | HOLD
    strength: float     # 0.0–1.0 conviction
    reasons: list[str]
    indicators_summary: str
    llm_analysis: Optional[str] = None
    source: str = "rule-based"  # llm | rule-based


class RiskAssessment(BaseModel):
    approved: bool
    reason: str
    position_size_lots: float
    stop_loss_pips: int
    take_profit_pips: int
    risk_reward_ratio: float
    current_daily_drawdown_pct: float
    current_total_drawdown_pct: float


class SupervisorDecision(BaseModel):
    action: str         # BUY | SELL | HOLD | FREEZE
    symbol: str
    confidence: float
    reasoning: str
    risk_note: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ExecutionResult(BaseModel):
    executed: bool
    mode: str           # PAPER_MODE | ACTIVE
    trade_id: Optional[str] = None
    symbol: Optional[str] = None
    action: Optional[str] = None
    lots: Optional[float] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    message: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class CycleResult(BaseModel):
    model_config = {"extra": "allow"}

    cycle_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    started_at: str
    finished_at: Optional[str] = None
    status: str = "running"  # running | completed | failed | frozen
    mode: str = "PAPER_MODE"
    symbols_analyzed: list[str] = []
    decision: Optional[SupervisorDecision] = None
    execution: Optional[ExecutionResult] = None
    errors: list[str] = []
    duration_ms: Optional[int] = None
    # Agentic brain output + FN compliance snapshot
    analyses: Optional[list[dict]] = None
    prop_status: Optional[dict] = None
    account: Optional[dict] = None
    risk: Optional[dict] = None


class AgentState(BaseModel):
    mode: str
    last_cycle_id: Optional[str] = None
    last_cycle_at: Optional[str] = None
    last_decision: Optional[str] = None
    daily_drawdown_pct: float = 0.0
    total_drawdown_pct: float = 0.0
    open_positions: int = 0
    cycles_today: int = 0
    is_ready: bool = False


class HealthResponse(BaseModel):
    status: str
    version: str = "1.0.0"
    mode: str
    llm_provider: str
    services: dict[str, bool]
    uptime_seconds: float
