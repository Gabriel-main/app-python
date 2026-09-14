"""
Navigator — Navegación entre vistas.

SRP: Solo maneja la navegación entre vistas.
DIP: Depende de ft.AnimatedSwitcher (abstracción Flet).
DRY: Una sola función navigate_to() para cualquier transición.
"""
from __future__ import annotations

import flet as ft


class Navigator:
    """Maneja la navegación entre vistas.
    
    El animated_switcher SIEMPRE permanece como contenido del view_container.
    - animate=True: duration=500ms (login/logout)
    - animate=False: duration=0ms (navegación entre vistas)
    """

    def __init__(
        self,
        animated_switcher: ft.AnimatedSwitcher,
    ) -> None:
        self._switcher = animated_switcher
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
        if not animate and index == self._current_index:
            return
        self._current_index = index
        self._switcher.duration = 500 if animate else 0
        self._switcher.content = view
        self._switcher.update()

    def reset(self) -> None:
        """Resetea el índice (útil para logout)."""
        self._current_index = -1

    @property
    def current_index(self) -> int:
        return self._current_index
