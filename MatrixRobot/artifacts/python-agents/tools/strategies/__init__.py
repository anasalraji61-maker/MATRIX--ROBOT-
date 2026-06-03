"""Pluggable trading-school strategies — each module exposes `analyze(bars, symbol) -> dict`.

The agentic brain calls these on demand via the tool registry. Each returns:
  {bias: 'bullish'|'bearish'|'neutral', score: -1..1, reasons: [...], key_levels: {...}}
"""
from . import wyckoff, elliott, harmonic, volume_profile, chart_patterns

__all__ = ["wyckoff", "elliott", "harmonic", "volume_profile", "chart_patterns"]
