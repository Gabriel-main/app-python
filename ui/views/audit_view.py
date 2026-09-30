"""
Audit View — Vista de auditoría del bot.

Muestra en tiempo real qué está haciendo el bot:
- Datos de entrada (precios, señales)
- Acciones tomadas (órdenes, stop losses)
- Estado del sistema (conexión, configuración)

Refactorizado para aplicar:
- SRP + DIP: Usa AuditService para obtener eventos
- PERFORMANCE: Usa update_batcher para un solo render
"""
from __future__ import annotations

import flet as ft

from core.event_bus import event_bus
from core.events import AuditEvent
from core.update_batcher import update_batcher
from services.audit_service import audit_service
from ui.components.audit_card import AuditCard
from ui.components.empty_state import EmptyState
from ui.components.view_header import ViewHeader

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

        self._empty_label = EmptyState(
            "Esperando eventos...",
            subtitle="El bot publicará eventos aquí.",
            icon=ft.Icons.FACT_CHECK_OUTLINED,
        )
        self._list_column.controls.append(self._empty_label)

        self.controls = [
            ViewHeader(
                "Auditoría",
                trailing=[self._filter_dropdown, self._event_count_text],
            ),
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
        if self._empty_label.visible:
            self._empty_label.visible = False
        self._list_column.controls.append(AuditCard(event))

        # Mantener máximo 200 tarjetas en UI
        if len(self._list_column.controls) > 200:
            self._list_column.controls = self._list_column.controls[-200:]

        self._update_count()
        update_batcher.mark_dirty(self._list_column)

    def _on_filter_changed(self, e: ft.ControlEvent) -> None:
        """Reconstruye la lista con el nuevo filtro."""
        self._category_filter = e.control.value or "TODOS"
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        """Reconstruye la lista de tarjetas según el filtro actual."""
        if self._category_filter == "TODOS":
            filtered = self._events
        else:
            filtered = [e for e in self._events if e.category == self._category_filter]
        filtered = filtered[-200:]

        self._empty_label.visible = not filtered
        self._list_column.controls = (
            [self._empty_label] + [AuditCard(e) for e in filtered]
        )

        self._update_count()
        update_batcher.mark_dirty(self._list_column)

    def _update_count(self) -> None:
        count = sum(1 for c in self._list_column.controls if isinstance(c, AuditCard))
        self._event_count_text.value = f"{count} evento{'s' if count != 1 else ''}"
