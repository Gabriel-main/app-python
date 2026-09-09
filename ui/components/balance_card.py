"""
BalanceCard — Card de fondos/cuenta del usuario.

Muestra el saldo de la cuenta según TRADING_TYPE (Spot/Futures/Margin).
Se actualiza automáticamente con BalanceUpdateEvent (auto-refresh).
"""
from __future__ import annotations

import time

import flet as ft

from config.settings import settings
from core.event_bus import event_bus
from core.events import BalanceUpdateEvent


def _format_amount(value: float) -> str:
    """Formatea un monto con separadores de miles."""
    if value >= 1000:
        return f"${value:,.2f}"
    elif value >= 1:
        return f"${value:.4f}"
    else:
        return f"${value:.6f}"


class BalanceCard(ft.Container):
    """Card que muestra el saldo de la cuenta del usuario."""

    def __init__(self) -> None:
        super().__init__()
        self._last_update: float = 0.0

        # Badge de tipo
        self._type_badge = ft.Container(
            content=ft.Text("SPOT", size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_400),
            bgcolor=ft.Colors.BLUE_900,
            border_radius=6,
            padding=ft.Padding(left=8, right=8, top=3, bottom=3),
        )

        # Textos de saldo
        self._label_1 = ft.Text("Disponible", size=11, color=ft.Colors.BLUE_GREY_400)
        self._value_1 = ft.Text("---", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)

        self._label_2 = ft.Text("Bloqueado", size=11, color=ft.Colors.BLUE_GREY_400)
        self._value_2 = ft.Text("---", size=13, color=ft.Colors.BLUE_GREY_300)

        self._label_3 = ft.Text("", size=11, color=ft.Colors.BLUE_GREY_400)
        self._value_3 = ft.Text("", size=13, color=ft.Colors.BLUE_GREY_300)

        # Timestamp
        self._time_text = ft.Text(
            "Sin datos",
            size=9,
            color=ft.Colors.BLUE_GREY_500,
        )

        # Loading indicator
        self._loading = ft.ProgressRing(
            width=14, height=14, stroke_width=2,
            color=ft.Colors.CYAN_400,
            visible=False,
        )

        self.bgcolor = ft.Colors.with_opacity(0.06, ft.Colors.WHITE)
        self.border_radius = 14
        self.padding = ft.Padding(left=16, right=16, top=12, bottom=12)

        self.content = ft.Column(
            controls=[
                # Header
                ft.Row(
                    controls=[
                        ft.Text("💰 Fondos", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                        ft.Container(expand=True),
                        self._type_badge,
                        ft.Container(width=4),
                        self._loading,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=8),
                # Fila 1
                ft.Row(
                    controls=[
                        ft.Column(
                            controls=[self._label_1, self._value_1],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                ),
                ft.Container(height=4),
                # Fila 2
                ft.Row(
                    controls=[
                        ft.Column(
                            controls=[self._label_2, self._value_2],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                ),
                ft.Container(height=4),
                # Fila 3 (oculta por defecto)
                ft.Row(
                    controls=[
                        ft.Column(
                            controls=[self._label_3, self._value_3],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    visible=False,
                ),
                # Timestamp
                self._time_text,
            ],
            spacing=0,
        )

    def did_mount(self) -> None:
        event_bus.subscribe(BalanceUpdateEvent, self._on_balance_update)

    def will_unmount(self) -> None:
        event_bus.unsubscribe(BalanceUpdateEvent, self._on_balance_update)

    async def _on_balance_update(self, event: BalanceUpdateEvent) -> None:
        """Actualiza la card con el nuevo saldo."""
        self._last_update = event.timestamp
        self._update_badge(event.trading_type)
        self._update_values(event)
        self._update_timestamp()
        self.update()

    def _update_badge(self, trading_type: str) -> None:
        """Actualiza el badge según TRADING_TYPE."""
        type_colors = {
            "SPOT": (ft.Colors.BLUE_400, ft.Colors.BLUE_900, "SPOT"),
            "FUTURES": (ft.Colors.PURPLE_400, ft.Colors.PURPLE_900, "FUTURES"),
            "MARGIN": (ft.Colors.ORANGE_400, ft.Colors.ORANGE_900, "MARGIN"),
        }
        color, bg, label = type_colors.get(trading_type, (ft.Colors.BLUE_400, ft.Colors.BLUE_900, "SPOT"))
        self._type_badge.content = ft.Text(label, size=10, weight=ft.FontWeight.BOLD, color=color)
        self._type_badge.bgcolor = bg

    def _update_values(self, event: BalanceUpdateEvent) -> None:
        """Actualiza los valores según TRADING_TYPE."""
        # Resetear
        self._label_2.visible = True
        self._value_2.visible = True
        self._label_3.visible = False
        self._value_3.visible = False

        if event.trading_type == "FUTURES":
            self._label_1.value = "Wallet"
            self._value_1.value = _format_amount(event.free)
            self._label_2.value = "Disponible"
            self._value_2.value = _format_amount(event.available)
            if event.unrealized_pnl != 0:
                self._label_3.value = "PnL No Real."
                pnl_color = ft.Colors.GREEN_400 if event.unrealized_pnl >= 0 else ft.Colors.RED_400
                sign = "+" if event.unrealized_pnl >= 0 else ""
                self._value_3.value = f"{sign}{_format_amount(event.unrealized_pnl)}"
                self._value_3.color = pnl_color
                self._label_3.visible = True
                self._value_3.visible = True

        elif event.trading_type == "MARGIN":
            self._label_1.value = "Net Asset"
            self._value_1.value = _format_amount(event.free)
            self._label_2.value = "Prestado"
            self._value_2.value = _format_amount(event.borrowed)
            if event.interest > 0:
                self._label_3.value = "Interés"
                self._value_3.value = _format_amount(event.interest)
                self._label_3.visible = True
                self._value_3.visible = True

        else:  # SPOT
            self._label_1.value = "Disponible"
            self._value_1.value = _format_amount(event.free)
            self._label_2.value = "Bloqueado"
            self._value_2.value = _format_amount(event.locked)

    def _update_timestamp(self) -> None:
        """Actualiza el timestamp de la última actualización."""
        elapsed = time.time() - self._last_update
        if elapsed < 5:
            self._time_text.value = "Actualizado ahora"
        elif elapsed < 60:
            self._time_text.value = f" hace {int(elapsed)}s"
        else:
            self._time_text.value = f" hace {int(elapsed / 60)}m"
