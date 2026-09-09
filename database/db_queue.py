"""
DB Queue Worker — Escrituras asíncronas sin bloquear el Event Loop.

REGLA: Las escrituras en DB NUNCA bloquean la recepción de eventos de mercado.
Todas las operaciones de escritura se encolan en asyncio.Queue y las procesa
un worker en background de forma separada.

Uso:
    await db_queue.enqueue_tick(tick_event)
    await db_queue.enqueue_order(order_event)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal, Union

from database.connection import get_session
from database.models import Order, PriceTick
from core.events import OrderExecutedEvent, PriceTickEvent

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Items de la cola
# ---------------------------------------------------------------------------

@dataclass
class _TickWriteItem:
    event: PriceTickEvent


@dataclass
class _OrderWriteItem:
    event: OrderExecutedEvent


_QueueItem = Union[_TickWriteItem, _OrderWriteItem]


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class DBQueueWorker:
    """Worker singleton que procesa escrituras en DB desde una cola async."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._queue: asyncio.Queue[_QueueItem] = asyncio.Queue(maxsize=maxsize)
        self._running: bool = False
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Encolar operaciones (llamar desde servicios)
    # ------------------------------------------------------------------

    def enqueue_tick(self, event: PriceTickEvent) -> None:
        """Encola un tick de precio para guardar en DB. No bloqueante."""
        try:
            self._queue.put_nowait(_TickWriteItem(event))
        except asyncio.QueueFull:
            log.warning("DB queue full, dropping tick for %s", event.symbol)

    def enqueue_order(self, event: OrderExecutedEvent) -> None:
        """Encola una orden ejecutada para guardar en DB. No bloqueante."""
        try:
            self._queue.put_nowait(_OrderWriteItem(event))
        except asyncio.QueueFull:
            log.warning("DB queue full, dropping order %s", event.order_id)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._worker_loop(), name="db_queue_worker")
        log.info("DBQueueWorker started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("DBQueueWorker stopped")

    # ------------------------------------------------------------------
    # Loop interno
    # ------------------------------------------------------------------

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                item = await self._queue.get()
                await self._process(item)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.exception("DBQueueWorker error: %s", exc)

    async def _process(self, item: _QueueItem) -> None:
        if isinstance(item, _TickWriteItem):
            await self._save_tick(item.event)
        elif isinstance(item, _OrderWriteItem):
            await self._save_order(item.event)

    async def _save_tick(self, event: PriceTickEvent) -> None:
        try:
            async with get_session() as session:
                tick = PriceTick(
                    symbol=event.symbol,
                    price=event.price,
                    change_pct=event.change_pct,
                    volume=event.volume,
                    high_24h=event.high_24h,
                    low_24h=event.low_24h,
                    timestamp=event.timestamp,
                )
                session.add(tick)
        except Exception as exc:
            log.error("Failed to save tick: %s", exc)

    async def _save_order(self, event: OrderExecutedEvent) -> None:
        try:
            async with get_session() as session:
                order = Order(
                    order_id=event.order_id,
                    symbol=event.symbol,
                    side=event.side,
                    quantity=event.quantity,
                    price=event.price,
                    mode=event.mode,
                    status="FILLED",
                    timestamp=event.timestamp,
                )
                session.add(order)
        except Exception as exc:
            log.error("Failed to save order: %s", exc)


# Instancia global singleton
db_queue = DBQueueWorker()
