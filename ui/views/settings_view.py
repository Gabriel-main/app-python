"""
Settings View — Configuración del bot de trading.

Permite al usuario cambiar:
- Modo de operación (Paper / Live)
- Tipo de trading (Spot/Futures/Margin)
- API Keys (solo en modo Live, campos con password=True)

Al guardar: muestra modal de confirmación, luego publica SettingsUpdatedEvent.
"""
from __future__ import annotations

from pathlib import Path

import flet as ft

from config.settings import settings
from core.event_bus import event_bus
from core.events import SettingsUpdatedEvent


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
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
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
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
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
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
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
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
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
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.CYAN_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            visible=settings.ORDER_TYPE == "LIMIT",
        )

        self._api_key_field = ft.TextField(
            label="Binance API Key",
            value=settings.BINANCE_API_KEY,
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.KEY,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.AMBER_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            visible=settings.TRADING_MODE == "LIVE",
        )

        self._api_secret_field = ft.TextField(
            label="Binance API Secret",
            value=settings.BINANCE_API_SECRET,
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.LOCK,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.AMBER_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            visible=settings.TRADING_MODE == "LIVE",
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
                bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
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
                bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
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

            # Guardar
            ft.Row(controls=[self._save_btn], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row(controls=[self._feedback_text], alignment=ft.MainAxisAlignment.CENTER),
        ]

        self.spacing = 16
        self.expand = True
        self.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        self.scroll = ft.ScrollMode.AUTO

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

    def _on_trading_type_changed(self, e: ft.ControlEvent) -> None:
        trading_type = e.control.value
        show_leverage = trading_type in ("FUTURES", "MARGIN")
        self._leverage_dropdown.visible = show_leverage
        self._leverage_dropdown.update()

    def _on_order_type_changed(self, e: ft.ControlEvent) -> None:
        is_limit = e.control.value == "LIMIT"
        self._limit_price_field.visible = is_limit
        self._limit_price_field.update()

    def _on_save(self, e: ft.ControlEvent) -> None:
        """Abre modal de confirmación antes de guardar."""
        self._show_confirm_dialog()

    def _show_confirm_dialog(self) -> None:
        """Muestra modal de confirmación con resumen de cambios."""
        mode = self._mode_dropdown.value or "PAPER"
        trading_type = self._trading_type_dropdown.value or "SPOT"
        leverage = int(self._leverage_dropdown.value or "1")
        order_type = self._order_type_dropdown.value or "MARKET"
        limit_price = float(self._limit_price_field.value or "0")

        # Construir resumen de cambios
        changes = []
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

        if not changes:
            changes.append("No hay cambios detectados")

        # Crear modal
        self._confirm_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar Cambios", color=ft.Colors.WHITE, size=15),
            bgcolor=ft.Colors.GREY_900,
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
                    on_click=lambda _: self._close_dialog(),
                ),
                ft.FilledButton(
                    "Confirmar",
                    on_click=lambda _: self._apply_changes(),
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
        self._confirm_dialog.open = True
        self.page.update()

    def _apply_changes(self) -> None:
        """Aplica los cambios después de confirmar en el modal."""
        # Mostrar spinner mientras se procesa
        self._confirm_dialog.content = ft.Column(
            controls=[
                ft.ProgressRing(width=28, height=28, stroke_width=3),
                ft.Container(height=10),
                ft.Text("Aplicando cambios...", color=ft.Colors.WHITE, size=14),
                ft.Text("El servicio se reconectará.", color=ft.Colors.AMBER_400, size=11),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            width=250,
        )
        self._confirm_dialog.actions = []
        self._confirm_dialog.update()

        symbol = settings.TRADING_SYMBOL  # Se toma del Dashboard SymbolPicker
        mode = self._mode_dropdown.value or "PAPER"
        trading_type = self._trading_type_dropdown.value or "SPOT"
        leverage = int(self._leverage_dropdown.value or "1")
        order_type = self._order_type_dropdown.value or "MARKET"
        limit_price = float(self._limit_price_field.value or "0")
        api_key = self._api_key_field.value or ""
        api_secret = self._api_secret_field.value or ""

        # Actualizar .env en disco
        self._write_env(mode, trading_type, leverage, order_type, limit_price,
                        api_key, api_secret)

        # Recargar settings en memoria
        settings.reload_from_env()

        # Publicar evento para que los servicios reaccionen
        event_bus.publish(SettingsUpdatedEvent(
            symbol=symbol,
            mode=mode,
            trading_type=trading_type,
            leverage=leverage,
            order_type=order_type,
            limit_price=limit_price,
            trade_amount=settings.TRADE_AMOUNT,
            trade_currency=settings.TRADE_CURRENCY,
            stop_loss=settings.STOP_LOSS,
            stop_loss_type=settings.STOP_LOSS_TYPE,
            timeframe=settings.TIMEFRAME,
            timeframe_unit=settings.TIMEFRAME_UNIT,
            api_key=api_key,
            api_secret=api_secret,
        ))

        self._close_dialog()
        self._feedback_text.value = "✅ Configuración guardada. Reconectando..."
        self._feedback_text.color = ft.Colors.GREEN_400
        self._feedback_text.update()

    def _close_dialog(self) -> None:
        """Cierra el modal de confirmación."""
        if hasattr(self, '_confirm_dialog') and self._confirm_dialog:
            self._confirm_dialog.open = False
            self.page.update()
            # Limpiar overlay
            if self._confirm_dialog in self.page.overlay:
                self.page.overlay.remove(self._confirm_dialog)

    @staticmethod
    def _write_env(mode: str, trading_type: str, leverage: int,
                   order_type: str, limit_price: float,
                   api_key: str, api_secret: str) -> None:
        """Escribe/actualiza el archivo .env con la nueva configuración."""
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        lines = []
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()

        def set_var(lines: list[str], key: str, val: str) -> list[str]:
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={val}"
                    return lines
            lines.append(f"{key}={val}")
            return lines

        lines = set_var(lines, "TRADING_MODE", mode)
        lines = set_var(lines, "TRADING_TYPE", trading_type)
        lines = set_var(lines, "LEVERAGE", str(leverage))
        lines = set_var(lines, "ORDER_TYPE", order_type)
        lines = set_var(lines, "LIMIT_PRICE", str(limit_price))
        lines = set_var(lines, "BINANCE_API_KEY", api_key)
        lines = set_var(lines, "BINANCE_API_SECRET", api_secret)

        env_path.write_text("\n".join(lines), encoding="utf-8")
