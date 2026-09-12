"""
BotToggle — Botón ON/OFF del bot de trading.

Extraído de DashboardView para aplicar SRP.
Publica BotStateChangedEvent al hacer click.
Suscribite a BotStateChangedEvent para sincronización bidireccional.
"""
from __future__ import annotations

import flet as ft

from config.settings import settings
from core.event_bus import event_bus
from core.events import BotStateChangedEvent


class BotToggle(ft.FilledButton):
    """Botón que inicia/detiene el bot de trading."""

    def __init__(self) -> None:
        super().__init__()
        self._active: bool = False
        self.on_click = self._on_click

        self.content = "▶  Iniciar Operaciones"
        self.icon = ft.Icons.PLAY_CIRCLE
        self.style = ft.ButtonStyle(
            bgcolor=ft.Colors.GREEN_800,
            color=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=12),
            padding=ft.Padding(left=20, right=20, top=16, bottom=16),
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def did_mount(self) -> None:
        event_bus.subscribe(BotStateChangedEvent, self._on_bot_state_changed)

    def will_unmount(self) -> None:
        event_bus.unsubscribe(BotStateChangedEvent, self._on_bot_state_changed)

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------
    def _on_click(self, e: ft.ControlEvent) -> None:
        self._active = not self._active
        event_bus.publish(
            BotStateChangedEvent(
                is_running=self._active,
                mode=settings.TRADING_MODE,
            )
        )
        self._update_appearance()

    async def _on_bot_state_changed(self, event: BotStateChangedEvent) -> None:
        """Sincroniza estado si el bot se detiene/inicia externamente."""
        if self._active != event.is_running:
            self._active = event.is_running
            self._update_appearance()

    # ------------------------------------------------------------------
    # UI Update
    # ------------------------------------------------------------------
    def _update_appearance(self) -> None:
        if self._active:
            self.content = "⏸  Detener Operaciones"
            self.style.bgcolor = ft.Colors.RED_800
            self.icon = ft.Icons.PAUSE_CIRCLE
        else:
            self.content = "▶  Iniciar Operaciones"
            self.style.bgcolor = ft.Colors.GREEN_800
            self.icon = ft.Icons.PLAY_CIRCLE
        try:
            self.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        """Actualiza estado desde fuera (ej: al cargar config guardada)."""
        if self._active != active:
            self._active = active
            self._update_appearance()
