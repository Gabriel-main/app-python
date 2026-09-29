"""
NotificationToast — Toast efímero para notificaciones de órdenes.

Se suscribe a OrderExecutedEvent y OrderFailedEvent, muestra un toast
auto-ocultable con fade-out.

Principios:
- SRP: Solo muestra notificaciones, no ejecuta lógica de negocio
- OCP: Nuevo evento = nueva suscripción, no modificar existente
- DIP: Depende de EventBus (abstracción)
- REACTIVIDAD ATÓMICA: Solo control.update() vía update_batcher
- CERO POLLING: Se oculta con asyncio.sleep + animate_opacity
"""
from __future__ import annotations

import asyncio

import flet as ft

from core.event_bus import event_bus
from core.events import OrderExecutedEvent, OrderFailedEvent
from core.update_batcher import update_batcher

# Colores del toast
_SUCCESS_COLOR = ft.Colors.GREEN_400
_ERROR_COLOR = ft.Colors.RED_400
_SUCCESS_BG = "#1b3a1f"
_ERROR_BG = "#3a1b1b"

_TOAST_DURATION = 4.0  # segundos visibles


class NotificationToast(ft.Container):
    """Toast flotante que muestra resultados de órdenes (éxito o fallo)."""

    def __init__(self) -> None:
        super().__init__()

        self._hide_task: asyncio.Task | None = None

        self._icon = ft.Icon(ft.Icons.CHECK_CIRCLE, color=_SUCCESS_COLOR, size=20)
        self._title = ft.Text(
            "",
            size=13,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.WHITE,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        self._detail = ft.Text(
            "",
            size=11,
            color=ft.Colors.GREY_400,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        self.content = ft.Container(
            bgcolor=_SUCCESS_BG,
            border_radius=12,
            padding=ft.Padding(left=14, right=14, top=10, bottom=10),
            content=ft.Row(
                controls=[
                    self._icon,
                    ft.Column(
                        controls=[self._title, self._detail],
                        spacing=2,
                        expand=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            opacity=0.0,
            animate_opacity=ft.Animation(300, ft.AnimationCurve.EASE_IN_OUT),
            visible=False,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def did_mount(self) -> None:
        event_bus.subscribe(OrderExecutedEvent, self._on_order_executed)
        event_bus.subscribe(OrderFailedEvent, self._on_order_failed)

    def will_unmount(self) -> None:
        event_bus.unsubscribe(OrderExecutedEvent, self._on_order_executed)
        event_bus.unsubscribe(OrderFailedEvent, self._on_order_failed)
        if self._hide_task and not self._hide_task.done():
            self._hide_task.cancel()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    async def _on_order_executed(self, event: OrderExecutedEvent) -> None:
        side_label = "Compra" if event.side == "BUY" else "Venta"
        self._show(
            success=True,
            title=f"Orden ejecutada — {side_label}",
            detail=f"{event.quantity:.6f} @ ${event.price:,.2f} [{event.mode}]",
        )

    async def _on_order_failed(self, event: OrderFailedEvent) -> None:
        side_label = "compra" if event.side == "BUY" else "venta"
        self._show(
            success=False,
            title=f"Error en {side_label}",
            detail=event.error[:80],
        )

    # ------------------------------------------------------------------
    # Lógica del toast
    # ------------------------------------------------------------------
    def _show(self, *, success: bool, title: str, detail: str) -> None:
        """Muestra el toast y programa auto-ocultamiento."""
        self._icon.name = (
            ft.Icons.CHECK_CIRCLE if success else ft.Icons.ERROR
        )
        self._icon.color = _SUCCESS_COLOR if success else _ERROR_COLOR
        self._title.value = title
        self._detail.value = detail
        self.content.bgcolor = _SUCCESS_BG if success else _ERROR_BG

        # Cancelar auto-hide anterior si existe
        if self._hide_task and not self._hide_task.done():
            self._hide_task.cancel()

        # Mostrar con fade-in
        self.content.visible = True
        self.content.opacity = 1.0
        update_batcher.mark_dirty(self.content)

        # Programar auto-hide
        self._hide_task = asyncio.create_task(
            self._auto_hide(), name="notification_toast_hide"
        )

    async def _auto_hide(self) -> None:
        """Oculta el toast tras _TOAST_DURATION segundos (sin polling)."""
        try:
            await asyncio.sleep(_TOAST_DURATION)
            self.content.opacity = 0.0
            update_batcher.mark_dirty(self.content)
            await asyncio.sleep(0.3)  # espera a que termine la animación
            self.content.visible = False
            update_batcher.mark_dirty(self.content)
        except asyncio.CancelledError:
            pass
