"""
Contratos de Datos — Eventos del EventBus.

Estos dataclasses son los únicos contratos de comunicación entre
la capa de servicios (backend) y la capa de interfaz (UI).

REGLA: UI nunca llama a servicios directamente. Backend nunca toca widgets.
Todo fluye a través de estos eventos publicados en el AsyncEventBus.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
import time


# ---------------------------------------------------------------------------
# Eventos de Mercado
# ---------------------------------------------------------------------------

@dataclass
class PriceTickEvent:
    """Tick de precio recibido en tiempo real desde Binance WebSocket."""
    symbol: str
    price: float
    change_pct: float        # % cambio 24h
    volume: float            # volumen USDT 24h
    high_24h: float
    low_24h: float
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Eventos del Bot Engine
# ---------------------------------------------------------------------------

@dataclass
class BotSignalEvent:
    """Señal generada por el bot tras calcular el cruce de medias móviles."""
    symbol: str
    signal: Literal["BUY", "SELL", "HOLD"]
    ma_fast: float           # valor MA rápida
    ma_slow: float           # valor MA lenta
    confidence: float        # 0.0–1.0 (qué tan pronunciado es el cruce)
    timestamp: float = field(default_factory=time.time)


@dataclass
class OrderExecutedEvent:
    """Orden ejecutada por el bot (paper o live)."""
    order_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float
    price: float
    mode: Literal["PAPER", "LIVE"]
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Eventos de Infraestructura
# ---------------------------------------------------------------------------

@dataclass
class ConnectionStatusEvent:
    """Cambio de estado de la conexión WebSocket a Binance."""
    status: Literal["CONNECTING", "CONNECTED", "DISCONNECTED", "RECONNECTING"]
    message: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class BotStateChangedEvent:
    """El bot fue activado o desactivado desde la UI."""
    is_running: bool
    mode: Literal["PAPER", "LIVE"]


@dataclass
class SettingsUpdatedEvent:
    """El usuario guardó nueva configuración desde Settings."""
    symbol: str
    ma_fast: int
    ma_slow: int
    mode: Literal["PAPER", "LIVE"]
    api_key: str = ""
    api_secret: str = ""
