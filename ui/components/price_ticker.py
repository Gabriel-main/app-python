"""
PriceTicker — Widget reactivo de precio en tiempo real.

Refactorizado para aplicar SRP:
- Usa EventBusSubscriber mixin para lifecycle
"""
from __future__ import annotations

import logging

import flet as ft
from config.settings import settings
from core.events import PriceTickEvent, SettingsUpdatedEvent
from ui.components.base import EventBusSubscriber

log = logging.getLogger(__name__)


class PriceTicker(ft.Column, EventBusSubscriber):
    """Widget de precio en tiempo real con flash animado."""

    def __init__(self, symbol: str = "BTCUSDT") -> None:
        super().__init__()
        self.symbol = symbol
        self._last_price: float = 0.0

        self._symbol_label = ft.Text(
            value=symbol,
            style=ft.TextStyle(
                size=12,
                weight=ft.FontWeight.W_500,
                color=ft.Colors.BLUE_GREY_400,
                letter_spacing=2,
            ),
        )
        self._price_text = ft.Text(
            "---",
            size=36,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.WHITE,
        )
        self._change_badge = ft.Container(
            content=ft.Text("0.00%", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
            bgcolor=ft.Colors.BLUE_GREY_700,
            border_radius=6,
            padding=ft.Padding(left=8, right=8, top=3, bottom=3),
        )

        price_row = ft.Row(
            controls=[self._price_text, self._change_badge],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        )

        self.controls = [self._symbol_label, price_row]
        self.spacing = 2

        self._event_subscriptions = [
            (PriceTickEvent, self._on_price_tick),
            (SettingsUpdatedEvent, self._on_settings_updated),
        ]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def did_mount(self) -> None:
        self._setup_subscriptions()
        self._sync_symbol()

    def will_unmount(self) -> None:
        self._teardown_subscriptions()

    def _sync_symbol(self) -> None:
        if settings.TRADING_SYMBOL != self.symbol:
            self.symbol = settings.TRADING_SYMBOL
            self._symbol_label.value = self.symbol
            self._last_price = 0.0
            self._price_text.value = "---"
            try:
                self.update()
            except RuntimeError:
                pass

    # ------------------------------------------------------------------
    # Responsive
    # ------------------------------------------------------------------
    def _on_resize(self, width: float, height: float) -> None:
        is_small = width < 360
        price_size = 28 if is_small else 36
        self._price_text.style = ft.TextStyle(
            size=price_size,
            weight=ft.FontWeight.BOLD,
            color=self._price_text.color,
        )
        try:
            self._price_text.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    async def _on_price_tick(self, event: PriceTickEvent) -> None:
        if event.symbol != self.symbol:
            return

        is_up = event.price >= self._last_price
        self._last_price = event.price

        price_color = ft.Colors.GREEN_400 if is_up else ft.Colors.RED_400
        change_color = ft.Colors.GREEN_700 if event.change_pct >= 0 else ft.Colors.RED_700
        sign = "+" if event.change_pct >= 0 else ""

        self._price_text.value = f"${event.price:,.2f}"
        self._price_text.color = price_color

        self._change_badge.content.value = f"{sign}{event.change_pct:.2f}%"
        self._change_badge.bgcolor = change_color

        try:
            self._price_text.update()
            self._change_badge.update()
        except RuntimeError:
            pass

    async def _on_settings_updated(self, event: SettingsUpdatedEvent) -> None:
        self._sync_symbol()
