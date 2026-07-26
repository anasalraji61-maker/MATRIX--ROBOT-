"""Run one-symbol backtest via Brain API. Usage: python scripts/run_backtest_one.py EURUSD"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_secret() -> str:
    for line in ROOT.joinpath(".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("MT5_BRIDGE_SECRET="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def main() -> int:
    symbol = (sys.argv[1] if len(sys.argv) > 1 else "EURUSD").upper()
    secret = _load_secret()
    if not secret:
        print("ERROR: MT5_BRIDGE_SECRET missing in .env")
        return 1

    body = json.dumps({
        "symbol": symbol,
        "bars_limit": 2000,
        "timeframe": "H1",
        "include_trades": False,
    }).encode()

    req = urllib.request.Request(
        "http://127.0.0.1:8000/agents/backtest/run",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Brain-Secret": secret},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
        return 1
    except urllib.error.URLError as e:
        print(f"Connection failed: {e.reason}")
        print("Is START_BRAIN.bat running?")
        return 1

    stats = data.get("stats") or {}
    print()
    print("=== BACKTEST RESULT ===")
    print(f"symbol:         {data.get('symbol')}")
    print(f"bars:           {data.get('bars_count')}")
    print(f"n_trades:       {stats.get('n_trades')}")
    print(f"win_rate:       {stats.get('win_rate')}")
    print(f"profit_factor:  {stats.get('profit_factor')}")
    print(f"total_r:        {stats.get('total_r')}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
