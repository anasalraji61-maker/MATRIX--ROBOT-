"""Scanner off-session execution and FX-only filter tests."""
from __future__ import annotations

from unittest.mock import patch

from tools.off_session_limits import scanner_may_execute_off_session_small
from tools.off_session_scanner import _tradable_symbols


class _FxOnlySettings:
    off_session_scan_fx_only = True
    active_disabled_symbols = "US30,US500,USTEC"
    symbols = "EURUSD,XAUUSD,US30"

    @property
    def symbol_list(self):
        return ["EURUSD", "XAUUSD", "US30"]

    @property
    def active_disabled_symbol_set(self):
        return {"US30", "US500", "USTEC"}


def test_scanner_fx_only_skips_metals_and_indices():
    state = {
        "symbols_analyzed": ["EURUSD", "XAUUSD", "US30"],
        "market_data": {"data_quality": {}},
        "mode": "ACTIVE",
    }
    with patch("tools.off_session_scanner.get_settings", return_value=_FxOnlySettings()):
        with patch("tools.off_session_scanner.symbol_quarantine_reason", return_value=""):
            symbols = _tradable_symbols(state, _FxOnlySettings())
    assert symbols == ["EURUSD"]


def test_scanner_execution_flag_gating():
    plan = {"cycle_type": "scanner", "active_killzone": "none"}

    class _On:
        smart_watcher_execute_off_session_small = True
        allow_off_session_small_trades = True
        session_filter_mode = "extended"

    class _Off:
        smart_watcher_execute_off_session_small = False
        allow_off_session_small_trades = True
        session_filter_mode = "extended"

    assert scanner_may_execute_off_session_small("ACTIVE", plan, _On()) is True
    assert scanner_may_execute_off_session_small("ACTIVE", plan, _Off()) is False
    assert scanner_may_execute_off_session_small("PAPER_MODE", plan, _On()) is False
    assert scanner_may_execute_off_session_small(
        "ACTIVE", {"cycle_type": "full", "active_killzone": "none"}, _On(),
    ) is False
