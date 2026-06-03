"""
Persistent runtime state for Matrix Robot.

Stores user-set trading mode and scheduler config in a JSON file so they
survive service restarts (deploys, code changes, crashes).
"""
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("matrix.runtime")

_STATE_DIR = Path(__file__).parent / ".state"
_STATE_FILE = _STATE_DIR / "runtime.json"


def _ensure_dir() -> None:
    _STATE_DIR.mkdir(exist_ok=True)


def load() -> dict:
    if not _STATE_FILE.exists():
        return {}
    try:
        with open(_STATE_FILE) as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load runtime state: {e}")
        return {}


def save(data: dict) -> None:
    _ensure_dir()
    try:
        with open(_STATE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Could not save runtime state: {e}")


def update(**kwargs) -> dict:
    state = load()
    state.update(kwargs)
    save(state)
    return state


def get_mode() -> Optional[str]:
    return load().get("mode")


def set_mode(mode: str) -> None:
    update(mode=mode)


def get_scheduler() -> dict:
    return load().get("scheduler", {})


def set_scheduler(running: bool, interval_minutes: int) -> None:
    update(scheduler={"running": running, "interval_minutes": interval_minutes})
