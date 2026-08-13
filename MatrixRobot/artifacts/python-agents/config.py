from pydantic_settings import BaseSettings
from functools import lru_cache

# Populate os.environ from .env so modules using os.getenv() (e.g. the MT5
# bridge secret header) work outside Replit, where secrets are real env vars.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Settings(BaseSettings):
    # LLM — Gemini Flash preferred (free 1500/day), OpenRouter, then OpenAI
    gemini_api_key: str = ""
    google_api_key: str = ""  # alternate name used by AI Studio
    openrouter_api_key: str = ""
    openai_api_key: str = ""

    # Models — "gemini-flash-latest" routes to gemini-3.5-flash (free tier: 5 RPM)
    gemini_model: str = "gemini-2.5-flash"
    primary_model: str = "openai/gpt-4o-mini"
    fallback_model: str = "openai/gpt-4o-mini"

    # Market data
    polygon_api_key: str = ""
    twelve_data_api_key: str = ""

    # Broker
    mt5_login: str = ""
    mt5_password: str = ""
    mt5_server: str = ""
    mt5_bridge_url: str = ""  # HTTP bridge URL e.g. http://192.168.1.100:5555

    # Memory — Supabase/Postgres (set DATABASE_URL in .env)
    redis_url: str = ""
    database_url: str = ""

    # Telegram alerts (free Bot API)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Scheduler — default 90 min between trading cycles
    scheduler_interval_minutes: int = 90
    auto_start_scheduler: bool = True

    # Embeddings for pgvector (OpenRouter)
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimensions: int = 1536

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
    max_trades_per_day: int = 30              # hard daily cap (counted at OPEN)
    min_position_hold_seconds: int = 60       # block close < 60s after open
    require_stop_loss: bool = True            # reject any order with sl_pips <= 0
    # FN consistency: a single day's profit cannot exceed N% of starting balance
    # (would be flagged as gambling / non-reproducible strategy on payout review)
    max_daily_profit_pct: float = 30.0

    # Concurrent trade limits
    max_concurrent_positions: int = 7         # FN demo primary — aligned with risk caps
    min_conviction_threshold: float = 0.60    # legacy floor; tiers override when enabled

    # ── Trade sizing tiers (same analysis quality, different risk budget) ──
    enable_small_trades: bool = True
    small_trade_min_strength: float = 0.60
    normal_trade_min_strength: float = 0.68
    small_trade_max_risk_pct: float = 0.25
    small_trade_max_per_day: int = 12
    small_trade_max_open: int = 4
    small_trade_require_rr_min: float = 1.2
    normal_trade_require_rr_min: float = 1.5

    # MT5 position reconciler — polls bridge locally (no LLM cost)
    position_reconcile_interval_seconds: int = 10

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

    # Micro-account sizing (helps very small REAL accounts not get rejected
    # solely because broker min-lot risk can't fit the default % budget).
    # Only affects compute_safe_sizing when account_profile=REAL and live equity
    # is <= real_micro_equity_threshold.
    real_micro_equity_threshold: float = 100.0
    real_micro_max_risk_per_trade_pct: float = 3.5
    real_micro_strength_floor_for_sizing: float = 0.8

    # Trading state: PAPER_MODE | ACTIVE | FROZEN
    trading_state: str = "PAPER_MODE"

    # Live trading gate — must be explicitly set to true in env to allow ACTIVE mode.
    # Even with MT5 configured, switching to ACTIVE is blocked unless this is true.
    # Set ALLOW_LIVE_TRADING=true in Replit Secrets only when ready for real execution.
    allow_live_trading: bool = False

    # Trading style: conservative | aggressive | scalp (see tools/trading_profiles.py)
    trading_profile: str = "conservative"
    primary_timeframe: str = "H1"   # H1 intraday; M5 when TRADING_PROFILE=scalp

    # ── V11 Full Power Demo profile ───────────────────────────────────
    trading_mode_profile: str = ""           # FULL_POWER_DEMO
    symbol_universe_mode: str = ""           # full_55
    run_24h_full_analysis: bool = False
    run_24h_all_systems: bool = False
    allow_24h_scalping: bool = True
    allow_24h_intraday: bool = True
    allow_24h_swing: bool = True
    allow_24h_normal_trades: bool = True
    allow_24h_small_trades: bool = True
    off_session_24h_max_open_trades: int = 4
    off_session_24h_max_trades_per_day: int = 20
    off_session_24h_risk_multiplier_normal: float = 0.35
    off_session_24h_risk_multiplier_small: float = 0.20
    full_analysis_all_symbols: bool = False
    deep_analysis_top_n: int = 15
    council_top_n: int = 8
    council_full_universe_debug: bool = False
    council_mode: str = "shadow"             # shadow | advisory | enforce
    i_understand_real_risk: bool = False
    intraday_max_trades_per_day: int = 10
    swing_max_trades_per_day: int = 3
    max_same_currency_exposure: int = 3
    max_correlated_trades: int = 2
    full_power_llm_top_n: int = 15
    scalping_use_trailing: bool = True
    scalping_use_breakeven: bool = True

    # Symbols — 48 FX + gold/silver + WTI/Brent + Dow/S&P/Nasdaq (see symbol_registry)
    symbols: str = ""  # default filled from symbol_registry in model_post_init

    # ── Advanced Analytics ────────────────────────────────────
    # Multi-timeframe consensus / correlation guard / vol regime / calendar
    multi_timeframe_enabled: bool = True
    mtf_required_alignment: int = 2          # # of TFs that must align for high conviction
    mtf_max_symbols: int = 12              # MTF deep fetch only for top N symbols per cycle
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

    # ── Multi-account ─────────────────────────────────────────
    # JSON list of account dicts — see tools/accounts.py for schema.
    # Leave empty to use the legacy single MT5_* primary account.
    accounts_json: str = ""

    # ── ML signal filter (Phase 3D) — NumPy JSON model, no torch in Brain ──
    ml_filter_enabled: bool = True
    ml_filter_mode: str = "shadow"          # shadow first 3-7 days, then enforce
    ml_retrain_enabled: bool = False
    ml_retrain_interval_hours: int = 168
    ml_retrain_symbols: str = "EURUSD,XAUUSD,GBPUSD,USDJPY,US500"
    ml_retrain_bars: int = 3000
    rl_enabled: bool = True
    rl_mode: str = "shadow"
    rl_min_q_value: float = -0.15             # block if learned Q below this
    rl_learning_rate: float = 0.12

    # ── Evolution Entity (autonomous continuous self-development on VPS) ──
    evolution_entity_enabled: bool = True
    evolution_entity_interval_minutes: int = 15
    evolution_digest_hours: float = 6.0

    # ── Self-learning immune system (all layers — prevent repeat mistakes) ──
    self_learning_enabled: bool = True
    self_learning_repeat_threshold: int = 2   # same fingerprint → block
    self_learning_block_hours: float = 12.0

    # ── Loss investigator (post-mortem: why brain lost + change thinking + advice) ──
    loss_investigator_enabled: bool = True
    loss_investigator_use_llm: bool = True

    # ── Mistake learner (auto defensive APE from closed losses — lightweight) ──
    # Not full ML training; tracks streaks and applies PAUSE / REDUCE_RISK / etc.
    mistake_learner_enabled: bool = True
    mistake_learner_pause_after_symbol_losses: int = 2
    mistake_learner_reduce_risk_after: int = 3
    mistake_learner_tighten_after: int = 4
    mistake_learner_skip_after: int = 5
    ml_min_win_prob: float = 0.38           # veto if model win_prob below this
    ml_model_path: str = "ml_models/signal_EURUSD_XAUUSD_2000bars.pt"
    ml_model_json_path: str = ""            # empty = auto .json next to .pt

    # ── Phase 5: Intraday Adaptive (session + position manager) ───────
    phase5_intraday_enabled: bool = True
    phase5_session_require_killzone: bool = False  # extended mode trades off-session (SMALL)
    phase5_block_low_liquidity: bool = False       # extended mode — FX allowed off-session
    phase5_scheduler_adaptive: bool = True
    phase5_scheduler_high_liq_minutes: int = 30   # London/NY
    phase5_scheduler_medium_liq_minutes: int = 45  # Asian
    phase5_scheduler_low_liq_minutes: int = 30     # off-session (extended 24h)
    # Session filter: 24h (all systems) | extended | tiered | strict | off
    session_filter_mode: str = "extended"
    tiered_block_metals_outside_kz: bool = True
    tiered_block_oil_outside_kz: bool = True
    tiered_block_indices_outside_kz: bool = True
    off_session_min_strength: float = 0.80
    allow_off_session_small_trades: bool = True
    off_session_trade_tier: str = "SMALL"
    off_session_risk_multiplier: float = 0.15
    off_session_max_open_trades: int = 1
    off_session_max_trades_per_day: int = 2
    off_session_require_spread_ok: bool = True
    off_session_require_no_news: bool = True
    off_session_require_data_clean: bool = True
    off_session_min_rr: float = 1.8
    off_session_allowed_assets: str = "FX_ONLY"
    # Smart Watcher — scanner outside killzones; escalates strong SMALL to Brain
    smart_watcher_enabled: bool = True
    off_session_scanner_minutes: int = 30
    off_session_maintenance_minutes: int = 15
    off_session_escalation_min_strength: float = 0.80
    off_session_max_brain_escalations: int = 3
    off_session_scan_fx_only: bool = True
    # Demo only: allow scanner cycle to execute SMALL trades outside killzone
    smart_watcher_execute_off_session_small: bool = False
    estimated_full_cycle_cost_usd: float = 0.06
    estimated_scanner_cycle_cost_usd: float = 0.02
    estimated_maintenance_cycle_cost_usd: float = 0.005
    estimated_brain_escalation_cost_usd: float = 0.06
    phase5_sl_atr_mult_high: float = 1.0
    phase5_sl_atr_mult_medium: float = 1.25
    phase5_sl_atr_mult_low: float = 1.5
    phase5_tp_rr_high: float = 1.5
    phase5_tp_rr_medium: float = 1.75
    phase5_tp_rr_low: float = 2.0
    phase5_position_manager_enabled: bool = True
    phase5_max_hold_hours: float = 8.0
    phase5_breakeven_at_r: float = 1.0
    phase5_trail_start_r: float = 1.5
    phase5_trail_lock_r: float = 0.5           # lock this many R once trailing starts
    phase5_session_end_exit: bool = True       # close stale trades entering low-liq window
    phase5_liquidity_guard_enabled: bool = True
    phase5_max_spread_pips_fx: float = 3.0
    phase5_max_spread_pips_xau: float = 50.0
    phase5_max_spread_pips_index: float = 30.0
    phase5_max_spread_pips_oil: float = 8.0

    # ── V11: Scalping Engine (separate from V10 intraday/swing — demo-first) ──
    scalping_enabled: bool = False
    scalping_demo_only: bool = True
    scalping_mode: str = "shadow"              # shadow | advisory | enforce
    scalping_allowed_assets: str = "FX_ONLY"   # FX_ONLY — no metals/indices/oil initially
    scalping_timeframes: str = "M1,M5,M15"
    scalping_max_trades_per_day: int = 10
    scalping_max_open_trades: int = 2
    scalping_risk_multiplier: float = 0.10
    scalping_min_strength: float = 0.62
    scalping_min_rr: float = 1.1
    scalping_max_hold_minutes: int = 30
    scalping_sl_pips_min: float = 3.0
    scalping_sl_pips_max: float = 8.0
    scalping_tp_pips_min: float = 3.0
    scalping_tp_pips_max: float = 10.0
    scalping_max_spread_pips_fx: float = 2.0
    # 55-symbol funnel — cheap scan always; deep/GPT only for top N
    scanner_universe_use_full_registry: bool = True
    cheap_scan_top_deep: int = 10
    council_top_candidates: int = 5
    council_gpt_top_n: int = 3
    council_enabled: bool = True

    # ── Phase 6: Professional hardening (ChatGPT review fixes) ────────
    prop_server_utc_offset_hours: int = 3       # FundedNext server ~ GMT+2/+3
    active_fail_closed_data: bool = True        # block ACTIVE on mock quotes/bars/news
    active_data_per_symbol_quarantine: bool = True  # one bad symbol must not block all
    active_data_global_block_ratio: float = 0.5   # block cycle if >=50% symbols stale
    active_disabled_symbols: str = "US30,US500,USTEC"
    # Surgical hotfix — session quarantine + CHF/time/XAGUSD (ChatGPT review)
    symbol_quarantine: str = ""
    chf_pairs_min_strength: float = 0.0
    chf_pairs_min_rr: float = 0.0
    time_filter_09_12_min_strength_bonus: float = 0.0
    time_filter_09_12_min_rr_bonus: float = 0.0
    xagusd_risk_multiplier: float = 1.0
    xagusd_require_breakeven: bool = False
    xagusd_max_single_loss_usd: float = 0.0
    active_require_live_news: bool = True
    news_allow_mock: bool = False
    active_fail_closed_no_account: bool = True  # emergency + risk block if no account
    active_verify_sltp_after_open: bool = True   # verify SL on bridge; close if missing
    prop_qualified_trades_required: int = 5      # min closed trades (challenge tracking)
    prop_news_strict_funded: bool = True         # FN_FUNDED: block entries in news window
    active_allow_native_mt5: bool = False        # block native MT5 when HTTP bridge is configured
    active_require_persistent_state: bool = True # ACTIVE needs Postgres or Redis
    active_secondary_fanout: bool = False        # secondary accounts disabled in ACTIVE until hardened

    # API base path (proxy routing)
    base_path: str = "/agents"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def model_post_init(self, __context) -> None:
        import os
        # Strip whitespace/tabs from all key fields
        object.__setattr__(self, "polygon_api_key", self.polygon_api_key.strip())
        object.__setattr__(self, "twelve_data_api_key", self.twelve_data_api_key.strip())
        object.__setattr__(self, "gemini_api_key", self.gemini_api_key.strip())
        object.__setattr__(self, "google_api_key", self.google_api_key.strip())
        object.__setattr__(self, "openrouter_api_key", self.openrouter_api_key.strip())
        object.__setattr__(self, "openai_api_key", self.openai_api_key.strip())
        object.__setattr__(self, "database_url", self.database_url.strip())
        object.__setattr__(self, "telegram_bot_token", self.telegram_bot_token.strip())
        object.__setattr__(self, "telegram_chat_id", self.telegram_chat_id.strip())
        if not (self.symbols or "").strip():
            from tools.symbol_registry import DEMO_SYMBOLS_CSV
            object.__setattr__(self, "symbols", DEMO_SYMBOLS_CSV)
        from tools.trading_profiles import apply_trading_profile
        from tools.trading_mode_profiles import apply_trading_mode_profile, _env_file_has
        preserved_full_analysis = self.full_analysis_all_symbols
        has_full_analysis_env = _env_file_has("FULL_ANALYSIS_ALL_SYMBOLS")
        apply_trading_profile(self)
        apply_trading_mode_profile(self)
        if has_full_analysis_env:
            object.__setattr__(self, "full_analysis_all_symbols", preserved_full_analysis)
        # Expose DATABASE_URL for memory.py pool
        if self.database_url and not os.environ.get("DATABASE_URL"):
            os.environ["DATABASE_URL"] = self.database_url

    @property
    def effective_gemini_key(self) -> str:
        # Prefer GOOGLE_API_KEY (AI Studio standard), fall back to GEMINI_API_KEY
        return self.google_api_key or self.gemini_api_key or ""

    @property
    def symbol_list(self) -> list[str]:
        raw = [s.strip().upper() for s in self.symbols.split(",") if s.strip()]
        disabled = self.active_disabled_symbol_set
        return [s for s in raw if s not in disabled]

    @property
    def active_disabled_symbol_set(self) -> set[str]:
        return {s.strip().upper() for s in self.active_disabled_symbols.split(",") if s.strip()}

    @property
    def symbol_quarantine_set(self) -> set[str]:
        return {s.strip().upper() for s in self.symbol_quarantine.split(",") if s.strip()}

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
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def has_redis(self) -> bool:
        return bool(self.redis_url)

    @property
    def has_database(self) -> bool:
        import os
        return bool(self.database_url or os.environ.get("DATABASE_URL"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
