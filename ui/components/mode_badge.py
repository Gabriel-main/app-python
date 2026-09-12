"""
ModeBadge — Badge de modo (PAPER/LIVE) con actualización encapsulada.

Extraído de DashboardView para aplicar SRP + encapsulamiento.
Reemplaza el acceso directo a content.value / content.color.
"""
from __future__ import annotations

import flet as ft

from ui.components.colors import MODE_COLORS


class ModeBadge(ft.Container):
    """Badge que muestra el modo de operación actual."""

    def __init__(self, mode: str = "PAPER") -> None:
        super().__init__()
        self._mode = mode
        color = MODE_COLORS.get(mode, MODE_COLORS["PAPER"])

        self._text = ft.Text(
            mode,
            size=11,
            weight=ft.FontWeight.BOLD,
            color=color,
        )
        self.content = self._text
        self.bgcolor = ft.Colors.with_opacity(0.15, color)
        self.border = ft.Border.all(1, color)
        self.border_radius = 6
        self.padding = ft.Padding(left=10, right=10, top=4, bottom=4)
        self.tooltip = "Paper = Simulado | Live = Real"

    def update_mode(self, mode: str) -> None:
        """Actualiza el modo de forma encapsulada."""
        self._mode = mode
        color = MODE_COLORS.get(mode, MODE_COLORS["PAPER"])
        self._text.value = mode
        self._text.color = color
        self.bgcolor = ft.Colors.with_opacity(0.15, color)
        self.border = ft.Border.all(1, color)
        try:
            self.update()
        except RuntimeError:
            pass

    @property
    def mode(self) -> str:
        return self._mode
