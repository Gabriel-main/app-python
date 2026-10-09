"""
Tests de _balance_error_msg (SettingsView) — gate de fondos reactivo.

Regresión: el formulario bloquea con saldo insuficiente (PAPER: capital
completo vs free; LIVE FUTURES: margen = monto ÷ leverage vs available).
Sin BalanceUpdateEvent aún → fail-open (None), la regla de montos y
Binance siguen siendo la autoridad.
"""
from core.events import BalanceUpdateEvent
from ui.views.settings_view import SettingsView


def _view(
    amount="1000.0",
    trading_type="FUTURES",
    leverage=10,
    mode="PAPER",
    balance: BalanceUpdateEvent | None = None,
) -> SettingsView:
    view = SettingsView()
    view._params_section._amount_field.value = amount
    view._type_section._trading_type_dropdown.value = trading_type
    view._type_section._leverage_dropdown.value = str(leverage)
    view._mode_section._mode_dropdown.value = mode
    view._balance_ref = balance
    return view


def test_paper_insufficient_free_errors():
    view = _view(balance=BalanceUpdateEvent(
        asset="USDT", trading_type="SPOT", free=45.0,
    ))
    err = view._balance_error_msg()
    assert err is not None and "Saldo insuficiente" in err


def test_paper_sufficient_free_passes():
    view = _view(balance=BalanceUpdateEvent(
        asset="USDT", trading_type="SPOT", free=5000.0,
    ))
    assert view._balance_error_msg() is None


def test_live_futures_margin_short_errors():
    """1000 ÷ 10 = 100 de margen vs available 3 → bloqueado."""
    view = _view(
        mode="LIVE",
        balance=BalanceUpdateEvent(
            asset="USDT", trading_type="FUTURES",
            free=5000.0, available=3.0,
        ),
    )
    err = view._balance_error_msg()
    assert err is not None and "Margen insuficiente" in err


def test_live_futures_margin_covered_passes():
    view = _view(
        mode="LIVE",
        balance=BalanceUpdateEvent(
            asset="USDT", trading_type="FUTURES",
            free=5000.0, available=100.0,
        ),
    )
    assert view._balance_error_msg() is None


def test_unknown_balance_fails_open():
    view = _view(balance=None)
    assert view._balance_error_msg() is None
