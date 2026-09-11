"""
Dashboard View — Pantalla principal del bot de trading.

Incluye:
- Header con símbolo y ConnectionIndicator
- PriceTicker (precio en tiempo real con flash)
- MiniChart (sparkline últimos 60 ticks)
- Stats de 24h (high/low/volumen) — reactivos a PriceTickEvent
- BalanceCard (saldo de cuenta auto-refresh)
- Sección de Parámetros (monto, símbolo, SL, temporalidad, leverage)
- BotStatusBar (señal MA actual)
- OperationsPanel (operaciones duales OC/OV)
- Botón ON/OFF del bot
"""
from __future__ import annotations

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
from ui.components.symbol_picker import SymbolPicker


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
        self._symbol_picker = SymbolPicker(on_symbol_changed=self._on_symbol_changed)
        self._balance_card = BalanceCard()

        # --- Stats 24h ---
        self._high_text = ft.Text("---", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.GREEN_400)
        self._low_text = ft.Text("---", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.RED_400)
        self._vol_text = ft.Text("---", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.BLUE_300)

        # --- Parámetros de operación ---
        self._amount_field = ft.TextField(
            label="Monto",
            value=str(settings.TRADE_AMOUNT),
            hint_text="10.0",
            keyboard_type=ft.KeyboardType.NUMBER,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.CYAN_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            expand=True,
        )

        self._currency_dropdown = ft.Dropdown(
            value=settings.TRADE_CURRENCY,
            options=[
                ft.DropdownOption(key="USDT", text="USDT"),
                ft.DropdownOption(key="USDC", text="USDC"),
            ],
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.CYAN_400,
            color=ft.Colors.WHITE,
            width=100,
        )

        self._sl_field = ft.TextField(
            label="Stop Loss",
            value=str(settings.STOP_LOSS),
            hint_text="1.01",
            keyboard_type=ft.KeyboardType.NUMBER,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.CYAN_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            expand=True,
        )

        self._sl_type_dropdown = ft.Dropdown(
            value=settings.STOP_LOSS_TYPE,
            options=[
                ft.DropdownOption(key="PERCENT", text="%"),
                ft.DropdownOption(key="USDT", text="USDT"),
            ],
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.CYAN_400,
            color=ft.Colors.WHITE,
            width=80,
        )

        self._timeframe_field = ft.TextField(
            label="Temporalidad",
            value=str(settings.TIMEFRAME),
            hint_text="1",
            keyboard_type=ft.KeyboardType.NUMBER,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.CYAN_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            expand=True,
        )

        self._timeframe_unit_dropdown = ft.Dropdown(
            value=settings.TIMEFRAME_UNIT,
            options=[
                ft.DropdownOption(key="MINUTES", text="Min"),
                ft.DropdownOption(key="HOURS", text="Horas"),
            ],
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.CYAN_400,
            color=ft.Colors.WHITE,
            width=80,
        )

        leverage_options = [ft.DropdownOption(key=str(i), text=f"{i}x") for i in [1, 2, 3, 5, 10, 15, 20]]
        self._leverage_dropdown = ft.Dropdown(
            label="Apalancamiento",
            value=str(settings.LEVERAGE),
            options=leverage_options,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.PURPLE_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
        )

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
        trading_type_colors = {
            "SPOT": (ft.Colors.BLUE_400, ft.Colors.BLUE_900),
            "FUTURES": (ft.Colors.PURPLE_400, ft.Colors.PURPLE_900),
            "MARGIN": (ft.Colors.ORANGE_400, ft.Colors.ORANGE_900),
        }
        tt_color, tt_bg = trading_type_colors.get(settings.TRADING_TYPE, (ft.Colors.BLUE_400, ft.Colors.BLUE_900))

        self._trading_type_badge = ft.Container(
            content=ft.Text(settings.TRADING_TYPE, size=10, weight=ft.FontWeight.BOLD, color=tt_color),
            bgcolor=tt_bg,
            border=ft.Border.all(1, tt_color),
            border_radius=6,
            padding=ft.Padding(left=8, right=8, top=3, bottom=3),
        )

        mode_color = ft.Colors.AMBER_400 if settings.TRADING_MODE == "PAPER" else ft.Colors.RED_400
        self._mode_badge = ft.Container(
            content=ft.Text(settings.TRADING_MODE, size=11, weight=ft.FontWeight.BOLD, color=mode_color),
            bgcolor=ft.Colors.with_opacity(0.15, mode_color),
            border=ft.Border.all(1, mode_color),
            border_radius=6,
            padding=ft.Padding(left=10, right=10, top=4, bottom=4),
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
                    self._trading_type_badge,
                    ft.Container(width=6),
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

            # Sección de Parámetros
            ft.Container(
                bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
                border_radius=14,
                padding=ft.Padding(left=16, right=16, top=12, bottom=12),
                content=ft.Column(
                    controls=[
                        ft.Text("📋 Parámetros", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                        ft.Container(height=4),
                        # Símbolo
                        self._symbol_picker,
                        # Monto + Moneda
                        ft.Row(
                            controls=[
                                self._amount_field,
                                self._currency_dropdown,
                            ],
                            spacing=8,
                        ),
                        # Stop Loss + Tipo
                        ft.Row(
                            controls=[
                                self._sl_field,
                                self._sl_type_dropdown,
                            ],
                            spacing=8,
                        ),
                        # Temporalidad + Unidad
                        ft.Row(
                            controls=[
                                self._timeframe_field,
                                self._timeframe_unit_dropdown,
                            ],
                            spacing=8,
                        ),
                        # Apalancamiento
                        self._leverage_dropdown,
                    ],
                    spacing=10,
                ),
            ),

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

    def will_unmount(self) -> None:
        event_bus.unsubscribe(PriceTickEvent, self._on_price_tick)
        event_bus.unsubscribe(SettingsUpdatedEvent, self._on_settings_updated)

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
        trading_type_colors = {
            "SPOT": (ft.Colors.BLUE_400, ft.Colors.BLUE_900),
            "FUTURES": (ft.Colors.PURPLE_400, ft.Colors.PURPLE_900),
            "MARGIN": (ft.Colors.ORANGE_400, ft.Colors.ORANGE_900),
        }
        tt_color, tt_bg = trading_type_colors.get(event.trading_type, (ft.Colors.BLUE_400, ft.Colors.BLUE_900))
        self._trading_type_badge.content.value = event.trading_type
        self._trading_type_badge.content.color = tt_color
        self._trading_type_badge.bgcolor = tt_bg
        self._trading_type_badge.border = ft.Border.all(1, tt_color)
        self._trading_type_badge.update()

        mode_color = ft.Colors.AMBER_400 if event.mode == "PAPER" else ft.Colors.RED_400
        self._mode_badge.content.value = event.mode
        self._mode_badge.content.color = mode_color
        self._mode_badge.bgcolor = ft.Colors.with_opacity(0.15, mode_color)
        self._mode_badge.border = ft.Border.all(1, mode_color)
        self._mode_badge.update()

    def _on_symbol_changed(self, symbol: str) -> None:
        """Cuando el usuario cambia el símbolo, actualizar ticker y chart."""
        self._ticker.symbol = symbol
        self._chart.symbol = symbol
        self._ticker.update()
        self._chart.update()

    def _toggle_bot(self, e: ft.ControlEvent) -> None:
        """Inicia o detiene el bot de trading."""
        self._bot_active = not self._bot_active

        # Guardar parámetros en settings antes de publicar
        self._save_params_to_settings()

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

    def _save_params_to_settings(self) -> None:
        """Guarda los parámetros del dashboard en settings."""
        try:
            settings.TRADE_AMOUNT = float(self._amount_field.value or "10.0")
        except ValueError:
            settings.TRADE_AMOUNT = 10.0

        settings.TRADE_CURRENCY = self._currency_dropdown.value or "USDT"

        try:
            settings.STOP_LOSS = float(self._sl_field.value or "1.01")
        except ValueError:
            settings.STOP_LOSS = 1.01

        settings.STOP_LOSS_TYPE = self._sl_type_dropdown.value or "PERCENT"

        try:
            settings.TIMEFRAME = int(self._timeframe_field.value or "1")
        except ValueError:
            settings.TIMEFRAME = 1

        settings.TIMEFRAME_UNIT = self._timeframe_unit_dropdown.value or "MINUTES"

        try:
            settings.LEVERAGE = int(self._leverage_dropdown.value or "1")
        except ValueError:
            settings.LEVERAGE = 1
