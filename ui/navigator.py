"""
Navigator — Navegación entre vistas con animación.

SRP: Solo cambia el contenido del AnimatedSwitcher.
DRY: Una sola función para cualquier transición de vista.
"""
from __future__ import annotations

import flet as ft


class Navigator:
    """Maneja la navegación entre vistas con transiciones animadas."""

    def __init__(self, animated_switcher: ft.AnimatedSwitcher) -> None:
        self._switcher = animated_switcher
        self._current_index: int = -1

    def navigate_to(self, index: int, view: ft.Control) -> None:
        """Cambia a la vista indicada con animación FADE."""
        if index == self._current_index:
            return
        self._current_index = index
        self._switcher.content = view
        self._switcher.update()

    def reset(self) -> None:
        """Resetea el índice (útil para logout)."""
        self._current_index = -1

    @property
    def current_index(self) -> int:
        return self._current_index
