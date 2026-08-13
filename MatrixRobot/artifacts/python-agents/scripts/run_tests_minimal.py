"""Run pytest with langgraph/langchain_openai blocked — simulates minimal CI env."""
from __future__ import annotations

import builtins
import sys

BLOCK_ROOTS = ("langgraph", "langchain_openai", "langchain_core")
_real_import = builtins.__import__


def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name in sys.modules:
        return sys.modules[name]
    root = name.split(".")[0]
    if root in BLOCK_ROOTS:
        raise ImportError(f"No module named '{name}'")
    return _real_import(name, globals, locals, fromlist, level)


builtins.__import__ = _blocked_import

import pytest

sys.exit(pytest.main(["-q"]))
