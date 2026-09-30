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
from core.update_batcher import update_batcher
from services.trading_rules import MIN_FUTURES_NOTIONAL, validate_amount
from ui.components.api_key_manager import ApiKeyManager
from ui.components.symbol_picker import SymbolPicker

# Pasos disponibles para el dropdown de leverage (filtrados por max de Binance)
_LEVERAGE_STEPS: list[int] = [
    1, 2, 3, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 125, 150,
]

# Máximo de ítems visibles en el menú del dropdown antes de hacer scroll
_LEVERAGE_VISIBLE: int = 5
# Alto fijo de cada ítem (px) — hace determinista la cuenta de ítems visibles
_LEVERAGE_ITEM_H: int = 44


def _leverage_options(values: list[int]) -> list[ft.DropdownOption]:
    """Construye las opciones del dropdown de leverage con alto fijo por ítem.

    Conserva `text` (lo muestra el campo colapsado) y agrega `content`
    con altura fija para que menu_height = N * _LEVERAGE_ITEM_H sea exacto.
    """
    return [
        ft.DropdownOption(
            key=str(v),
            text=f"{v}x",
            content=ft.Container(
                content=ft.Text(f"{v}x"),
                height=_LEVERAGE_ITEM_H,
                alignment=ft.Alignment.CENTER_LEFT,
                padding=ft.Padding.symmetric(vertical=0, horizontal=16),
            ),
        )
        for v in values
    ]


def _leverage_menu_height(count: int) -> int:
    """Alta del menú: muestra hasta _LEVERAGE_VISIBLE ítems y scrollea el resto."""
    return min(count, _LEVERAGE_VISIBLE) * _LEVERAGE_ITEM_H


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
        update_batcher.mark_dirty(self)


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
    menu_height: int | None = None,
) -> ft.Dropdown:
    return ft.Dropdown(
        label=label,
        value=value,
        options=options,
        focused_border_color=focused_color,
        width=width,
        visible=visible,
        on_select=on_select,
        menu_height=menu_height,
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
    reveal_password: bool = True,
    expand: bool = False,
    width: int | None = None,
    visible: bool = True,
    disabled: bool = False,
    read_only: bool = False,
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
        disabled=disabled,
        read_only=read_only,
        on_change=on_change,
        **_FIELD_STYLE,
    )
    if prefix_icon:
        kwargs["prefix_icon"] = prefix_icon
    if keyboard_type:
        kwargs["keyboard_type"] = keyboard_type
    if password:
        kwargs["password"] = True
        kwargs["can_reveal_password"] = reveal_password
    return ft.TextField(**kwargs)


# ---------------------------------------------------------------------------
# Section: Trading Mode
# ---------------------------------------------------------------------------
class TradingModeSection(ft.Container):
    """Sección: Modo de operación + API Keys (solo lectura) + warning."""

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
            value=ApiKeyManager.mask_key(settings.BINANCE_API_KEY),
            focused_color=ft.Colors.AMBER_400,
            password=True,
            reveal_password=False,
            prefix_icon=ft.Icons.KEY,
            visible=settings.TRADING_MODE == "LIVE",
            disabled=True,
            read_only=True,
        )

        self._api_secret_field = _textfield(
            label="Binance API Secret",
            value=ApiKeyManager.mask_key(settings.BINANCE_API_SECRET),
            focused_color=ft.Colors.AMBER_400,
            password=True,
            reveal_password=False,
            prefix_icon=ft.Icons.LOCK,
            visible=settings.TRADING_MODE == "LIVE",
            disabled=True,
            read_only=True,
        )

        self._api_info_text = ApiKeyManager.get_info_text()
        self._api_info_text.visible = settings.TRADING_MODE == "LIVE"

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
                self._api_info_text,
            ],
            spacing=12,
        )

    def _on_mode_changed(self, e: ft.ControlEvent) -> None:
        is_live = e.control.value == "LIVE"
        self._api_key_field.visible = is_live
        self._api_secret_field.visible = is_live
        self._api_info_text.visible = is_live
        self._live_warning.visible = is_live
        update_batcher.mark_dirty(self._api_key_field)
        update_batcher.mark_dirty(self._api_secret_field)
        update_batcher.mark_dirty(self._api_info_text)
        update_batcher.mark_dirty(self._live_warning)
        self._notify_change()

    def _notify_change(self, *args) -> None:
        if self._on_change:
            self._on_change()

    def get_mode(self) -> str:
        return self._mode_dropdown.value or "PAPER"

    def restore(self, form_snapshot: dict) -> None:
        self._mode_dropdown.value = form_snapshot["mode"]
        is_live = form_snapshot["mode"] == "LIVE"
        self._api_key_field.visible = is_live
        self._api_secret_field.visible = is_live
        self._api_info_text.visible = is_live
        self._live_warning.visible = is_live

    def set_disabled(self, disabled: bool) -> None:
        """Bloquea/desbloquea los campos de esta sección."""
        _set_fields_disabled(self, disabled)
        update_batcher.mark_dirty(self)

    def sync_from_settings(self) -> None:
        """Re-sincroniza widgets desde el settings singleton."""
        self.restore({
            "mode": settings.TRADING_MODE,
        })
        update_batcher.mark_dirty(self)


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

        leverage_options = _leverage_options(
            [i for i in _LEVERAGE_STEPS if i <= 20]  # default hasta 20x (amplía set_max_leverage)
        )
        self._leverage_dropdown = _dropdown(
            label="Leverage",
            value=str(settings.LEVERAGE),
            options=leverage_options,
            focused_color=ft.Colors.PURPLE_400,
            visible=settings.TRADING_TYPE in ("FUTURES", "MARGIN"),
            menu_height=_leverage_menu_height(len(leverage_options)),
        )
        self._max_lev_label = ft.Text(
            "",
            size=11,
            color=ft.Colors.BLUE_GREY_400,
            visible=False,
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

        self._limit_price_hint = ft.Text(
            "Entrada a precio fijo: solo se ejecuta si el mercado llega a este "
            "precio; si no, queda pendiente hasta cancelar el bot o cambiar ajustes.",
            size=11,
            italic=True,
            color=ft.Colors.BLUE_GREY_400,
            visible=settings.ORDER_TYPE == "LIMIT",
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
                self._max_lev_label,
                self._order_type_dropdown,
                self._limit_price_field,
                self._limit_price_hint,
                ft.Text("Futures/Margin permiten leverage y posiciones long/short.", size=11, color=ft.Colors.BLUE_GREY_400),
            ],
            spacing=12,
        )

    def _on_trading_type_changed(self, e: ft.ControlEvent) -> None:
        show_leverage = e.control.value in ("FUTURES", "MARGIN")
        self._leverage_dropdown.visible = show_leverage
        update_batcher.mark_dirty(self._leverage_dropdown)
        self._notify_change()
        if self._on_type_changed:
            self._on_type_changed(e.control.value)

    def _on_order_type_changed(self, e: ft.ControlEvent) -> None:
        is_limit = e.control.value == "LIMIT"
        self._limit_price_field.visible = is_limit
        self._limit_price_hint.visible = is_limit
        update_batcher.mark_dirty(self._limit_price_field)
        update_batcher.mark_dirty(self._limit_price_hint)
        self._notify_change()

    def _notify_change(self, *args) -> None:
        if self._on_change:
            self._on_change()

    def get_trading_type(self) -> str:
        return self._trading_type_dropdown.value or "SPOT"

    def get_leverage(self) -> int:
        return int(self._leverage_dropdown.value or "1")

    def set_max_leverage(self, max_leverage: int) -> None:
        """Actualiza las opciones del dropdown según el máximo de Binance.

        Filtra _LEVERAGE_STEPS a los valores <= max_leverage.
        Si el valor actual supera el nuevo máximo, baja al mayor permitido.
        """
        steps = [i for i in _LEVERAGE_STEPS if i <= max_leverage]
        if not steps:
            steps = [1]

        options = _leverage_options(steps)
        self._leverage_dropdown.options = options
        self._leverage_dropdown.menu_height = _leverage_menu_height(len(options))

        current = int(self._leverage_dropdown.value or "1")
        if current > max_leverage:
            self._leverage_dropdown.value = str(steps[-1])

        # Label indicativo del máximo
        trading_type = self._trading_type_dropdown.value or "SPOT"
        if trading_type in ("FUTURES", "MARGIN"):
            self._max_lev_label.value = f"Máximo permitido: {max_leverage}x"
            self._max_lev_label.visible = True
        else:
            self._max_lev_label.visible = False

        update_batcher.mark_dirty(self._leverage_dropdown)
        update_batcher.mark_dirty(self._max_lev_label)

    def get_order_type(self) -> str:
        return self._order_type_dropdown.value or "MARKET"

    def get_limit_price(self) -> float:
        """Precio límite parseado de forma segura (texto vacío/inválido → 0.0)."""
        try:
            return float(self._limit_price_field.value or "0")
        except (TypeError, ValueError):
            return 0.0

    def restore(self, form_snapshot: dict) -> None:
        self._trading_type_dropdown.value = form_snapshot["trading_type"]
        self._leverage_dropdown.value = str(form_snapshot["leverage"])
        self._order_type_dropdown.value = form_snapshot["order_type"]
        self._limit_price_field.value = str(form_snapshot["limit_price"])
        show_leverage = form_snapshot["trading_type"] in ("FUTURES", "MARGIN")
        self._leverage_dropdown.visible = show_leverage
        is_limit = form_snapshot["order_type"] == "LIMIT"
        self._limit_price_field.visible = is_limit
        self._limit_price_hint.visible = is_limit

    def set_disabled(self, disabled: bool) -> None:
        """Bloquea/desbloquea los campos de esta sección."""
        _set_fields_disabled(self, disabled)
        update_batcher.mark_dirty(self)

    def sync_from_settings(self) -> None:
        """Re-sincroniza widgets desde el settings singleton."""
        self.restore({
            "trading_type": settings.TRADING_TYPE,
            "leverage": settings.LEVERAGE,
            "order_type": settings.ORDER_TYPE,
            "limit_price": settings.LIMIT_PRICE,
        })
        update_batcher.mark_dirty(self)


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

        # --- Mensajes de error de validación (inline, bajo cada campo) ---
        self._amount_error = ft.Text(
            "", size=11, color=ft.Colors.RED_400, visible=False,
        )
        self._sl_error = ft.Text(
            "", size=11, color=ft.Colors.RED_400, visible=False,
        )
        self._timeframe_error = ft.Text(
            "", size=11, color=ft.Colors.RED_400, visible=False,
        )

        self.bgcolor = ft.Colors.BLUE_GREY_900
        self.border_radius = 14
        self.padding = ft.Padding.all(16)
        self.width = 380
        self.content = ft.Column(
            controls=[
                ft.Text("📋 Parámetros", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                ft.Row(controls=[self._amount_field, self._currency_dropdown], spacing=8),
                self._amount_error,
                self._symbol_picker,
                ft.Row(controls=[self._sl_field, self._sl_type_dropdown], spacing=8),
                self._sl_error,
                ft.Row(controls=[self._timeframe_field, self._timeframe_unit_dropdown], spacing=8),
                self._timeframe_error,
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
        """Monto parseado de forma segura (texto vacío/inválido → 0.0)."""
        try:
            return float(self._amount_field.value or "0")
        except (TypeError, ValueError):
            return 0.0

    def get_currency(self) -> str:
        return self._currency_dropdown.value or "USDT"

    def get_sl(self) -> float:
        """Stop Loss parseado de forma segura (texto vacío/inválido → 0.0)."""
        try:
            return float(self._sl_field.value or "0")
        except (TypeError, ValueError):
            return 0.0

    def get_sl_type(self) -> str:
        return self._sl_type_dropdown.value or "PERCENT"

    def get_timeframe(self) -> int:
        """Temporalidad parseada de forma segura (vacío/inválido → 0)."""
        try:
            return int(float(self._timeframe_field.value or "0"))
        except (TypeError, ValueError):
            return 0

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
        update_batcher.mark_dirty(self)

    def set_validation_errors(
        self,
        amount: str | None,
        stop_loss: str | None,
        timeframe: str | None,
    ) -> None:
        """Muestra/oculta los mensajes de error inline (None = oculto)."""
        for control, message in (
            (self._amount_error, amount),
            (self._sl_error, stop_loss),
            (self._timeframe_error, timeframe),
        ):
            control.value = message or ""
            control.visible = message is not None
            update_batcher.mark_dirty(control)

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
        update_batcher.mark_dirty(self)


# ---------------------------------------------------------------------------
# Helpers: Validaciones del formulario (puros y testeables)
# ---------------------------------------------------------------------------
# SRP: `validate_amount` y `MIN_FUTURES_NOTIONAL` viven en
# services/trading_rules (fuente única, compartida con BotEngine — DRY) y se
# re-exportan desde aquí para no romper los imports existentes.


def validate_stop_loss(sl: float, sl_type: str) -> str | None:
    """Valida el stop loss. Retorna mensaje de error o None."""
    if sl <= 0:
        return "El Stop Loss debe ser mayor a 0."
    if sl_type == "PERCENT" and sl > 100:
        return "Con tipo %, el Stop Loss debe estar entre 0 y 100."
    return None


def validate_timeframe(tf: int) -> str | None:
    """Valida la temporalidad. Retorna mensaje de error o None."""
    if tf < 1:
        return "La temporalidad debe ser al menos 1."
    return None


# Desviación máxima permitida entre LIMIT_PRICE y el precio de mercado.
# El mismo precio alimenta las entradas BUY y SELL, así que solo un precio
# cercano al mercado es alcanzable en ambas direcciones.
LIMIT_PRICE_MAX_DEVIATION_PCT: float = 5.0


def validate_limit_price(
    limit_price: float, reference_price: float, order_type: str,
) -> str | None:
    """Valida el precio límite contra el mercado. Retorna mensaje o None."""
    if order_type != "LIMIT":
        return None
    if limit_price <= 0:
        return "El precio límite debe ser mayor a 0."
    if reference_price <= 0:
        # Sin precio de referencia todavía: solo aplica la regla > 0
        return None
    deviation = abs(limit_price - reference_price) / reference_price * 100.0
    if deviation > LIMIT_PRICE_MAX_DEVIATION_PCT:
        return (
            f"El precio límite (${limit_price:,.4f}) está a {deviation:.1f}% del "
            f"mercado (${reference_price:,.4f}). Debe estar dentro de "
            f"{LIMIT_PRICE_MAX_DEVIATION_PCT:g}% para que la orden pueda llenarse."
        )
    return None


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
        if form.limit_price != settings.LIMIT_PRICE and form.order_type == "LIMIT":
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
        update_batcher.mark_dirty(page)
        dialog.open = True
        update_batcher.mark_dirty(dialog)
        return dialog

    @staticmethod
    def close(dialog: ft.AlertDialog, page: ft.Page) -> None:
        """Cierra el modal."""
        if dialog:
            dialog.open = False
            dialog.update()
            if dialog in page.overlay:
                page.overlay.remove(dialog)
