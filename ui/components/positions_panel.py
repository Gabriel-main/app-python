"""
PositionsPanel — Panel de posiciones abiertas (Futures/Margin).

Refactorizado para aplicar SRP + DRY:
- Usa base mixin para lifecycle
- Manejo seguro de RuntimeError en updates
"""
from __future__ import annotations

import flet as ft

from core.event_bus import event_bus
from core.events import PositionUpdateEvent
from ui.components.position_card import PositionCard


class PositionsPanel(ft.Container):
    """Panel que lista posiciones abiertas con PnL en tiempo real."""

    def __init__(self) -> None:
        super().__init__()
        self._positions: dict[str, dict] = {}

        self._empty_text = ft.Text(
            "Sin posiciones abiertas.",
            size=12,
            color=ft.Colors.BLUE_GREY_400,
            text_align=ft.TextAlign.CENTER,
        )
        self._count_text = ft.Text("0 posiciones", size=11, color=ft.Colors.BLUE_GREY_400)
        self._total_pnl_text = ft.Text(
            "PnL Total: $0.00",
            size=12,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.BLUE_GREY_400,
        )
        self._positions_column = ft.Column(spacing=8)

        self.content = ft.Container(
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_radius=14,
            padding=ft.Padding(left=16, right=16, top=12, bottom=12),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text("📊 Posiciones Abiertas", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                            ft.Container(expand=True),
                            self._count_text,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=4),
                    self._total_pnl_text,
                    ft.Container(height=4),
                    self._positions_column,
                    self._empty_text,
                ],
                spacing=0,
            ),
        )

    def did_mount(self) -> None:
        event_bus.subscribe(PositionUpdateEvent, self._on_position_update)

    def will_unmount(self) -> None:
        event_bus.unsubscribe(PositionUpdateEvent, self._on_position_update)

    async def _on_position_update(self, event: PositionUpdateEvent) -> None:
        key = f"{event.symbol}_{event.side}"
        self._positions[key] = {
            "symbol": event.symbol,
            "side": event.side,
            "quantity": event.quantity,
            "entry_price": event.entry_price,
            "mark_price": event.mark_price,
            "unrealized_pnl": event.unrealized_pnl,
            "leverage": event.leverage,
            "trading_type": event.trading_type,
        }
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        self._positions_column.controls.clear()

        if not self._positions:
            self._empty_text.visible = True
            self._total_pnl_text.value = "PnL Total: $0.00"
            self._total_pnl_text.color = ft.Colors.BLUE_GREY_400
        else:
            self._empty_text.visible = False
            total_pnl = 0.0

            for pos in self._positions.values():
                self._positions_column.controls.append(PositionCard(pos))
                total_pnl += pos.get("unrealized_pnl", 0)

            sign = "+" if total_pnl >= 0 else ""
            pnl_color = ft.Colors.GREEN_400 if total_pnl >= 0 else ft.Colors.RED_400
            self._total_pnl_text.value = f"PnL Total: {sign}${total_pnl:.2f}"
            self._total_pnl_text.color = pnl_color

        count = len(self._positions)
        self._count_text.value = f"{count} posición{'es' if count != 1 else ''}"

        try:
            self._positions_column.update()
            self._count_text.update()
            self._total_pnl_text.update()
            self._empty_text.update()
        except RuntimeError:
            pass
