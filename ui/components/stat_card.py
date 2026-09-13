"""
StatCard — Card reutilizable para estadísticas.

Aplica:
- DRY: Elimina repetición de Container + bgcolor + border_radius + padding
  que aparece en Stats24H, BalanceCard y otros componentes
- SRP: Solo construye la estructura visual de una card de estadísticas
- OCP: Permite extensión vía header_extras sin manipular DOM interno
"""
from __future__ import annotations

from typing import Any

import flet as ft

from ui.components.base import EventBusSubscriber


class StatCard(ft.Container, EventBusSubscriber):
    """Card base para estadísticas con header y filas de datos.

    Uso:
        card = StatCard(
            title="Estadísticas 24h",
            rows=[
                ("Máx 24h", high_text),
                ("Mín 24h", low_text),
                ("Volumen", vol_text),
            ],
        )

    Extensión (OCP):
        card = StatCard(
            title="Fondos",
            rows=[...],
            header_extras=[type_badge, loading_indicator],
        )
    """

    # Estilo base compartido (DRY)
    _STYLE: dict[str, Any] = {
        "bgcolor": ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
        "border_radius": 14,
        "padding": ft.Padding(left=16, right=16, top=12, bottom=12),
    }

    def __init__(
        self,
        title: str,
        rows: list[tuple[str, ft.Text]],
        event_subscriptions: list[tuple[Any, Any]] | None = None,
        show_dividers: bool = True,
        header_extras: list[ft.Control] | None = None,
    ) -> None:
        # Inicializar ft.Container PRIMERO (necesita _values)
        super().__init__()

        # Expand para distribución equitativa en Rows
        self.expand = True

        # Aplicar estilo base (DRY)
        for key, value in self._STYLE.items():
            setattr(self, key, value)

        # Header con título + extras (OCP: extensión segura)
        self._title = ft.Text(
            title,
            size=14,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.WHITE,
        )

        header_controls: list[ft.Control] = [
            self._title,
            ft.Container(expand=True),
        ]
        if header_extras:
            header_controls.extend(header_extras)

        # Construir filas de datos dinámicamente
        row_controls: list[ft.Control] = []
        for i, (label, text_control) in enumerate(rows):
            if i > 0 and show_dividers:
                row_controls.append(
                    ft.VerticalDivider(
                        color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)
                    )
                )

            row_controls.append(
                ft.Column(
                    controls=[
                        ft.Text(
                            label,
                            size=10,
                            color=ft.Colors.BLUE_GREY_400,
                        ),
                        text_control,
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

        self.content = ft.Column(
            controls=[
                ft.Row(
                    controls=header_controls,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=8),
                ft.Row(
                    controls=row_controls,
                    alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                ),
            ],
            spacing=0,
        )

        # Suscripciones al EventBus (SRP: delega a mixin)
        self._event_subscriptions = event_subscriptions or []
