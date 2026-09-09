"""
Orders View — Lista de órdenes ejecutadas.

Carga el historial desde la base de datos al montar la vista.
Se actualiza reactivamente con cada OrderExecutedEvent nuevo.
"""
from __future__ import annotations

import flet as ft
from sqlmodel import select

from core.event_bus import event_bus
from core.events import OrderExecutedEvent
from database.connection import get_session
from database.models import Order
from ui.components.order_card import OrderCard


class OrdersView(ft.Column):
    """Vista de historial de órdenes ejecutadas."""

    def __init__(self) -> None:
        super().__init__()
        self._loading = True

        self._list_column = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO)
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
        import asyncio
        asyncio.create_task(self._load_orders(), name="load_orders_view")

    def will_unmount(self) -> None:
        event_bus.unsubscribe(OrderExecutedEvent, self._on_order_executed)

    # ------------------------------------------------------------------
    # Carga inicial desde DB
    # ------------------------------------------------------------------
    async def _load_orders(self) -> None:
        try:
            async with get_session() as session:
                result = await session.exec(
                    select(Order).order_by(Order.timestamp.desc()).limit(100)
                )
                orders = result.all()

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
                    self._list_column.controls.append(
                        OrderCard(order.model_dump())
                    )

            count = len(orders) if orders else 0
            self._order_count_text.value = f"{count} orden{'es' if count != 1 else ''}"

        except Exception as exc:
            self._list_column.controls.append(
                ft.Text(f"Error cargando órdenes: {exc}", color=ft.Colors.RED_400, size=12)
            )

        # Ocultar loading
        self._loading_ring.visible = False
        self._loading_ring.update()
        self._list_column.update()
        self._order_count_text.update()

    # ------------------------------------------------------------------
    # Actualización reactiva
    # ------------------------------------------------------------------
    async def _on_order_executed(self, event: OrderExecutedEvent) -> None:
        """Añade la nueva orden al tope de la lista sin recargar."""
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

        # Actualizar contador
        count = len(self._list_column.controls)
        self._order_count_text.value = f"{count} orden{'es' if count != 1 else ''}"

        self._list_column.update()
        self._order_count_text.update()
