"""
Correlation guard — prevents opening multiple correlated trades in the same
direction (e.g. BUY EURUSD + BUY GBPUSD = same USD-bearish bet twice).

Uses a static, hand-curated forex correlation map (well-known relationships)
rather than rolling-window calculation: more deterministic, safer for
prop-firm rules that flag "stacked exposure".
"""
from __future__ import annotations

from models.schemas import CorrelationReport, CorrelationGroup
from tools import memory


# Each group = symbols that move together. If we are already in BUY on one,
# we should not open BUY on another from the same group.
GROUPS: list[CorrelationGroup] = [
    CorrelationGroup(name="USD-bearish-majors",
                     members=["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]),
    CorrelationGroup(name="USD-bullish-majors",
                     members=["USDCHF", "USDCAD", "USDJPY"]),
    CorrelationGroup(name="JPY-cross-block",
                     members=["EURJPY", "GBPJPY", "AUDJPY", "CHFJPY",
                              "CADJPY", "NZDJPY", "USDJPY"]),
    CorrelationGroup(name="EUR-cross-block",
                     members=["EURUSD", "EURGBP", "EURJPY", "EURAUD",
                              "EURCHF"]),
    CorrelationGroup(name="CHF-block",
                     members=["USDCHF", "EURCHF", "GBPCHF", "CHFJPY"]),
    CorrelationGroup(name="AUD-NZD-commodity",
                     members=["AUDUSD", "NZDUSD", "AUDCAD", "AUDNZD"]),
]


# In-process map kept alongside CorrelationReport (schema only allows one
# `open_direction` string per group; we keep the full set of directions here).
_group_dirs: dict[str, set[str]] = {}


def build_report(open_positions: list[dict] | None = None) -> CorrelationReport:
    """Mark groups with their current open directions and list blocked (symbol, side) keys.

    A symbol+action is blocked when the correlation group it belongs to
    already has at least one open position in the SAME direction. We track
    BUY and SELL exposure independently per group, so mixed-direction
    exposure does not let either side slip through unblocked.
    """
    open_positions = open_positions or memory.retrieve("open_positions") or []

    # Map symbol → set of directions currently open
    open_dir: dict[str, set[str]] = {}
    for p in open_positions:
        sym = p.get("symbol")
        act = p.get("action")
        if sym and act in ("BUY", "SELL"):
            open_dir.setdefault(sym, set()).add(act)

    groups: list[CorrelationGroup] = []
    blocked: set[str] = set()
    _group_dirs.clear()

    for g in GROUPS:
        dirs_in_group: set[str] = set()
        for m in g.members:
            if m in open_dir:
                dirs_in_group |= open_dir[m]
        _group_dirs[g.name] = dirs_in_group

        # Schema keeps a single representative direction for display:
        # MIXED when both sides exist, otherwise the lone side.
        if dirs_in_group == {"BUY", "SELL"}:
            display_dir = "MIXED"
        elif dirs_in_group:
            display_dir = next(iter(dirs_in_group))
        else:
            display_dir = None

        groups.append(CorrelationGroup(
            name=g.name, members=g.members, open_direction=display_dir,
        ))

        for d in dirs_in_group:
            for m in g.members:
                blocked.add(f"{m}:{d}")

    return CorrelationReport(groups=groups, blocked_pairs=sorted(blocked))


def is_blocked(symbol: str, action: str, report: CorrelationReport | None = None) -> tuple[bool, str]:
    """Return (blocked, reason). True = adding this trade would over-stack a group."""
    if report is None:
        report = build_report()
    key = f"{symbol}:{action}"
    if key not in report.blocked_pairs:
        return False, ""
    # Find an offending group for the message (must contain symbol and have this side open)
    for g in report.groups:
        if symbol not in g.members:
            continue
        dirs = _group_dirs.get(g.name, set())
        if action in dirs:
            return True, f"correlation: group '{g.name}' already has {action} exposure"
    return True, f"correlation: existing {action} exposure in a correlated group"
