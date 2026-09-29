"""
Tests para SettingsSections — Secciones del formulario de configuración.
"""
import flet as ft
from unittest.mock import patch, MagicMock

from ui.components.settings_sections import (
    SettingsFormData,
    TradingModeSection,
    TradingTypeSection,
    OperationParamsSection,
    ConfirmDialogHelper,
)


def test_settings_form_data_creation():
    form = SettingsFormData(
        symbol="BTCUSDT", mode="PAPER", trading_type="SPOT",
        leverage=1, order_type="MARKET", limit_price=0.0,
        amount=10.0, currency="USDT",
        sl=1.01, sl_type="PERCENT", timeframe=1, tf_unit="MINUTES",
    )
    assert form.symbol == "BTCUSDT"
    assert form.mode == "PAPER"
    assert form.leverage == 1


def test_settings_form_data_immutable():
    form = SettingsFormData(
        symbol="BTCUSDT", mode="PAPER", trading_type="SPOT",
        leverage=1, order_type="MARKET", limit_price=0.0,
        amount=10.0, currency="USDT",
        sl=1.01, sl_type="PERCENT", timeframe=1, tf_unit="MINUTES",
    )
    try:
        form.symbol = "ETHUSDT"
        assert False, "Should be immutable"
    except AttributeError:
        pass


def test_mode_section_initial():
    section = TradingModeSection()
    assert section.get_mode() == "PAPER"


def test_type_section_initial():
    section = TradingTypeSection()
    assert section.get_trading_type() == "SPOT"
    assert section.get_leverage() == 1
    assert section.get_order_type() == "MARKET"


def test_type_section_get_limit_price():
    section = TradingTypeSection()
    price = section.get_limit_price()
    assert isinstance(price, float)


# ---------------------------------------------------------------------------
# set_max_leverage — dropdown dinámico según máximo de Binance
# ---------------------------------------------------------------------------
def test_set_max_leverage_150():
    """max=150 → todas las opciones disponibles."""
    section = TradingTypeSection()
    section.set_max_leverage(150)
    keys = [int(o.key) for o in section._leverage_dropdown.options]
    assert keys == [1, 2, 3, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 125, 150]


def test_set_max_leverage_125():
    """max=125 → sin 150."""
    section = TradingTypeSection()
    section.set_max_leverage(125)
    keys = [int(o.key) for o in section._leverage_dropdown.options]
    assert 150 not in keys
    assert 125 in keys
    assert keys[-1] == 125


def test_set_max_leverage_50():
    """max=50 → recorta en 50."""
    section = TradingTypeSection()
    section.set_max_leverage(50)
    keys = [int(o.key) for o in section._leverage_dropdown.options]
    assert keys == [1, 2, 3, 5, 10, 15, 20, 25, 30, 40, 50]


def test_set_max_leverage_clamps_current_value():
    """Si el valor actual supera el nuevo max, baja al mayor permitido."""
    section = TradingTypeSection()
    section.set_max_leverage(150)
    section._leverage_dropdown.value = "150"
    section.set_max_leverage(50)
    assert int(section._leverage_dropdown.value) == 50


def test_set_max_leverage_label_visible_futures():
    """En FUTURES muestra label con el máximo."""
    section = TradingTypeSection()
    section._trading_type_dropdown.value = "FUTURES"
    section.set_max_leverage(125)
    assert section._max_lev_label.visible is True
    assert "125" in section._max_lev_label.value


def test_set_max_leverage_label_hidden_spot():
    """En SPOT oculta el label."""
    section = TradingTypeSection()
    section._trading_type_dropdown.value = "SPOT"
    section.set_max_leverage(125)
    assert section._max_lev_label.visible is False


def test_params_section_initial():
    section = OperationParamsSection()
    assert section.get_symbol() == "BTCUSDT"
    assert section.get_amount() == 10.0
    assert section.get_currency() == "USDT"
    assert section.get_sl() == 1.01
    assert section.get_sl_type() == "PERCENT"
    assert section.get_timeframe() == 1
    assert section.get_tf_unit() == "MINUTES"


def test_confirm_dialog_builds_changes():
    with patch("ui.components.settings_sections.settings") as mock_settings:
        mock_settings.TRADING_SYMBOL = "BTCUSDT"
        mock_settings.TRADING_MODE = "PAPER"
        mock_settings.TRADING_TYPE = "SPOT"
        mock_settings.LEVERAGE = 1
        mock_settings.ORDER_TYPE = "MARKET"
        mock_settings.LIMIT_PRICE = 0.0
        mock_settings.TRADE_AMOUNT = 10.0
        mock_settings.TRADE_CURRENCY = "USDT"
        mock_settings.STOP_LOSS = 1.01
        mock_settings.STOP_LOSS_TYPE = "PERCENT"
        mock_settings.TIMEFRAME = 1
        mock_settings.TIMEFRAME_UNIT = "MINUTES"

        form = SettingsFormData(
            symbol="ETHUSDT", mode="LIVE", trading_type="FUTURES",
            leverage=5, order_type="LIMIT", limit_price=3500.0,
            amount=50.0, currency="USDC",
            sl=1.05, sl_type="USDT", timeframe=5, tf_unit="HOURS",
        )
        changes = ConfirmDialogHelper.build_changes_summary(form)
        assert len(changes) > 0
        assert any("Símbolo" in c for c in changes)
        assert any("Modo" in c for c in changes)


def test_confirm_dialog_empty_changes():
    with patch("ui.components.settings_sections.settings") as mock_settings:
        mock_settings.TRADING_SYMBOL = "BTCUSDT"
        mock_settings.TRADING_MODE = "PAPER"
        mock_settings.TRADING_TYPE = "SPOT"
        mock_settings.LEVERAGE = 1
        mock_settings.ORDER_TYPE = "MARKET"
        mock_settings.LIMIT_PRICE = 0.0
        mock_settings.TRADE_AMOUNT = 10.0
        mock_settings.TRADE_CURRENCY = "USDT"
        mock_settings.STOP_LOSS = 1.01
        mock_settings.STOP_LOSS_TYPE = "PERCENT"
        mock_settings.TIMEFRAME = 1
        mock_settings.TIMEFRAME_UNIT = "MINUTES"

        form = SettingsFormData(
            symbol="BTCUSDT", mode="PAPER", trading_type="SPOT",
            leverage=1, order_type="MARKET", limit_price=0.0,
            amount=10.0, currency="USDT",
            sl=1.01, sl_type="PERCENT", timeframe=1, tf_unit="MINUTES",
        )
        changes = ConfirmDialogHelper.build_changes_summary(form)
        assert len(changes) == 1
        assert "No hay cambios" in changes[0]


def test_mode_section_restore():
    section = TradingModeSection()
    snapshot = {"mode": "LIVE"}
    section.restore(snapshot)
    assert section.get_mode() == "LIVE"


def test_type_section_restore():
    section = TradingTypeSection()
    snapshot = {
        "trading_type": "FUTURES", "leverage": 10,
        "order_type": "LIMIT", "limit_price": 65000.0,
    }
    section.restore(snapshot)
    assert section.get_trading_type() == "FUTURES"
    assert section.get_leverage() == 10
    assert section.get_order_type() == "LIMIT"
    assert section.get_limit_price() == 65000.0
