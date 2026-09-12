"""
Settings View — Configuración del bot de trading.

Permite al usuario cambiar:
- Símbolo de trading
- Modo de operación (Paper / Live)
- Tipo de trading (Spot/Futures/Margin)
- API Keys (solo en modo Live, campos con password=True)
- Parámetros de operación (Monto, Stop Loss, Temporalidad)

Al guardar: muestra modal de confirmación, luego publica SettingsUpdatedEvent.
"""
from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from config.settings import settings
from core.event_bus import event_bus
from core.events import NavigateToEvent, SettingsUpdatedEvent
from services.env_service import EnvService
from ui.components.symbol_picker import SymbolPicker


@dataclass(frozen=True)
class SettingsFormData:
    """DTO inmutable con valores del formulario de configuración."""
    symbol: str
    mode: str
    trading_type: str
    leverage: int
    order_type: str
    limit_price: float
    api_key: str
    api_secret: str
    amount: float
    currency: str
    sl: float
    sl_type: str
    timeframe: int
    tf_unit: str


class SettingsView(ft.Column):
    """Pantalla de configuración del bot."""

    def __init__(self) -> None:
        super().__init__()

        # --- Campos de formulario ---
        self._mode_dropdown = ft.Dropdown(
            label="Modo de Operación",
            value=settings.TRADING_MODE,
            options=[
                ft.DropdownOption(key="PAPER", text="📄 Paper Trading (Simulado)"),
                ft.DropdownOption(key="LIVE", text="⚡ Live Trading (Real)"),
            ],
            bgcolor=ft.Colors.GREY_900,
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.AMBER_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            on_select=self._on_mode_changed,
        )

        # --- Trading Type (Spot/Futures/Margin) ---
        self._trading_type_dropdown = ft.Dropdown(
            label="Tipo de Trading",
            value=settings.TRADING_TYPE,
            options=[
                ft.DropdownOption(key="SPOT", text="💰 Spot"),
                ft.DropdownOption(key="FUTURES", text="📈 Futures (USDT-M)"),
                ft.DropdownOption(key="MARGIN", text="🔄 Cross Margin"),
            ],
            bgcolor=ft.Colors.GREY_900,
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.PURPLE_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            on_select=self._on_trading_type_changed,
        )

        # --- Leverage (solo Futures/Margin) ---
        leverage_options = [ft.DropdownOption(key=str(i), text=f"{i}x") for i in [1, 2, 3, 5, 10, 15, 20]]
        self._leverage_dropdown = ft.Dropdown(
            label="Leverage",
            value=str(settings.LEVERAGE),
            options=leverage_options,
            bgcolor=ft.Colors.GREY_900,
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.PURPLE_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            visible=settings.TRADING_TYPE in ("FUTURES", "MARGIN"),
        )

        # --- Order Type (MARKET/LIMIT) ---
        self._order_type_dropdown = ft.Dropdown(
            label="Tipo de Orden",
            value=settings.ORDER_TYPE,
            options=[
                ft.DropdownOption(key="MARKET", text="⚡ Market (Inmediata)"),
                ft.DropdownOption(key="LIMIT", text="🎯 Limit (Con precio)"),
            ],
            bgcolor=ft.Colors.GREY_900,
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.CYAN_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            on_select=self._on_order_type_changed,
        )

        # --- Limit Price (solo LIMIT) ---
        self._limit_price_field = ft.TextField(
            label="Precio Límite",
            value=str(settings.LIMIT_PRICE) if settings.LIMIT_PRICE > 0 else "",
            hint_text="Ej: 65000.00",
            prefix_icon=ft.Icons.ATTACH_MONEY,
            keyboard_type=ft.KeyboardType.NUMBER,
            bgcolor=ft.Colors.GREY_900,
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.CYAN_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            visible=settings.ORDER_TYPE == "LIMIT",
            on_change=lambda e: self._update_save_button_state(),
        )

        self._api_key_field = ft.TextField(
            label="Binance API Key",
            value=settings.BINANCE_API_KEY,
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.KEY,
            bgcolor=ft.Colors.GREY_900,
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.AMBER_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            visible=settings.TRADING_MODE == "LIVE",
            on_change=lambda e: self._update_save_button_state(),
        )

        self._api_secret_field = ft.TextField(
            label="Binance API Secret",
            value=settings.BINANCE_API_SECRET,
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.LOCK,
            bgcolor=ft.Colors.GREY_900,
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.AMBER_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            visible=settings.TRADING_MODE == "LIVE",
            on_change=lambda e: self._update_save_button_state(),
        )

        self._live_warning = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.WARNING_AMBER, color=ft.Colors.AMBER_400, size=16),
                    ft.Text(
                        "Live Mode ejecuta órdenes reales en Binance.\nÚsalo con responsabilidad.",
                        size=12,
                        color=ft.Colors.AMBER_300,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
                spacing=8,
            ),
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.AMBER_400),
            border_radius=10,
            padding=ft.Padding.all(12),
            visible=settings.TRADING_MODE == "LIVE",
        )

        # --- SymbolPicker ---
        self._symbol_picker = SymbolPicker(
            on_symbol_changed=self._on_symbol_changed
        )

        # --- Parámetros de Operación ---
        self._amount_field = ft.TextField(
            label="Monto",
            value=str(settings.TRADE_AMOUNT),
            hint_text="10.0",
            prefix_icon=ft.Icons.ATTACH_MONEY,
            keyboard_type=ft.KeyboardType.NUMBER,
            bgcolor=ft.Colors.GREY_900,
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.CYAN_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            expand=True,
            on_change=lambda e: self._update_save_button_state(),
        )

        self._currency_dropdown = ft.Dropdown(
            label="Moneda",
            value=settings.TRADE_CURRENCY,
            options=[
                ft.DropdownOption(key="USDT", text="USDT"),
                ft.DropdownOption(key="USDC", text="USDC"),
            ],
            bgcolor=ft.Colors.GREY_900,
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.CYAN_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            width=120,
            on_select=self._on_currency_changed,
        )

        self._sl_field = ft.TextField(
            label="Stop Loss",
            value=str(settings.STOP_LOSS),
            hint_text="1.01",
            prefix_icon=ft.Icons.TRENDING_DOWN,
            keyboard_type=ft.KeyboardType.NUMBER,
            bgcolor=ft.Colors.GREY_900,
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.RED_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            expand=True,
            on_change=lambda e: self._update_save_button_state(),
        )

        self._sl_type_dropdown = ft.Dropdown(
            label="Tipo SL",
            value=settings.STOP_LOSS_TYPE,
            options=[
                ft.DropdownOption(key="PERCENT", text="%"),
                ft.DropdownOption(key="USDT", text="USDT"),
            ],
            bgcolor=ft.Colors.GREY_900,
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.RED_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            width=100,
            on_select=lambda e: self._update_save_button_state(),
        )

        self._timeframe_field = ft.TextField(
            label="Temporalidad",
            value=str(settings.TIMEFRAME),
            hint_text="1",
            prefix_icon=ft.Icons.TIMER,
            keyboard_type=ft.KeyboardType.NUMBER,
            bgcolor=ft.Colors.GREY_900,
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.AMBER_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            expand=True,
            on_change=lambda e: self._update_save_button_state(),
        )

        self._timeframe_unit_dropdown = ft.Dropdown(
            label="Unidad",
            value=settings.TIMEFRAME_UNIT,
            options=[
                ft.DropdownOption(key="MINUTES", text="Min"),
                ft.DropdownOption(key="HOURS", text="Horas"),
            ],
            bgcolor=ft.Colors.GREY_900,
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.AMBER_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            width=100,
            on_select=lambda e: self._update_save_button_state(),
        )

        self._save_btn = ft.FilledButton(
            content="Guardar y Reconectar",
            icon=ft.Icons.SAVE,
            on_click=self._on_save,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_800,
                color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.Padding(left=24, right=24, top=14, bottom=14),
            ),
        )

        self._feedback_text = ft.Text("", size=12, color=ft.Colors.GREEN_400)

        # --- Layout ---
        self.controls = [
            ft.Text(
                "Configuración",
                size=22,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.WHITE,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Container(
                width=380,
                content=ft.Divider(color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE), height=20),
            ),

            # Modo
            ft.Container(
                width=380,
                bgcolor=ft.Colors.BLUE_GREY_900,
                border_radius=14,
                padding=ft.Padding.all(16),
                content=ft.Column(
                    controls=[
                        ft.Text("⚙️ Modo de Operación", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                        self._mode_dropdown,
                        self._live_warning,
                        self._api_key_field,
                        self._api_secret_field,
                    ],
                    spacing=12,
                ),
            ),

            # Tipo de Trading
            ft.Container(
                width=380,
                bgcolor=ft.Colors.BLUE_GREY_900,
                border_radius=14,
                padding=ft.Padding.all(16),
                content=ft.Column(
                    controls=[
                        ft.Text("🔄 Tipo de Trading", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                        self._trading_type_dropdown,
                        self._leverage_dropdown,
                        self._order_type_dropdown,
                        self._limit_price_field,
                        ft.Text(
                            "Futures/Margin permiten leverage y posiciones long/short.",
                            size=11, color=ft.Colors.BLUE_GREY_400,
                        ),
                    ],
                    spacing=12,
                ),
            ),

            # Parámetros de Operación
            ft.Container(
                width=380,
                bgcolor=ft.Colors.BLUE_GREY_900,
                border_radius=14,
                padding=ft.Padding.all(16),
                content=ft.Column(
                    controls=[
                        ft.Text("📋 Parámetros", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                        ft.Row(controls=[self._amount_field, self._currency_dropdown], spacing=8),
                        self._symbol_picker,
                        ft.Row(controls=[self._sl_field, self._sl_type_dropdown], spacing=8),
                        ft.Row(controls=[self._timeframe_field, self._timeframe_unit_dropdown], spacing=8),
                    ],
                    spacing=12,
                ),
            ),

            # Guardar
            ft.Row(controls=[self._save_btn], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row(controls=[self._feedback_text], alignment=ft.MainAxisAlignment.CENTER),
        ]

        self.spacing = 16
        self.expand = True
        self.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        self.scroll = ft.ScrollMode.AUTO
        self._save_btn.disabled = not self._has_changes()

    # ------------------------------------------------------------------
    # Detección de cambios
    # ------------------------------------------------------------------
    def _has_changes(self) -> bool:
        """Retorna True si el formulario difiere de la configuración actual."""
        mode = self._mode_dropdown.value or "PAPER"
        trading_type = self._trading_type_dropdown.value or "SPOT"
        leverage = int(self._leverage_dropdown.value or "1")
        order_type = self._order_type_dropdown.value or "MARKET"
        limit_price = float(self._limit_price_field.value or "0")
        
        # Nuevos campos
        symbol = self._symbol_picker.get_selected_symbol()
        amount = float(self._amount_field.value or "10.0")
        currency = self._currency_dropdown.value or "USDT"
        sl = float(self._sl_field.value or "1.01")
        sl_type = self._sl_type_dropdown.value or "PERCENT"
        timeframe = int(self._timeframe_field.value or "1")
        tf_unit = self._timeframe_unit_dropdown.value or "MINUTES"

        return (
            mode != settings.TRADING_MODE
            or trading_type != settings.TRADING_TYPE
            or leverage != settings.LEVERAGE
            or order_type != settings.ORDER_TYPE
            or (order_type == "LIMIT" and limit_price != settings.LIMIT_PRICE)
            or symbol != settings.TRADING_SYMBOL
            or amount != settings.TRADE_AMOUNT
            or currency != settings.TRADE_CURRENCY
            or sl != settings.STOP_LOSS
            or sl_type != settings.STOP_LOSS_TYPE
            or timeframe != settings.TIMEFRAME
            or tf_unit != settings.TIMEFRAME_UNIT
        )

    def _update_save_button_state(self) -> None:
        """Habilita/deshabilita el botón según si hay cambios."""
        self._save_btn.disabled = not self._has_changes()
        self._save_btn.update()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_mode_changed(self, e: ft.ControlEvent) -> None:
        is_live = e.control.value == "LIVE"
        self._api_key_field.visible = is_live
        self._api_secret_field.visible = is_live
        self._live_warning.visible = is_live
        self._api_key_field.update()
        self._api_secret_field.update()
        self._live_warning.update()
        self._update_save_button_state()

    def _on_trading_type_changed(self, e: ft.ControlEvent) -> None:
        trading_type = e.control.value
        show_leverage = trading_type in ("FUTURES", "MARGIN")
        self._leverage_dropdown.visible = show_leverage
        self._leverage_dropdown.update()
        self._update_save_button_state()

    def _on_order_type_changed(self, e: ft.ControlEvent) -> None:
        is_limit = e.control.value == "LIMIT"
        self._limit_price_field.visible = is_limit
        self._limit_price_field.update()
        self._update_save_button_state()

    def _on_symbol_changed(self, symbol: str) -> None:
        self._update_save_button_state()

    def _on_currency_changed(self, e: ft.ControlEvent) -> None:
        self._update_save_button_state()

    def _on_save(self, e: ft.ControlEvent) -> None:
        """Abre modal de confirmación antes de guardar."""
        self._show_confirm_dialog()

    def _on_cancel(self, e: ft.ControlEvent) -> None:
        """Handler para botón Cancelar del modal."""
        self._close_dialog()

    def _on_confirm(self, e: ft.ControlEvent) -> None:
        """Handler para botón Confirmar del modal."""
        self._apply_changes()

    def _show_confirm_dialog(self) -> None:
        """Muestra modal de confirmación con resumen de cambios."""
        mode = self._mode_dropdown.value or "PAPER"
        trading_type = self._trading_type_dropdown.value or "SPOT"
        leverage = int(self._leverage_dropdown.value or "1")
        order_type = self._order_type_dropdown.value or "MARKET"
        limit_price = float(self._limit_price_field.value or "0")
        
        # Nuevos campos
        symbol = self._symbol_picker.get_selected_symbol()
        amount = float(self._amount_field.value or "10.0")
        currency = self._currency_dropdown.value or "USDT"
        sl = float(self._sl_field.value or "1.01")
        sl_type = self._sl_type_dropdown.value or "PERCENT"
        timeframe = int(self._timeframe_field.value or "1")
        tf_unit = self._timeframe_unit_dropdown.value or "MINUTES"

        # Construir resumen de cambios
        changes = []
        if symbol != settings.TRADING_SYMBOL:
            changes.append(f"Símbolo: {settings.TRADING_SYMBOL} → {symbol}")
        if mode != settings.TRADING_MODE:
            changes.append(f"Modo: {settings.TRADING_MODE} → {mode}")
        if trading_type != settings.TRADING_TYPE:
            changes.append(f"Tipo: {settings.TRADING_TYPE} → {trading_type}")
        if leverage != settings.LEVERAGE:
            changes.append(f"Leverage: {settings.LEVERAGE}x → {leverage}x")
        if order_type != settings.ORDER_TYPE:
            changes.append(f"Orden: {settings.ORDER_TYPE} → {order_type}")
        if limit_price != settings.LIMIT_PRICE and settings.ORDER_TYPE == "LIMIT":
            changes.append(f"Precio Límite: ${settings.LIMIT_PRICE} → ${limit_price}")
        if amount != settings.TRADE_AMOUNT:
            changes.append(f"Monto: ${settings.TRADE_AMOUNT} → ${amount}")
        if currency != settings.TRADE_CURRENCY:
            changes.append(f"Moneda: {settings.TRADE_CURRENCY} → {currency}")
        if sl != settings.STOP_LOSS:
            changes.append(f"Stop Loss: {settings.STOP_LOSS} → {sl}")
        if sl_type != settings.STOP_LOSS_TYPE:
            changes.append(f"Tipo SL: {settings.STOP_LOSS_TYPE} → {sl_type}")
        if timeframe != settings.TIMEFRAME:
            changes.append(f"Temporalidad: {settings.TIMEFRAME} → {timeframe}")
        if tf_unit != settings.TIMEFRAME_UNIT:
            changes.append(f"Unidad: {settings.TIMEFRAME_UNIT} → {tf_unit}")

        if not changes:
            changes.append("No hay cambios detectados")

        # Crear modal
        self._confirm_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar Cambios", color=ft.Colors.WHITE, size=15),
            bgcolor=ft.Colors.BLUE_GREY_900,
            content=ft.Column(
                controls=[
                    ft.Text("Se aplicarán los siguientes cambios:", color=ft.Colors.BLUE_GREY_300),
                    ft.Container(height=8),
                    *[ft.Text(f"• {c}", color=ft.Colors.WHITE, size=13) for c in changes],
                    ft.Container(height=8),
                    ft.Text(
                        "El servicio se reconectará.",
                        size=11,
                        color=ft.Colors.AMBER_400,
                    ),
                ],
                spacing=0,
                width=300,
                height=150,
            ),
            actions=[
                ft.TextButton(
                    "Cancelar",
                    on_click=self._on_cancel,
                ),
                ft.FilledButton(
                    "Confirmar",
                    on_click=self._on_confirm,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.BLUE_800,
                        color=ft.Colors.WHITE,
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            inset_padding=ft.Padding.all(12),
        )

        self.page.overlay.append(self._confirm_dialog)
        self.page.update()
        self._confirm_dialog.open = True
        self._confirm_dialog.update()

    # ------------------------------------------------------------------
    # Form helpers
    # ------------------------------------------------------------------
    def _build_form_data(self) -> SettingsFormData:
        """Extrae valores del formulario como DTO inmutable."""
        return SettingsFormData(
            symbol=self._symbol_picker.get_selected_symbol(),
            mode=self._mode_dropdown.value or "PAPER",
            trading_type=self._trading_type_dropdown.value or "SPOT",
            leverage=int(self._leverage_dropdown.value or "1"),
            order_type=self._order_type_dropdown.value or "MARKET",
            limit_price=float(self._limit_price_field.value or "0"),
            api_key=self._api_key_field.value or "",
            api_secret=self._api_secret_field.value or "",
            amount=float(self._amount_field.value or "10.0"),
            currency=self._currency_dropdown.value or "USDT",
            sl=float(self._sl_field.value or "1.01"),
            sl_type=self._sl_type_dropdown.value or "PERCENT",
            timeframe=int(self._timeframe_field.value or "1"),
            tf_unit=self._timeframe_unit_dropdown.value or "MINUTES",
        )

    def _build_env_snapshot(self) -> dict:
        """Snapshot de .env para rollback en caso de error."""
        return {
            "BINANCE_API_KEY": settings.BINANCE_API_KEY,
            "BINANCE_API_SECRET": settings.BINANCE_API_SECRET,
        }

    def _update_settings_from_form(self, form: SettingsFormData) -> None:
        """Actualiza settings en memoria desde el DTO del formulario."""
        settings.reload_from_env()
        settings.TRADING_SYMBOL = form.symbol
        settings.TRADING_MODE = form.mode
        settings.TRADING_TYPE = form.trading_type
        settings.LEVERAGE = form.leverage
        settings.ORDER_TYPE = form.order_type
        settings.LIMIT_PRICE = form.limit_price
        settings.TRADE_AMOUNT = form.amount
        settings.TRADE_CURRENCY = form.currency
        settings.STOP_LOSS = form.sl
        settings.STOP_LOSS_TYPE = form.sl_type
        settings.TIMEFRAME = form.timeframe
        settings.TIMEFRAME_UNIT = form.tf_unit

    # ------------------------------------------------------------------
    # Apply changes
    # ------------------------------------------------------------------
    def _apply_changes(self) -> None:
        """Aplica los cambios después de confirmar en el modal."""
        self._confirm_dialog.content = ft.Column(
            controls=[
                ft.ProgressRing(width=28, height=28, stroke_width=3),
                ft.Container(height=10),
                ft.Text("Aplicando cambios...", color=ft.Colors.WHITE, size=14),
                ft.Text("El servicio se reconectará.", color=ft.Colors.AMBER_400, size=11),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            width=250,
            height=150,
        )
        self._confirm_dialog.actions = []
        self._confirm_dialog.update()

        form = self._build_form_data()
        env_snapshot = self._build_env_snapshot()
        form_snapshot = vars(form)

        try:
            EnvService.save_sensitive(form.api_key, form.api_secret)

            import asyncio
            asyncio.create_task(self._save_config_to_db(form))

            self._update_settings_from_form(form)

            event_bus.publish(SettingsUpdatedEvent(
                symbol=form.symbol,
                mode=form.mode,
                trading_type=form.trading_type,
                leverage=form.leverage,
                order_type=form.order_type,
                limit_price=form.limit_price,
                trade_amount=form.amount,
                trade_currency=form.currency,
                stop_loss=form.sl,
                stop_loss_type=form.sl_type,
                timeframe=form.timeframe,
                timeframe_unit=form.tf_unit,
                api_key=form.api_key,
                api_secret=form.api_secret,
            ))

            self._feedback_text.value = "✅ Configuración guardada. Reconectando..."
            self._feedback_text.color = ft.Colors.GREEN_400
            event_bus.publish(NavigateToEvent(index=0))

        except Exception as exc:
            EnvService.rollback(env_snapshot)
            settings.reload_from_env()
            self._restore_form_fields(form_snapshot)
            self._feedback_text.value = f"❌ Error: {exc}. Cambios revertidos."
            self._feedback_text.color = ft.Colors.RED_400

        finally:
            self._close_dialog()
            self._feedback_text.update()

    async def _save_config_to_db(self, form: SettingsFormData) -> None:
        """Guarda la configuración de trading en la base de datos."""
        from services.config_service import config_service
        await config_service.update(
            trading_symbol=form.symbol,
            trading_mode=form.mode,
            trading_type=form.trading_type,
            leverage=form.leverage,
            order_type=form.order_type,
            limit_price=form.limit_price,
            trade_amount=form.amount,
            trade_currency=form.currency,
            stop_loss=form.sl,
            stop_loss_type=form.sl_type,
            timeframe=form.timeframe,
            timeframe_unit=form.tf_unit,
        )

    def _restore_form_fields(self, form_snapshot: dict) -> None:
        """Restaura los campos del formulario a valores anteriores."""
        self._mode_dropdown.value = form_snapshot["mode"]
        self._trading_type_dropdown.value = form_snapshot["trading_type"]
        self._leverage_dropdown.value = str(form_snapshot["leverage"])
        self._order_type_dropdown.value = form_snapshot["order_type"]
        self._limit_price_field.value = str(form_snapshot["limit_price"])
        self._api_key_field.value = form_snapshot["api_key"]
        self._api_secret_field.value = form_snapshot["api_secret"]
        self._amount_field.value = str(form_snapshot["amount"])
        self._currency_dropdown.value = form_snapshot["currency"]
        self._sl_field.value = str(form_snapshot["sl"])
        self._sl_type_dropdown.value = form_snapshot["sl_type"]
        self._timeframe_field.value = str(form_snapshot["timeframe"])
        self._timeframe_unit_dropdown.value = form_snapshot["tf_unit"]

        is_live = form_snapshot["mode"] == "LIVE"
        self._api_key_field.visible = is_live
        self._api_secret_field.visible = is_live
        self._live_warning.visible = is_live

        show_leverage = form_snapshot["trading_type"] in ("FUTURES", "MARGIN")
        self._leverage_dropdown.visible = show_leverage

        is_limit = form_snapshot["order_type"] == "LIMIT"
        self._limit_price_field.visible = is_limit

    def refresh_symbols(self) -> None:
        """Refresca la lista de símbolos del SymbolPicker."""
        if hasattr(self, '_symbol_picker'):
            self._symbol_picker.refresh_symbols()

    def _close_dialog(self) -> None:
        """Cierra el modal de confirmación."""
        if hasattr(self, '_confirm_dialog') and self._confirm_dialog:
            self._confirm_dialog.open = False
            self._confirm_dialog.update()
            if self._confirm_dialog in self.page.overlay:
                self.page.overlay.remove(self._confirm_dialog)
