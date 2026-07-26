"""Per-symbol pip/point sizing — FX, metals, indices (+ optional MT5 broker specs)."""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("matrix.symbol_specs")

_broker_cache: dict[str, "SymbolSpec"] = {}


@dataclass(frozen=True)
class SymbolSpec:
    pip_size: float
    pip_value: float  # USD per pip/point per standard lot (approx)
    asset_class: str
    volume_min: float = 0.01
    volume_step: float = 0.01
    source: str = "static"


_SPECS: dict[str, SymbolSpec] = {
    "XAUUSD": SymbolSpec(0.10, 10.0, "metal"),
    "XAGUSD": SymbolSpec(0.001, 5.0, "metal"),
    "USOIL": SymbolSpec(0.01, 10.0, "oil", volume_min=0.01, volume_step=0.01),
    "UKOIL": SymbolSpec(0.01, 10.0, "oil", volume_min=0.01, volume_step=0.01),
    "US30": SymbolSpec(1.0, 1.0, "index", volume_min=1.0, volume_step=1.0),
    "US500": SymbolSpec(0.01, 5.0, "index", volume_min=0.1, volume_step=0.1),
    "USTEC": SymbolSpec(0.01, 2.0, "index", volume_min=0.1, volume_step=0.1),
}

_PIP_VALUES = {
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0, "NZDUSD": 10.0,
    "USDCHF": 11.0, "USDCAD": 7.5, "USDJPY": 6.7,
    "EURGBP": 13.0, "EURJPY": 6.7, "GBPJPY": 6.7, "AUDJPY": 6.7,
    "CHFJPY": 6.7, "CADJPY": 6.7, "NZDJPY": 6.7,
    "EURAUD": 7.5, "EURCHF": 11.0, "GBPCHF": 11.0,
    "AUDCAD": 7.5, "AUDNZD": 7.0, "EURCAD": 7.5, "EURNZD": 7.0,
    "EURSEK": 1.0, "EURNOK": 1.0, "EURPLN": 2.5, "EURHUF": 0.03,
    "EURTRY": 0.3, "EURSGD": 7.5, "GBPAUD": 7.5, "GBPCAD": 7.5,
    "GBPNZD": 7.0, "GBPSEK": 1.0, "GBPSGD": 7.5, "AUDCHF": 11.0,
    "AUDSGD": 7.5, "NZDCAD": 7.5, "NZDCHF": 11.0, "CADCHF": 11.0,
    "CHFSGD": 7.5, "USDSEK": 1.0, "USDNOK": 1.0, "USDTRY": 0.3,
    "USDZAR": 0.55, "USDMXN": 0.55, "USDPLN": 2.5, "USDHUF": 0.03,
    "USDSGD": 7.5, "USDHKD": 1.3, "USDCNH": 1.4,
}

_BROKER_PRIORITY = {"US30", "US500", "USTEC", "XAUUSD", "XAGUSD", "USOIL", "UKOIL"}


def spec_from_broker_info(info: dict) -> SymbolSpec | None:
    try:
        point = float(info.get("point") or 0)
        digits = int(info.get("digits") or 5)
        tick_value = float(info.get("trade_tick_value") or 0)
        tick_size = float(info.get("trade_tick_size") or point or 0)
        if point <= 0 or tick_size <= 0:
            return None
        pip_size = point * 10 if digits in (3, 5) else point
        pip_value = (tick_value / tick_size) * pip_size
        sym = str(info.get("symbol", "")).upper()
        from tools.symbol_registry import INDICES, METALS, OIL
        asset = "index" if sym in INDICES else (
            "metal" if sym in METALS else (
                "oil" if sym in OIL else "fx"
            )
        )
        return SymbolSpec(
            pip_size=pip_size,
            pip_value=round(pip_value, 4),
            asset_class=asset,
            volume_min=float(info.get("volume_min") or 0.01),
            volume_step=float(info.get("volume_step") or 0.01),
            source="mt5",
        )
    except (TypeError, ValueError):
        return None


async def refresh_broker_specs(symbols: list[str], bridge_url: str | None = None) -> dict[str, SymbolSpec]:
    """Fetch broker specs for priority symbols via MT5 bridge."""
    from config import get_settings
    from tools.mt5_bridge import _http_symbol_info

    settings = get_settings()
    url = (bridge_url or settings.mt5_bridge_url or "").rstrip("/")
    if not url:
        return {}
    updated: dict[str, SymbolSpec] = {}
    for sym in symbols:
        if sym.upper() not in _BROKER_PRIORITY:
            continue
        try:
            info = await _http_symbol_info(url, sym)
            spec = spec_from_broker_info(info)
            if spec:
                _broker_cache[sym.upper()] = spec
                updated[sym.upper()] = spec
        except Exception as exc:
            logger.debug("broker spec fetch failed for %s: %s", sym, exc)
    return updated


def _static_pip_size(symbol: str) -> float:
    """Default pip/point size without broker cache or recursion."""
    sym = (symbol or "").upper()
    if sym in _SPECS:
        return _SPECS[sym].pip_size
    if "JPY" in sym:
        return 0.01
    return 0.0001


def get_spec(symbol: str) -> SymbolSpec:
    sym = (symbol or "").upper()
    if sym in _broker_cache:
        return _broker_cache[sym]
    if sym in _SPECS:
        return _SPECS[sym]
    return SymbolSpec(
        pip_size=_static_pip_size(sym),
        pip_value=_PIP_VALUES.get(sym, 10.0),
        asset_class="fx",
    )


def pip_size_for(symbol: str) -> float:
    sym = (symbol or "").upper()
    if sym in _broker_cache:
        return _broker_cache[sym].pip_size
    return _static_pip_size(sym)


def pip_value_for(symbol: str) -> float:
    return get_spec(symbol).pip_value


PIP_VALUE = {**_PIP_VALUES, **{k: v.pip_value for k, v in _SPECS.items()}}
