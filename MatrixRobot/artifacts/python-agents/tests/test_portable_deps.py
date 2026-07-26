"""Verify optional-dep stubs from tests/conftest.py work."""
from __future__ import annotations

import sys

from tests.conftest import _stub_langgraph, _stub_langchain_openai


def test_langgraph_stub_supports_graph_import():
    from tests.conftest import _stub_langgraph
    import sys
    for name in list(sys.modules):
        if name == "agents.graph" or name.startswith("langgraph"):
            del sys.modules[name]
    _stub_langgraph()
    from langgraph.graph import StateGraph, END, START  # noqa: F401
    import importlib
    mod = importlib.import_module("agents.graph")
    assert hasattr(mod, "_node_emergency")


def test_ta_stub_allows_graph_import():
    from tests.conftest import _stub_ta
    import sys
    for name in list(sys.modules):
        if name == "agents.graph" or name.startswith("ta"):
            del sys.modules[name]
    _stub_ta()
    import importlib
    mod = importlib.import_module("agents.graph")
    assert hasattr(mod, "_node_skip")


def test_langchain_openai_stub_exists():
    _stub_langchain_openai()
    from langchain_openai import ChatOpenAI  # noqa: F401

    assert ChatOpenAI is not None
