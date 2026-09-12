"""
Colores — Mapa centralizado de constantes de color.

Elimina la repetición de diccionarios de color que aparecen en
order_card, position_card, operations_panel, bot_status_bar,
balance_card y connection_indicator.
"""
from __future__ import annotations

import flet as ft


# ---------------------------------------------------------------------------
# Lado de operación (BUY/SELL)
# ---------------------------------------------------------------------------
SIDE_COLORS: dict[str, tuple[ft.Color, ft.Color]] = {
    "BUY":  (ft.Colors.GREEN_400, ft.Colors.GREEN_900),
    "SELL": (ft.Colors.RED_400,   ft.Colors.RED_900),
}

SIDE_LABELS: dict[str, str] = {
    "BUY":  "COMPRA",
    "SELL": "VENTA",
}


# ---------------------------------------------------------------------------
# Estado de operación
# ---------------------------------------------------------------------------
STATE_COLORS: dict[str, tuple[ft.Color, ft.Color, str]] = {
    "ACTIVE":  (ft.Colors.GREEN_400,     ft.Colors.GREEN_900,     "ACTIVA"),
    "PENDING": (ft.Colors.AMBER_400,     ft.Colors.AMBER_900,     "PENDIENTE"),
    "PAST":    (ft.Colors.BLUE_GREY_400, ft.Colors.BLUE_GREY_800, "PASADA"),
}


# ---------------------------------------------------------------------------
# Tipo de trading
# ---------------------------------------------------------------------------
TRADING_TYPE_COLORS: dict[str, tuple[ft.Color, ft.Color, str]] = {
    "SPOT":    (ft.Colors.BLUE_400,   ft.Colors.BLUE_900,   "SPOT"),
    "FUTURES": (ft.Colors.PURPLE_400, ft.Colors.PURPLE_900, "FUTURES"),
    "MARGIN":  (ft.Colors.ORANGE_400, ft.Colors.ORANGE_900, "MARGIN"),
}


# ---------------------------------------------------------------------------
# Señal del bot
# ---------------------------------------------------------------------------
SIGNAL_COLORS: dict[str, tuple[ft.Color, ft.Color]] = {
    "BUY":  (ft.Colors.GREEN_400,     ft.Colors.GREEN_900),
    "SELL": (ft.Colors.RED_400,       ft.Colors.RED_900),
    "HOLD": (ft.Colors.BLUE_GREY_400, ft.Colors.BLUE_GREY_900),
}


# ---------------------------------------------------------------------------
# Estado de conexión WebSocket
# ---------------------------------------------------------------------------
CONNECTION_COLORS: dict[str, tuple[ft.Color, str, str]] = {
    "CONNECTING":   (ft.Colors.AMBER_400,  "wifi_find",       "Conectando..."),
    "CONNECTED":    (ft.Colors.GREEN_400,  "wifi",            "Conectado"),
    "DISCONNECTED": (ft.Colors.RED_400,    "wifi_off",        "Desconectado"),
    "RECONNECTING": (ft.Colors.ORANGE_400, "wifi_tethering",  "Reconectando..."),
}


# ---------------------------------------------------------------------------
# Modo de operación
# ---------------------------------------------------------------------------
MODE_COLORS: dict[str, ft.Color] = {
    "PAPER": ft.Colors.AMBER_400,
    "LIVE":  ft.Colors.RED_400,
}
