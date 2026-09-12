"""
Dashboard View — Pantalla principal del bot de trading.

Refactorizado para aplicar SRP:
- Stats24H maneja stats 24h (extraído)
- BotToggle maneja ON/OFF del bot (extraído)
- ModeBadge maneja el badge de modo (extraído)
"""
from __future__ import annotations

import logging

import flet as ft

from config.settings import settings
from core.event_bus import event_bus
from core.events import PriceTickEvent, SettingsUpdatedEvent
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
    """Vista principal con precio en tiempo real y estado del bot."""

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

        # --- Layout ---
        self.controls = [
            # Header
            ft.Row(
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
            ),

            ft.Divider(color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE), height=1),

            # Precio principal
            ft.Container(
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
            ),

            # Stats 24h
            self._stats,

            # Balance Card
            self._balance_card,

            # Bot status bar
            self._bot_bar,

            # Botón toggle bot
            ft.Row(
                controls=[self._toggle_btn],
                alignment=ft.MainAxisAlignment.CENTER,
            ),

            # Operaciones duales
            self._operations_panel,
        ]

        self.spacing = 12
        self.scroll = ft.ScrollMode.AUTO

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
        self._ticker._sync_symbol()
        self._chart._sync_symbol()
        self._stats.update_symbol(settings.TRADING_SYMBOL)

    # ------------------------------------------------------------------
    # Responsive — se llama desde app_layout.on_resize
    # ------------------------------------------------------------------
    def _on_resize(self, width: float, height: float) -> None:
        """Ajusta tamaños de fuente según ancho de pantalla."""
        self._stats._on_resize(width, height)
        self._ticker._on_resize(width, height)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    async def _on_settings_updated(self, event: SettingsUpdatedEvent) -> None:
        """Actualiza badges del header al cambiar configuración."""
        log.info("DashboardView: settings updated - symbol=%s, trading_type=%s, mode=%s",
                 event.symbol, event.trading_type, event.mode)
        self._sync_from_settings()
