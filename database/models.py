"""
Modelos de Base de Datos — SQLModel Tables.

Contratos de persistencia para ticks de precio y órdenes ejecutadas.
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
    status: str = Field(default="FILLED")   # "FILLED" | "PENDING" | "CANCELLED"
    pnl: Optional[float] = None        # Profit & Loss calculado al cerrar
    timestamp: float = Field(default_factory=time.time)
