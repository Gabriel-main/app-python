"""
ViewHeader — Header estándar de vista (título + slots + divider).

Elimina la duplicación del header repetido en OrdersView, AuditView,
DashboardView, SettingsView y ConfigView.

Principios aplicados:
- SRP: Solo presenta. No suscribe eventos ni conoce estado de negocio.
- OCP: Nuevos slots (leading/subtitle/trailing/show_divider) se agregan
  como parámetros opcionales sin modificar el componente.
- DRY: El estilo del título (22/BOLD/WHITE), el spacer `expand` y el
  divider `with_opacity(0.1, WHITE)` viven en UN solo lugar.
"""
from __future__ import annotations

import flet as ft


class ViewHeader(ft.Column):
    """Header de vista: Row[título + slots] + Divider opcional.

    Args:
        title: Título de la vista (siempre 22 / BOLD / WHITE).
        leading: Control a la izquierda del título (ej. botón de volver).
        subtitle: Control debajo del título (ej. indicador de conexión).
        trailing: Controles a la derecha (contador, dropdown, badge...).
            Si se omite, NO se inserta el `Container(expand=True)` y el Row
            shrink-wraps (los padres centrados siguen centrando el bloque).
        show_divider: False si el layout de la vista ya dibuja el divider.
        divider_width: Ancho fijo del divider (380 para vistas angostas).
        divider_height: Altura del divider (1 por defecto, 20 en vistas angostas).
        spacing: Separación Row ↔ Divider (usar la del Column de la vista).
    """

    def __init__(
        self,
        title: str,
        *,
        leading: ft.Control | None = None,
        subtitle: ft.Control | None = None,
        trailing: list[ft.Control] | None = None,
        show_divider: bool = True,
        divider_width: float | None = None,
        divider_height: float = 1,
        spacing: float = 12,
    ) -> None:
        super().__init__()
        self.spacing = spacing

        title_text = ft.Text(
            title,
            size=22,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.WHITE,
        )
        left = ft.Column(
            controls=[title_text] + ([subtitle] if subtitle is not None else []),
            spacing=2,
        )

        row_controls: list[ft.Control] = []
        if leading is not None:
            row_controls.append(leading)
        row_controls.append(left)
        if trailing:
            row_controls.append(ft.Container(expand=True))
            row_controls.extend(trailing)

        # Sin slots laterales el Row ocupa todo el ancho y solo debe
        # centrar el título (caso Configuración); con slots, alineación
        # inicial para que leading quede a la izquierda.
        row_alignment = (
            ft.MainAxisAlignment.CENTER
            if leading is None and not trailing
            else ft.MainAxisAlignment.START
        )

        self.controls = [
            ft.Row(
                controls=row_controls,
                alignment=row_alignment,
                vertical_alignment=(
                    ft.CrossAxisAlignment.START if subtitle is not None
                    else ft.CrossAxisAlignment.CENTER
                ),
            ),
        ]

        # Los padres (vistas) alinean al centro: el divider con ancho fijo
        # (380) tiene que seguir centrado igual que antes del refactor.
        self.horizontal_alignment = ft.CrossAxisAlignment.CENTER

        if show_divider:
            divider = ft.Divider(
                color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
                height=divider_height,
            )
            if divider_width is not None:
                divider = ft.Container(width=divider_width, content=divider)
            self.controls.append(divider)
