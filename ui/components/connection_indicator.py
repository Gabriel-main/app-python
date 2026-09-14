"""
ConnectionIndicator — Indicador visual de estado del WebSocket.

Refactorizado para aplicar:
- SRP: Solo muestra estado de conexión
- DIP: Depende de eventos, no de BinanceService
- DRY: _apply_status() unifica lógica de ambos handlers
- Solicita estado actual al montar (ConnectionStatusRequestEvent)
"""
from __future__ import annotations

import flet as ft

from core.event_bus import event_bus
from core.events import (
    ConnectionStatusEvent,
    ConnectionStatusRequestEvent,
    ConnectionStatusSnapshotEvent,
)
from ui.components.colors import CONNECTION_COLORS


class ConnectionIndicator(ft.Row):
    """Pill de estado de conexión con icono animado."""

    def __init__(self) -> None:
        super().__init__()

        self._dot = ft.Container(
            width=8, height=8,
            border_radius=4,
            bgcolor=ft.Colors.AMBER_400,
            animate=ft.Animation(600, ft.AnimationCurve.EASE_IN_OUT),
        )
        self._icon = ft.Icon(ft.Icons.WIFI_FIND, size=14, color=ft.Colors.AMBER_400)
        self._label = ft.Text("Conectando...", size=11, color=ft.Colors.AMBER_400)

        self.controls = [self._dot, self._icon, self._label]
        self.vertical_alignment = ft.CrossAxisAlignment.CENTER
        self.spacing = 5

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def did_mount(self) -> None:
        event_bus.subscribe(ConnectionStatusEvent, self._on_connection_status)
        event_bus.subscribe(ConnectionStatusSnapshotEvent, self._on_status_snapshot)
        event_bus.publish(ConnectionStatusRequestEvent())

    def will_unmount(self) -> None:
        event_bus.unsubscribe(ConnectionStatusEvent, self._on_connection_status)
        event_bus.unsubscribe(ConnectionStatusSnapshotEvent, self._on_status_snapshot)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    async def _on_status_snapshot(self, event: ConnectionStatusSnapshotEvent) -> None:
        """Recibe el estado actual de conexión al montar."""
        self._apply_status(event.status, event.message)

    async def _on_connection_status(self, event: ConnectionStatusEvent) -> None:
        """Recibe cambios de estado en tiempo real."""
        self._apply_status(event.status, event.message)

    def _apply_status(self, status: str, message: str) -> None:
        """Aplica el estado visual (DRY: lógica unificada)."""
        color, icon_name, default_text = CONNECTION_COLORS.get(
            status, (ft.Colors.GREY_400, "help", status)
        )
        text = message or default_text

        self._dot.bgcolor = color
        self._icon.name = icon_name
        self._icon.color = color
        self._label.value = text
        self._label.color = color

        try:
            self.update()
        except RuntimeError:
            pass
