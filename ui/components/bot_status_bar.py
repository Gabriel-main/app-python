"""
BotStatusBar — Barra de estado del bot con señal actual y valores de MA.

Refactorizado para aplicar:
- SRP: Usa SIGNAL_COLORS de colors.py
- Performance: Agrupa updates en un solo self.content.update()
"""
from __future__ import annotations

import flet as ft

from core.event_bus import event_bus
from core.events import BotSignalEvent, BotStateChangedEvent
from ui.components.colors import SIGNAL_COLORS


class BotStatusBar(ft.Container):
    """Widget que muestra el estado actual del bot engine."""

    def __init__(self) -> None:
        super().__init__()

        self._signal_text = ft.Text(
            "HOLD",
            size=18,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_GREY_400,
        )
        self._signal_icon = ft.Icon(ft.Icons.REMOVE, color=ft.Colors.BLUE_GREY_400, size=20)
        self._ma_fast_text = ft.Text("MA(7): ---", size=11, color=ft.Colors.BLUE_GREY_300)
        self._ma_slow_text = ft.Text("MA(25): ---", size=11, color=ft.Colors.BLUE_GREY_300)
        self._confidence_bar = ft.ProgressBar(
            value=0.0,
            width=140,
            color=ft.Colors.BLUE_GREY_400,
            bgcolor=ft.Colors.BLUE_GREY_900,
        )
        self._bot_status_dot = ft.Container(
            width=8, height=8,
            border_radius=4,
            bgcolor=ft.Colors.GREEN_400,
            animate=ft.Animation(800, ft.AnimationCurve.EASE_IN_OUT),
        )
        self._bot_label = ft.Text("BOT ACTIVO", size=10, color=ft.Colors.GREEN_400)

        self.content = ft.Container(
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.WHITE),
            border_radius=14,
            padding=ft.Padding(left=16, right=16, top=12, bottom=12),
            content=ft.Column(
                controls=[
                    # Fila superior: señal + estado bot
                    ft.Row(
                        controls=[
                            self._signal_icon,
                            self._signal_text,
                            ft.Container(expand=True),
                            ft.Row(
                                controls=[self._bot_status_dot, self._bot_label],
                                spacing=6,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    # Fila inferior: MAs + barra confianza
                    ft.Row(
                        controls=[
                            self._ma_fast_text,
                            ft.Text("·", color=ft.Colors.BLUE_GREY_700),
                            self._ma_slow_text,
                            ft.Container(expand=True),
                            ft.Column(
                                controls=[
                                    ft.Text("Confianza", size=9, color=ft.Colors.BLUE_GREY_500),
                                    self._confidence_bar,
                                ],
                                spacing=2,
                                horizontal_alignment=ft.CrossAxisAlignment.END,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=8,
            ),
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def did_mount(self) -> None:
        event_bus.subscribe(BotSignalEvent, self._on_bot_signal)
        event_bus.subscribe(BotStateChangedEvent, self._on_bot_state_changed)

    def will_unmount(self) -> None:
        event_bus.unsubscribe(BotSignalEvent, self._on_bot_signal)
        event_bus.unsubscribe(BotStateChangedEvent, self._on_bot_state_changed)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    async def _on_bot_signal(self, event: BotSignalEvent) -> None:
        from config.settings import settings
        fg, bg = SIGNAL_COLORS.get(event.signal, SIGNAL_COLORS["HOLD"])

        icon_map = {"BUY": ft.Icons.ARROW_UPWARD, "SELL": ft.Icons.ARROW_DOWNWARD, "HOLD": ft.Icons.REMOVE}

        self._signal_text.value = event.signal
        self._signal_text.color = fg

        self._signal_icon.name = icon_map.get(event.signal, ft.Icons.REMOVE)
        self._signal_icon.color = fg

        self._ma_fast_text.value = f"MA({settings.BOT_MA_FAST}): {event.ma_fast:,.2f}"
        self._ma_slow_text.value = f"MA({settings.BOT_MA_SLOW}): {event.ma_slow:,.2f}"

        self._confidence_bar.value = event.confidence
        self._confidence_bar.color = fg

        # Update agrupado — un solo render
        try:
            self.content.update()
        except RuntimeError:
            pass

    async def _on_bot_state_changed(self, event: BotStateChangedEvent) -> None:
        if event.is_running:
            self._bot_status_dot.bgcolor = ft.Colors.GREEN_400
            self._bot_label.value = "BOT ACTIVO"
            self._bot_label.color = ft.Colors.GREEN_400
        else:
            self._bot_status_dot.bgcolor = ft.Colors.GREY_600
            self._bot_label.value = "BOT PAUSADO"
            self._bot_label.color = ft.Colors.GREY_600

        try:
            self.content.update()
        except RuntimeError:
            pass
