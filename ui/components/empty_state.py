"""
EmptyState — Bloque de estado vacío compartido.

Elimina la duplicación de empty states repetidos con el mismo patrón
(Text centrado + icono + título + subtítulo) en OrdersView, AuditView,
OperationsPanel y PositionsPanel.

Principios aplicados:
- SRP: Solo presenta "no hay nada aquí". No decide cuándo mostrarse
  (eso lo hace el contenedor dueño de los datos).
- OCP: icon/title/subtitle/size son parámetros; nuevas vistas usan el
  componente sin modificarlo.
- DRY: Un solo lugar define color, tamaño y alineación del vacío.
"""
from __future__ import annotations

import flet as ft

_EMPTY_COLOR = ft.Colors.BLUE_GREY_400
_SUBTITLE_COLOR = ft.Colors.BLUE_GREY_600


class EmptyState(ft.Container):
    """Centra icono + título + subtítulo dentro del contenedor padre.

    Args:
        title: Mensaje principal (siempre centrado).
        subtitle: Mensaje secundario opcional debajo del título.
        icon: Nombre de `ft.Icons` a mostrar encima. None = sin icono.
        title_size: Tamaño del título (13 en vistas, 12 en paneles).
        spacing: Separación entre icono y título.
    """

    def __init__(
        self,
        title: str,
        *,
        subtitle: str | None = None,
        icon: str | None = None,
        title_size: int = 13,
        spacing: float = 8,
    ) -> None:
        super().__init__()
        self.padding = ft.Padding.symmetric(vertical=16, horizontal=12)
        self.alignment = ft.Alignment.CENTER

        controls: list[ft.Control] = []
        if icon is not None:
            controls.append(
                ft.Icon(icon, size=32, color=ft.Colors.BLUE_GREY_700),
            )
        controls.append(
            ft.Text(
                title,
                size=title_size,
                color=_EMPTY_COLOR,
                text_align=ft.TextAlign.CENTER,
            ),
        )
        if subtitle:
            controls.append(
                ft.Text(
                    subtitle,
                    size=title_size - 2,
                    color=_SUBTITLE_COLOR,
                    text_align=ft.TextAlign.CENTER,
                )
            )

        self.content = ft.Column(
            controls=controls,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=spacing,
        )
