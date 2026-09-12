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
        api_key="", api_secret="", amount=10.0, currency="USDT",
        sl=1.01, sl_type="PERCENT", timeframe=1, tf_unit="MINUTES",
    )
    assert form.symbol == "BTCUSDT"
    assert form.mode == "PAPER"
    assert form.leverage == 1


def test_settings_form_data_immutable():
    form = SettingsFormData(
        symbol="BTCUSDT", mode="PAPER", trading_type="SPOT",
        leverage=1, order_type="MARKET", limit_price=0.0,
        api_key="", api_secret="", amount=10.0, currency="USDT",
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


def test_mode_section_get_api_keys():
    section = TradingModeSection()
    key, secret = section.get_api_keys()
    assert isinstance(key, str)
    assert isinstance(secret, str)


def test_type_section_initial():
    section = TradingTypeSection()
    assert section.get_trading_type() == "SPOT"
    assert section.get_leverage() == 1
    assert section.get_order_type() == "MARKET"


def test_type_section_get_limit_price():
    section = TradingTypeSection()
    price = section.get_limit_price()
    assert isinstance(price, float)


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
            api_key="key", api_secret="secret", amount=50.0, currency="USDC",
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
            api_key="", api_secret="", amount=10.0, currency="USDT",
            sl=1.01, sl_type="PERCENT", timeframe=1, tf_unit="MINUTES",
        )
        changes = ConfirmDialogHelper.build_changes_summary(form)
        assert len(changes) == 1
        assert "No hay cambios" in changes[0]


def test_mode_section_restore():
    section = TradingModeSection()
    snapshot = {"mode": "LIVE", "api_key": "key123", "api_secret": "sec456"}
    section.restore(snapshot)
    assert section.get_mode() == "LIVE"
    key, secret = section.get_api_keys()
    assert key == "key123"
    assert secret == "sec456"


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
