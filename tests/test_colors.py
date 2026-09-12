"""
Tests para Colors — Mapa centralizado de constantes de color.
"""
from ui.components.colors import (
    SIDE_COLORS,
    SIDE_LABELS,
    STATE_COLORS,
    TRADING_TYPE_COLORS,
    SIGNAL_COLORS,
    CONNECTION_COLORS,
    MODE_COLORS,
)


def test_side_colors_has_buy_sell():
    assert "BUY" in SIDE_COLORS
    assert "SELL" in SIDE_COLORS


def test_side_colors_tuples_have_2_elements():
    for key, val in SIDE_COLORS.items():
        assert len(val) == 2, f"{key} should have 2 elements"


def test_side_labels_match_keys():
    assert set(SIDE_LABELS.keys()) == set(SIDE_COLORS.keys())


def test_state_colors_has_active_pending_past():
    assert "ACTIVE" in STATE_COLORS
    assert "PENDING" in STATE_COLORS
    assert "PAST" in STATE_COLORS


def test_state_colors_tuples_have_3_elements():
    for key, val in STATE_COLORS.items():
        assert len(val) == 3, f"{key} should have 3 elements (fg, bg, label)"


def test_trading_type_colors_has_spot_futures_margin():
    assert "SPOT" in TRADING_TYPE_COLORS
    assert "FUTURES" in TRADING_TYPE_COLORS
    assert "MARGIN" in TRADING_TYPE_COLORS


def test_trading_type_colors_tuples_have_3_elements():
    for key, val in TRADING_TYPE_COLORS.items():
        assert len(val) == 3, f"{key} should have 3 elements (fg, bg, label)"


def test_signal_colors_has_buy_sell_hold():
    assert "BUY" in SIGNAL_COLORS
    assert "SELL" in SIGNAL_COLORS
    assert "HOLD" in SIGNAL_COLORS


def test_connection_colors_has_all_states():
    expected = {"CONNECTING", "CONNECTED", "DISCONNECTED", "RECONNECTING"}
    assert set(CONNECTION_COLORS.keys()) == expected


def test_connection_colors_tuples_have_3_elements():
    for key, val in CONNECTION_COLORS.items():
        assert len(val) == 3, f"{key} should have 3 elements (color, icon, text)"


def test_mode_colors_has_paper_live():
    assert "PAPER" in MODE_COLORS
    assert "LIVE" in MODE_COLORS
