"""
Audit View — Vista de auditoría del bot.

Muestra en tiempo real qué está haciendo el bot:
- Datos de entrada (precios, señales)
- Acciones tomadas (órdenes, stop losses)
- Estado del sistema (conexión, configuración)

Refactorizado para aplicar SRP + DIP:
- Usa AuditService para obtener eventos
- Lifecycle: suscribir en did_mount(), des-suscribir en will_unmount()
"""
from __future__ import annotations

import flet as ft

from core.event_bus import event_bus
from core.events import AuditEvent
from services.audit_service import audit_service
from ui.components.audit_card import AuditCard

# Categorías disponibles para filtro
_CATEGORIES = [
    "TODOS",
    "CONNECTION",
    "PRICE",
    "SIGNAL",
    "ORDER",
    "OPERATION",
    "POSITION",
    "STATE",
    "CONFIG",
]


class AuditView(ft.Column):
    """Vista de auditoría del bot con eventos en tiempo real."""

    def __init__(self) -> None:
        super().__init__()
        self._category_filter = "TODOS"
        self._events: list[AuditEvent] = []

        self._filter_dropdown = ft.Dropdown(
            label="Filtrar",
            value="TODOS",
            options=[ft.DropdownOption(key=c, text=c) for c in _CATEGORIES],
            focused_border_color=ft.Colors.PURPLE_400,
            width=140,
            bgcolor=ft.Colors.GREY_900,
            border_color=ft.Colors.BLUE_GREY_700,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            on_select=self._on_filter_changed,
        )

        self._event_count_text = ft.Text("0 eventos", size=11, color=ft.Colors.BLUE_GREY_400)

        self._list_column = ft.Column(
            spacing=4,
            scroll=ft.ScrollMode.AUTO,
            auto_scroll=True,
            expand=True,
        )

        self._empty_label = ft.Text(
            "Esperando eventos...\nEl bot publicará eventos aquí.",
            size=13,
            color=ft.Colors.BLUE_GREY_400,
            text_align=ft.TextAlign.CENTER,
        )

        self.controls = [
            # Header
            ft.Row(
                controls=[
                    ft.Text("Auditoría", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    ft.Container(expand=True),
                    self._filter_dropdown,
                    self._event_count_text,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Divider(color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE), height=1),
            self._list_column,
        ]
        self.spacing = 12
        self.expand = True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def did_mount(self) -> None:
        event_bus.subscribe(AuditEvent, self._on_audit_event)
        # Cargar eventos existentes
        existing = audit_service.get_recent_events(100)
        for event in existing:
            self._add_event_card(event)

    def will_unmount(self) -> None:
        event_bus.unsubscribe(AuditEvent, self._on_audit_event)

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------
    async def _on_audit_event(self, event: AuditEvent) -> None:
        self._add_event_card(event)

    def _add_event_card(self, event: AuditEvent) -> None:
        """Agrega tarjeta de evento si pasa el filtro."""
        if self._category_filter != "TODOS" and event.category != self._category_filter:
            return

        self._events.append(event)
        self._list_column.controls.append(AuditCard(event))

        # Mantener máximo 200 tarjetas en UI
        if len(self._list_column.controls) > 200:
            self._list_column.controls = self._list_column.controls[-200:]

        self._update_count()
        try:
            self._list_column.update()
        except RuntimeError:
            pass

    def _on_filter_changed(self, e: ft.ControlEvent) -> None:
        """Reconstruye la lista con el nuevo filtro."""
        self._category_filter = e.control.value or "TODOS"
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        """Reconstruye la lista de tarjetas según el filtro actual."""
        self._list_column.controls.clear()

        if self._category_filter == "TODOS":
            filtered = self._events
        else:
            filtered = [e for e in self._events if e.category == self._category_filter]

        for event in filtered[-200:]:
            self._list_column.controls.append(AuditCard(event))

        self._update_count()
        try:
            self._list_column.update()
        except RuntimeError:
            pass

    def _update_count(self) -> None:
        count = len(self._list_column.controls)
        self._event_count_text.value = f"{count} evento{'s' if count != 1 else ''}"
