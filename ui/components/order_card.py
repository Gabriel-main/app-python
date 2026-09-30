"""
OrderCard — Tarjeta de orden (ejecutada / pendiente / cancelada).

Refactorizado de función a clase para aplicar:
- SRP: Construcción + estado + flash viven en la tarjeta; la vista solo
  la inserta/actualiza y nunca muta sus campos internos.
- DRY: Colores/etiquetas de estado salen de colors.STATUS_COLORS;
  el lado usa SIDE_COLORS / SIDE_LABELS y el modo MODE_COLORS.
- PERFORMANCE: update_status() muta en sitio (sin recrear widgets).
- REACTIVIDAD: El flash verde/rojo usa animate_opacity + un único
  asyncio.Task one-shot (CERO POLLING), cancelado en will_unmount.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import flet as ft

from core.update_batcher import update_batcher
from ui.components.colors import MODE_COLORS, SIDE_COLORS, SIDE_LABELS, STATUS_COLORS

_CARD_BG = ft.Colors.with_opacity(0.08, ft.Colors.WHITE)
_UNKNOWN_COLOR = ft.Colors.BLUE_GREY_400

# Duración del flash (segundos)
_FLASH_IN = 0.30
_FLASH_HOLD = 0.25
_FLASH_OUT = 0.25
_FLASH_SETTLE = 0.35


def _fmt_timestamp(ts: float | int) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")
    except Exception:
        return "---"


class OrderCard(ft.Card):
    """Tarjeta de orden. `order` es un dict con campos de Order."""

    def __init__(self, order: dict, *, flash: bool = False) -> None:
        super().__init__()
        self.order_id: str | None = order.get("order_id")
        self._flash_task: asyncio.Task | None = None

        side = order.get("side", "BUY")
        mode = order.get("mode", "PAPER")
        pnl = order.get("pnl")
        status = str(order.get("status") or "FILLED")

        side_fg, side_bg = SIDE_COLORS.get(side, (ft.Colors.WHITE, ft.Colors.GREY_800))
        side_label = SIDE_LABELS.get(side, side)
        self._mode_color = MODE_COLORS.get(mode, ft.Colors.BLUE_GREY_400)
        status_color, status_label = STATUS_COLORS.get(status, (_UNKNOWN_COLOR, status))
        self._status = status
        self._status_color = status_color
        self._pnl_value = pnl

        pnl_text = "---"
        pnl_color = ft.Colors.BLUE_GREY_400
        if pnl is not None:
            sign = "+" if pnl >= 0 else ""
            pnl_text = f"{sign}{pnl:.2f} USDT"
            pnl_color = ft.Colors.GREEN_400 if pnl >= 0 else ft.Colors.RED_400

        self._symbol = ft.Text(
            order.get("symbol", "---"),
            size=14,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.WHITE,
        )
        self._detail = ft.Text(
            f"${float(order.get('price') or 0):,.2f}  ×  "
            f"{float(order.get('quantity') or 0):.4f}",
            size=11,
            color=ft.Colors.BLUE_GREY_300,
        )
        self._pnl = ft.Text(
            pnl_text,
            size=13,
            weight=ft.FontWeight.W_600,
            color=pnl_color,
            text_align=ft.TextAlign.END,
        )
        self._status_chip = self._make_chip(status_label, status_color)
        self._mode_chip = self._make_chip(mode, self._mode_color)
        self._timestamp = ft.Text(_fmt_timestamp(order.get("timestamp", 0)), size=9, color=ft.Colors.BLUE_GREY_500)

        self.elevation = 0
        self.bgcolor = _CARD_BG
        self.animate_opacity = ft.Animation(300, ft.AnimationCurve.EASE_OUT)
        self.opacity = 1.0
        self.content = ft.Container(
            padding=ft.Padding(left=16, right=16, top=12, bottom=12),
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Text(side_label, size=11, weight=ft.FontWeight.BOLD, color=side_fg),
                        bgcolor=side_bg,
                        border_radius=6,
                        padding=ft.Padding(left=8, right=8, top=4, bottom=4),
                    ),
                    ft.Column(
                        controls=[self._symbol, self._detail],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Column(
                        controls=[
                            self._pnl,
                            ft.Row(
                                controls=[
                                    self._status_chip,
                                    self._mode_chip,
                                    self._timestamp,
                                ],
                                spacing=4,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                        spacing=4,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
        )

        if flash:
            self._start_flash()

    # ------------------------------------------------------------------
    # Construcción interna
    # ------------------------------------------------------------------
    @staticmethod
    def _make_chip(label: str, color: ft.Color) -> ft.Container:
        """Chip outline (borde + texto en color de estado)."""
        return ft.Container(
            content=ft.Text(label, size=9, color=color),
            border=ft.Border.all(1, color),
            border_radius=4,
            padding=ft.Padding(left=4, right=4, top=2, bottom=2),
        )

    def _set_chip(self, chip: ft.Container, label: str, color: ft.Color) -> None:
        text = chip.content
        text.value = label
        text.color = color
        chip.border = ft.Border.all(1, color)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    @property
    def status(self) -> str:
        return self._status

    @property
    def pnl_text(self) -> str:
        return self._pnl.value or ""

    def set_pnl(self, value: float) -> None:
        if value == self._pnl_value:
            return
        self._pnl_value = value
        self._pnl.value = f"{'+' if value >= 0 else ''}{value:.2f} USDT"
        self._pnl.color = ft.Colors.GREEN_400 if value >= 0 else ft.Colors.RED_400
        update_batcher.mark_dirty(self._pnl)

    def flash(self) -> None:
        """Reproduce el flash de aparición (verde/rojo/ámbar)."""
        self._start_flash()

    def update_status(self, status: str, *, flash: bool = False) -> None:
        """Cambia el estado de la orden en sitio (sin recrear la tarjeta)."""
        color, label = STATUS_COLORS.get(status, (_UNKNOWN_COLOR, status))
        self._status = status
        self._status_color = color
        self._set_chip(self._status_chip, label, color)
        update_batcher.mark_dirty(self._status_chip)
        if flash:
            self._start_flash()

    def will_unmount(self) -> None:
        if self._flash_task and not self._flash_task.done():
            self._flash_task.cancel()

    # ------------------------------------------------------------------
    # Flash de aparición (one-shot, CERO POLLING)
    # ------------------------------------------------------------------
    def _start_flash(self) -> None:
        # Sin event loop (p. ej. construcción fuera de runtime) no hay
        # animación posible: la tarjeta se muestra en su estado neutro.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._flash_task and not self._flash_task.done():
            self._flash_task.cancel()
        self._flash_task = asyncio.create_task(
            self._run_flash(), name=f"order_card_flash_{self.order_id}"
        )

    async def _run_flash(self) -> None:
        """Aparece fundido en color de estado, parpadea y se asienta neutro."""
        flash_bg = ft.Colors.with_opacity(0.35, self._status_color)
        try:
            self.opacity = 0.0
            self.bgcolor = flash_bg
            update_batcher.mark_dirty(self)

            await asyncio.sleep(0.05)
            self.opacity = 1.0
            update_batcher.mark_dirty(self)
            await asyncio.sleep(_FLASH_IN + _FLASH_HOLD)

            self.opacity = 0.0
            update_batcher.mark_dirty(self)
            await asyncio.sleep(_FLASH_OUT)

            self.bgcolor = _CARD_BG
            self.opacity = 1.0
            update_batcher.mark_dirty(self)
            await asyncio.sleep(_FLASH_SETTLE)
        except asyncio.CancelledError:
            self.bgcolor = _CARD_BG
            self.opacity = 1.0
            raise
