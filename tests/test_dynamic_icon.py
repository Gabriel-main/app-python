"""
Tests de DynamicIcon y su integración (T2.1 — bug de glifos en Flet 0.86.5).

Regresión: `ft.Icon.name` NO es un campo serializable en Flet 0.86.5 —
asignarlo dejaba el glifo congelado. Los 4 componentes deben cambiar el
campo `icon` en runtime.
"""
import flet as ft
import pytest

from core.events import BotSignalEvent
from ui.components.bot_status_bar import BotStatusBar
from ui.components.connection_indicator import ConnectionIndicator
from ui.components.dynamic_icon import DynamicIcon
from ui.components.notification_toast import NotificationToast
from ui.components.settings_sections import SymbolValidationIndicator


def test_set_icon_mutates_serializable_field():
    icon = DynamicIcon(ft.Icons.WIFI_FIND, size=14)
    assert icon.icon == ft.Icons.WIFI_FIND

    icon.set_icon(ft.Icons.WIFI_OFF, ft.Colors.RED_400)

    assert icon.icon == ft.Icons.WIFI_OFF      # campo serializable cambiado
    assert icon.color == ft.Colors.RED_400
    assert "name" not in icon._values          # jamás usa el campo falso


def test_connection_indicator_changes_glyph_per_status():
    ind = ConnectionIndicator()
    assert ind._icon.icon == ft.Icons.WIFI_FIND

    ind._apply_status("DISCONNECTED", "")
    assert ind._icon.icon == ft.Icons.WIFI_OFF
    assert ind._icon.color == ft.Colors.RED_400

    ind._apply_status("CONNECTED", "Conectado")
    assert ind._icon.icon == ft.Icons.WIFI
    assert ind._icon.color == ft.Colors.GREEN_400


def test_symbol_validation_indicator_changes_glyph():
    indicator = SymbolValidationIndicator()

    indicator.set_status(indicator.INVALID, symbol="FAKEUSDT", trading_type="SPOT")
    assert indicator._icon.icon == ft.Icons.CANCEL        # NO queda en CHECK_CIRCLE

    indicator.set_status(indicator.VALIDATING, symbol="BTCUSDT")
    assert indicator._icon.icon == ft.Icons.HOURGLASS_EMPTY

    indicator.set_status(indicator.VALID, symbol="BTCUSDT", trading_type="SPOT")
    assert indicator._icon.icon == ft.Icons.CHECK_CIRCLE


@pytest.mark.asyncio
async def test_notification_toast_error_shows_error_glyph():
    toast = NotificationToast()
    assert toast._icon.icon == ft.Icons.CHECK_CIRCLE

    toast._show(success=False, title="Error", detail="fallo")

    assert toast._icon.icon == ft.Icons.ERROR   # NO el check de éxito
    assert toast._icon.color == ft.Colors.RED_400

    if toast._hide_task:                        # no dejar task huérfana
        toast._hide_task.cancel()


@pytest.mark.asyncio
async def test_bot_status_bar_signal_glyph_follows_signal():
    bar = BotStatusBar()
    assert bar._signal_icon.icon == ft.Icons.REMOVE

    await bar._on_bot_signal(BotSignalEvent(
        symbol="BTCUSDT", signal="BUY",
        ma_fast=65000.0, ma_slow=64000.0, confidence=0.8,
    ))
    assert bar._signal_icon.icon == ft.Icons.ARROW_UPWARD
    assert bar._signal_icon.color == ft.Colors.GREEN_400

    await bar._on_bot_signal(BotSignalEvent(
        symbol="BTCUSDT", signal="SELL",
        ma_fast=64000.0, ma_slow=65000.0, confidence=0.8,
    ))
    assert bar._signal_icon.icon == ft.Icons.ARROW_DOWNWARD
    assert bar._signal_icon.color == ft.Colors.RED_400
