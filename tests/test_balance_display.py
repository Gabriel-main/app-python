"""
Tests para BalanceDisplay — Strategy pattern de balance.
"""
from unittest.mock import MagicMock

from ui.components.balance_display import (
    format_amount,
    get_strategy,
    SpotBalanceDisplay,
    FuturesBalanceDisplay,
    MarginBalanceDisplay,
)


def test_format_large_amount():
    assert format_amount(1234.56) == "$1,234.56"


def test_format_medium_amount():
    assert format_amount(1.2345) == "$1.2345"


def test_format_small_amount():
    assert format_amount(0.001234) == "$0.001234"


def test_format_exact_1000():
    assert format_amount(1000.0) == "$1,000.00"


def test_format_exact_1():
    assert format_amount(1.0) == "$1.0000"


def test_format_zero():
    assert format_amount(0.0) == "$0.000000"


def test_spot_labels():
    s = SpotBalanceDisplay()
    assert s.get_labels() == ("Disponible", "Bloqueado", None)


def test_spot_values():
    s = SpotBalanceDisplay()
    event = MagicMock()
    event.free = 1000.50
    event.locked = 200.25
    v1, v2, v3 = s.format_values(event)
    assert v1 == "$1,000.50"
    assert v2 == "$200.2500"
    assert v3 is None


def test_futures_labels():
    s = FuturesBalanceDisplay()
    assert s.get_labels() == ("Wallet", "Disponible", "PnL No Real.")


def test_futures_values_with_pnl():
    s = FuturesBalanceDisplay()
    event = MagicMock()
    event.free = 5000.0
    event.available = 3000.0
    event.unrealized_pnl = 150.75
    v1, v2, v3 = s.format_values(event)
    assert v1 == "$5,000.00"
    assert v2 == "$3,000.00"
    assert v3 == "+$150.7500"


def test_futures_values_no_pnl():
    s = FuturesBalanceDisplay()
    event = MagicMock()
    event.free = 5000.0
    event.available = 3000.0
    event.unrealized_pnl = 0.0
    _, _, v3 = s.format_values(event)
    assert v3 is None


def test_futures_values_negative_pnl():
    s = FuturesBalanceDisplay()
    event = MagicMock()
    event.free = 5000.0
    event.available = 3000.0
    event.unrealized_pnl = -100.0
    _, _, v3 = s.format_values(event)
    assert v3 == "-$100.0000"


def test_margin_labels():
    s = MarginBalanceDisplay()
    assert s.get_labels() == ("Net Asset", "Prestado", "Interés")


def test_margin_values_with_interest():
    s = MarginBalanceDisplay()
    event = MagicMock()
    event.free = 2000.0
    event.borrowed = 1000.0
    event.interest = 25.50
    v1, v2, v3 = s.format_values(event)
    assert v1 == "$2,000.00"
    assert v2 == "$1,000.00"
    assert v3 == "$25.5000"


def test_margin_values_no_interest():
    s = MarginBalanceDisplay()
    event = MagicMock()
    event.free = 2000.0
    event.borrowed = 1000.0
    event.interest = 0.0
    _, _, v3 = s.format_values(event)
    assert v3 is None


def test_get_strategy_spot():
    assert isinstance(get_strategy("SPOT"), SpotBalanceDisplay)


def test_get_strategy_futures():
    assert isinstance(get_strategy("FUTURES"), FuturesBalanceDisplay)


def test_get_strategy_margin():
    assert isinstance(get_strategy("MARGIN"), MarginBalanceDisplay)


def test_get_strategy_unknown_returns_spot():
    assert isinstance(get_strategy("UNKNOWN"), SpotBalanceDisplay)
