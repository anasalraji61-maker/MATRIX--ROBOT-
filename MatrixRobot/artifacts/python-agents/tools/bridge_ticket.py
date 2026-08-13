"""Pure position-ticket resolution — testable without MetaTrader5."""
from __future__ import annotations

from typing import Any, Callable


def resolve_position_ticket(
    positions_get: Callable[..., list[Any] | None],
    symbol: str,
    magic: int,
    volume: float,
    comment: str,
    deal_ticket: int,
) -> int | None:
    """Return live position.ticket or None — never guess deal_ticket without proof."""
    if deal_ticket:
        by_ticket = positions_get(ticket=int(deal_ticket))
        if by_ticket:
            return int(by_ticket[0].ticket)

    candidates = positions_get(symbol=symbol) or []
    matched = [
        p for p in candidates
        if int(getattr(p, "magic", 0)) == int(magic)
        and abs(float(getattr(p, "volume", 0)) - float(volume)) < 1e-6
        and (not comment or comment in (getattr(p, "comment", "") or ""))
    ]
    if matched:
        return int(sorted(matched, key=lambda p: getattr(p, "time", 0), reverse=True)[0].ticket)

    return None
