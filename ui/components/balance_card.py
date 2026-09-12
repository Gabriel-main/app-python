"""
BalanceCard — Card de fondos/cuenta del usuario.

Refactorizado para aplicar:
- DRY: Reutiliza StatCard para estructura base
- OCP: Usa BalanceDisplayStrategy para formatos por trading type
- SRP: Solo maneja lógica de balance y formato
"""
from __future__ import annotations

import time

import flet as ft

from config.settings import settings
from core.event_bus import event_bus
from core.events import BalanceUpdateEvent, SettingsUpdatedEvent
from ui.components.balance_display import (
    get_strategy,
    format_amount,
    BalanceDisplayStrategy,
)
from ui.components.badges import Badge
from ui.components.colors import TRADING_TYPE_COLORS
from ui.components.stat_card import StatCard


class BalanceCard(StatCard):
    """Card que muestra el saldo de la cuenta del usuario."""

    def __init__(self) -> None:
        self._last_update: float = 0.0
        self._strategy: BalanceDisplayStrategy = get_strategy(settings.TRADING_TYPE)

        # Badge de tipo (elemento específico de BalanceCard)
        type_info = TRADING_TYPE_COLORS.get(settings.TRADING_TYPE, TRADING_TYPE_COLORS["SPOT"])
        self._type_badge = Badge(
            label=type_info[2], fg_color=type_info[0], bg_color=type_info[1]
        )

        # Textos de saldo
        labels = self._strategy.get_labels()
        self._label_1 = ft.Text(labels[0], size=11, color=ft.Colors.BLUE_GREY_400)
        self._value_1 = ft.Text("---", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)

        self._label_2 = ft.Text(labels[1] or "", size=11, color=ft.Colors.BLUE_GREY_400)
        self._value_2 = ft.Text("---", size=13, color=ft.Colors.BLUE_GREY_300)

        self._label_3 = ft.Text(labels[2] or "", size=11, color=ft.Colors.BLUE_GREY_400)
        self._value_3 = ft.Text("", size=13, color=ft.Colors.BLUE_GREY_300)

        # Timestamp
        self._time_text = ft.Text("Sin datos", size=9, color=ft.Colors.BLUE_GREY_500)

        # Loading indicator
        self._loading = ft.ProgressRing(
            width=14, height=14, stroke_width=2,
            color=ft.Colors.CYAN_400, visible=False,
        )

        # Inicializar StatCard con estructura base
        super().__init__(
            title="💰 Fondos",
            rows=[
                (labels[0], self._value_1),
                (labels[1] or "", self._value_2),
                (labels[2] or "", self._value_3),
            ],
            event_subscriptions=[
                (BalanceUpdateEvent, self._on_balance_update),
                (SettingsUpdatedEvent, self._on_settings_updated),
            ],
            show_dividers=False,
        )

        # Agregar elementos específicos de BalanceCard al header
        self._inject_header_extras()

    def _inject_header_extras(self) -> None:
        """Inyecta badge y loading indicator en el header existente."""
        if isinstance(self.content, ft.Column) and len(self.content.controls) > 0:
            header_row = self.content.controls[0]
            if isinstance(header_row, ft.Row):
                # Insertar antes del Container(expand=True)
                header_row.controls.insert(-1, self._type_badge)
                header_row.controls.insert(-1, ft.Container(width=4))
                header_row.controls.insert(-1, self._loading)

        # Agregar timestamp al final
        if isinstance(self.content, ft.Column):
            self.content.controls.append(self._time_text)

    def did_mount(self) -> None:
        self._setup_subscriptions()

    def will_unmount(self) -> None:
        self._teardown_subscriptions()

    def _sync_from_settings(self) -> None:
        """Re-sincroniza strategy y badge desde settings."""
        self._strategy = get_strategy(settings.TRADING_TYPE)
        type_info = TRADING_TYPE_COLORS.get(settings.TRADING_TYPE, TRADING_TYPE_COLORS["SPOT"])
        self._type_badge.update_label(type_info[2], fg_color=type_info[0], bg_color=type_info[1])
        self._apply_labels()
        try:
            self.update()
        except RuntimeError:
            pass

    def _apply_labels(self) -> None:
        """Aplica los labels de la estrategia actual."""
        labels = self._strategy.get_labels()
        self._label_1.value = labels[0]
        self._label_2.value = labels[1] or ""
        self._label_2.visible = labels[1] is not None
        self._value_2.visible = labels[1] is not None
        self._label_3.value = labels[2] or ""
        self._label_3.visible = False
        self._value_3.visible = False

    async def _on_balance_update(self, event: BalanceUpdateEvent) -> None:
        """Actualiza valores con datos reales del balance."""
        self._last_update = event.timestamp
        self._loading.visible = False

        v1, v2, v3 = self._strategy.format_values(event)
        self._value_1.value = v1
        self._value_2.value = v2 or "---"

        if v3 is not None:
            self._label_3.visible = True
            self._value_3.visible = True
            self._value_3.value = v3
            pnl_val = event.unrealized_pnl if hasattr(event, "unrealized_pnl") else 0
            self._value_3.color = ft.Colors.GREEN_400 if pnl_val >= 0 else ft.Colors.RED_400
        else:
            self._label_3.visible = False
            self._value_3.visible = False

        self._update_timestamp()
        try:
            self.update()
        except RuntimeError:
            pass

    async def _on_settings_updated(self, event: SettingsUpdatedEvent) -> None:
        """Actualiza badge, labels y muestra indicador de carga."""
        self._sync_from_settings()
        self._loading.visible = True
        self._time_text.value = f"Cargando saldo de {event.trading_type}..."
        try:
            self.update()
        except RuntimeError:
            pass

    def _update_timestamp(self) -> None:
        elapsed = time.time() - self._last_update
        if elapsed < 5:
            self._time_text.value = "Actualizado ahora"
        elif elapsed < 60:
            self._time_text.value = f" hace {int(elapsed)}s"
        else:
            self._time_text.value = f" hace {int(elapsed / 60)}m"
