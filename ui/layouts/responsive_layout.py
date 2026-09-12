"""
ResponsiveLayout — Layout responsivo que adapta secciones a horizontal/vertical.

Aplica:
- DIP: Depende de DashboardLayout (abstracción), no de implementaciones concretas
- LSP: Es sustituible por cualquier otro DashboardLayout
- SRP: Solo construye layout, no maneja eventos ni lifecycle
"""
from __future__ import annotations

from typing import Any

import flet as ft

from ui.layouts.base_layout import DashboardLayout


class ResponsiveDashboardLayout(DashboardLayout):
    """Layout responsivo: combina stats+balance y bot_status+toggle en filas."""

    BREAKPOINT: float = 600.0

    def build(self, components: dict[str, Any]) -> ft.Control:
        stats_row = ft.Row(
            controls=[
                components["stats"],
                components["balance"],
            ],
            spacing=10,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        return ft.Column(
            controls=[
                components["header"],
                ft.Divider(
                    color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
                    height=1,
                ),
                components["price_section"],
                stats_row,
                components["bot_status"],
                components["operations"],
                ft.Row(
                    controls=[components["bot_toggle"]],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            spacing=12,
        )

    def get_breakpoint(self) -> float:
        return self.BREAKPOINT
