"""
Dashboard View — Pantalla principal del bot de trading.

Incluye:
- Header con símbolo y ConnectionIndicator
- PriceTicker (precio en tiempo real con flash)
- MiniChart (sparkline últimos 60 ticks)
- Stats de 24h (high/low/volumen) — reactivos a PriceTickEvent
- BalanceCard (saldo de cuenta auto-refresh)
- BotStatusBar (señal MA actual)
- OperationsPanel (operaciones duales OC/OV)
- Botón ON/OFF del bot
"""
from __future__ import annotations

import logging

import flet as ft

from config.settings import settings
from core.event_bus import event_bus
from core.events import BotStateChangedEvent, PriceTickEvent, SettingsUpdatedEvent
from ui.components.balance_card import BalanceCard
from ui.components.bot_status_bar import BotStatusBar
from ui.components.connection_indicator import ConnectionIndicator
from ui.components.mini_chart import MiniChart
from ui.components.operations_panel import OperationsPanel
from ui.components.price_ticker import PriceTicker

log = logging.getLogger(__name__)


class DashboardView(ft.Column):
    """Vista principal con precio en tiempo real y estado del bot."""

    def __init__(self) -> None:
        super().__init__()
        self._bot_active: bool = False

        # --- Componentes reactivos ---
        self._ticker = PriceTicker(symbol=settings.TRADING_SYMBOL)
        self._chart = MiniChart(symbol=settings.TRADING_SYMBOL)
        self._bot_bar = BotStatusBar()
        self._conn_indicator = ConnectionIndicator()
        self._operations_panel = OperationsPanel()
        self._balance_card = BalanceCard()

        # --- Stats 24h ---
        self._high_text = ft.Text("---", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.GREEN_400)
        self._low_text = ft.Text("---", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.RED_400)
        self._vol_text = ft.Text("---", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.BLUE_300)

        # --- Botón ON/OFF bot ---
        self._toggle_btn = ft.FilledButton(
            content="▶  Iniciar Operaciones",
            icon=ft.Icons.PLAY_CIRCLE,
            on_click=self._toggle_bot,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.GREEN_800,
                color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.Padding(left=20, right=20, top=16, bottom=16),
            ),
        )

        # --- Layout ---
        mode_color = ft.Colors.AMBER_400 if settings.TRADING_MODE == "PAPER" else ft.Colors.RED_400
        self._mode_badge = ft.Container(
            content=ft.Text(settings.TRADING_MODE, size=11, weight=ft.FontWeight.BOLD, color=mode_color),
            bgcolor=ft.Colors.with_opacity(0.15, mode_color),
            border=ft.Border.all(1, mode_color),
            border_radius=6,
            padding=ft.Padding(left=10, right=10, top=4, bottom=4),
            tooltip="Paper = Simulado | Live = Real",
        )

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
            ft.Container(
                bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
                border_radius=14,
                padding=ft.Padding(left=16, right=16, top=12, bottom=12),
                content=ft.Row(
                    controls=[
                        ft.Column(
                            controls=[
                                ft.Text("Máx 24h", size=10, color=ft.Colors.BLUE_GREY_400),
                                self._high_text,
                            ],
                            spacing=2,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.VerticalDivider(color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)),
                        ft.Column(
                            controls=[
                                ft.Text("Mín 24h", size=10, color=ft.Colors.BLUE_GREY_400),
                                self._low_text,
                            ],
                            spacing=2,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.VerticalDivider(color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)),
                        ft.Column(
                            controls=[
                                ft.Text("Volumen", size=10, color=ft.Colors.BLUE_GREY_400),
                                self._vol_text,
                            ],
                            spacing=2,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                ),
            ),

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
        event_bus.subscribe(PriceTickEvent, self._on_price_tick)
        event_bus.subscribe(SettingsUpdatedEvent, self._on_settings_updated)
        self._sync_from_settings()

    def will_unmount(self) -> None:
        event_bus.unsubscribe(PriceTickEvent, self._on_price_tick)
        event_bus.unsubscribe(SettingsUpdatedEvent, self._on_settings_updated)

    def _sync_from_settings(self) -> None:
        """Re-sincroniza estado desde settings (llamar en did_mount)."""
        self._sync_badges()
        self._ticker._sync_symbol()
        self._chart._sync_symbol()

    def _sync_badges(self) -> None:
        """Sincroniza badges con los valores actuales de settings."""
        mode_color = ft.Colors.AMBER_400 if settings.TRADING_MODE == "PAPER" else ft.Colors.RED_400
        self._mode_badge.content.value = settings.TRADING_MODE
        self._mode_badge.content.color = mode_color
        self._mode_badge.bgcolor = ft.Colors.with_opacity(0.15, mode_color)
        self._mode_badge.border = ft.Border.all(1, mode_color)
        self._mode_badge.update()

    # ------------------------------------------------------------------
    # Responsive — se llama desde app_layout.on_resize
    # ------------------------------------------------------------------
    def _on_resize(self, width: float, height: float) -> None:
        """Ajusta tamaños de fuente según ancho de pantalla."""
        is_small = width < 360
        # Stats
        stats_size = 11 if is_small else 13
        self._high_text.style = ft.TextStyle(size=stats_size, weight=ft.FontWeight.W_600, color=ft.Colors.GREEN_400)
        self._low_text.style = ft.TextStyle(size=stats_size, weight=ft.FontWeight.W_600, color=ft.Colors.RED_400)
        self._vol_text.style = ft.TextStyle(size=stats_size, weight=ft.FontWeight.W_500, color=ft.Colors.BLUE_300)
        self._high_text.update()
        self._low_text.update()
        self._vol_text.update()
        # Propagar a hijos
        self._ticker._on_resize(width, height)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    async def _on_price_tick(self, event: PriceTickEvent) -> None:
        if event.symbol != settings.TRADING_SYMBOL:
            return
        log.debug("DashboardView: price tick - symbol=%s, price=%.2f", event.symbol, event.price)
        # Actualizar stats 24h individualmente
        self._high_text.value = f"${event.high_24h:,.2f}"
        self._high_text.update()
        self._low_text.value = f"${event.low_24h:,.2f}"
        self._low_text.update()

        vol_m = event.volume / 1_000_000
        self._vol_text.value = f"${vol_m:.1f}M"
        self._vol_text.update()

    async def _on_settings_updated(self, event: SettingsUpdatedEvent) -> None:
        """Actualiza badges del header al cambiar configuración."""
        log.info("DashboardView: settings updated - symbol=%s, trading_type=%s, mode=%s",
                 event.symbol, event.trading_type, event.mode)
        self._sync_from_settings()

    def _toggle_bot(self, e: ft.ControlEvent) -> None:
        """Inicia o detiene el bot de trading."""
        self._bot_active = not self._bot_active

        event_bus.publish(BotStateChangedEvent(
            is_running=self._bot_active,
            mode=settings.TRADING_MODE,
        ))

        if self._bot_active:
            self._toggle_btn.content = "⏸  Detener Operaciones"
            self._toggle_btn.style.bgcolor = ft.Colors.RED_800
            self._toggle_btn.icon = ft.Icons.PAUSE_CIRCLE
        else:
            self._toggle_btn.content = "▶  Iniciar Operaciones"
            self._toggle_btn.style.bgcolor = ft.Colors.GREEN_800
            self._toggle_btn.icon = ft.Icons.PLAY_CIRCLE
        self._toggle_btn.update()
