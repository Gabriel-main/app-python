"""
Badge — Componente reutilizable de etiqueta con color.

Elimina la repetición del patrón Container + Text + color
que aparece en dashboard, balance_card, order_card, position_card,
operations_panel y bot_status_bar.
"""
from __future__ import annotations

import flet as ft


class Badge(ft.Container):
    """Badge reutilizable con texto, color de fondo y borde."""

    def __init__(
        self,
        label: str,
        fg_color: ft.Color,
        bg_color: ft.Color,
        size: int = 10,
        border_radius: int = 6,
    ) -> None:
        super().__init__()
        self._label_text = ft.Text(
            label,
            size=size,
            weight=ft.FontWeight.BOLD,
            color=fg_color,
        )
        self.content = self._label_text
        self.bgcolor = bg_color
        self.border_radius = border_radius
        self.padding = ft.Padding(left=8, right=8, top=3, bottom=3)

    def update_label(
        self,
        label: str,
        fg_color: ft.Color | None = None,
        bg_color: ft.Color | None = None,
    ) -> None:
        """Actualiza label y colores de forma atómica."""
        self._label_text.value = label
        if fg_color is not None:
            self._label_text.color = fg_color
        if bg_color is not None:
            self.bgcolor = bg_color
        try:
            self.update()
        except RuntimeError:
            pass

    @property
    def label(self) -> str:
        return self._label_text.value or ""
