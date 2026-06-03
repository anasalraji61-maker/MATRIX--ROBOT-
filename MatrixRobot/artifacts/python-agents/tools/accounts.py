"""Multi-account registry.

Lets the bot fan out a single signal set across multiple MT5 accounts
(e.g. FundedNext demo + a real broker account), each with its own bridge
URL, risk-per-trade %, and prop-firm tag.

Configuration sources (in priority order):
  1. ACCOUNTS_JSON env var — JSON list of account dicts.
  2. Legacy single-account from MT5_* + risk_* settings (always present
     as account_id="primary" so existing deployments keep working).

Account schema (JSON):
    {
      "id": "fn_demo",                 # unique short id (used in memory keys)
      "label": "FN Demo",               # human label for dashboard
      "bridge_url": "http://...:5555",
      "risk_per_trade_pct": 0.8,        # overrides settings.max_risk_per_trade_pct
      "max_daily_drawdown_pct": 4.0,    # optional per-account override
      "max_total_drawdown_pct": 9.0,    # optional
      "prop_firm": "FundedNext",        # "" if no prop firm rules apply
      "starting_balance": 0.0,          # 0 = auto-snapshot on first run
      "enabled": true
    }
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

    def to_dict(self) -> dict:
        return asdict(self)


_DEFAULT_PRIMARY_ID = "primary"


def _legacy_primary(s) -> Account:
    """Build the legacy single-account from settings so existing deployments
    that don't set ACCOUNTS_JSON keep working unchanged."""
    return Account(
        id=_DEFAULT_PRIMARY_ID,
        label=(s.prop_firm or "Primary") + " (legacy MT5_*)",
        bridge_url=(s.mt5_bridge_url or "").rstrip("/"),
        risk_per_trade_pct=float(s.max_risk_per_trade_pct),
        max_daily_drawdown_pct=float(s.max_daily_drawdown_pct),
        max_total_drawdown_pct=float(s.max_total_drawdown_pct),
        prop_firm=str(s.prop_firm or ""),
        starting_balance=float(s.prop_starting_balance or 0.0),
        enabled=True,
    )


def load_accounts() -> list[Account]:
    """Return the ordered list of configured accounts.

    Always returns at least one account (the legacy primary) so the
    execution agent can iterate unconditionally.
    """
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
            out.append(Account(
                id=acct_id,
                label=str(item.get("label") or acct_id),
                bridge_url=str(item.get("bridge_url") or "").rstrip("/"),
                risk_per_trade_pct=float(item.get("risk_per_trade_pct", s.max_risk_per_trade_pct)),
                max_daily_drawdown_pct=float(item.get("max_daily_drawdown_pct", s.max_daily_drawdown_pct)),
                max_total_drawdown_pct=float(item.get("max_total_drawdown_pct", s.max_total_drawdown_pct)),
                prop_firm=str(item.get("prop_firm") or ""),
                starting_balance=float(item.get("starting_balance", 0.0)),
                enabled=bool(item.get("enabled", True)),
            ))
        except Exception as e:
            logger.warning(f"Skipping account {acct_id!r}: {e}")

    if not out:
        return [primary]

    # If the JSON already declared a "primary" id, don't double it.
    if not any(a.id == _DEFAULT_PRIMARY_ID for a in out) and primary.bridge_url:
        # Legacy primary bridge is configured AND not referenced — keep it
        # at the front so default behavior persists.
        out.insert(0, primary)
    return out


def enabled_accounts() -> list[Account]:
    return [a for a in load_accounts() if a.enabled]


def get_account(account_id: str) -> Optional[Account]:
    for a in load_accounts():
        if a.id == account_id:
            return a
    return None
