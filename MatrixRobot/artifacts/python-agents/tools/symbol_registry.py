"""Central symbol universe — 48 FX pairs + metals + oil + US indices."""

from __future__ import annotations

# ── 48 major / liquid forex pairs worldwide ─────────────────────────────
FOREX_SYMBOLS: tuple[str, ...] = (
    # G10 majors (7)
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD",
    # EUR crosses (12)
    "EURGBP", "EURJPY", "EURAUD", "EURCHF", "EURCAD", "EURNZD",
    "EURSEK", "EURNOK", "EURPLN", "EURHUF", "EURTRY", "EURSGD",
    # GBP crosses (7)
    "GBPJPY", "GBPAUD", "GBPCAD", "GBPNZD", "GBPCHF", "GBPSEK", "GBPSGD",
    # AUD / NZD / CAD / CHF crosses (11)
    "AUDJPY", "AUDCAD", "AUDNZD", "AUDCHF", "AUDSGD",
    "NZDJPY", "NZDCAD", "NZDCHF",
    "CADJPY", "CADCHF",
    "CHFJPY", "CHFSGD",
    # USD exotics / EM (10)
    "USDSEK", "USDNOK", "USDTRY", "USDZAR", "USDMXN",
    "USDPLN", "USDHUF", "USDSGD", "USDHKD", "USDCNH",
)

FOREX_SET = frozenset(FOREX_SYMBOLS)

FX_MAJORS: tuple[str, ...] = FOREX_SYMBOLS[:7]
FX_CROSSES: tuple[str, ...] = FOREX_SYMBOLS[7:]

METALS = frozenset({"XAUUSD", "XAGUSD"})
OIL = frozenset({"USOIL", "UKOIL"})
INDICES = frozenset({"US30", "US500", "USTEC"})
COMMODITIES = METALS | OIL

ALL_SYMBOLS: tuple[str, ...] = FOREX_SYMBOLS + tuple(sorted(COMMODITIES | INDICES))
DEFAULT_SYMBOLS_CSV = ",".join(ALL_SYMBOLS)

# Demo VPS default — 25 liquid pairs (7 majors + 17 crosses + gold). Indices/oil excluded.
DEMO_SYMBOLS: tuple[str, ...] = (
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD",
    "EURGBP", "EURJPY", "EURAUD", "EURCHF", "EURCAD", "EURNZD",
    "GBPJPY", "GBPAUD", "GBPCAD", "GBPCHF", "GBPNZD",
    "AUDJPY", "AUDCAD", "AUDNZD", "AUDCHF",
    "NZDJPY", "NZDCAD",
    "XAUUSD",
)
DEMO_SYMBOLS_CSV = ",".join(DEMO_SYMBOLS)


def asset_class(symbol: str) -> str:
    sym = (symbol or "").upper()
    if sym in INDICES:
        return "indices"
    if sym in METALS:
        return "metals"
    if sym in OIL:
        return "oil"
    return "fx"
