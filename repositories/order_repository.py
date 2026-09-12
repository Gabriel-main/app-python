"""
OrderRepository — Acceso a datos de órdenes.

Aplica DIP: OrdersView recibe esta interfaz en vez de acceder
a la DB directamente con sqlmodel.get_session.
"""
from __future__ import annotations

import logging
from typing import Protocol

from database.connection import get_session
from database.models import Order

log = logging.getLogger(__name__)


class OrderRepositoryProtocol(Protocol):
    """Interfaz para repositorio de órdenes."""

    async def get_recent_orders(self, limit: int = 100) -> list[dict]: ...


class SQLOrderRepository:
    """Implementación con aiosqlite + SQLModel."""

    async def get_recent_orders(self, limit: int = 100) -> list[dict]:
        from sqlmodel import select

        try:
            async with get_session() as session:
                result = await session.exec(
                    select(Order).order_by(Order.timestamp.desc()).limit(limit)
                )
                orders = result.all()
                return [o.model_dump() for o in orders]
        except Exception as exc:
            log.error("Failed to load orders: %s", exc)
            return []
