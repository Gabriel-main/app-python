"""
Navigator — Navegación entre vistas.

SRP: Solo maneja la navegación entre vistas.
DIP: Depende de ft.Control (abstracción), no de implementaciones concretas.
DRY: Una sola función navigate_to() para cualquier transición.
"""
from __future__ import annotations

import flet as ft


class Navigator:
    """Maneja la navegación entre vistas con dos estrategias:
    - Animada (FADE 500ms): Solo para login/logout
    - Directa (sin animación): Para navegación entre vistas
    """

    def __init__(
        self,
        animated_switcher: ft.AnimatedSwitcher,
        view_container: ft.Container,
    ) -> None:
        self._switcher = animated_switcher
        self._container = view_container
        self._current_index: int = -1

    def navigate_to(
        self,
        index: int,
        view: ft.Control,
        animate: bool = False,
    ) -> None:
        """Cambia a la vista indicada.
        
        animate=True: Login/logout con FADE 500ms
        animate=False: Navegación instantánea (default)
        """
        if index == self._current_index:
            return
        self._current_index = index

        if animate:
            self._switcher.transition = ft.AnimatedSwitcherTransition.FADE
            self._switcher.duration = 500
            self._switcher.content = view
            self._switcher.update()
        else:
            self._container.content = view
            self._container.update()

    def reset(self) -> None:
        """Resetea el índice (útil para logout)."""
        self._current_index = -1

    @property
    def current_index(self) -> int:
        return self._current_index
