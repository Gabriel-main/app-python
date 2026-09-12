"""
MiniChart — Gráfico sparkline de los últimos N ticks de precio.

Refactorizado para aplicar SRP:
- Usa EventBusSubscriber mixin para lifecycle
"""
from __future__ import annotations

import logging
from collections import deque

import flet as ft
import flet.canvas as cv

from config.settings import settings
from core.events import BalanceUpdateEvent, PriceTickEvent, SettingsUpdatedEvent
from ui.components.base import EventBusSubscriber

log = logging.getLogger(__name__)


class MiniChart(ft.Container, EventBusSubscriber):
    """Sparkline de precio de los últimos PRICE_BUFFER_SIZE ticks."""

    HEIGHT = 90
    PADDING = 8

    def __init__(self, symbol: str = "BTCUSDT") -> None:
        super().__init__()
        self.symbol = symbol
        self._prices: deque[float] = deque(maxlen=settings.PRICE_BUFFER_SIZE)

        self._canvas = cv.Canvas(
            content=ft.Container(),
            width=300,
            height=self.HEIGHT,
        )

        self._chart_label = ft.Text("Precio 1m", size=10, color=ft.Colors.BLUE_GREY_400)

        self.content = ft.Column(
            controls=[
                self._chart_label,
                self._canvas,
            ],
            spacing=4,
        )
        self.bgcolor = ft.Colors.with_opacity(0.05, ft.Colors.WHITE)
        self.border_radius = 12
        self.padding = self.PADDING
        self.expand = True

        self._event_subscriptions = [
            (PriceTickEvent, self._on_price_tick),
            (SettingsUpdatedEvent, self._on_settings_updated),
            (BalanceUpdateEvent, self._on_balance_update),
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
            self._prices.clear()
            self._redraw()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    async def _on_price_tick(self, event: PriceTickEvent) -> None:
        if event.symbol != self.symbol:
            return
        self._prices.append(event.price)
        self._redraw()

    async def _on_settings_updated(self, event: SettingsUpdatedEvent) -> None:
        self._sync_symbol()

    async def _on_balance_update(self, event: BalanceUpdateEvent) -> None:
        type_labels = {
            "SPOT": "Precio Spot",
            "FUTURES": "Precio Futures",
            "MARGIN": "Precio Margin",
        }
        label = type_labels.get(event.trading_type, "Precio 1m")
        self._chart_label.value = label
        try:
            self._chart_label.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Dibujo del sparkline
    # ------------------------------------------------------------------
    def _redraw(self) -> None:
        if len(self._prices) < 2:
            return

        prices = list(self._prices)
        min_p = min(prices)
        max_p = max(prices)
        price_range = max_p - min_p or 1

        canvas_width = max(self.width or 300, 200) - self.PADDING * 2
        h = self.HEIGHT - self.PADDING * 2
        n = len(prices)

        self._canvas.width = canvas_width + self.PADDING * 2

        def to_xy(i: int, p: float):
            x = (i / (n - 1)) * canvas_width + self.PADDING
            y = h - ((p - min_p) / price_range) * h + self.PADDING
            return x, y

        shapes: list = []
        for i in range(n - 1):
            x1, y1 = to_xy(i, prices[i])
            x2, y2 = to_xy(i + 1, prices[i + 1])
            color = ft.Colors.GREEN_400 if prices[i + 1] >= prices[i] else ft.Colors.RED_400
            shapes.append(
                cv.Line(
                    x1=x1, y1=y1, x2=x2, y2=y2,
                    paint=ft.Paint(
                        stroke_width=1.5,
                        style=ft.PaintingStyle.STROKE,
                        color=color,
                    ),
                )
            )

        lx, ly = to_xy(n - 1, prices[-1])
        shapes.append(
            cv.Circle(
                x=lx, y=ly, radius=3,
                paint=ft.Paint(color=ft.Colors.WHITE),
            )
        )

        self._canvas.shapes = shapes
        try:
            self._canvas.update()
        except RuntimeError:
            pass
