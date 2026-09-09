"""
ConnectionIndicator — Indicador visual de estado del WebSocket.

Suscrito a ConnectionStatusEvent. Muestra un punto de color animado
con el texto de estado de la conexión.
"""
from __future__ import annotations

import flet as ft

from core.event_bus import event_bus
from core.events import ConnectionStatusEvent


_STATUS_CONFIG = {
    "CONNECTING":   (ft.Colors.AMBER_400,     ft.Icons.WIFI_FIND,     "Conectando..."),
    "CONNECTED":    (ft.Colors.GREEN_400,      ft.Icons.WIFI,          "Conectado"),
    "DISCONNECTED": (ft.Colors.RED_400,        ft.Icons.WIFI_OFF,      "Desconectado"),
    "RECONNECTING": (ft.Colors.ORANGE_400,     ft.Icons.WIFI_TETHERING,"Reconectando..."),
}


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

    def will_unmount(self) -> None:
        event_bus.unsubscribe(ConnectionStatusEvent, self._on_connection_status)

    # ------------------------------------------------------------------
    # Handler
    # ------------------------------------------------------------------
    async def _on_connection_status(self, event: ConnectionStatusEvent) -> None:
        color, icon, default_text = _STATUS_CONFIG.get(
            event.status, (ft.Colors.GREY_400, ft.Icons.HELP, event.status)
        )
        text = event.message or default_text

        self._dot.bgcolor = color
        self._dot.update()

        self._icon.name = icon
        self._icon.color = color
        self._icon.update()

        self._label.value = text
        self._label.color = color
        self._label.update()
