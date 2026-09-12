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
from core.events import NavigateToEvent, SettingsUpdatedEvent
from services.settings_persistence import EnvSettingsPersistence
from ui.components.settings_sections import (
    ConfirmDialogHelper,
    OperationParamsSection,
    SettingsFormData,
    TradingModeSection,
    TradingTypeSection,
)


class SettingsView(ft.Column):
    """Pantalla de configuración del bot."""

    def __init__(self, persistence=None, symbol_repository=None) -> None:
        super().__init__()
        self._persistence = persistence or EnvSettingsPersistence()

        # --- Secciones ---
        self._mode_section = TradingModeSection(on_change=self._update_save_button_state)
        self._type_section = TradingTypeSection(on_change=self._update_save_button_state)
        self._params_section = OperationParamsSection(
            symbol_repository=symbol_repository,
            on_change=self._update_save_button_state,
        )

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

        # --- Layout ---
        self.controls = [
            ft.Text("Configuración", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE, text_align=ft.TextAlign.CENTER),
            ft.Container(width=380, content=ft.Divider(color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE), height=20)),
            self._mode_section,
            self._type_section,
            self._params_section,
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
        self._save_btn.disabled = not self._has_changes()
        try:
            self._save_btn.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Build form data
    # ------------------------------------------------------------------
    def _build_form_data(self) -> SettingsFormData:
        api_key, api_secret = self._mode_section.get_api_keys()
        return SettingsFormData(
            symbol=self._params_section.get_symbol(),
            mode=self._mode_section.get_mode(),
            trading_type=self._type_section.get_trading_type(),
            leverage=self._type_section.get_leverage(),
            order_type=self._type_section.get_order_type(),
            limit_price=self._type_section.get_limit_price(),
            api_key=api_key,
            api_secret=api_secret,
            amount=self._params_section.get_amount(),
            currency=self._params_section.get_currency(),
            sl=self._params_section.get_sl(),
            sl_type=self._params_section.get_sl_type(),
            timeframe=self._params_section.get_timeframe(),
            tf_unit=self._params_section.get_tf_unit(),
        )

    def _build_env_snapshot(self) -> dict:
        return {
            "BINANCE_API_KEY": settings.BINANCE_API_KEY,
            "BINANCE_API_SECRET": settings.BINANCE_API_SECRET,
        }

    def _update_settings_from_form(self, form: SettingsFormData) -> None:
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
    # Handlers
    # ------------------------------------------------------------------
    def _on_save(self, e: ft.ControlEvent) -> None:
        form = self._build_form_data()
        changes = ConfirmDialogHelper.build_changes_summary(form)
        self._confirm_dialog = ConfirmDialogHelper.show(
            self.page, changes, self._on_confirm, self._on_cancel
        )

    def _on_cancel(self, e: ft.ControlEvent) -> None:
        ConfirmDialogHelper.close(self._confirm_dialog, self.page)

    def _on_confirm(self, e: ft.ControlEvent) -> None:
        self._apply_changes()

    def _apply_changes(self) -> None:
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
        env_snapshot = self._build_env_snapshot()
        form_snapshot = vars(form)

        try:
            self._persistence.save_sensitive(form.api_key, form.api_secret)
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
            self._persistence.rollback(env_snapshot)
            settings.reload_from_env()
            self._restore_form_fields(form_snapshot)
            self._feedback_text.value = f"❌ Error: {exc}. Cambios revertidos."
            self._feedback_text.color = ft.Colors.RED_400

        finally:
            ConfirmDialogHelper.close(self._confirm_dialog, self.page)
            try:
                self._feedback_text.update()
            except RuntimeError:
                pass

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

    def refresh_symbols(self) -> None:
        self._params_section.refresh_symbols()
