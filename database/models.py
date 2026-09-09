"""
Modelos de Base de Datos — SQLModel Tables.

Contratos de persistencia para ticks de precio, órdenes ejecutadas
y posiciones abiertas (Futures/Margin).
"""
from __future__ import annotations

from typing import Optional
from sqlmodel import Field, SQLModel
import time


class PriceTick(SQLModel, table=True):
    """Registro de un tick de precio recibido del WebSocket."""
    __tablename__ = "price_ticks"

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    price: float
    change_pct: float
    volume: float
    high_24h: float
    low_24h: float
    timestamp: float = Field(default_factory=time.time)


class Order(SQLModel, table=True):
    """Registro de una orden ejecutada por el bot (paper o live)."""
    __tablename__ = "orders"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: str = Field(unique=True, index=True)
    symbol: str = Field(index=True)
    side: str                          # "BUY" | "SELL"
    quantity: float
    price: float
    mode: str                          # "PAPER" | "LIVE"
    trading_type: str = "SPOT"         # "SPOT" | "FUTURES" | "MARGIN"
    leverage: int = 1                  # 1x-20x (solo Futures/Margin)
    order_type: str = "MARKET"         # "MARKET" | "LIMIT"
    status: str = Field(default="FILLED")   # "FILLED" | "PENDING" | "CANCELLED"
    pnl: Optional[float] = None        # Profit & Loss calculado al cerrar
    timestamp: float = Field(default_factory=time.time)


class Position(SQLModel, table=True):
    """Posición abierta (Futures/Margin) con PnL no realizado."""
    __tablename__ = "positions"

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    side: str                          # "LONG" | "SHORT"
    quantity: float
    entry_price: float
    mark_price: float = 0.0
    unrealized_pnl: float = 0.0
    leverage: int = 1
    trading_type: str                  # "FUTURES" | "MARGIN"
    status: str = "OPEN"               # "OPEN" | "CLOSED"
    closed_price: Optional[float] = None
    closed_pnl: Optional[float] = None
    opened_at: float = Field(default_factory=time.time)
    closed_at: Optional[float] = None


class Operation(SQLModel, table=True):
    """Operación del motor dual (OC/OV) con stop loss y temporalidad."""
    __tablename__ = "operations"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: str = Field(unique=True, index=True)
    symbol: str = Field(index=True)
    side: str                          # "BUY" | "SELL"
    state: str                         # "ACTIVE" | "PENDING" | "PAST"
    entry_price: float
    stop_loss: float
    quantity: float
    trading_type: str = "SPOT"         # "SPOT" | "FUTURES" | "MARGIN"
    trade_currency: str = "USDT"       # "USDT" | "USDC"
    mode: str = "PAPER"                # "PAPER" | "LIVE"
    pnl: Optional[float] = None
    created_at: float = Field(default_factory=time.time)
    closed_at: Optional[float] = None
