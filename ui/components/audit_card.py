"""
AuditCard — Tarjeta de evento de auditoría.

Refactorizado para aplicar SRP:
- Muestra un evento de auditoría con formato legible
- Icono por categoría
- Color por tipo de evento
"""
from __future__ import annotations

from datetime import datetime

import flet as ft

from core.events import AuditEvent

# ---------------------------------------------------------------------------
# Configuración por categoría (DRY)
# ---------------------------------------------------------------------------
CATEGORY_CONFIG: dict[str, dict] = {
    "CONNECTION": {"icon": ft.Icons.WIFI, "color": ft.Colors.BLUE_400, "label": "CONEXIÓN"},
    "PRICE": {"icon": ft.Icons.TRENDING_UP, "color": ft.Colors.GREEN_400, "label": "PRECIO"},
    "SIGNAL": {"icon": ft.Icons.SHOW_CHART, "color": ft.Colors.PURPLE_400, "label": "SEÑAL"},
    "ORDER": {"icon": ft.Icons.SHOPPING_CART, "color": ft.Colors.AMBER_400, "label": "ORDEN"},
    "OPERATION": {"icon": ft.Icons.SWAP_HORIZ, "color": ft.Colors.CYAN_400, "label": "OPERACIÓN"},
    "POSITION": {"icon": ft.Icons.ACCOUNT_BALANCE_WALLET, "color": ft.Colors.TEAL_400, "label": "POSICIÓN"},
    "STATE": {"icon": ft.Icons.POWER_SETTINGS_NEW, "color": ft.Colors.ORANGE_400, "label": "ESTADO"},
    "CONFIG": {"icon": ft.Icons.SETTINGS, "color": ft.Colors.GREY_400, "label": "CONFIG"},
}

_DEFAULT_CONFIG = {"icon": ft.Icons.INFO, "color": ft.Colors.BLUE_GREY_400, "label": "INFO"}


def AuditCard(event: AuditEvent) -> ft.Card:
    """Construye una tarjeta de evento de auditoría."""
    config = CATEGORY_CONFIG.get(event.category, _DEFAULT_CONFIG)

    # Formato de fecha
    try:
        dt = datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S")
    except Exception:
        dt = "--:--:--"

    return ft.Card(
        bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
        elevation=0,
        content=ft.Container(
            padding=ft.Padding(left=12, right=12, top=8, bottom=8),
            content=ft.Row(
                controls=[
                    # Icono de categoría
                    ft.Icon(config["icon"], color=config["color"], size=18),
                    # Info principal
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Container(
                                        content=ft.Text(
                                            config["label"],
                                            size=9,
                                            weight=ft.FontWeight.BOLD,
                                            color=config["color"],
                                        ),
                                        bgcolor=ft.Colors.with_opacity(0.15, config["color"]),
                                        border_radius=4,
                                        padding=ft.Padding(left=6, right=6, top=2, bottom=2),
                                    ),
                                    ft.Text(
                                        event.action,
                                        size=10,
                                        weight=ft.FontWeight.W_600,
                                        color=ft.Colors.WHITE,
                                    ),
                                    ft.Container(expand=True),
                                    ft.Text(dt, size=9, color=ft.Colors.BLUE_GREY_500),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=6,
                            ),
                            ft.Text(
                                event.detail,
                                size=11,
                                color=ft.Colors.BLUE_GREY_300,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
        ),
    )
