"""Multi-account registry.

Lets the bot fan out a single signal set across multiple MT5 accounts
(e.g. FundedNext demo + a real micro account), each with its own bridge
URL, risk limits, and optional symbol filter.

Configuration:
  1. ACCOUNTS_JSON env var — JSON array of secondary account configs.
  2. Legacy primary from MT5_* + global risk settings (always present).

Each account trades the SAME brain signals but sizes independently via
compute_safe_sizing(equity, starting_balance, per-account risk %).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from typing import Optional

from config import get_settings

logger = logging.getLogger("matrix.accounts")


@dataclass
class Account:
    id: str
    label: str
    bridge_url: str
    risk_per_trade_pct: float
    max_daily_drawdown_pct: float
    max_total_drawdown_pct: float
    prop_firm: str
    starting_balance: float
    enabled: bool
    # Per-account profile — FN_CHALLENGE | FN_FUNDED | REAL
    account_profile: str = "FN_CHALLENGE"
    # Comma-separated symbol allow-list; empty = all symbols from brain
    symbols: str = ""
    max_concurrent_positions: int = 0   # 0 = use global default
    max_trades_per_day: int = 0         # 0 = use global default
    min_conviction_threshold: float = 0.0  # 0 = use global default

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def symbol_list(self) -> list[str]:
        if not self.symbols.strip():
            return []
        return [s.strip().upper() for s in self.symbols.split(",") if s.strip()]

    def allows_symbol(self, symbol: str) -> bool:
        allowed = self.symbol_list
        if not allowed:
            return True
        return symbol.upper() in allowed


_DEFAULT_PRIMARY_ID = "primary"


def _parse_account(item: dict, s) -> Account:
    acct_id = str(item.get("id") or "").strip()
    profile = str(item.get("account_profile") or s.account_profile or "FN_CHALLENGE").upper()
    return Account(
        id=acct_id,
        label=str(item.get("label") or acct_id),
        bridge_url=str(item.get("bridge_url") or "").rstrip("/"),
        risk_per_trade_pct=float(item.get("risk_per_trade_pct", s.max_risk_per_trade_pct)),
        max_daily_drawdown_pct=float(
            item.get("max_daily_drawdown_pct", s.max_daily_drawdown_pct)
        ),
        max_total_drawdown_pct=float(
            item.get("max_total_drawdown_pct", s.max_total_drawdown_pct)
        ),
        prop_firm=str(item.get("prop_firm") or ""),
        starting_balance=float(item.get("starting_balance", 0.0)),
        enabled=bool(item.get("enabled", True)),
        account_profile=profile,
        symbols=str(item.get("symbols") or ""),
        max_concurrent_positions=int(item.get("max_concurrent_positions", 0) or 0),
        max_trades_per_day=int(item.get("max_trades_per_day", 0) or 0),
        min_conviction_threshold=float(item.get("min_conviction_threshold", 0.0) or 0.0),
    )


def _legacy_primary(s) -> Account:
    """Primary account from MT5_* env — FundedNext demo on VPS."""
    return Account(
        id=_DEFAULT_PRIMARY_ID,
        label=(s.prop_firm or "Primary") + " (FN Demo)",
        bridge_url=(s.mt5_bridge_url or "").rstrip("/"),
        risk_per_trade_pct=float(s.max_risk_per_trade_pct),
        max_daily_drawdown_pct=float(s.max_daily_drawdown_pct),
        max_total_drawdown_pct=float(s.max_total_drawdown_pct),
        prop_firm=str(s.prop_firm or ""),
        starting_balance=float(s.prop_starting_balance or 0.0),
        enabled=True,
        account_profile=str(s.account_profile or "FN_CHALLENGE").upper(),
        symbols="",
        max_concurrent_positions=int(s.max_concurrent_positions),
        max_trades_per_day=int(s.max_trades_per_day),
        min_conviction_threshold=float(s.min_conviction_threshold),
    )


def load_accounts() -> list[Account]:
    """Return all configured accounts (primary + secondaries from JSON)."""
    s = get_settings()
    primary = _legacy_primary(s)

    raw = (s.accounts_json or "").strip()
    if not raw:
        return [primary]

    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("ACCOUNTS_JSON must be a JSON array")
    except Exception as e:
        logger.warning(f"ACCOUNTS_JSON parse failed: {e} — falling back to legacy primary")
        return [primary]

    out: list[Account] = []
    seen_ids: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        acct_id = str(item.get("id") or "").strip()
        if not acct_id or acct_id in seen_ids:
            continue
        seen_ids.add(acct_id)
        try:
            out.append(_parse_account(item, s))
        except Exception as e:
            logger.warning(f"Skipping account {acct_id!r}: {e}")

    if not out:
        return [primary]

    if not any(a.id == _DEFAULT_PRIMARY_ID for a in out) and primary.bridge_url:
        out.insert(0, primary)
    return out


def enabled_accounts() -> list[Account]:
    return [a for a in load_accounts() if a.enabled]


def get_account(account_id: str) -> Optional[Account]:
    for a in load_accounts():
        if a.id == account_id:
            return a
    return None
