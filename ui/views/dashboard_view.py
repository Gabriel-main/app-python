"""
Dashboard View — Pantalla principal del bot de trading.

Refactorizado para aplicar:
- SRP: Solo orquesta componentes, delega layout a ResponsiveDashboardLayout
- DIP: Depende de DashboardLayout (abstracción), no de implementación concreta
- OCP: Nuevo layout = nueva clase, no modificar DashboardView
"""
from __future__ import annotations

import logging

import flet as ft

from config.settings import settings
from core.event_bus import event_bus
from core.events import PriceTickEvent, SettingsUpdatedEvent
from ui.layouts.responsive_layout import ResponsiveDashboardLayout
from ui.components.bot_toggle import BotToggle
from ui.components.connection_indicator import ConnectionIndicator
from ui.components.mini_chart import MiniChart
from ui.components.mode_badge import ModeBadge
from ui.components.operations_panel import OperationsPanel
from ui.components.price_ticker import PriceTicker
from ui.components.stats_24h import Stats24H
from ui.components.balance_card import BalanceCard
from ui.components.bot_status_bar import BotStatusBar

log = logging.getLogger(__name__)


class DashboardView(ft.Column):
    """Vista principal — delega layout a ResponsiveDashboardLayout."""

    def __init__(self) -> None:
        super().__init__()

        # --- Componentes reactivos ---
        self._ticker = PriceTicker(symbol=settings.TRADING_SYMBOL)
        self._chart = MiniChart(symbol=settings.TRADING_SYMBOL)
        self._bot_bar = BotStatusBar()
        self._conn_indicator = ConnectionIndicator()
        self._operations_panel = OperationsPanel()
        self._balance_card = BalanceCard()
        self._stats = Stats24H(symbol=settings.TRADING_SYMBOL)
        self._toggle_btn = BotToggle()
        self._mode_badge = ModeBadge(mode=settings.TRADING_MODE)

        # --- Layout (DIP: inyección de dependencias) ---
        components = {
            "header": self._build_header(),
            "price_section": self._build_price_section(),
            "stats": self._stats,
            "balance": self._balance_card,
            "bot_status": self._bot_bar,
            "bot_toggle": self._toggle_btn,
            "operations": self._operations_panel,
        }

        self._layout = ResponsiveDashboardLayout()
        self.controls = [self._layout.build(components)]
        self.spacing = 12
        self.scroll = ft.Scrollbar(thickness=6, interactive=True)

    def _build_header(self) -> ft.Control:
        """Construye el header con título, indicador de conexión y badge de modo."""
        return ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        ft.Text(
                            settings.APP_TITLE,
                            size=22,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE,
                        ),
                        self._conn_indicator,
                    ],
                    spacing=2,
                ),
                ft.Container(expand=True),
                self._mode_badge,
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def _build_price_section(self) -> ft.Control:
        """Construye la sección de precio con ticker y chart."""
        return ft.Container(
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_radius=16,
            padding=ft.Padding.all(20),
            content=ft.Column(
                controls=[
                    self._ticker,
                    ft.Container(height=8),
                    self._chart,
                ],
                spacing=0,
            ),
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def did_mount(self) -> None:
        event_bus.subscribe(SettingsUpdatedEvent, self._on_settings_updated)
        self._sync_from_settings()

    def will_unmount(self) -> None:
        event_bus.unsubscribe(SettingsUpdatedEvent, self._on_settings_updated)

    def _sync_from_settings(self) -> None:
        """Re-sincroniza estado desde settings (llamar en did_mount)."""
        self._mode_badge.update_mode(settings.TRADING_MODE)
        self._ticker.sync_symbol()
        self._chart.sync_symbol()
        self._stats.update_symbol(settings.TRADING_SYMBOL)

    # ------------------------------------------------------------------
    # Responsive — se llama desde app_layout.on_resize
    # ------------------------------------------------------------------
    def _on_resize(self, width: float, height: float) -> None:
        """Ajusta tamaños de fuente según ancho de pantalla."""
        self._stats.on_resize(width, height)
        self._ticker.on_resize(width, height)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    async def _on_settings_updated(self, event: SettingsUpdatedEvent) -> None:
        """Actualiza badges del header al cambiar configuración."""
        log.info(
            "DashboardView: settings updated - symbol=%s, trading_type=%s, mode=%s",
            event.symbol,
            event.trading_type,
            event.mode,
        )
        self._sync_from_settings()
