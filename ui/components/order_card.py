"""
OrderCard — Tarjeta de orden ejecutada.

Refactorizado para aplicar DRY:
- Usa SIDE_COLORS, SIDE_LABELS, MODE_COLORS de colors.py
"""
from __future__ import annotations

import flet as ft
from datetime import datetime

from ui.components.colors import SIDE_COLORS, SIDE_LABELS, MODE_COLORS


def OrderCard(order: dict) -> ft.Card:
    """Construye una tarjeta de orden. `order` es un dict con campos de Order."""

    side = order.get("side", "BUY")
    mode = order.get("mode", "PAPER")
    pnl = order.get("pnl")
    ts = order.get("timestamp", 0)

    side_fg, side_bg = SIDE_COLORS.get(side, (ft.Colors.WHITE, ft.Colors.GREY_800))
    side_label = SIDE_LABELS.get(side, side)
    mode_color = MODE_COLORS.get(mode, ft.Colors.BLUE_GREY_400)

    pnl_text = ""
    pnl_color = ft.Colors.BLUE_GREY_400
    if pnl is not None:
        sign = "+" if pnl >= 0 else ""
        pnl_text = f"{sign}{pnl:.2f} USDT"
        pnl_color = ft.Colors.GREEN_400 if pnl >= 0 else ft.Colors.RED_400

    # Formato de fecha
    try:
        dt = datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")
    except Exception:
        dt = "---"

    return ft.Card(
        color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE),
        elevation=0,
        content=ft.Container(
            padding=ft.Padding(left=16, right=16, top=12, bottom=12),
            content=ft.Row(
                controls=[
                    # Lado badge
                    ft.Container(
                        content=ft.Text(side_label, size=11, weight=ft.FontWeight.BOLD, color=side_fg),
                        bgcolor=side_bg,
                        border_radius=6,
                        padding=ft.Padding(left=8, right=8, top=4, bottom=4),
                    ),
                    # Info centro
                    ft.Column(
                        controls=[
                            ft.Text(
                                order.get("symbol", "---"),
                                size=14,
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.WHITE,
                            ),
                            ft.Text(
                                f"${float(order.get('price') or 0):,.2f}  ×  {float(order.get('quantity') or 0):.4f}",
                                size=11,
                                color=ft.Colors.BLUE_GREY_300,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    # Derecha: PnL + modo + fecha
                    ft.Column(
                        controls=[
                            ft.Text(
                                pnl_text or "---",
                                size=13,
                                weight=ft.FontWeight.W_600,
                                color=pnl_color,
                                text_align=ft.TextAlign.END,
                            ),
                            ft.Row(
                                controls=[
                                    ft.Container(
                                        content=ft.Text(mode, size=9, color=mode_color),
                                        border=ft.Border.all(1, mode_color),
                                        border_radius=4,
                                        padding=ft.Padding(left=4, right=4, top=2, bottom=2),
                                    ),
                                    ft.Text(dt, size=9, color=ft.Colors.BLUE_GREY_500),
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
        ),
    )
