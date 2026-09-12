"""
DB Queue Worker — Escrituras asíncronas sin bloquear el Event Loop.

REGLA: Las escrituras en DB NUNCA bloquean la recepción de eventos de mercado.
Todas las operaciones de escritura se encolan en asyncio.Queue y las procesa
un worker en background de forma separada.

Uso:
    await db_queue.enqueue_tick(tick_event)
    await db_queue.enqueue_order(order_event)
    await db_queue.enqueue_operation_update(event)
    await db_queue.enqueue_position_update(event)
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Union

from database.connection import get_session
from database.models import Operation, Order, Position, PriceTick
from core.event_bus import event_bus
from core.events import (
    OperationUpdateEvent,
    OrderExecutedEvent,
    PositionUpdateEvent,
    PriceTickEvent,
)

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


@dataclass
class _OperationUpdateItem:
    event: OperationUpdateEvent


@dataclass
class _PositionUpdateItem:
    event: PositionUpdateEvent


_QueueItem = Union[_TickWriteItem, _OrderWriteItem, _OperationUpdateItem, _PositionUpdateItem]


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

    def enqueue_operation_update(self, event: OperationUpdateEvent) -> None:
        """Encola una actualización de operación para guardar en DB. No bloqueante."""
        try:
            self._queue.put_nowait(_OperationUpdateItem(event))
        except asyncio.QueueFull:
            log.warning("DB queue full, dropping operation update")

    def enqueue_position_update(self, event: PositionUpdateEvent) -> None:
        """Encola una actualización de posición para guardar en DB. No bloqueante."""
        try:
            self._queue.put_nowait(_PositionUpdateItem(event))
        except asyncio.QueueFull:
            log.warning("DB queue full, dropping position update")

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._worker_loop(), name="db_queue_worker")

        # Suscribirse a eventos para persistencia
        event_bus.subscribe(OperationUpdateEvent, self._on_operation_update)
        event_bus.subscribe(PositionUpdateEvent, self._on_position_update)

        log.info("DBQueueWorker started")

    async def stop(self) -> None:
        self._running = False
        event_bus.unsubscribe(OperationUpdateEvent, self._on_operation_update)
        event_bus.unsubscribe(PositionUpdateEvent, self._on_position_update)
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("DBQueueWorker stopped")

    # ------------------------------------------------------------------
    # Handlers de eventos
    # ------------------------------------------------------------------

    async def _on_operation_update(self, event: OperationUpdateEvent) -> None:
        """Handler directo — encola para escritura."""
        self.enqueue_operation_update(event)

    async def _on_position_update(self, event: PositionUpdateEvent) -> None:
        """Handler directo — encola para escritura."""
        self.enqueue_position_update(event)

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
        elif isinstance(item, _OperationUpdateItem):
            await self._save_operation_update(item.event)
        elif isinstance(item, _PositionUpdateItem):
            await self._save_position_update(item.event)

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
                await session.commit()
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
                    entry_price=event.entry_price,
                    trading_type=event.trading_type,
                    leverage=event.leverage,
                    order_type=event.order_type,
                    status="FILLED",
                    timestamp=event.timestamp,
                )
                session.add(order)
                await session.commit()
        except Exception as exc:
            log.error("Failed to save order: %s", exc)

    async def _save_operation_update(self, event: OperationUpdateEvent) -> None:
        """Persiste el estado de las operaciones en la tabla operations."""
        try:
            async with get_session() as session:
                for op in event.operations:
                    # Buscar si ya existe
                    from sqlmodel import select
                    stmt = select(Operation).where(Operation.order_id == op.order_id)
                    result = await session.exec(stmt)
                    existing = result.first()

                    if existing:
                        # Actualizar
                        existing.state = op.state
                        existing.entry_price = op.entry_price
                        existing.stop_loss = op.stop_loss
                        existing.quantity = op.quantity
                        if op.state == "PAST":
                            existing.closed_at = time.time()
                    else:
                        # Insertar nueva
                        new_op = Operation(
                            order_id=op.order_id,
                            symbol=event.operations[0].order_id.split("-")[0] if event.operations else "UNKNOWN",
                            side=op.side,
                            state=op.state,
                            entry_price=op.entry_price,
                            stop_loss=op.stop_loss,
                            quantity=op.quantity,
                            trading_type="SPOT",
                            trade_currency="USDT",
                            mode="PAPER",
                            created_at=op.timestamp,
                        )
                        session.add(new_op)
                await session.commit()
        except Exception as exc:
            log.error("Failed to save operation update: %s", exc)

    async def _save_position_update(self, event: PositionUpdateEvent) -> None:
        """Persiste el estado de las posiciones en la tabla positions."""
        try:
            async with get_session() as session:
                from sqlmodel import select
                # Buscar posición abierta para este símbolo y lado
                side_db = "LONG" if event.side == "LONG" else "SHORT"
                stmt = select(Position).where(
                    Position.symbol == event.symbol,
                    Position.side == side_db,
                    Position.status == "OPEN",
                )
                result = await session.exec(stmt)
                existing = result.first()

                if existing:
                    # Actualizar
                    existing.mark_price = event.mark_price
                    existing.unrealized_pnl = event.unrealized_pnl
                    existing.leverage = event.leverage
                else:
                    # Insertar nueva
                    new_pos = Position(
                        symbol=event.symbol,
                        side=side_db,
                        quantity=event.quantity,
                        entry_price=event.entry_price,
                        mark_price=event.mark_price,
                        unrealized_pnl=event.unrealized_pnl,
                        leverage=event.leverage,
                        trading_type=event.trading_type,
                        status="OPEN",
                    )
                    session.add(new_pos)
                await session.commit()
        except Exception as exc:
            log.error("Failed to save position update: %s", exc)


# Instancia global singleton
db_queue = DBQueueWorker()
