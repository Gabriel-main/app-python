"""
Tests de ToastShowEvent (T2.4 — feedback visible al guardar settings).

Cubre: suscripción simétrica del NotificationToast, handler que pinta el
toast, y que SettingsView._apply_changes publique el toast en éxito/error
(el feedback local no se ve porque la vista navega al Dashboard).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import flet as ft
import pytest

from core.events import ToastShowEvent
from ui.components.notification_toast import NotificationToast
from ui.views.settings_view import SettingsView


def _form() -> SimpleNamespace:
    return SimpleNamespace(
        symbol="BTCUSDT", mode="PAPER", trading_type="SPOT",
        leverage=10, order_type="MARKET", limit_price=0.0,
        amount=100.0, currency="USDT", sl=0.0, sl_type="PERCENT",
        timeframe=1, tf_unit="MINUTES",
    )


def _toasts(mock_bus) -> list[ToastShowEvent]:
    return [
        c.args[0] for c in mock_bus.publish.call_args_list
        if isinstance(c.args[0], ToastShowEvent)
    ]


# ---------------------------------------------------------------------------
# NotificationToast — suscripción y handler
# ---------------------------------------------------------------------------
def test_toast_subscribes_and_unsubscribes_toast_show_event():
    toast = NotificationToast()
    with patch("ui.components.notification_toast.event_bus") as bus:
        toast.did_mount()
        toast.will_unmount()

    subs = [c.args[0] for c in bus.subscribe.call_args_list]
    unsubs = [c.args[0] for c in bus.unsubscribe.call_args_list]
    assert ToastShowEvent in subs
    assert ToastShowEvent in unsubs
    assert subs == unsubs   # simétrico (5 subs en total, 1 por evento)


@pytest.mark.asyncio
async def test_on_toast_show_displays_event():
    toast = NotificationToast()

    await toast._on_toast_show(
        ToastShowEvent(success=True, title="Configuración guardada", detail="Reconectando...")
    )

    assert toast._icon.icon == ft.Icons.CHECK_CIRCLE
    assert toast._title.value == "Configuración guardada"
    assert toast._detail.value == "Reconectando..."
    assert toast.content.visible is True

    if toast._hide_task:
        toast._hide_task.cancel()


@pytest.mark.asyncio
async def test_on_toast_show_error_uses_error_glyph():
    toast = NotificationToast()

    await toast._on_toast_show(
        ToastShowEvent(success=False, title="Error al guardar", detail="boom")
    )

    assert toast._icon.icon == ft.Icons.ERROR
    assert toast._icon.color == ft.Colors.RED_400

    if toast._hide_task:
        toast._hide_task.cancel()


# ---------------------------------------------------------------------------
# SettingsView — publica el toast en éxito y error
# ---------------------------------------------------------------------------
def test_apply_changes_success_publishes_toast():
    with patch("ui.views.settings_view.event_bus") as bus, \
         patch.object(SettingsView, "_build_form_data", return_value=_form()), \
         patch.object(SettingsView, "_save_config_to_db", new=AsyncMock()), \
         patch.object(SettingsView, "_update_settings_from_form"):
        view = SettingsView()
        asyncio.run(view._apply_changes())

    toasts = _toasts(bus)
    assert len(toasts) == 1
    assert toasts[0].success is True
    assert toasts[0].title == "Configuración guardada"


def test_apply_changes_error_publishes_toast():
    with patch("ui.views.settings_view.event_bus") as bus, \
         patch("ui.views.settings_view.settings"), \
         patch.object(SettingsView, "_build_form_data", return_value=_form()), \
         patch.object(SettingsView, "_save_config_to_db",
                      new=AsyncMock(side_effect=RuntimeError("db down"))):
        view = SettingsView()
        asyncio.run(view._apply_changes())

    toasts = _toasts(bus)
    assert len(toasts) == 1
    assert toasts[0].success is False
    assert toasts[0].title == "Error al guardar"
    assert "db down" in toasts[0].detail
