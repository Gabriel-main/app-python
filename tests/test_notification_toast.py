"""
Tests de NotificationToast — el detalle de OrderFailedEvent no se trunca
antes de lo accionable.

Regresión en vivo: "La cantidad 0.059 es menor al mínimo 0.454 o..." se
cortaba a 80 chars, escondiendo "Monto mínimo a precio actual: 50.00 USDT".
"""
import pytest

from core.events import OrderFailedEvent
from ui.components.notification_toast import NotificationToast


@pytest.mark.asyncio
async def test_order_failed_keeps_actionable_tail():
    toast = NotificationToast()
    error = (
        "La cantidad 0.05905333 es menor al mínimo 0.454256 operable en "
        "SOLUSDT. Monto mínimo a precio actual: 50.00 USDT."
    )
    try:
        await toast._on_order_failed(
            OrderFailedEvent(operation_id="STARTUP", side="BUY", error=error),
        )
        assert toast._detail.value == error[:160]
        # El detalle accionable (monto mínimo) no debe quedar fuera
        assert "50.00 USDT" in toast._detail.value
    finally:
        if toast._hide_task and not toast._hide_task.done():
            toast._hide_task.cancel()


@pytest.mark.asyncio
async def test_detail_allows_two_lines():
    toast = NotificationToast()
    assert toast._detail.max_lines == 2
