"""
Settings View — Configuración del bot de trading.

Permite al usuario cambiar:
- Par de trading (símbolo)
- Parámetros de estrategia (MA rápida / MA lenta)
- Modo de operación (Paper / Live)
- API Keys (solo en modo Live, campos con password=True)

Al guardar: publica SettingsUpdatedEvent para que los servicios se reconfiguren.
"""
from __future__ import annotations

import os
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
        self._symbol_field = ft.TextField(
            label="Par de Trading",
            value=settings.TRADING_SYMBOL,
            hint_text="Ej: BTCUSDT, ETHUSDT",
            prefix_icon=ft.Icons.CURRENCY_BITCOIN,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.BLUE_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
        )

        self._ma_fast_field = ft.TextField(
            label="MA Rápida",
            value=str(settings.BOT_MA_FAST),
            hint_text="Ej: 7",
            prefix_icon=ft.Icons.SPEED,
            keyboard_type=ft.KeyboardType.NUMBER,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.GREEN_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
        )

        self._ma_slow_field = ft.TextField(
            label="MA Lenta",
            value=str(settings.BOT_MA_SLOW),
            hint_text="Ej: 25",
            prefix_icon=ft.Icons.SHOW_CHART,
            keyboard_type=ft.KeyboardType.NUMBER,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.ORANGE_400,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
        )

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
            ft.Text("Configuración", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            ft.Divider(color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE), height=1),

            # Estrategia
            ft.Container(
                bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
                border_radius=14,
                padding=ft.Padding.all(16),
                content=ft.Column(
                    controls=[
                        ft.Text("📈 Estrategia MA Crossover", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                        self._symbol_field,
                        ft.Row(controls=[self._ma_fast_field, self._ma_slow_field], spacing=12),
                        ft.Text(
                            "El bot genera señal BUY cuando MA rápida supera MA lenta, y SELL cuando cruza por debajo.",
                            size=11, color=ft.Colors.BLUE_GREY_400,
                        ),
                    ],
                    spacing=12,
                ),
            ),

            # Modo
            ft.Container(
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

            # Guardar
            ft.Row(controls=[self._save_btn], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row(controls=[self._feedback_text], alignment=ft.MainAxisAlignment.CENTER),
        ]

        self.spacing = 16
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

    def _on_save(self, e: ft.ControlEvent) -> None:
        try:
            ma_fast = int(self._ma_fast_field.value or "7")
            ma_slow = int(self._ma_slow_field.value or "25")
        except ValueError:
            self._feedback_text.value = "❌ MA Rápida y MA Lenta deben ser números enteros."
            self._feedback_text.color = ft.Colors.RED_400
            self._feedback_text.update()
            return

        if ma_fast >= ma_slow:
            self._feedback_text.value = "❌ MA Rápida debe ser menor que MA Lenta."
            self._feedback_text.color = ft.Colors.RED_400
            self._feedback_text.update()
            return

        symbol = (self._symbol_field.value or "BTCUSDT").strip().upper()
        mode = self._mode_dropdown.value or "PAPER"
        api_key = self._api_key_field.value or ""
        api_secret = self._api_secret_field.value or ""

        # Actualizar .env en disco
        self._write_env(symbol, mode, ma_fast, ma_slow, api_key, api_secret)

        # Recargar settings en memoria
        settings.reload_from_env()

        # Publicar evento para que los servicios reaccionen
        event_bus.publish(SettingsUpdatedEvent(
            symbol=symbol,
            ma_fast=ma_fast,
            ma_slow=ma_slow,
            mode=mode,
            api_key=api_key,
            api_secret=api_secret,
        ))

        self._feedback_text.value = "✅ Configuración guardada. Reconectando..."
        self._feedback_text.color = ft.Colors.GREEN_400
        self._feedback_text.update()

    @staticmethod
    def _write_env(symbol: str, mode: str, ma_fast: int, ma_slow: int,
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

        lines = set_var(lines, "TRADING_SYMBOL", symbol)
        lines = set_var(lines, "TRADING_MODE", mode)
        lines = set_var(lines, "BOT_MA_FAST", str(ma_fast))
        lines = set_var(lines, "BOT_MA_SLOW", str(ma_slow))
        lines = set_var(lines, "BINANCE_API_KEY", api_key)
        lines = set_var(lines, "BINANCE_API_SECRET", api_secret)

        env_path.write_text("\n".join(lines), encoding="utf-8")
