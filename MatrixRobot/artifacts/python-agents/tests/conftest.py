"""Test bootstrap — stub optional LLM/graph deps when not installed.

Allows `pytest -q` to pass in minimal CI/VPS check environments that only
install core deps. Production VPS should still run:
  pip install -r requirements.txt
"""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock


def _stub_langgraph() -> None:
    lg = ModuleType("langgraph")
    lg_graph = ModuleType("langgraph.graph")

    class _Compiled:
        async def ainvoke(self, state):
            return state

    class StateGraph:
        def __init__(self, _state_type=None):
            self._nodes = {}

        def add_node(self, name, fn):
            self._nodes[name] = fn
            return self

        def add_edge(self, *_a, **_k):
            return self

        def add_conditional_edges(self, *_a, **_k):
            return self

        def compile(self):
            return _Compiled()

    lg_graph.StateGraph = StateGraph
    lg_graph.END = "__end__"
    lg_graph.START = "__start__"
    sys.modules["langgraph"] = lg
    sys.modules["langgraph.graph"] = lg_graph


def _stub_langchain_core_tools() -> None:
    core = sys.modules.get("langchain_core")
    if core is None or not hasattr(core, "__path__"):
        core = ModuleType("langchain_core")
        core.__path__ = []  # type: ignore[attr-defined]
        sys.modules["langchain_core"] = core

    tools_mod = ModuleType("langchain_core.tools")

    def tool(fn=None, *args, **kwargs):
        if fn is None:
            return lambda f: f
        return fn

    tools_mod.tool = tool
    sys.modules["langchain_core.tools"] = tools_mod
    setattr(core, "tools", tools_mod)

    if "langchain_core.messages" not in sys.modules:
        lcm = ModuleType("langchain_core.messages")

        class _Msg:
            def __init__(self, content=""):
                self.content = content

        lcm.SystemMessage = _Msg
        lcm.HumanMessage = _Msg
        sys.modules["langchain_core.messages"] = lcm


def _stub_langchain_openai() -> None:
    mod = ModuleType("langchain_openai")

    class ChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    mod.ChatOpenAI = ChatOpenAI
    sys.modules["langchain_openai"] = mod
    _stub_langchain_core_tools()


def _stub_ta() -> None:
    """Minimal ta stub so agents.graph imports without ta installed."""
    ta = ModuleType("ta")
    for sub in ("momentum", "trend", "volatility", "volume"):
        sys.modules[f"ta.{sub}"] = ModuleType(f"ta.{sub}")
    sys.modules["ta"] = ta


def _ensure_optional_deps() -> None:
    try:
        import langgraph  # noqa: F401
    except ImportError:
        if "langgraph.graph" not in sys.modules:
            _stub_langgraph()

    try:
        import langchain_openai  # noqa: F401
        import langchain_core.tools  # noqa: F401
    except ImportError:
        if "langchain_openai" not in sys.modules:
            _stub_langchain_openai()
        elif "langchain_core.tools" not in sys.modules:
            _stub_langchain_core_tools()

    try:
        import ta  # noqa: F401
    except ImportError:
        if "ta" not in sys.modules:
            _stub_ta()


# Run at conftest import time — before test modules load graph/supervisor paths.
_ensure_optional_deps()
