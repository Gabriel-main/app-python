"""
Settings View — Configuración del bot de trading.

Refactorizado para aplicar SRP + DIP:
- TradingModeSection maneja modo + API keys
- TradingTypeSection maneja tipo + leverage + order type
- OperationParamsSection maneja parámetros de operación
- ConfirmDialogHelper maneja modal de confirmación
- SettingsPersistence maneja persistencia de .env
"""
from __future__ import annotations

import asyncio

import flet as ft

from config.settings import settings
from core.event_bus import event_bus
from core.events import BalanceUpdateEvent, BotStateChangedEvent, NavigateToEvent, PriceTickEvent, SettingsUpdatedEvent
from core.update_batcher import update_batcher
from services.settings_persistence import EnvSettingsPersistence
from services.trading_rules import QuantitySizer, effective_min_notional, validate_funds
from ui.components.settings_sections import (
    ConfirmDialogHelper,
    OperationParamsSection,
    SettingsFormData,
    SymbolValidationIndicator,
    TradingModeSection,
    TradingTypeSection,
    validate_amount,
    validate_limit_price,
    validate_stop_loss,
    validate_timeframe,
)
from ui.components.view_header import ViewHeader


class SettingsView(ft.Column):
    """Pantalla de ajustes del bot de trading."""

    def __init__(self, persistence=None, symbol_repository=None) -> None:
        super().__init__()
        self._persistence = persistence or EnvSettingsPersistence()
        self._symbol_repository = symbol_repository
        self._bot_active: bool = False
        self._page: ft.Page | None = None

        # --- Secciones ---
        self._mode_section = TradingModeSection(on_change=self._update_save_button_state)
        self._type_section = TradingTypeSection(
            on_change=self._update_save_button_state,
            on_type_changed=self._on_trading_type_changed_for_validation,
        )
        self._params_section = OperationParamsSection(
            symbol_repository=symbol_repository,
            on_change=self._update_save_button_state,
            on_symbol_changed_for_validation=self._on_symbol_changed_for_validation,
            on_currency_changed_for_reload=self._on_currency_changed_for_reload,
        )

        # --- Indicador de validación ---
        self._validation_indicator = SymbolValidationIndicator()

        # Último precio de mercado conocido — única referencia alimentada por
        # PriceTickEvent, la usan la validación de LIMIT_PRICE y la de monto
        self._market_price_ref: float = 0.0
        # Último saldo conocido — BalanceUpdateEvent. None = desconocido →
        # validate_funds fail-open hasta que llegue el primer evento.
        self._balance_ref: BalanceUpdateEvent | None = None

        # DIP: el mismo QuantitySizer que usa BotEngine — misma size_entry()
        # para validar el monto aquí y para operar allá (DRY, cero duplicación)
        self._sizer = QuantitySizer(symbol_repository)

        # --- Botón guardar ---
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

        # --- Botón regresar ---
        self._back_btn = ft.IconButton(
            icon=ft.Icons.ARROW_BACK_IOS,
            icon_color=ft.Colors.BLUE_400,
            icon_size=20,
            on_click=self._on_back,
            tooltip="Volver a Configuración",
        )

        # --- Layout ---
        self.controls = [
            ViewHeader(
                "Ajustes del Bot",
                leading=self._back_btn,
                divider_width=380,
                divider_height=20,
                spacing=16,
            ),
            self._mode_section,
            self._type_section,
            self._params_section,
            ft.Container(
                content=self._validation_indicator,
                width=380,
                padding=ft.Padding.only(left=4, bottom=4),
            ),
            ft.Row(controls=[self._save_btn], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row(controls=[self._feedback_text], alignment=ft.MainAxisAlignment.CENTER),
        ]

        self.spacing = 16
        self.expand = True
        self.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        self.scroll = ft.ScrollMode.AUTO
        self._save_btn.disabled = not self._has_changes()

        self._confirm_dialog = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def did_mount(self) -> None:
        self._page = self.page
        # Re-sincronizar campos del formulario desde settings
        self._mode_section.sync_from_settings()
        self._type_section.sync_from_settings()
        self._params_section.sync_from_settings()
        # Sincronizar estado actual del bot (no solo eventos futuros)
        from services.bot_engine import bot_engine
        self._bot_active = bot_engine.is_active
        self._update_form_lock()
        # Validación proactiva al abrir (ej: FUTURES con monto < 50)
        self._update_save_button_state()
        event_bus.subscribe(BotStateChangedEvent, self._on_bot_state_changed)
        event_bus.subscribe(PriceTickEvent, self._on_price_tick)
        event_bus.subscribe(BalanceUpdateEvent, self._on_balance_update)
        # Consultar leverage máximo de Binance para el símbolo actual
        asyncio.create_task(self._refresh_max_leverage())
        # Precio de referencia (LIMIT_PRICE) y filtros del exchange (monto)
        asyncio.create_task(self._refresh_market_reference())
        asyncio.create_task(self._refresh_sizer())

    def will_unmount(self) -> None:
        event_bus.unsubscribe(BotStateChangedEvent, self._on_bot_state_changed)
        event_bus.unsubscribe(PriceTickEvent, self._on_price_tick)
        event_bus.unsubscribe(BalanceUpdateEvent, self._on_balance_update)

    async def _on_price_tick(self, event: PriceTickEvent) -> None:
        """Mantiene fresco el precio de referencia (sin polling)."""
        if event.symbol != self._params_section.get_symbol():
            return
        before = self._validation_signature()
        self._market_price_ref = event.price
        # Solo revalidar si alguna regla cambió de resultado: evita marcar
        # el botón como dirty en cada tick del WebSocket.
        if self._validation_signature() != before:
            self._update_save_button_state()

    async def _on_balance_update(self, event: BalanceUpdateEvent) -> None:
        """Mantiene fresco el saldo de referencia (push, sin polling)."""
        if event.asset != settings.TRADE_CURRENCY:
            return
        if event.trading_type != settings.TRADING_TYPE:
            return
        before = self._validation_signature()
        self._balance_ref = event
        # Solo revalidar si cambió la validez (mismo patrón que el tick)
        if self._validation_signature() != before:
            self._update_save_button_state()

    async def _refresh_market_reference(self) -> None:
        """Consulta el precio actual del símbolo del formulario (silencioso)."""
        if not self._symbol_repository:
            return
        symbol = self._params_section.get_symbol()
        try:
            price = await self._symbol_repository.get_symbol_price(symbol)
        except Exception:
            price = 0.0
        if symbol != self._params_section.get_symbol():
            return  # el símbolo cambió durante la consulta: dato obsoleto
        self._market_price_ref = price if price > 0 else 0.0
        self._update_save_button_state()

    async def _refresh_sizer(self) -> None:
        """Carga los filtros del exchange (minQty/stepSize/minNotional)."""
        if not self._symbol_repository:
            return
        symbol = self._params_section.get_symbol()
        trading_type = self._type_section.get_trading_type()
        await self._sizer.refresh(symbol, trading_type)
        if symbol != self._params_section.get_symbol():
            return  # el símbolo cambió durante la consulta: dato obsoleto
        self._update_save_button_state()

    async def _on_bot_state_changed(self, event: BotStateChangedEvent) -> None:
        """Actualiza estado del bot y bloquea/desbloquea formulario."""
        self._bot_active = event.is_running
        self._update_form_lock()

    def _update_form_lock(self) -> None:
        """Bloquea/desbloquea el formulario según estado del bot."""
        disabled = self._bot_active
        self._mode_section.set_disabled(disabled)
        self._type_section.set_disabled(disabled)
        self._params_section.set_disabled(disabled)
        limit_msg = self._limit_price_error_msg()
        self._type_section.set_limit_price_error(limit_msg)
        balance_msg = self._balance_error_msg()
        self._params_section.set_balance_error(balance_msg)
        self._save_btn.disabled = (
            disabled
            or not self._has_changes()
            or limit_msg is not None
            or balance_msg is not None
            or any(self._form_errors())
        )
        update_batcher.mark_dirty(self._save_btn)

    # ------------------------------------------------------------------
    # Detección de cambios
    # ------------------------------------------------------------------
    def _has_changes(self) -> bool:
        return (
            self._mode_section.get_mode() != settings.TRADING_MODE
            or self._type_section.get_trading_type() != settings.TRADING_TYPE
            or self._type_section.get_leverage() != settings.LEVERAGE
            or self._type_section.get_order_type() != settings.ORDER_TYPE
            or (self._type_section.get_order_type() == "LIMIT" and self._type_section.get_limit_price() != settings.LIMIT_PRICE)
            or self._params_section.get_symbol() != settings.TRADING_SYMBOL
            or self._params_section.get_amount() != settings.TRADE_AMOUNT
            or self._params_section.get_currency() != settings.TRADE_CURRENCY
            or self._params_section.get_sl() != settings.STOP_LOSS
            or self._params_section.get_sl_type() != settings.STOP_LOSS_TYPE
            or self._params_section.get_timeframe() != settings.TIMEFRAME
            or self._params_section.get_tf_unit() != settings.TIMEFRAME_UNIT
        )

    def _update_save_button_state(self) -> None:
        has_changes = self._has_changes()
        symbol_valid = not self._validation_indicator.visible or (
            self._validation_indicator._icon.color == ft.Colors.GREEN_400
        )
        limit_msg = self._limit_price_error_msg()
        self._type_section.set_limit_price_error(limit_msg)
        balance_msg = self._balance_error_msg()
        self._params_section.set_balance_error(balance_msg)
        errors = self._form_errors()
        self._params_section.set_validation_errors(*errors)
        self._save_btn.disabled = (
            not has_changes or not symbol_valid or limit_msg is not None
            or balance_msg is not None or any(errors)
        )
        update_batcher.mark_dirty(self._save_btn)

    def _limit_price_error_msg(self) -> str | None:
        """Mensaje de error del precio límite, o None si es válido."""
        return validate_limit_price(
            self._type_section.get_limit_price(),
            self._market_price_ref,
            self._type_section.get_order_type(),
        )

    def _amount_error_msg(self) -> str | None:
        """Error del monto: reglas base + sizing contra los filtros reales.

        El mínimo notional es POR SÍMBOLO (BTC≈50, SOL≈6, XRP≈5): se resuelve
        con effective_min_notional() — fallback al global 50 solo si los
        filtros del símbolo son desconocidos. Sin precio de referencia solo
        aplica esta regla de notional (graceful degradation); el cálculo por
        cantidad/minQty queda para cuando llega el tick.
        """
        amount = self._params_section.get_amount()
        trading_type = self._type_section.get_trading_type()
        base = validate_amount(
            amount,
            trading_type,
            min_notional=effective_min_notional(
                self._sizer.filters, trading_type,
            ),
        )
        if base is not None or self._market_price_ref <= 0:
            return base
        return self._sizer.size(amount, self._market_price_ref, trading_type).error

    def _validation_signature(self) -> tuple[str | None, str | None, str | None]:
        """Par de validez (precio límite, monto, fondos) — detecta cambios por evento."""
        return (
            self._limit_price_error_msg(),
            self._amount_error_msg(),
            self._balance_error_msg(),
        )

    def _balance_error_msg(self) -> str | None:
        """Error de fondos: saldo vs monto, con la regla de Binance
        (FUTURES valida margen = monto ÷ leverage vs availableBalance)."""
        bal = self._balance_ref
        return validate_funds(
            self._params_section.get_amount(),
            self._type_section.get_trading_type(),
            self._type_section.get_leverage(),
            free=bal.free if bal is not None else None,
            available=bal.available if bal is not None else None,
            mode=self._mode_section.get_mode(),
            asset=settings.TRADE_CURRENCY,
        )

    def _form_errors(self) -> tuple[str | None, str | None, str | None]:
        """Errores de validación: (monto, stop loss, temporalidad)."""
        return (
            self._amount_error_msg(),
            validate_stop_loss(
                self._params_section.get_sl(),
                self._params_section.get_sl_type(),
            ),
            validate_timeframe(self._params_section.get_timeframe()),
        )

    # ------------------------------------------------------------------
    # Validación de símbolo
    # ------------------------------------------------------------------
    def _on_symbol_changed_for_validation(self, symbol: str) -> None:
        # El precio anterior ya no corresponde al símbolo editado
        self._market_price_ref = 0.0
        self._update_save_button_state()
        asyncio.create_task(self._validate_current_symbol())
        asyncio.create_task(self._refresh_max_leverage())
        asyncio.create_task(self._refresh_market_reference())
        # Los filtros (minQty/stepSize) también son por símbolo
        asyncio.create_task(self._refresh_sizer())

    def _on_trading_type_changed_for_validation(self, trading_type: str) -> None:
        self._params_section.update_trading_type(trading_type)
        asyncio.create_task(self._validate_current_symbol())
        asyncio.create_task(self._refresh_max_leverage())
        # Spot y Futures aplican filtros distintos
        asyncio.create_task(self._refresh_sizer())

    def _on_currency_changed_for_reload(self, currency: str) -> None:
        if self._symbol_repository:
            self._symbol_repository.clear_cache()
        self._params_section.update_currency(currency)

    async def _validate_current_symbol(self) -> None:
        symbol = self._params_section.get_symbol()
        trading_type = self._type_section.get_trading_type()
        self._validation_indicator.set_status(
            SymbolValidationIndicator.VALIDATING, symbol, trading_type,
        )
        try:
            exists, symbols = await self._symbol_repository.validate_symbol(
                symbol, trading_type,
            )
            if exists:
                self._validation_indicator.set_status(
                    SymbolValidationIndicator.VALID, symbol, trading_type,
                )
            else:
                self._validation_indicator.set_status(
                    SymbolValidationIndicator.INVALID, symbol, trading_type, symbols,
                )
        except Exception:
            self._validation_indicator.set_status(SymbolValidationIndicator.ERROR)
        self._update_save_button_state()

    async def _refresh_max_leverage(self) -> None:
        """Consulta el leverage máximo de Binance para el símbolo actual
        y actualiza las opciones del dropdown."""
        if not self._symbol_repository:
            return
        symbol = self._params_section.get_symbol()
        trading_type = self._type_section.get_trading_type()
        try:
            max_lev = await self._symbol_repository.get_max_leverage(
                symbol, trading_type,
            )
            self._type_section.set_max_leverage(max_lev)
        except Exception:
            # Fallback silencioso — el dropdown mantiene sus opciones actuales
            pass

    # ------------------------------------------------------------------
    # Build form data
    # ------------------------------------------------------------------
    def _build_form_data(self) -> SettingsFormData:
        return SettingsFormData(
            symbol=self._params_section.get_symbol(),
            mode=self._mode_section.get_mode(),
            trading_type=self._type_section.get_trading_type(),
            leverage=self._type_section.get_leverage(),
            order_type=self._type_section.get_order_type(),
            limit_price=self._type_section.get_limit_price(),
            amount=self._params_section.get_amount(),
            currency=self._params_section.get_currency(),
            sl=self._params_section.get_sl(),
            sl_type=self._params_section.get_sl_type(),
            timeframe=self._params_section.get_timeframe(),
            tf_unit=self._params_section.get_tf_unit(),
        )

    def _update_settings_from_form(self, form: SettingsFormData) -> None:
        settings.reload_from_env()
        settings.from_dict({
            "trading_symbol": form.symbol,
            "trading_mode": form.mode,
            "trading_type": form.trading_type,
            "leverage": form.leverage,
            "order_type": form.order_type,
            "limit_price": form.limit_price,
            "trade_amount": form.amount,
            "trade_currency": form.currency,
            "stop_loss": form.sl,
            "stop_loss_type": form.sl_type,
            "timeframe": form.timeframe,
            "timeframe_unit": form.tf_unit,
        })

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_back(self, e: ft.ControlEvent) -> None:
        """Regresa a la vista de Configuración."""
        event_bus.publish(NavigateToEvent(index=2))

    def _on_save(self, e: ft.ControlEvent) -> None:
        if self._bot_active:
            self._show_bot_active_warning()
            return
        limit_msg = self._limit_price_error_msg()
        if limit_msg is not None:
            self._type_section.set_limit_price_error(limit_msg)
            return
        balance_msg = self._balance_error_msg()
        if balance_msg is not None:
            self._params_section.set_balance_error(balance_msg)
            return
        errors = self._form_errors()
        if any(errors):
            self._params_section.set_validation_errors(*errors)
            return
        form = self._build_form_data()
        changes = ConfirmDialogHelper.build_changes_summary(form)
        self._confirm_dialog = ConfirmDialogHelper.show(
            self.page, changes, self._on_confirm, self._on_cancel
        )

    def _on_cancel(self, e: ft.ControlEvent) -> None:
        ConfirmDialogHelper.close(self._confirm_dialog, self.page)

    async def _on_confirm(self, e: ft.ControlEvent) -> None:
        await self._apply_changes()

    async def _apply_changes(self) -> None:
        if self._confirm_dialog:
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
        form_snapshot = vars(form)

        try:
            await self._save_config_to_db(form)
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
            ))

            self._feedback_text.value = "✅ Configuración guardada. Reconectando..."
            self._feedback_text.color = ft.Colors.GREEN_400
            event_bus.publish(NavigateToEvent(index=0))

        except Exception as exc:
            settings.reload_from_env()
            self._restore_form_fields(form_snapshot)
            self._feedback_text.value = f"❌ Error: {exc}. Cambios revertidos."
            self._feedback_text.color = ft.Colors.RED_400

        finally:
            ConfirmDialogHelper.close(self._confirm_dialog, self.page)
            update_batcher.mark_dirty(self._feedback_text)

    async def _save_config_to_db(self, form: SettingsFormData) -> None:
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
        self._mode_section.restore(form_snapshot)
        self._type_section.restore(form_snapshot)
        self._params_section.restore(form_snapshot)
        self._update_save_button_state()

    def _show_bot_active_warning(self) -> None:
        """Muestra alerta de que el bot debe detenerse primero."""
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Bot Activo", color=ft.Colors.AMBER_400, size=15),
            bgcolor=ft.Colors.BLUE_GREY_900,
            content=ft.Text(
                "Detén el bot primero para cambiar configuración.",
                color=ft.Colors.BLUE_GREY_300,
            ),
            actions=[
                ft.TextButton(
                    "Entendido",
                    on_click=lambda e: self._close_warning_dialog(dialog),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        if self._page:
            self._page.overlay.append(dialog)
            update_batcher.mark_dirty(self._page)
            dialog.open = True
            update_batcher.mark_dirty(dialog)

    def _close_warning_dialog(self, dialog: ft.AlertDialog) -> None:
        """Cierra el modal de advertencia."""
        if dialog:
            dialog.open = False
            update_batcher.mark_dirty(dialog)
            if self._page and dialog in self._page.overlay:
                self._page.overlay.remove(dialog)
                update_batcher.mark_dirty(self._page)

    def refresh_symbols(self) -> None:
        self._params_section.refresh_symbols()
