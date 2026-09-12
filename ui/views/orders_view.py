"""
Orders View — Lista de órdenes ejecutadas.

Refactorizado para aplicar DIP:
- Usa OrderRepository en vez de acceder a DB directamente
"""
from __future__ import annotations

import asyncio
from typing import Protocol

import flet as ft

from core.event_bus import event_bus
from core.events import OrderExecutedEvent
from ui.components.order_card import OrderCard


class OrdersView(ft.Column):
    """Vista de historial de órdenes ejecutadas."""

    def __init__(self, order_repository: object | None = None) -> None:
        super().__init__()
        self._repository = order_repository
        self._load_task: asyncio.Task | None = None

        self._list_column = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        self._loading_ring = ft.ProgressRing(width=32, height=32, stroke_width=3)
        self._empty_label = ft.Text(
            "Sin órdenes aún.\nEl bot ejecutará órdenes cuando detecte señales.",
            size=13,
            color=ft.Colors.BLUE_GREY_400,
            text_align=ft.TextAlign.CENTER,
        )
        self._order_count_text = ft.Text("0 órdenes", size=11, color=ft.Colors.BLUE_GREY_400)

        self.controls = [
            # Header
            ft.Row(
                controls=[
                    ft.Text("Órdenes", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    ft.Container(expand=True),
                    self._order_count_text,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Divider(color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE), height=1),

            # Contenedor principal
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=[self._loading_ring],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                    ],
                    ref=None,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                expand=True,
            ),
            self._list_column,
        ]
        self.spacing = 12
        self.expand = True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def did_mount(self) -> None:
        event_bus.subscribe(OrderExecutedEvent, self._on_order_executed)
        self._load_task = asyncio.create_task(self._load_orders(), name="load_orders_view")

    def will_unmount(self) -> None:
        event_bus.unsubscribe(OrderExecutedEvent, self._on_order_executed)
        if self._load_task and not self._load_task.done():
            self._load_task.cancel()

    # ------------------------------------------------------------------
    # Carga inicial desde DB
    # ------------------------------------------------------------------
    async def _load_orders(self) -> None:
        try:
            if not self._repository:
                raise RuntimeError("OrderRepository no inyectado en OrdersView")

            orders = await self._repository.get_recent_orders(100)

            self._list_column.controls.clear()

            if not orders:
                self._list_column.controls.append(
                    ft.Row(
                        controls=[self._empty_label],
                        alignment=ft.MainAxisAlignment.CENTER,
                    )
                )
            else:
                for order in orders:
                    self._list_column.controls.append(OrderCard(order))

            count = len(orders) if orders else 0
            self._order_count_text.value = f"{count} orden{'es' if count != 1 else ''}"

        except asyncio.CancelledError:
            return
        except Exception as exc:
            self._list_column.controls.append(
                ft.Text(f"Error cargando órdenes: {exc}", color=ft.Colors.RED_400, size=12)
            )

        # Ocultar loading
        self._loading_ring.visible = False
        try:
            self._loading_ring.update()
            self._list_column.update()
            self._order_count_text.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Actualización reactiva
    # ------------------------------------------------------------------
    async def _on_order_executed(self, event: OrderExecutedEvent) -> None:
        order_dict = {
            "order_id": event.order_id,
            "symbol": event.symbol,
            "side": event.side,
            "quantity": event.quantity,
            "price": event.price,
            "mode": event.mode,
            "status": "FILLED",
            "pnl": None,
            "timestamp": event.timestamp,
        }

        # Quitar el mensaje de "sin órdenes" si existía
        self._list_column.controls = [
            c for c in self._list_column.controls
            if not (isinstance(c, ft.Row) and any(isinstance(x, ft.Text) and "Sin órdenes" in (x.value or "") for x in c.controls))
        ]

        self._list_column.controls.insert(0, OrderCard(order_dict))

        count = len(self._list_column.controls)
        self._order_count_text.value = f"{count} orden{'es' if count != 1 else ''}"

        try:
            self._list_column.update()
            self._order_count_text.update()
        except RuntimeError:
            pass
