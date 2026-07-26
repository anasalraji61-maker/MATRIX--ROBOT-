Matrix Robot V10 Hotfix — Deployment Instructions
================================================

IMPORTANT: Apply files INTO artifacts/python-agents/
------------------------------------------------------
The zip root contains: tools/, agents/, config.py, routes/, etc.

DO NOT copy to the MatrixRobot project root.

Correct target (VPS):
  C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\python-agents\

Correct target (laptop):
  ...\MatrixRobot\MatrixRobot\artifacts\python-agents\

PowerShell deploy example:
  $src = "C:\path\to\hotfix_extracted"
  $dst = "C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\python-agents"
  robocopy $src $dst /E /XD __pycache__ .pytest_cache /XF *.pyc

Verify after copy:
  cd $dst
  $env:PYTHONPATH="."
  python -m compileall -q .
  python -m pytest -q

Required .env flags for Demo VPS
--------------------------------
SMART_WATCHER_ENABLED=true          # scanner outside killzones (NOT full brain every 30m)
SMART_WATCHER_EXECUTE_OFF_SESSION_SMALL=true   # Demo only: execute SMALL outside killzone
SESSION_FILTER_MODE=extended
PRIMARY_MODEL=openai/gpt-4o-mini
ML_FILTER_MODE=shadow
RL_MODE=shadow
ML_RETRAIN_ENABLED=false
ACTIVE_DISABLED_SYMBOLS=US30,US500,USTEC
OFF_SESSION_ALLOWED_ASSETS=FX_ONLY
OFF_SESSION_RISK_MULTIPLIER=0.15
OFF_SESSION_MAX_OPEN_TRADES=1
OFF_SESSION_MAX_TRADES_PER_DAY=2

Symbols: leave SYMBOLS empty for 25-pair demo default, or set explicit list:
  SYMBOLS=EURUSD,GBPUSD,USDJPY,...

For full 52-symbol universe set SYMBOLS to the full CSV from tools/symbol_registry.py DEFAULT_SYMBOLS_CSV.

Smart Watcher behavior (when enabled)
-------------------------------------
London/NY  -> full cycle + brain
Asian      -> full cycle + brain (SMALL trades)
Off-session, no positions -> scanner (cheap, brain only on escalation >= 0.80)
Off-session, open positions -> maintenance (emergency + position manager only)

Check: GET /agents/session/status  (shows cycle_type, watcher_stats)
