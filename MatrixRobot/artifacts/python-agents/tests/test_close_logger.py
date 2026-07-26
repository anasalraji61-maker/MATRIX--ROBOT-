from tools.close_logger import normalize_close_reason


def test_normalize_close_reason_sl_tp():
    assert normalize_close_reason("stop_loss") == "stop_loss"
    assert normalize_close_reason("take_profit") == "take_profit"
    assert normalize_close_reason("reason_4") == "stop_loss"
    assert normalize_close_reason("reason_5") == "take_profit"
    assert normalize_close_reason(None) == "unknown"
