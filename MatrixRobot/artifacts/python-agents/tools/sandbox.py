"""
Safe-ish Python execution sandbox for the Agentic Brain.

The brain may want to compute a custom statistic that no pre-built tool covers
(e.g. correlation between two rolling z-scores, a bespoke regression, a custom
ATR variant). Rather than ship every conceivable analytic as its own @tool, we
expose ONE tool: `run_python_code`, which runs short snippets against the bars
the data agent already fetched.

Hardening:
  - Strip dangerous builtins (`open`, `exec`, `eval`, `compile`, `__import__`,
    `input`, `breakpoint`, `help`).
  - Pre-import a fixed whitelist (math, statistics, numpy, pandas). No dynamic
    `import` available to the snippet.
  - Run in a worker thread with a hard wall-clock timeout (default 5s). We
    cannot kill a Python thread, but we can refuse to wait for it; the snippet
    has no I/O so a runaway loop only burns CPU until the cycle ends.
  - Output is whatever the snippet assigns to `result` (preferred) OR captured
    stdout. Truncated to 2000 chars.

This is NOT a security boundary against a hostile attacker — the brain is our
own LLM. It IS a guard against accidental footguns and infinite loops.
"""
from __future__ import annotations
import io
import json
import threading
import contextlib
from typing import Any

_BLOCKED_BUILTINS = {
    "open", "exec", "eval", "compile", "__import__", "input",
    "breakpoint", "help", "exit", "quit",
    # Extra: prevent any access to OS, network, or shell from the sandbox
    "os", "sys", "subprocess", "socket", "requests", "urllib",
    "pathlib", "shutil", "glob", "importlib",
}


def _safe_builtins() -> dict:
    import builtins as _b
    out = {k: getattr(_b, k) for k in dir(_b)
           if not k.startswith("_") and k not in _BLOCKED_BUILTINS}
    out["__import__"] = None  # explicitly nuke import
    return out


def run(code: str, bars_by_symbol: dict[str, list[dict]],
        extra_context: dict | None = None, timeout_s: float = 5.0) -> dict:
    """Execute `code` in a sandboxed namespace.

    Available names inside the snippet:
      - math, statistics, json (modules)
      - np (numpy), pd (pandas) if installed
      - bars: dict[symbol] -> list of bar dicts {open,high,low,close,volume,ts}
      - get_bars(symbol) -> list of bar dicts (convenience)
      - context: dict of any extra values supplied by the caller

    Snippet should assign `result = <something json-serialisable>`.
    If no `result` is set, captured stdout is returned instead.
    """
    try:
        import math as _math
        import statistics as _stats
        # Explicit None bindings for modules that MUST NOT be reachable.
        # __import__ is already None via _safe_builtins(), but we shadow the
        # module names too so even a pre-bound reference can't be used.
        ns: dict[str, Any] = {
            "__builtins__": _safe_builtins(),
            "math": _math,
            "statistics": _stats,
            "json": json,
            "bars": bars_by_symbol,
            "get_bars": lambda s: bars_by_symbol.get(str(s).upper(), []),
            "context": dict(extra_context or {}),
            "result": None,
            # Hard-block dangerous modules (belt + suspenders alongside __import__=None)
            "os": None,
            "sys": None,
            "subprocess": None,
            "socket": None,
            "requests": None,
            "urllib": None,
            "pathlib": None,
            "shutil": None,
            "open": None,
        }
        try:
            import numpy as _np
            ns["np"] = _np
        except Exception:
            pass
        try:
            import pandas as _pd
            ns["pd"] = _pd
        except Exception:
            pass

        stdout_buf = io.StringIO()
        err: dict[str, Any] = {}

        def _worker():
            try:
                with contextlib.redirect_stdout(stdout_buf):
                    exec(code, ns)
            except BaseException as e:  # snippet errors
                err["type"] = type(e).__name__
                err["msg"] = str(e)[:500]

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join(timeout=timeout_s)
        if t.is_alive():
            return {"error": "timeout", "timeout_s": timeout_s}
        if err:
            return {"error": err["type"], "message": err["msg"]}

        result = ns.get("result")
        stdout = stdout_buf.getvalue()
        # Prefer explicit `result`, fallback to stdout.
        if result is None and stdout:
            return {"stdout": stdout[:2000]}
        # Make result JSON-serialisable
        try:
            json.dumps(result, default=str)
            payload: dict[str, Any] = {"result": result}
        except Exception:
            payload = {"result": str(result)[:2000]}
        if stdout:
            payload["stdout"] = stdout[:1000]
        return payload
    except Exception as e:
        return {"error": "sandbox_failure", "message": f"{type(e).__name__}: {e}"}
