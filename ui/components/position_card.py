"""
PositionCard — Tarjeta de posición abierta (Futures/Margin).

Muestra:
- Símbolo, lado (LONG/SHORT), leverage
- Precio de entrada, precio mark, PnL no realizado
- Barra de progreso del PnL
"""
from __future__ import annotations

import flet as ft


def PositionCard(position: dict) -> ft.Card:
    """Construye una tarjeta de posición. `position` es un dict con campos de Position."""

    side = position.get("side", "LONG")
    symbol = position.get("symbol", "---")
    quantity = position.get("quantity", 0)
    entry_price = position.get("entry_price", 0)
    mark_price = position.get("mark_price", 0)
    unrealized_pnl = position.get("unrealized_pnl", 0)
    leverage = position.get("leverage", 1)
    trading_type = position.get("trading_type", "FUTURES")

    side_color = ft.Colors.GREEN_400 if side == "LONG" else ft.Colors.RED_400
    side_bg = ft.Colors.GREEN_900 if side == "LONG" else ft.Colors.RED_900

    # Calcular PnL %
    pnl_pct = 0.0
    if entry_price > 0:
        if side == "LONG":
            pnl_pct = ((mark_price - entry_price) / entry_price) * 100 * leverage
        else:
            pnl_pct = ((entry_price - mark_price) / entry_price) * 100 * leverage

    pnl_color = ft.Colors.GREEN_400 if unrealized_pnl >= 0 else ft.Colors.RED_400
    sign = "+" if unrealized_pnl >= 0 else ""

    return ft.Card(
        color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE),
        elevation=0,
        content=ft.Container(
            padding=ft.Padding(left=16, right=16, top=12, bottom=12),
            content=ft.Column(
                controls=[
                    # Fila superior: lado + símbolo + leverage
                    ft.Row(
                        controls=[
                            # Badge LONG/SHORT
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
                            # Símbolo
                            ft.Text(
                                symbol,
                                size=14,
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.WHITE,
                            ),
                            ft.Container(expand=True),
                            # Leverage badge
                            ft.Container(
                                content=ft.Text(
                                    f"{leverage}x",
                                    size=10,
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.PURPLE_400,
                                ),
                                bgcolor=ft.Colors.PURPLE_900,
                                border_radius=4,
                                padding=ft.Padding(left=6, right=6, top=2, bottom=2),
                            ),
                            # Trading type badge
                            ft.Container(
                                content=ft.Text(
                                    trading_type,
                                    size=9,
                                    color=ft.Colors.BLUE_GREY_400,
                                ),
                                border=ft.Border.all(1, ft.Colors.BLUE_GREY_700),
                                border_radius=4,
                                padding=ft.Padding(left=4, right=4, top=2, bottom=2),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=4),
                    # Fila media: precios
                    ft.Row(
                        controls=[
                            ft.Column(
                                controls=[
                                    ft.Text("Entrada", size=9, color=ft.Colors.BLUE_GREY_500),
                                    ft.Text(f"${entry_price:,.2f}", size=12, color=ft.Colors.WHITE),
                                ],
                                spacing=1,
                                expand=True,
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text("Mark", size=9, color=ft.Colors.BLUE_GREY_500),
                                    ft.Text(f"${mark_price:,.2f}", size=12, color=ft.Colors.WHITE),
                                ],
                                spacing=1,
                                expand=True,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text("Cantidad", size=9, color=ft.Colors.BLUE_GREY_500),
                                    ft.Text(f"{quantity:.6f}", size=12, color=ft.Colors.WHITE),
                                ],
                                spacing=1,
                                expand=True,
                                horizontal_alignment=ft.CrossAxisAlignment.END,
                            ),
                        ],
                    ),
                    ft.Container(height=4),
                    # Fila inferior: PnL
                    ft.Row(
                        controls=[
                            ft.Text(
                                f"PnL: {sign}{unrealized_pnl:.2f} USDT ({sign}{pnl_pct:.2f}%)",
                                size=13,
                                weight=ft.FontWeight.W_600,
                                color=pnl_color,
                            ),
                        ],
                    ),
                ],
                spacing=0,
            ),
        ),
    )
