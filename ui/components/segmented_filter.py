"""
SegmentedFilter — Filtros en chips segmentados (1 sola fila).

Sustituye al ft.Dropdown de la vista Órdenes: en móvil un desplegable
esconde el estado actual del filtro tras un tap extra; los chips dejan
ver de un vistazo qué filtro está activo.

Principios aplicados:
- SRP: Solo presenta las opciones y emite la selección. Quién filtra
  (y con qué criterio) lo decide la vista dueña de los datos.
- OCP: Nuevas opciones = nuevos tuples en `options`; el componente no cambia.
- DRY: El estilo seleccionado/no-seleccionado vive en un solo lugar.
- REACTIVIDAD: La selección se pinta con update_batcher (control.update()).
"""
from __future__ import annotations

from collections.abc import Callable, Sequence

import flet as ft

from core.update_batcher import update_batcher

_SELECTED_BG = ft.Colors.with_opacity(0.18, ft.Colors.CYAN_400)
_SELECTED_FG = ft.Colors.WHITE
_IDLE_BG = ft.Colors.with_opacity(0.04, ft.Colors.WHITE)
_IDLE_FG = ft.Colors.BLUE_GREY_400


class SegmentedFilter(ft.Row):
    """Fila de chips segmentados de ancho completo.

    Args:
        options: Pares `(clave, etiqueta)` a mostrar, en orden.
        value: Clave inicialmente seleccionada.
        on_change: Callback `f(clave)` al seleccionar un chip.
    """

    def __init__(
        self,
        options: Sequence[tuple[str, str]],
        *,
        value: str,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self._value = value
        self._on_change = on_change
        self._chips: dict[str, tuple[ft.Container, ft.Text]] = {}

        chips: list[ft.Control] = []
        for key, label in options:
            text = ft.Text(
                label,
                size=10,
                weight=ft.FontWeight.W_600,
                color=_IDLE_FG,
                text_align=ft.TextAlign.CENTER,
                max_lines=1,
            )
            chip = ft.Container(
                expand=True,
                content=text,
                padding=ft.Padding(top=6, bottom=6),
                border_radius=6,
                alignment=ft.Alignment.CENTER,
                on_click=self._make_handler(key),
            )
            self._chips[key] = (chip, text)
            chips.append(chip)

        self.controls = [
            ft.Container(
                expand=True,
                bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
                border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.WHITE)),
                border_radius=8,
                padding=2,
                content=ft.Row(
                    controls=chips,
                    spacing=2,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
        ]
        self.alignment = ft.MainAxisAlignment.START
        self.vertical_alignment = ft.CrossAxisAlignment.CENTER
        self._paint(value)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, new_value: str) -> None:
        if new_value == self._value or new_value not in self._chips:
            return
        self._value = new_value
        self._paint(new_value)
        update_batcher.mark_dirty(self)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _make_handler(self, key: str) -> Callable[[ft.ControlEvent], None]:
        def handler(_e: ft.ControlEvent) -> None:
            self.value = key
            if self._on_change is not None:
                self._on_change(key)

        return handler

    def _paint(self, selected: str) -> None:
        for key, (chip, text) in self._chips.items():
            is_selected = key == selected
            chip.bgcolor = _SELECTED_BG if is_selected else _IDLE_BG
            text.color = _SELECTED_FG if is_selected else _IDLE_FG
