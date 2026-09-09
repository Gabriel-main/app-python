"""
OrderCard — Tarjeta de orden ejecutada.

Recibe un dict de datos de orden y muestra:
- Símbolo, lado (BUY/SELL), precio, cantidad, modo (PAPER/LIVE), PnL.
"""
from __future__ import annotations

import flet as ft
from datetime import datetime


def OrderCard(order: dict) -> ft.Card:
    """Construye una tarjeta de orden. `order` es un dict con campos de Order."""

    side = order.get("side", "BUY")
    mode = order.get("mode", "PAPER")
    pnl = order.get("pnl")
    ts = order.get("timestamp", 0)

    side_color = ft.Colors.GREEN_400 if side == "BUY" else ft.Colors.RED_400
    side_bg = ft.Colors.GREEN_900 if side == "BUY" else ft.Colors.RED_900
    mode_color = ft.Colors.AMBER_400 if mode == "LIVE" else ft.Colors.BLUE_GREY_400

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
                    # Lado (BUY/SELL) badge
                    ft.Container(
                        content=ft.Text(
                            side,
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            color=side_color,
                        ),
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
                                f"${order.get('price', 0):,.2f}  ×  {order.get('quantity', 0):.4f}",
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
