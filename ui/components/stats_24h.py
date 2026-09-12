"""
Stats24H — Estadísticas 24h usando StatCard (DRY).

Refactorizado para aplicar:
- DRY: Reutiliza StatCard en lugar de Container manual
- SRP: Solo maneja datos de stats 24h
"""
from __future__ import annotations

import logging

import flet as ft

from core.event_bus import event_bus
from core.events import PriceTickEvent
from ui.components.stat_card import StatCard

log = logging.getLogger(__name__)


class Stats24H(StatCard):
    """Stats 24h: high, low, volumen — reactivo a PriceTickEvent."""

    def __init__(self, symbol: str = "BTCUSDT") -> None:
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

        super().__init__(
            title="Estadísticas 24h",
            rows=[
                ("Máx 24h", self._high_text),
                ("Mín 24h", self._low_text),
                ("Volumen", self._vol_text),
            ],
            event_subscriptions=[(PriceTickEvent, self._on_price_tick)],
        )

    def did_mount(self) -> None:
        self._setup_subscriptions()

    def will_unmount(self) -> None:
        self._teardown_subscriptions()

    def _on_resize(self, width: float, height: float) -> None:
        is_small = width < 360
        size = 11 if is_small else 13
        self._high_text.style = ft.TextStyle(
            size=size, weight=ft.FontWeight.W_600, color=ft.Colors.GREEN_400
        )
        self._low_text.style = ft.TextStyle(
            size=size, weight=ft.FontWeight.W_600, color=ft.Colors.RED_400
        )
        self._vol_text.style = ft.TextStyle(
            size=size, weight=ft.FontWeight.W_500, color=ft.Colors.BLUE_300
        )
        try:
            self._high_text.update()
            self._low_text.update()
            self._vol_text.update()
        except RuntimeError:
            pass

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
