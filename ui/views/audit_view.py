"""
Audit View — Vista de auditoría del bot.

Muestra en tiempo real qué está haciendo el bot:
- Datos de entrada (precios, señales)
- Acciones tomadas (órdenes, stop losses)
- Estado del sistema (conexión, configuración)

Refactorizado para aplicar:
- SRP + DIP: Usa AuditService para obtener eventos
- PERFORMANCE: Usa update_batcher para un solo render
- MODELO ≠ RENDER: `_events` almacena todo; el filtro se aplica al pintar.
  El conteo sale del modelo (nunca de introspección sobre los widgets).
"""
from __future__ import annotations

import flet as ft

from core.event_bus import event_bus
from core.events import AuditEvent
from core.update_batcher import update_batcher
from services.audit_service import audit_service
from ui.components.audit_card import build_audit_card
from ui.components.count_text import CountText
from ui.components.empty_state import EmptyState
from ui.components.view_header import ViewHeader

# Tope del buffer en memoria: espejo de AuditService.max_events (200).
# Con el store capado, la lista de tarjetas nunca supera este valor:
# no hace falta recortar los `controls` en cada inserción.
_MAX_EVENTS = 200

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

        self._event_count_text = CountText("evento", "eventos")

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
            self._add_event(event)

    def will_unmount(self) -> None:
        event_bus.unsubscribe(AuditEvent, self._on_audit_event)

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------
    async def _on_audit_event(self, event: AuditEvent) -> None:
        self._add_event(event)

    # ------------------------------------------------------------------
    # Modelo (fuente de verdad) vs Render
    # ------------------------------------------------------------------
    def _matches(self, event: AuditEvent) -> bool:
        """El filtro pertenece al render, nunca al almacenamiento."""
        return (
            self._category_filter == "TODOS"
            or event.category == self._category_filter
        )

    def _visible_events(self) -> list[AuditEvent]:
        """Eventos que el filtro actual debe mostrar."""
        if self._category_filter == "TODOS":
            return self._events
        return [e for e in self._events if e.category == self._category_filter]

    def _evict_overflow(self) -> bool:
        """Recorta el buffer a `_MAX_EVENTS`.

        Returns:
            True si salió algún evento que estaba visible (y por lo tanto
            su tarjeta también debe irse de la lista).
        """
        overflow = len(self._events) - _MAX_EVENTS
        if overflow <= 0:
            return False

        evicted = self._events[:overflow]
        del self._events[:overflow]

        visible_dropped = sum(1 for e in evicted if self._matches(e))
        evicted_visible = visible_dropped > 0
        if evicted_visible:
            controls = self._list_column.controls
            # Invariante: el EmptyState vive siempre en controls[0] y las
            # tarjetas se apilan en orden cronológico → la más antigua es [1].
            while (
                visible_dropped > 0
                and len(controls) > 1
                and controls[0] is self._empty_label
            ):
                del controls[1]
                visible_dropped -= 1
        return evicted_visible

    def _add_event(self, event: AuditEvent) -> None:
        """Almacena el evento y pinta su tarjeta solo si pasa el filtro.

        Almacenar SIEMPRE es lo que permite cambiar de filtro sin perder
        historial; el filtro es exclusivamente una decisión de render.
        """
        self._events.append(event)
        evicted_visible = self._evict_overflow()

        if not self._matches(event):
            if evicted_visible:
                self._update_count()
                update_batcher.mark_dirty(self._list_column)
            return

        if self._empty_label.visible:
            self._empty_label.visible = False
        self._list_column.controls.append(build_audit_card(event))
        self._update_count()
        update_batcher.mark_dirty(self._list_column)

    def _on_filter_changed(self, e: ft.ControlEvent) -> None:
        """Reconstruye la lista con el nuevo filtro."""
        self._category_filter = e.control.value or "TODOS"
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        """Reconstruye la lista de tarjetas desde el modelo."""
        visible = self._visible_events()
        self._empty_label.visible = not visible
        self._list_column.controls = (
            [self._empty_label] + [build_audit_card(e) for e in visible]
        )
        self._update_count()
        update_batcher.mark_dirty(self._list_column)

    def _update_count(self) -> None:
        # Conteo desde el modelo: sin introspección de tipos sobre widgets
        self._event_count_text.set_count(len(self._visible_events()))
