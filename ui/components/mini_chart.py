"""
MiniChart — Gráfico sparkline de los últimos N ticks de precio.

Dibuja una línea de precio usando ft.Canvas con puntos conectados.
Se actualiza en cada PriceTickEvent añadiendo el nuevo precio al buffer.

Regla: Solo redibuja el canvas (chart_canvas.update()), no la vista completa.
"""
from __future__ import annotations

from collections import deque

import flet as ft
import flet.canvas as cv

from config.settings import settings
from core.event_bus import event_bus
from core.events import PriceTickEvent


class MiniChart(ft.Container):
    """Sparkline de precio de los últimos PRICE_BUFFER_SIZE ticks."""

    HEIGHT = 90
    PADDING = 8

    def __init__(self, symbol: str = "BTCUSDT") -> None:
        super().__init__()
        self.symbol = symbol
        self._prices: deque[float] = deque(maxlen=settings.PRICE_BUFFER_SIZE)

        self._canvas = cv.Canvas(
            content=ft.Container(),
            width=300,  # default, se recalcula en _redraw
            height=self.HEIGHT,
        )

        self.content = ft.Column(
            controls=[
                ft.Text("Precio 1m", size=10, color=ft.Colors.BLUE_GREY_400),
                self._canvas,
            ],
            spacing=4,
        )
        self.bgcolor = ft.Colors.with_opacity(0.05, ft.Colors.WHITE)
        self.border_radius = 12
        self.padding = self.PADDING
        self.expand = True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def did_mount(self) -> None:
        event_bus.subscribe(PriceTickEvent, self._on_price_tick)

    def will_unmount(self) -> None:
        event_bus.unsubscribe(PriceTickEvent, self._on_price_tick)

    # ------------------------------------------------------------------
    # Handler
    # ------------------------------------------------------------------
    async def _on_price_tick(self, event: PriceTickEvent) -> None:
        if event.symbol != self.symbol:
            return
        self._prices.append(event.price)
        self._redraw()

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

        # Usar ancho real del contenedor si está disponible
        canvas_width = max(self.width or 300, 200) - self.PADDING * 2
        h = self.HEIGHT - self.PADDING * 2
        n = len(prices)

        # Actualizar ancho del canvas
        self._canvas.width = canvas_width + self.PADDING * 2

        # Normalizar puntos a coordenadas de canvas
        def to_xy(i: int, p: float):
            x = (i / (n - 1)) * canvas_width + self.PADDING
            y = h - ((p - min_p) / price_range) * h + self.PADDING
            return x, y

        shapes: list[cv.Path] = []
        for i in range(n - 1):
            x1, y1 = to_xy(i, prices[i])
            x2, y2 = to_xy(i + 1, prices[i + 1])
            # Color verde si precio sube, rojo si baja
            color = ft.Colors.GREEN_400 if prices[i + 1] >= prices[i] else ft.Colors.RED_400
            shapes.append(
                cv.Path(
                    elements=[cv.MoveTo(x1, y1), cv.LineTo(x2, y2)],
                    paint=ft.Paint(
                        stroke_width=1.5,
                        style=ft.PaintingStyle.STROKE,
                        color=color,
                    ),
                )
            )

        # Punto del precio actual
        lx, ly = to_xy(n - 1, prices[-1])
        shapes.append(
            cv.Circle(
                x=lx, y=ly, radius=3,
                paint=ft.Paint(color=ft.Colors.WHITE),
            )
        )

        self._canvas.shapes = shapes
        self._canvas.update()
