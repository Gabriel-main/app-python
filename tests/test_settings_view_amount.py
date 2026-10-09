"""
Tests de _amount_error_msg (SettingsView) — mínimo notional POR SÍMBOLO.

Regresión: SOLUSDC con monto 6 NO debe ser bloqueado por el global de 50;
el mínimo real (6) viene de SymbolFilters via QuantitySizer. El fallback de
50 solo aplica si los filtros del símbolo son desconocidos (sin exchangeInfo).
"""
from services.trading_rules import SymbolFilters
from ui.views.settings_view import SettingsView

_SOL_FILTERS = SymbolFilters(symbol="SOLUSDC", step_size=0.01, min_notional=6.0)


def _view(amount: str, filters: SymbolFilters, trading_type: str = "FUTURES") -> SettingsView:
    view = SettingsView()
    view._params_section._amount_field.value = amount
    view._type_section._trading_type_dropdown.value = trading_type
    view._sizer._filters = filters
    view._market_price_ref = 0.0  # sin precio aún: solo regla de notional
    return view


def test_sol_usdc_amount_six_passes_with_symbol_filters():
    view = _view("6.0", _SOL_FILTERS)
    assert view._amount_error_msg() is None


def test_sol_usdc_below_symbol_min_reports_symbol_rule():
    view = _view("5.0", _SOL_FILTERS)
    err = view._amount_error_msg()
    assert err is not None and "6" in err
    assert "50" not in err  # jamás el global cuando hay filtros reales


def test_unknown_filters_futures_falls_back_to_global():
    view = _view("10.0", SymbolFilters.unknown())
    err = view._amount_error_msg()
    assert err is not None and "50" in err


def test_amount_zero_always_errors():
    view = _view("0.0", _SOL_FILTERS)
    assert view._amount_error_msg() is not None


def test_spot_ignores_notional_floor():
    view = _view("10.0", SymbolFilters.unknown(), trading_type="SPOT")
    assert view._amount_error_msg() is None


def test_with_price_uses_full_sizing():
    view = _view("6.0", _SOL_FILTERS)
    # 6 / 12 = 0.5 qty → operable
    view._market_price_ref = 12.0
    assert view._amount_error_msg() is None
    # 6 / 130 = 0.046 → floored a 0.04 → notional 5.2 < 6
    view._market_price_ref = 130.0
    assert view._amount_error_msg() is not None
