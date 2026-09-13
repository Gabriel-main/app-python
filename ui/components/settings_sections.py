"""
SettingsSections — Secciones del formulario de configuración.

Extraído de SettingsView para aplicar SRP:
- TradingModeSection: Modo + API Keys + warning
- TradingTypeSection: Tipo + leverage + order type + limit price
- OperationParamsSection: Monto, moneda, símbolo, stop loss, temporalidad
- ConfirmDialogHelper: Modal de confirmación
"""
from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from config.settings import settings
from ui.components.symbol_picker import SymbolPicker


# ---------------------------------------------------------------------------
# Helper: Bloqueo de campos (DRY)
# ---------------------------------------------------------------------------
def _set_fields_disabled(section: ft.Container, disabled: bool) -> None:
    """Deshabilita/habilita todos los campos editables de una sección."""
    def _walk(control):
        if hasattr(control, 'disabled'):
            control.disabled = disabled
        if hasattr(control, 'controls'):
            for child in control.controls:
                _walk(child)
        if hasattr(control, 'content') and control.content:
            _walk(control.content)
    _walk(section)


# ---------------------------------------------------------------------------
# Indicador de validación de símbolo (SRP: solo muestra estado)
# ---------------------------------------------------------------------------
class SymbolValidationIndicator(ft.Row):
    """Muestra el resultado de validar un símbolo en el mercado seleccionado."""

    IDLE = "idle"
    VALIDATING = "validating"
    VALID = "valid"
    INVALID = "invalid"
    ERROR = "error"

    def __init__(self) -> None:
        self._icon = ft.Icon(
            ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN_400, size=16,
        )
        self._text = ft.Text("", size=12)
        super().__init__(
            controls=[self._icon, self._text], spacing=4, visible=False,
        )

    def set_status(
        self,
        status: str,
        symbol: str = "",
        trading_type: str = "",
        available: list[str] | None = None,
    ) -> None:
        if status == self.VALIDATING:
            self._icon.name = ft.Icons.HOURGLASS_EMPTY
            self._icon.color = ft.Colors.GREY_400
            self._text.value = f"Verificando {symbol}..."
            self.visible = True
        elif status == self.VALID:
            self._icon.name = ft.Icons.CHECK_CIRCLE
            self._icon.color = ft.Colors.GREEN_400
            self._text.value = f"{symbol} existe en {trading_type}"
            self.visible = True
        elif status == self.INVALID:
            self._icon.name = ft.Icons.CANCEL
            self._icon.color = ft.Colors.RED_400
            examples = ", ".join(available[:5]) if available else "BTCUSDT, ETHUSDT..."
            self._text.value = (
                f"{symbol} no existe en {trading_type}. Prueba: {examples}"
            )
            self.visible = True
        elif status == self.ERROR:
            self._icon.name = ft.Icons.WARNING
            self._icon.color = ft.Colors.AMBER_400
            self._text.value = "No se pudo validar. Conéctate a internet."
            self.visible = True
        else:
            self.visible = False
        try:
            self.update()
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# DTO
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Estilos comunes de campo
# ---------------------------------------------------------------------------
_FIELD_STYLE = dict(
    bgcolor=ft.Colors.GREY_900,
    border_color=ft.Colors.BLUE_GREY_700,
    color=ft.Colors.WHITE,
    label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
)


def _dropdown(
    label: str,
    value: str,
    options: list[ft.DropdownOption],
    focused_color: ft.Color,
    on_select=None,
    width: int | None = None,
    visible: bool = True,
) -> ft.Dropdown:
    return ft.Dropdown(
        label=label,
        value=value,
        options=options,
        focused_border_color=focused_color,
        width=width,
        visible=visible,
        on_select=on_select,
        **_FIELD_STYLE,
    )


def _textfield(
    label: str,
    value: str,
    focused_color: ft.Color,
    hint_text: str = "",
    prefix_icon: str | None = None,
    keyboard_type=None,
    password: bool = False,
    expand: bool = False,
    width: int | None = None,
    visible: bool = True,
    on_change=None,
) -> ft.TextField:
    kwargs = dict(
        label=label,
        value=value,
        hint_text=hint_text,
        focused_border_color=focused_color,
        expand=expand,
        width=width,
        visible=visible,
        on_change=on_change,
        **_FIELD_STYLE,
    )
    if prefix_icon:
        kwargs["prefix_icon"] = prefix_icon
    if keyboard_type:
        kwargs["keyboard_type"] = keyboard_type
    if password:
        kwargs["password"] = True
        kwargs["can_reveal_password"] = True
    return ft.TextField(**kwargs)


# ---------------------------------------------------------------------------
# Section: Trading Mode
# ---------------------------------------------------------------------------
class TradingModeSection(ft.Container):
    """Sección: Modo de operación + API Keys + warning."""

    def __init__(self, on_change=None) -> None:
        super().__init__()
        self._on_change = on_change

        self._mode_dropdown = _dropdown(
            label="Modo de Operación",
            value=settings.TRADING_MODE,
            options=[
                ft.DropdownOption(key="PAPER", text="📄 Paper Trading (Simulado)"),
                ft.DropdownOption(key="LIVE", text="⚡ Live Trading (Real)"),
            ],
            focused_color=ft.Colors.AMBER_400,
            on_select=self._on_mode_changed,
        )

        self._api_key_field = _textfield(
            label="Binance API Key",
            value=settings.BINANCE_API_KEY,
            focused_color=ft.Colors.AMBER_400,
            password=True,
            prefix_icon=ft.Icons.KEY,
            visible=settings.TRADING_MODE == "LIVE",
            on_change=self._notify_change,
        )

        self._api_secret_field = _textfield(
            label="Binance API Secret",
            value=settings.BINANCE_API_SECRET,
            focused_color=ft.Colors.AMBER_400,
            password=True,
            prefix_icon=ft.Icons.LOCK,
            visible=settings.TRADING_MODE == "LIVE",
            on_change=self._notify_change,
        )

        self._live_warning = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.WARNING_AMBER, color=ft.Colors.AMBER_400, size=16),
                    ft.Text(
                        "Live Mode ejecuta órdenes reales en Binance.\nÚsalo con responsabilidad.",
                        size=12, color=ft.Colors.AMBER_300,
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

        self.bgcolor = ft.Colors.BLUE_GREY_900
        self.border_radius = 14
        self.padding = ft.Padding.all(16)
        self.width = 380
        self.content = ft.Column(
            controls=[
                ft.Text("⚙️ Modo de Operación", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                self._mode_dropdown,
                self._live_warning,
                self._api_key_field,
                self._api_secret_field,
            ],
            spacing=12,
        )

    def _on_mode_changed(self, e: ft.ControlEvent) -> None:
        is_live = e.control.value == "LIVE"
        self._api_key_field.visible = is_live
        self._api_secret_field.visible = is_live
        self._live_warning.visible = is_live
        try:
            self._api_key_field.update()
            self._api_secret_field.update()
            self._live_warning.update()
        except RuntimeError:
            pass
        self._notify_change()

    def _notify_change(self, *args) -> None:
        if self._on_change:
            self._on_change()

    def get_mode(self) -> str:
        return self._mode_dropdown.value or "PAPER"

    def get_api_keys(self) -> tuple[str, str]:
        return (self._api_key_field.value or "", self._api_secret_field.value or "")

    def restore(self, form_snapshot: dict) -> None:
        self._mode_dropdown.value = form_snapshot["mode"]
        self._api_key_field.value = form_snapshot["api_key"]
        self._api_secret_field.value = form_snapshot["api_secret"]
        is_live = form_snapshot["mode"] == "LIVE"
        self._api_key_field.visible = is_live
        self._api_secret_field.visible = is_live
        self._live_warning.visible = is_live

    def set_disabled(self, disabled: bool) -> None:
        """Bloquea/desbloquea los campos de esta sección."""
        _set_fields_disabled(self, disabled)
        try:
            self.update()
        except RuntimeError:
            pass

    def sync_from_settings(self) -> None:
        """Re-sincroniza widgets desde el settings singleton."""
        self.restore({
            "mode": settings.TRADING_MODE,
            "api_key": settings.BINANCE_API_KEY,
            "api_secret": settings.BINANCE_API_SECRET,
        })
        try:
            self.update()
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Section: Trading Type
# ---------------------------------------------------------------------------
class TradingTypeSection(ft.Container):
    """Sección: Tipo de trading + leverage + order type + limit price."""

    def __init__(self, on_change=None, on_type_changed=None) -> None:
        super().__init__()
        self._on_change = on_change
        self._on_type_changed = on_type_changed

        self._trading_type_dropdown = _dropdown(
            label="Tipo de Trading",
            value=settings.TRADING_TYPE,
            options=[
                ft.DropdownOption(key="SPOT", text="💰 Spot"),
                ft.DropdownOption(key="FUTURES", text="📈 Futures (USDT-M)"),
                ft.DropdownOption(key="MARGIN", text="🔄 Cross Margin"),
            ],
            focused_color=ft.Colors.PURPLE_400,
            on_select=self._on_trading_type_changed,
        )

        leverage_options = [ft.DropdownOption(key=str(i), text=f"{i}x") for i in [1, 2, 3, 5, 10, 15, 20]]
        self._leverage_dropdown = _dropdown(
            label="Leverage",
            value=str(settings.LEVERAGE),
            options=leverage_options,
            focused_color=ft.Colors.PURPLE_400,
            visible=settings.TRADING_TYPE in ("FUTURES", "MARGIN"),
        )

        self._order_type_dropdown = _dropdown(
            label="Tipo de Orden",
            value=settings.ORDER_TYPE,
            options=[
                ft.DropdownOption(key="MARKET", text="⚡ Market (Inmediata)"),
                ft.DropdownOption(key="LIMIT", text="🎯 Limit (Con precio)"),
            ],
            focused_color=ft.Colors.CYAN_400,
            on_select=self._on_order_type_changed,
        )

        self._limit_price_field = _textfield(
            label="Precio Límite",
            value=str(settings.LIMIT_PRICE) if settings.LIMIT_PRICE > 0 else "",
            focused_color=ft.Colors.CYAN_400,
            hint_text="Ej: 65000.00",
            prefix_icon=ft.Icons.ATTACH_MONEY,
            keyboard_type=ft.KeyboardType.NUMBER,
            visible=settings.ORDER_TYPE == "LIMIT",
            on_change=self._notify_change,
        )

        self.bgcolor = ft.Colors.BLUE_GREY_900
        self.border_radius = 14
        self.padding = ft.Padding.all(16)
        self.width = 380
        self.content = ft.Column(
            controls=[
                ft.Text("🔄 Tipo de Trading", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                self._trading_type_dropdown,
                self._leverage_dropdown,
                self._order_type_dropdown,
                self._limit_price_field,
                ft.Text("Futures/Margin permiten leverage y posiciones long/short.", size=11, color=ft.Colors.BLUE_GREY_400),
            ],
            spacing=12,
        )

    def _on_trading_type_changed(self, e: ft.ControlEvent) -> None:
        show_leverage = e.control.value in ("FUTURES", "MARGIN")
        self._leverage_dropdown.visible = show_leverage
        try:
            self._leverage_dropdown.update()
        except RuntimeError:
            pass
        self._notify_change()
        if self._on_type_changed:
            self._on_type_changed(e.control.value)

    def _on_order_type_changed(self, e: ft.ControlEvent) -> None:
        is_limit = e.control.value == "LIMIT"
        self._limit_price_field.visible = is_limit
        try:
            self._limit_price_field.update()
        except RuntimeError:
            pass
        self._notify_change()

    def _notify_change(self, *args) -> None:
        if self._on_change:
            self._on_change()

    def get_trading_type(self) -> str:
        return self._trading_type_dropdown.value or "SPOT"

    def get_leverage(self) -> int:
        return int(self._leverage_dropdown.value or "1")

    def get_order_type(self) -> str:
        return self._order_type_dropdown.value or "MARKET"

    def get_limit_price(self) -> float:
        return float(self._limit_price_field.value or "0")

    def restore(self, form_snapshot: dict) -> None:
        self._trading_type_dropdown.value = form_snapshot["trading_type"]
        self._leverage_dropdown.value = str(form_snapshot["leverage"])
        self._order_type_dropdown.value = form_snapshot["order_type"]
        self._limit_price_field.value = str(form_snapshot["limit_price"])
        show_leverage = form_snapshot["trading_type"] in ("FUTURES", "MARGIN")
        self._leverage_dropdown.visible = show_leverage
        is_limit = form_snapshot["order_type"] == "LIMIT"
        self._limit_price_field.visible = is_limit

    def set_disabled(self, disabled: bool) -> None:
        """Bloquea/desbloquea los campos de esta sección."""
        _set_fields_disabled(self, disabled)
        try:
            self.update()
        except RuntimeError:
            pass

    def sync_from_settings(self) -> None:
        """Re-sincroniza widgets desde el settings singleton."""
        self.restore({
            "trading_type": settings.TRADING_TYPE,
            "leverage": settings.LEVERAGE,
            "order_type": settings.ORDER_TYPE,
            "limit_price": settings.LIMIT_PRICE,
        })
        try:
            self.update()
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Section: Operation Parameters
# ---------------------------------------------------------------------------
class OperationParamsSection(ft.Container):
    """Sección: Monto, moneda, símbolo, stop loss, temporalidad."""

    def __init__(
        self,
        symbol_repository=None,
        on_change=None,
        on_symbol_changed_for_validation=None,
        on_currency_changed_for_reload=None,
    ) -> None:
        super().__init__()
        self._on_change = on_change
        self._on_symbol_changed_for_validation = on_symbol_changed_for_validation
        self._on_currency_changed_for_reload = on_currency_changed_for_reload

        self._amount_field = _textfield(
            label="Monto",
            value=str(settings.TRADE_AMOUNT),
            focused_color=ft.Colors.CYAN_400,
            hint_text="10.0",
            prefix_icon=ft.Icons.ATTACH_MONEY,
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
            on_change=self._notify_change,
        )

        self._currency_dropdown = _dropdown(
            label="Moneda",
            value=settings.TRADE_CURRENCY,
            options=[
                ft.DropdownOption(key="USDT", text="USDT"),
                ft.DropdownOption(key="USDC", text="USDC"),
            ],
            focused_color=ft.Colors.CYAN_400,
            width=120,
            on_select=self._on_currency_changed,
        )

        self._symbol_picker = SymbolPicker(
            on_symbol_changed=self._on_symbol_changed,
            symbol_repository=symbol_repository,
        )

        self._sl_field = _textfield(
            label="Stop Loss",
            value=str(settings.STOP_LOSS),
            focused_color=ft.Colors.RED_400,
            hint_text="1.01",
            prefix_icon=ft.Icons.TRENDING_DOWN,
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
            on_change=self._notify_change,
        )

        self._sl_type_dropdown = _dropdown(
            label="Tipo SL",
            value=settings.STOP_LOSS_TYPE,
            options=[
                ft.DropdownOption(key="PERCENT", text="%"),
                ft.DropdownOption(key="USDT", text="USDT"),
            ],
            focused_color=ft.Colors.RED_400,
            width=100,
            on_select=self._notify_change,
        )

        self._timeframe_field = _textfield(
            label="Temporalidad",
            value=str(settings.TIMEFRAME),
            focused_color=ft.Colors.AMBER_400,
            hint_text="1",
            prefix_icon=ft.Icons.TIMER,
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
            on_change=self._notify_change,
        )

        self._timeframe_unit_dropdown = _dropdown(
            label="Unidad",
            value=settings.TIMEFRAME_UNIT,
            options=[
                ft.DropdownOption(key="MINUTES", text="Min"),
                ft.DropdownOption(key="HOURS", text="Horas"),
            ],
            focused_color=ft.Colors.AMBER_400,
            width=100,
            on_select=self._notify_change,
        )

        self.bgcolor = ft.Colors.BLUE_GREY_900
        self.border_radius = 14
        self.padding = ft.Padding.all(16)
        self.width = 380
        self.content = ft.Column(
            controls=[
                ft.Text("📋 Parámetros", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                ft.Row(controls=[self._amount_field, self._currency_dropdown], spacing=8),
                self._symbol_picker,
                ft.Row(controls=[self._sl_field, self._sl_type_dropdown], spacing=8),
                ft.Row(controls=[self._timeframe_field, self._timeframe_unit_dropdown], spacing=8),
            ],
            spacing=12,
        )

    def _on_symbol_changed(self, symbol: str) -> None:
        self._notify_change()
        if self._on_symbol_changed_for_validation:
            self._on_symbol_changed_for_validation(symbol)

    def _on_currency_changed(self, e: ft.ControlEvent) -> None:
        self._notify_change()
        if self._on_currency_changed_for_reload:
            self._on_currency_changed_for_reload(e.control.value)

    def _notify_change(self, *args) -> None:
        if self._on_change:
            self._on_change()

    def get_symbol(self) -> str:
        return self._symbol_picker.get_selected_symbol()

    def get_amount(self) -> float:
        return float(self._amount_field.value or "10.0")

    def get_currency(self) -> str:
        return self._currency_dropdown.value or "USDT"

    def get_sl(self) -> float:
        return float(self._sl_field.value or "1.01")

    def get_sl_type(self) -> str:
        return self._sl_type_dropdown.value or "PERCENT"

    def get_timeframe(self) -> int:
        return int(self._timeframe_field.value or "1")

    def get_tf_unit(self) -> str:
        return self._timeframe_unit_dropdown.value or "MINUTES"

    def refresh_symbols(self) -> None:
        self._symbol_picker.refresh_symbols()

    def update_trading_type(self, trading_type: str) -> None:
        """Notifica al SymbolPicker que el mercado cambió."""
        self._symbol_picker.set_trading_type(trading_type)

    def update_currency(self, currency: str) -> None:
        """Notifica al SymbolPicker que la moneda cambió."""
        self._symbol_picker.set_currency(currency)

    def restore(self, form_snapshot: dict) -> None:
        self._amount_field.value = str(form_snapshot["amount"])
        self._currency_dropdown.value = form_snapshot["currency"]
        self._sl_field.value = str(form_snapshot["sl"])
        self._sl_type_dropdown.value = form_snapshot["sl_type"]
        self._timeframe_field.value = str(form_snapshot["timeframe"])
        self._timeframe_unit_dropdown.value = form_snapshot["tf_unit"]

    def set_disabled(self, disabled: bool) -> None:
        """Bloquea/desbloquea los campos de esta sección."""
        _set_fields_disabled(self, disabled)
        try:
            self.update()
        except RuntimeError:
            pass

    def sync_from_settings(self) -> None:
        """Re-sincroniza widgets desde el settings singleton."""
        self.restore({
            "amount": settings.TRADE_AMOUNT,
            "currency": settings.TRADE_CURRENCY,
            "sl": settings.STOP_LOSS,
            "sl_type": settings.STOP_LOSS_TYPE,
            "timeframe": settings.TIMEFRAME,
            "tf_unit": settings.TIMEFRAME_UNIT,
        })
        self._symbol_picker.set_symbol(settings.TRADING_SYMBOL)
        try:
            self.update()
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Helper: Confirm Dialog
# ---------------------------------------------------------------------------
class ConfirmDialogHelper:
    """Helper para modal de confirmación de settings."""

    @staticmethod
    def build_changes_summary(form: SettingsFormData) -> list[str]:
        """Construye resumen de cambios entre formulario y settings actuales."""
        changes = []
        if form.symbol != settings.TRADING_SYMBOL:
            changes.append(f"Símbolo: {settings.TRADING_SYMBOL} → {form.symbol}")
        if form.mode != settings.TRADING_MODE:
            changes.append(f"Modo: {settings.TRADING_MODE} → {form.mode}")
        if form.trading_type != settings.TRADING_TYPE:
            changes.append(f"Tipo: {settings.TRADING_TYPE} → {form.trading_type}")
        if form.leverage != settings.LEVERAGE:
            changes.append(f"Leverage: {settings.LEVERAGE}x → {form.leverage}x")
        if form.order_type != settings.ORDER_TYPE:
            changes.append(f"Orden: {settings.ORDER_TYPE} → {form.order_type}")
        if form.limit_price != settings.LIMIT_PRICE and settings.ORDER_TYPE == "LIMIT":
            changes.append(f"Precio Límite: ${settings.LIMIT_PRICE} → ${form.limit_price}")
        if form.amount != settings.TRADE_AMOUNT:
            changes.append(f"Monto: ${settings.TRADE_AMOUNT} → ${form.amount}")
        if form.currency != settings.TRADE_CURRENCY:
            changes.append(f"Moneda: {settings.TRADE_CURRENCY} → {form.currency}")
        if form.sl != settings.STOP_LOSS:
            changes.append(f"Stop Loss: {settings.STOP_LOSS} → {form.sl}")
        if form.sl_type != settings.STOP_LOSS_TYPE:
            changes.append(f"Tipo SL: {settings.STOP_LOSS_TYPE} → {form.sl_type}")
        if form.timeframe != settings.TIMEFRAME:
            changes.append(f"Temporalidad: {settings.TIMEFRAME} → {form.timeframe}")
        if form.tf_unit != settings.TIMEFRAME_UNIT:
            changes.append(f"Unidad: {settings.TIMEFRAME_UNIT} → {form.tf_unit}")
        if not changes:
            changes.append("No hay cambios detectados")
        return changes

    @staticmethod
    def show(page: ft.Page, changes: list[str], on_confirm, on_cancel) -> ft.AlertDialog:
        """Crea y muestra el modal de confirmación."""
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar Cambios", color=ft.Colors.WHITE, size=15),
            bgcolor=ft.Colors.BLUE_GREY_900,
            content=ft.Column(
                controls=[
                    ft.Text("Se aplicarán los siguientes cambios:", color=ft.Colors.BLUE_GREY_300),
                    ft.Container(height=8),
                    *[ft.Text(f"• {c}", color=ft.Colors.WHITE, size=13) for c in changes],
                    ft.Container(height=8),
                    ft.Text("El servicio se reconectará.", size=11, color=ft.Colors.AMBER_400),
                ],
                spacing=0,
                width=300,
                height=150,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=on_cancel),
                ft.FilledButton(
                    "Confirmar",
                    on_click=on_confirm,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_800, color=ft.Colors.WHITE),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            inset_padding=ft.Padding.all(12),
        )
        page.overlay.append(dialog)
        page.update()
        dialog.open = True
        dialog.update()
        return dialog

    @staticmethod
    def close(dialog: ft.AlertDialog, page: ft.Page) -> None:
        """Cierra el modal."""
        if dialog:
            dialog.open = False
            dialog.update()
            if dialog in page.overlay:
                page.overlay.remove(dialog)
