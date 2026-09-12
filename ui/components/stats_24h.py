"""
Stats24H — Componente reactivo de estadísticas 24h.

Extraído de DashboardView para aplicar SRP.
Muestra high, low y volumen de 24h, actualizado vía PriceTickEvent.
"""
from __future__ import annotations

import logging

import flet as ft

from config.settings import settings
from core.event_bus import event_bus
from core.events import PriceTickEvent
from ui.components.base import EventBusSubscriber

log = logging.getLogger(__name__)


class Stats24H(ft.Container, EventBusSubscriber):
    """Stats 24h: high, low, volumen — reactivo a PriceTickEvent."""

    HEIGHT = 70

    def __init__(self, symbol: str = "BTCUSDT") -> None:
        super().__init__()
        self._symbol = symbol

        self._high_text = ft.Text(
            "---", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.GREEN_400
        )
        self._low_text = ft.Text(
            "---", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.RED_400
        )
        self._vol_text = ft.Text(
            "---", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.BLUE_300
        )

        self._event_subscriptions = [
            (PriceTickEvent, self._on_price_tick),
        ]

        self.bgcolor = ft.Colors.with_opacity(0.06, ft.Colors.WHITE)
        self.border_radius = 14
        self.padding = ft.Padding(left=16, right=16, top=12, bottom=12)
        self.content = ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        ft.Text("Máx 24h", size=10, color=ft.Colors.BLUE_GREY_400),
                        self._high_text,
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.VerticalDivider(color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)),
                ft.Column(
                    controls=[
                        ft.Text("Mín 24h", size=10, color=ft.Colors.BLUE_GREY_400),
                        self._low_text,
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.VerticalDivider(color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)),
                ft.Column(
                    controls=[
                        ft.Text("Volumen", size=10, color=ft.Colors.BLUE_GREY_400),
                        self._vol_text,
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def did_mount(self) -> None:
        self._setup_subscriptions()

    def will_unmount(self) -> None:
        self._teardown_subscriptions()

    # ------------------------------------------------------------------
    # Responsive
    # ------------------------------------------------------------------
    def _on_resize(self, width: float, height: float) -> None:
        is_small = width < 360
        size = 11 if is_small else 13
        self._high_text.style = ft.TextStyle(size=size, weight=ft.FontWeight.W_600, color=ft.Colors.GREEN_400)
        self._low_text.style = ft.TextStyle(size=size, weight=ft.FontWeight.W_600, color=ft.Colors.RED_400)
        self._vol_text.style = ft.TextStyle(size=size, weight=ft.FontWeight.W_500, color=ft.Colors.BLUE_300)
        try:
            self._high_text.update()
            self._low_text.update()
            self._vol_text.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    async def _on_price_tick(self, event: PriceTickEvent) -> None:
        if event.symbol != self._symbol:
            return

        self._high_text.value = f"${event.high_24h:,.2f}"
        self._low_text.value = f"${event.low_24h:,.2f}"
        vol_m = event.volume / 1_000_000
        self._vol_text.value = f"${vol_m:.1f}M"

        try:
            self._high_text.update()
            self._low_text.update()
            self._vol_text.update()
        except RuntimeError:
            pass

    def update_symbol(self, symbol: str) -> None:
        """Actualiza el símbolo filtrado."""
        self._symbol = symbol
