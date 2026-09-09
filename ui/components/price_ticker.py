"""
PriceTicker — Widget reactivo de precio en tiempo real.

Suscrito a PriceTickEvent. Muestra precio actual con animación
de flash verde (subida) / rojo (bajada) en cada tick.

Regla: Solo actualiza los controles específicos (price_text.update()).
"""
from __future__ import annotations

import flet as ft
from core.event_bus import event_bus
from core.events import PriceTickEvent


class PriceTicker(ft.Column):
    """Widget de precio en tiempo real con flash animado."""

    def __init__(self, symbol: str = "BTCUSDT") -> None:
        super().__init__()
        self.symbol = symbol
        self._last_price: float = 0.0

        # --- Controles ---
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
        self._flash_overlay = ft.Container(
            expand=True,
            height=50,
            border_radius=8,
            opacity=0,
            animate_opacity=ft.Animation(300, ft.AnimationCurve.EASE_OUT),
        )

        # Fila precio + badge
        price_row = ft.Row(
            controls=[self._price_text, self._change_badge],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        )

        self.controls = [self._symbol_label, price_row]
        self.spacing = 2

    # ------------------------------------------------------------------
    # Lifecycle: suscribir/des-suscribir del EventBus
    # ------------------------------------------------------------------
    def did_mount(self) -> None:
        event_bus.subscribe(PriceTickEvent, self._on_price_tick)

    def will_unmount(self) -> None:
        event_bus.unsubscribe(PriceTickEvent, self._on_price_tick)

    # ------------------------------------------------------------------
    # Responsive — se llama desde DashboardView._on_resize
    # ------------------------------------------------------------------
    def _on_resize(self, width: float, height: float) -> None:
        """Ajusta tamaño de fuente del precio según ancho de pantalla."""
        is_small = width < 360
        price_size = 28 if is_small else 36
        self._price_text.style = ft.TextStyle(
            size=price_size,
            weight=ft.FontWeight.BOLD,
            color=self._price_text.color,
        )
        self._price_text.update()

    # ------------------------------------------------------------------
    # Handler
    # ------------------------------------------------------------------
    async def _on_price_tick(self, event: PriceTickEvent) -> None:
        if event.symbol != self.symbol:
            return

        is_up = event.price >= self._last_price
        self._last_price = event.price

        # Color del precio según dirección
        price_color = ft.Colors.GREEN_400 if is_up else ft.Colors.RED_400
        change_color = ft.Colors.GREEN_700 if event.change_pct >= 0 else ft.Colors.RED_700
        sign = "+" if event.change_pct >= 0 else ""

        # Actualizar controles individualmente (sin page.update())
        self._price_text.value = f"${event.price:,.2f}"
        self._price_text.color = price_color
        self._price_text.update()

        self._change_badge.content.value = f"{sign}{event.change_pct:.2f}%"
        self._change_badge.bgcolor = change_color
        self._change_badge.update()
