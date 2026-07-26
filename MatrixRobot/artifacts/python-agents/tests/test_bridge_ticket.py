"""Pure tests for bridge position ticket resolution — no MetaTrader5 required."""
from __future__ import annotations

from types import SimpleNamespace

from tools.bridge_ticket import resolve_position_ticket


def _pos(ticket, magic=20250518, volume=0.1, comment="matrix-robot", time=100):
    return SimpleNamespace(
        ticket=ticket, magic=magic, volume=volume, comment=comment, time=time,
    )


def test_returns_ticket_when_deal_id_matches_live_position():
    p = _pos(888001)

    def positions_get(**kw):
        if kw.get("ticket") == 123:
            return [p]
        return None

    assert resolve_position_ticket(positions_get, "EURUSD", 20250518, 0.1, "matrix-robot", 123) == 888001


def test_finds_by_symbol_magic_volume_comment():
    p = _pos(777002)

    def positions_get(**kw):
        if "ticket" in kw:
            return None
        return [p]

    tid = resolve_position_ticket(positions_get, "EURUSD", 20250518, 0.1, "matrix-robot", 999)
    assert tid == 777002


def test_never_returns_unverified_deal_ticket():
    def positions_get(**kw):
        return None

    assert resolve_position_ticket(positions_get, "EURUSD", 20250518, 0.1, "matrix-robot", 123) is None


def test_picks_latest_matching_position():
    older = _pos(1, time=10)
    newer = _pos(2, time=20)

    def positions_get(**kw):
        if "ticket" in kw:
            return None
        return [older, newer]

    assert resolve_position_ticket(positions_get, "EURUSD", 20250518, 0.1, "matrix-robot", 0) == 2
