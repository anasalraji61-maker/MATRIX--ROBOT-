from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # LLM — Gemini Flash preferred (free 1500/day), OpenRouter, then OpenAI
    gemini_api_key: str = ""
    google_api_key: str = ""  # alternate name used by AI Studio
    openrouter_api_key: str = ""
    openai_api_key: str = ""

    # Models — "gemini-flash-latest" routes to gemini-3.5-flash (free tier: 5 RPM)
    gemini_model: str = "gemini-2.5-flash"
    primary_model: str = "anthropic/claude-sonnet-4.5"
    fallback_model: str = "openai/gpt-4o-mini"

    # Market data
    polygon_api_key: str = ""
    twelve_data_api_key: str = ""

    # Broker
    mt5_login: str = ""
    mt5_password: str = ""
    mt5_server: str = ""
    mt5_bridge_url: str = ""  # HTTP bridge URL e.g. http://192.168.1.100:5555

    # Memory
    redis_url: str = ""

    # Security — shared secret for write-API authentication (same value as
    # MT5_BRIDGE_SECRET so no new secret is needed on either side).
    mt5_bridge_secret: str = ""
    # CORS allowed origins — comma-separated. Empty = localhost + 127.0.0.1 only.
    allowed_origins: str = ""
    # Expose /agents/docs and /agents/redoc (disable on hardened VPS)
    debug_docs: bool = False
    # Set DISABLE_SCHEDULER=true on Replit so the service acts as proxy-only.
    # The VPS brain is responsible for running cycles; Replit must NOT run its own.
    disable_scheduler: bool = False

    # Sentiment
    huggingface_api_key: str = ""

    # ── Internal risk targets (stricter than prop-firm hard caps) ─────
    # These trigger the bot's own "stop trading" before FundedNext's caps hit.
    max_daily_drawdown_pct: float = 4.0       # FN hard cap is 5% (1% buffer)
    max_total_drawdown_pct: float = 9.0       # FN hard cap is 10% (1% buffer)
    # Emergency circuit breaker: auto-liquidate ALL positions at this floating
    # daily DD, and hard-lock the day at max_daily_drawdown_pct (closes + halts).
    emergency_soft_cap_pct: float = 3.5       # liquidate all losing positions
    fn_max_daily_loss_pct: float = 5.0        # FN absolute hard cap (for reference)
    max_risk_per_trade_pct: float = 0.8       # 5 stopped trades = 4% daily
    max_total_open_risk_pct: float = 3.0      # cap sum of (open SL distances)
    # Safety buffer kept BELOW the internal DD target when sizing a new trade:
    # ensures one losing trade can never trigger our own stop-trade gate.
    sizing_safety_buffer_pct: float = 0.3

    # FundedNext extra rules (mandatory across PAPER and ACTIVE)
    max_trades_per_day: int = 20              # hard daily cap (counted at OPEN)
    min_position_hold_seconds: int = 60       # block close < 60s after open
    require_stop_loss: bool = True            # reject any order with sl_pips <= 0
    # FN consistency: a single day's profit cannot exceed N% of starting balance
    # (would be flagged as gambling / non-reproducible strategy on payout review)
    max_daily_profit_pct: float = 30.0

    # Concurrent trade limits
    max_concurrent_positions: int = 5         # aligned with risk caps
    min_conviction_threshold: float = 0.60    # min strength to open trade

    # ── FundedNext (or other prop firm) hard rules ────────────────────
    # The bot REFUSES any action that would cross these red lines.
    prop_firm: str = "FundedNext"
    prop_firm_plan: str = "Stellar 2-Step"
    prop_phase: str = "PHASE_1"               # PHASE_1 | PHASE_2 | FUNDED
    prop_starting_balance: float = 0.0        # 0 = auto-snapshot on first run
    prop_daily_loss_hard_cap_pct: float = 5.0
    prop_total_loss_hard_cap_pct: float = 10.0
    prop_min_trading_days: int = 5
    prop_consistency_max_day_share_pct: float = 40.0  # funded-phase rule
    prop_profit_target_pct: float = 8.0       # P1: 8%, P2: 5%, FUNDED: 0
    prop_allow_weekend_holding: bool = True   # FN allows; bot can override
    prop_allow_news_trading: bool = True      # FN allows; calendar guard still applies

    # ── FundedNext 2026 NEW rules (must be enforced) ──────────────────
    # Cumulative margin cap across ALL open positions. Breaching this even
    # without a loss = "risky behavior" flag + profit deduction.
    prop_margin_hard_cap_pct: float = 70.0
    prop_margin_internal_target_pct: float = 50.0  # internal stricter target
    # Funded-account only: total open-trade risk cap (sum of SL distances).
    # Stricter than the generic max_total_open_risk_pct (which is 3.0).
    prop_funded_open_risk_hard_cap_pct: float = 3.0
    # News window: on FUNDED phase only, ±5 min around HIGH-impact events,
    # profits are cut to 40% but losses are 100%. Internal policy: block
    # NEW trades in this window (existing trades can still be managed).
    prop_news_blackout_minutes: int = 5
    prop_news_blackout_funded_only: bool = True
    # XAUUSD leverage post Jan 2026 — 1:10 (was 1:100). Used to estimate
    # margin per lot for the 70% cap. Other instruments use FX defaults.
    prop_xau_leverage: int = 10
    prop_fx_leverage: int = 100
    # SL must be attached within N minutes of entry on funded — we always
    # send SL with the order so this is just a sanity check.
    prop_sl_required_within_seconds: int = 180

    # ── Account profile (controls which rule set is active) ───────────
    # FN_CHALLENGE = Phase 1/2 evaluation (strict caps, no scalping)
    # FN_FUNDED    = funded account (adds 3% open-risk + news haircut)
    # REAL         = personal money — relaxed (no daily trade cap, no
    #                concurrent cap, scalping allowed)
    account_profile: str = "FN_CHALLENGE"     # FN_CHALLENGE | FN_FUNDED | REAL

    # REAL-account overrides (only used when account_profile=REAL)
    real_max_trades_per_day: int = 200        # vs 20 on FN
    real_max_concurrent_positions: int = 20   # vs 5 on FN
    real_min_position_hold_seconds: int = 0   # scalping allowed
    real_exec_variance_enabled: bool = False  # disabled by default

    # Trading state: PAPER_MODE | ACTIVE | FROZEN
    trading_state: str = "PAPER_MODE"

    # Live trading gate — must be explicitly set to true in env to allow ACTIVE mode.
    # Even with MT5 configured, switching to ACTIVE is blocked unless this is true.
    # Set ALLOW_LIVE_TRADING=true in Replit Secrets only when ready for real execution.
    allow_live_trading: bool = False

    # Symbols to monitor — Forex + Metals + US Indices
    symbols: str = (
        "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,NZDUSD,USDCAD,"
        "EURGBP,EURJPY,GBPJPY,EURAUD,EURCHF,AUDJPY,CHFJPY,"
        "CADJPY,NZDJPY,GBPCHF,AUDCAD,AUDNZD,"
        "XAUUSD,XAGUSD,"
        "US30,US500,USTEC"
    )

    # ── Advanced Analytics ────────────────────────────────────
    # Multi-timeframe consensus / correlation guard / vol regime / calendar
    multi_timeframe_enabled: bool = True
    mtf_required_alignment: int = 2          # # of TFs that must align for high conviction
    correlation_guard_enabled: bool = True
    volatility_regime_enabled: bool = True
    economic_calendar_enabled: bool = True
    economic_calendar_pre_event_minutes: int = 10  # FN: blackout N min BEFORE HIGH events
    economic_calendar_post_event_minutes: int = 10  # FN: blackout N min AFTER HIGH events

    # ── ICT / SMC (Smart Money Concepts) ──────────────────────
    # Adds market-structure context (BOS / CHoCH / OB / FVG / liquidity /
    # premium-discount / killzones) on top of indicators + MTF. Strong
    # weight in the ensemble — funded-account friendly because every
    # entry has a structural reason.
    ict_smc_enabled: bool = True
    ict_killzones_only: bool = False        # if True, ignore signals outside killzones
    ict_min_confluence: int = 1             # require at least N ICT confluences for bias
    ict_ensemble_weight: float = 3.5        # weight in ensemble scoring (>= MTF=3.0)

    # ── Execution Variance (DISABLED — prop-firm compliance) ───────────
    # Execution variance — DISABLED by default. The bot is fully disclosed
    # as an EA to the prop firm. All lot sizes, SL/TP, and timing come
    # purely from the risk model. Only enable for personal multi-account
    # setups where copy-trading false-positives are a concern.
    # Configure via EXEC_VARIANCE_* environment variables only.
    exec_variance_enabled: bool = False
    exec_variance_lot_jitter_pct: float = 0.0
    exec_variance_pip_jitter: int = 0
    exec_variance_entry_delay_min_s: int = 0
    exec_variance_entry_delay_max_s: int = 0
    exec_variance_skip_signal_pct: float = 0.0
    exec_variance_schedule_jitter_pct: float = 0.0
    exec_variance_breaks_enabled: bool = False
    exec_variance_lunch_start_utc_h: int = 12
    exec_variance_lunch_end_utc_h: int = 13
    exec_variance_sleep_start_utc_h: int = 22
    exec_variance_sleep_end_utc_h: int = 5

    # ── Multi-account ─────────────────────────────────────────
    # JSON list of account dicts — see tools/accounts.py for schema.
    # Leave empty to use the legacy single MT5_* primary account.
    accounts_json: str = ""

    # API base path (proxy routing)
    base_path: str = "/agents"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def model_post_init(self, __context) -> None:
        # Strip whitespace/tabs from all key fields
        object.__setattr__(self, "polygon_api_key", self.polygon_api_key.strip())
        object.__setattr__(self, "twelve_data_api_key", self.twelve_data_api_key.strip())
        object.__setattr__(self, "gemini_api_key", self.gemini_api_key.strip())
        object.__setattr__(self, "google_api_key", self.google_api_key.strip())
        object.__setattr__(self, "openrouter_api_key", self.openrouter_api_key.strip())
        object.__setattr__(self, "openai_api_key", self.openai_api_key.strip())

    @property
    def effective_gemini_key(self) -> str:
        # Prefer GOOGLE_API_KEY (AI Studio standard), fall back to GEMINI_API_KEY
        return self.google_api_key or self.gemini_api_key or ""

    @property
    def symbol_list(self) -> list[str]:
        return [s.strip() for s in self.symbols.split(",")]

    @property
    def effective_openrouter_key(self) -> str:
        """Returns best available OpenRouter key. Prefers sk-or- prefixed keys."""
        for key in [self.openrouter_api_key, self.openai_api_key]:
            if key and key.startswith("sk-or-"):
                return key
        if self.openrouter_api_key:
            return self.openrouter_api_key
        return ""

    @property
    def effective_openai_key(self) -> str:
        """Returns OpenAI key only if it's a genuine OpenAI key."""
        if self.openai_api_key and not self.openai_api_key.startswith("sk-or-"):
            return self.openai_api_key
        return ""

    @property
    def has_llm(self) -> bool:
        return bool(
            self.effective_gemini_key
            or self.effective_openrouter_key
            or self.effective_openai_key
        )

    @property
    def has_polygon(self) -> bool:
        return bool(self.polygon_api_key)

    @property
    def has_twelve_data(self) -> bool:
        return bool(self.twelve_data_api_key)

    @property
    def has_mt5(self) -> bool:
        return bool(self.mt5_login and self.mt5_password and self.mt5_server)

    @property
    def has_redis(self) -> bool:
        return bool(self.redis_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
