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


@dataclass
class SymbolsListEvent:
    """Lista de símbolos disponibles (USDT/USDC) con precios actuales."""
    symbols: list[dict]  # [{symbol, base_asset, quote_asset, price}]
    trading_type: str = "SPOT"
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
    entry_price: float = 0.0        # Precio teórico de entrada (Pe) para PnL
    stop_loss: float = 0.0          # Precio de stop loss (PSL) para cálculo de PnL
    trading_type: Literal["SPOT", "FUTURES", "MARGIN"] = "SPOT"
    leverage: int = 1
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    limit_price: float = 0.0           # precio límite original (0 si MARKET)
    operation_id: str = ""          # OC-xxx / OV-xxx (id de la operación, no del executor)
    timestamp: float = field(default_factory=time.time)


@dataclass
class OrderFailedEvent:
    """Fallo al ejecutar una orden — elimina errores silenciosos."""
    operation_id: str
    side: Literal["BUY", "SELL"]
    error: str
    mode: Literal["PAPER", "LIVE"] = "PAPER"
    timestamp: float = field(default_factory=time.time)


@dataclass
class OrderPlacedEvent:
    """Orden LIMIT aceptada por el exchange/simulador — aún sin llenar.

    Solo se emite para órdenes LIMIT con status NEW. Nunca para MARKET
    (una MARKET siempre produce OrderExecutedEvent directamente).
    """
    order_id: str                    # clientOrderId generado por el bot
    operation_id: str                # OC-xxx / OV-xxx
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float
    price: float                     # precio límite de la orden
    order_type: Literal["LIMIT"] = "LIMIT"
    mode: Literal["PAPER", "LIVE"] = "PAPER"
    timestamp: float = field(default_factory=time.time)


@dataclass
class OrderFillEvent:
    """Notificación cruda de fill/cancelación de una orden.

    Productores: BinanceService (LIVE, user data stream executionReport)
    y BotEngine (PAPER, cruce de PriceTickEvent).
    Único consumidor: BotEngine (la convierte en OrderExecutedEvent /
    OrderCanceledEvent, que sí conocen entry_price/stop_loss de la operación).
    """
    order_id: str                    # clientOrderId que generó el bot
    status: Literal["FILLED", "CANCELED"]
    price: float = 0.0               # precio promedio del fill
    quantity: float = 0.0
    mode: Literal["PAPER", "LIVE"] = "PAPER"
    source: Literal["USER_STREAM", "PAPER_TICK"] = "USER_STREAM"
    timestamp: float = field(default_factory=time.time)


@dataclass
class OrderCanceledEvent:
    """Orden LIMIT cancelada (bot stop, settings, timeframe o exchange)."""
    order_id: str
    operation_id: str
    reason: str = ""
    mode: Literal["PAPER", "LIVE"] = "PAPER"
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Eventos de Operaciones Dual (OC/OV)
# ---------------------------------------------------------------------------

@dataclass
class OperationState:
    """Estado de una operación individual (COMPRA o VENTA).

    entry_filled: False mientras la orden de entrada LIMIT siga working
    (la operación aún no tiene posición; SL/PnL no aplican).
    """
    side: Literal["BUY", "SELL"]
    state: Literal["ACTIVE", "PENDING", "PAST"]
    entry_price: float       # Pe
    stop_loss: float         # PSL
    quantity: float
    order_id: str
    entry_filled: bool = True
    timestamp: float = field(default_factory=time.time)


@dataclass
class OperationUpdateEvent:
    """Actualización del estado de todas las operaciones activas/pendientes."""
    operations: list[OperationState] = field(default_factory=list)
    timeframe_remaining: float = 0.0  # segundos restantes del timer
    timeframe_total: float = 0.0      # segundos totales del timer
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Eventos de Posiciones (Futures/Margin)
# ---------------------------------------------------------------------------

@dataclass
class PositionUpdateEvent:
    """Actualización de posición abierta con PnL no realizado."""
    symbol: str
    side: Literal["LONG", "SHORT"]
    quantity: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: int
    trading_type: Literal["FUTURES", "MARGIN"]
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Eventos de Fondos (Account Balance)
# ---------------------------------------------------------------------------

@dataclass
class BalanceUpdateEvent:
    """Saldo de la cuenta del usuario según TRADING_TYPE."""
    asset: str                          # "USDT" | "USDC"
    trading_type: str                   # "SPOT" | "FUTURES" | "MARGIN"
    free: float                         # Saldo disponible
    locked: float = 0.0                 # Bloqueado en órdenes (Spot)
    borrowed: float = 0.0               # Prestado (Margin)
    interest: float = 0.0               # Interés (Margin)
    available: float = 0.0              # Disponible para operar (Futures)
    unrealized_pnl: float = 0.0         # PnL no realizado (Futures)
    margin_level: float = 0.0           # Nivel de margen (Margin)
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
class ConnectionStatusRequestEvent:
    """Solicitud del estado actual de conexión (UI → Backend)."""
    timestamp: float = field(default_factory=time.time)


@dataclass
class ConnectionStatusSnapshotEvent:
    """Snapshot del estado actual de conexión (Backend → UI)."""
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
    mode: Literal["PAPER", "LIVE"]
    trading_type: Literal["SPOT", "FUTURES", "MARGIN"] = "SPOT"
    leverage: int = 1
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    limit_price: float = 0.0
    trade_amount: float = 10.0
    trade_currency: str = "USDT"
    stop_loss: float = 1.01
    stop_loss_type: str = "PERCENT"
    timeframe: int = 1
    timeframe_unit: str = "MINUTES"


@dataclass
class NavigateToEvent:
    """Solicitud de navegación a un tab específico."""
    index: int  # 0=Dashboard, 1=Órdenes, 2=Config, 3=Auditoría, 4=Settings(Ajustes del Bot)


# ---------------------------------------------------------------------------
# Eventos de Dominio del Bot Engine (audit trail)
# ---------------------------------------------------------------------------

@dataclass
class TradingLifecycleEvent:
    """Cambio de ciclo de vida del bot (started/stopped)."""
    action: str                         # "STARTED" | "STOPPED"
    detail: str = ""
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class OperationInsertedEvent:
    """Nueva operación PENDING insertada por condición de SL."""
    active_side: str = ""
    active_sl: float = 0.0
    pa: float = 0.0
    new_pending_side: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class TimeframeCycleEvent:
    """Ciclo de temporalidad completado."""
    pa: float = 0.0
    active_side: str = ""
    new_pending_side: str = ""
    operations_count: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class StopLossEvent:
    """Stop loss ejecutado."""
    order_id: str = ""
    side: str = ""
    quantity: float = 0.0
    price: float = 0.0
    mode: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class InitialOrderEvent:
    """Orden inicial ejecutada."""
    order_id: str = ""
    side: str = ""
    quantity: float = 0.0
    price: float = 0.0
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Eventos de Autenticación
# ---------------------------------------------------------------------------

@dataclass
class AuthStateChangedEvent:
    """Cambio de estado de autenticación del usuario."""
    is_authenticated: bool
    timestamp: float = field(default_factory=time.time)


@dataclass
class LogoutRequestedEvent:
    """Solicitud de cierre de sesión."""
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Evento de Auditoría
# ---------------------------------------------------------------------------

@dataclass
class AuditEvent:
    """Evento de auditoría para trazabilidad del bot."""
    timestamp: float = field(default_factory=time.time)
    category: str = ""          # "CONNECTION", "PRICE", "SIGNAL", "ORDER", "OPERATION", "STATE", "CONFIG"
    action: str = ""            # "CONNECTED", "TICK", "BUY_SIGNAL", "ORDER_EXECUTED", etc.
    detail: str = ""            # Mensaje descriptivo
    data: dict = field(default_factory=dict)  # Datos adicionales
