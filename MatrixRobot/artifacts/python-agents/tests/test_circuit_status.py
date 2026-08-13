from tools.circuit_status import _bridge_block_reason


def test_bridge_block_when_circuit_open(monkeypatch):
    from tools import bridge_circuit

    class _S:
        mt5_bridge_url = "http://127.0.0.1:5555"

    monkeypatch.setattr("tools.circuit_status.get_settings", lambda: _S())
    monkeypatch.setattr(
        bridge_circuit, "is_open", lambda url: url == "http://127.0.0.1:5555",
    )
    blocked, code, info = _bridge_block_reason("ACTIVE")
    assert blocked is True
    assert code == "bridge_circuit_open"
    assert info["circuit_open"] is True


def test_bridge_not_required_in_paper_mode():
    blocked, code, info = _bridge_block_reason("PAPER_MODE")
    assert blocked is False
    assert code == ""
    assert info["required"] is False
