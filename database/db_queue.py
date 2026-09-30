"""
DB Queue Worker — Escrituras asíncronas sin bloquear el Event Loop.

REGLA: Las escrituras en DB NUNCA bloquean la recepción de eventos de mercado.
Todas las operaciones de escritura se encolan en colas asyncio y las procesa
un worker en background de forma separada.

Dos carriles con política distinta (separación que impide head-of-line):

  _CRITICAL   Órdenes (FILLED / PENDING / CANCELLED). Cola ILIMITADA: una orden
              jamás se descarta, aunque la DB se atasque. Si el backlog supera
              la marca alta, se avisa con log con throttle.
  _DROPPABLE  Ticks, actualizaciones de operación y de posición. Cola ACOTADA:
              si se llena se descarta el MÁS VIEJO, conservando lo más fresco
              (solo es seguro tirar "el más viejo" porque este carril no
              comparte cola con las órdenes).

Rutas declaradas en `_routes` (OCP): persistir un evento nuevo = añadir una
entrada, sin tocar el loop ni el método `enqueue`.

Uso:
    db_queue.enqueue(tick_event)     # síncrono, no bloqueante
    db_queue.enqueue(order_event)
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from config.settings import settings
from database.connection import get_session
from database.models import Operation, Order, Position, PriceTick
from core.event_bus import event_bus
from core.events import (
    OperationUpdateEvent,
    OrderCanceledEvent,
    OrderExecutedEvent,
    OrderPlacedEvent,
    PositionUpdateEvent,
    PriceTickEvent,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Política de carriles
# ---------------------------------------------------------------------------

_CRITICAL = "critical"
_DROPPABLE = "droppable"

#: Tamaño máximo del carril descartable. A ~2.5 escrituras/s son ~7 minutos
#: de margen antes de empezar a descartar.
_DROPPABLE_MAXSIZE = 1000

#: Backlog de órdenes que dispara la alarma (informativa: este carril no dropa).
_CRITICAL_HIGH_WATER = 100

#: Segundos mínimos entre avisos repetidos (drops y backlog).
_LOG_THROTTLE_S = 30.0

#: Eventos que se persisten vía suscripción al EventBus (el resto los encolan
#: los servicios directamente con `enqueue`, para garantizar orden PENDING→FILLED).
_SUBSCRIBED_EVENTS: tuple[type, ...] = (OperationUpdateEvent, PositionUpdateEvent)

_Saver = Callable[[Any], Awaitable[None]]
_Route = tuple[str, _Saver]


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class DBQueueWorker:
    """Worker singleton que procesa escrituras en DB desde colas async."""

    def __init__(
        self,
        *,
        droppable_maxsize: int = _DROPPABLE_MAXSIZE,
        critical_high_water: int = _CRITICAL_HIGH_WATER,
    ) -> None:
        # Cola crítica ILIMITADA (maxsize=0): put_nowait nunca lanza QueueFull.
        self._critical: asyncio.Queue[Any] = asyncio.Queue()
        self._droppable: asyncio.Queue[Any] = asyncio.Queue(maxsize=droppable_maxsize)
        self._wakeup = asyncio.Event()
        self._running: bool = False
        self._task: asyncio.Task | None = None

        self._critical_high_water = critical_high_water
        self._dropped: int = 0
        self._last_drop_log: float = 0.0
        self._last_backlog_log: float = 0.0

        self._routes: dict[type, _Route] = {
            OrderExecutedEvent: (_CRITICAL, self._save_order),
            OrderPlacedEvent: (_CRITICAL, self._save_order_placed),
            OrderCanceledEvent: (_CRITICAL, self._save_order_canceled),
            PriceTickEvent: (_DROPPABLE, self._save_tick),
            OperationUpdateEvent: (_DROPPABLE, self._save_operation_update),
            PositionUpdateEvent: (_DROPPABLE, self._save_position_update),
        }

    # ------------------------------------------------------------------
    # Encolar operaciones (llamar desde servicios)
    # ------------------------------------------------------------------

    def enqueue(self, event: Any) -> bool:
        """Encola un evento para persistencia. Síncrono, no bloqueante.

        Devuelve False si el evento no tiene ruta de persistencia. Una orden
        nunca se descarta; solo el carril descartable puede soltar elementos,
        y siempre los más viejos.
        """
        route = self._routes.get(type(event))
        if route is None:
            log.debug("DBQueue: sin ruta para %s", type(event).__name__)
            return False

        if route[0] == _CRITICAL:
            self._critical.put_nowait(event)
            self._watch_backlog()
        else:
            self._put_droppable(event)

        self._wakeup.set()
        return True

    def _put_droppable(self, event: Any) -> None:
        """Encola en el carril descartable; si está lleno, tira el más viejo."""
        try:
            self._droppable.put_nowait(event)
        except asyncio.QueueFull:
            try:
                self._droppable.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self._droppable.put_nowait(event)
            self._log_drop(event)

    def _log_drop(self, event: Any) -> None:
        """Cuenta drops (total de por vida) y avisa como mucho 1 vez cada 30 s."""
        self._dropped += 1
        now = time.monotonic()
        if now - self._last_drop_log < _LOG_THROTTLE_S:
            return
        self._last_drop_log = now
        log.warning(
            "DB queue descartable llena: %d escritura(s) descartada(s) en total "
            "(última: %s) — el worker no está drenando",
            self._dropped, type(event).__name__,
        )

    def _watch_backlog(self) -> None:
        """Alarma informativa si la cola de órdenes crece demasiado."""
        pending = self._critical.qsize()
        if pending < self._critical_high_water:
            return
        now = time.monotonic()
        if now - self._last_backlog_log < _LOG_THROTTLE_S:
            return
        self._last_backlog_log = now
        log.warning(
            "DB critical backlog: %d escritura(s) de órdenes pendiente(s)", pending
        )

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._worker_loop(), name="db_queue_worker")

        for event_type in _SUBSCRIBED_EVENTS:
            event_bus.subscribe(event_type, self._on_bus_event)

        log.info("DBQueueWorker started")

    async def stop(self) -> None:
        self._running = False
        for event_type in _SUBSCRIBED_EVENTS:
            event_bus.unsubscribe(event_type, self._on_bus_event)
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

    async def _on_bus_event(self, event: Any) -> None:
        """Handler del EventBus — encola para escritura."""
        self.enqueue(event)

    # ------------------------------------------------------------------
    # Loop interno
    # ------------------------------------------------------------------

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                # clear ANTES de mirar: un put posterior ya deja la señal puesta
                # y hace que wait() devuelva de inmediato (sin wakeup perdido).
                self._wakeup.clear()
                event = self._pop()
                if event is None:
                    await self._wakeup.wait()
                    continue
                await self._process(event)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.exception("DBQueueWorker error: %s", exc)

    def _pop(self) -> Any | None:
        """Extrae el siguiente evento: las órdenes SIEMPRE antes que los ticks."""
        for queue in (self._critical, self._droppable):
            try:
                return queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        return None

    async def _process(self, event: Any) -> None:
        """Despacha según el registro de rutas (sin cadena isinstance)."""
        route = self._routes.get(type(event))
        if route is None:
            log.debug("DBQueue: sin ruta para %s", type(event).__name__)
            return
        await route[1](event)

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

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

    async def _upsert_order_row(self, order_id: str, data: dict, updates: dict) -> None:
        """Inserta o actualiza una fila de orders por order_id (DRY).

        Permite la transición PENDING → FILLED/CANCELLED de las órdenes
        LIMIT (el insert-only anterior la hacía imposible).
        Si `data` está vacío y la fila no existe, no inserta nada.
        """
        from sqlmodel import select
        async with get_session() as session:
            stmt = select(Order).where(Order.order_id == order_id)
            result = await session.exec(stmt)
            existing = result.first()
            if existing:
                for key, value in updates.items():
                    setattr(existing, key, value)
            elif data:
                session.add(Order(**data))
            else:
                log.warning("Order %s not found for update, skipping", order_id)
                return
            await session.commit()

    async def _save_order(self, event: OrderExecutedEvent) -> None:
        try:
            await self._upsert_order_row(
                event.order_id,
                data={
                    "order_id": event.order_id,
                    "symbol": event.symbol,
                    "side": event.side,
                    "quantity": event.quantity,
                    "price": event.price,
                    "mode": event.mode,
                    "trading_type": event.trading_type,
                    "leverage": event.leverage,
                    "order_type": event.order_type,
                    "status": "FILLED",
                    "limit_price": event.limit_price,
                    "entry_price": event.entry_price,
                    "timestamp": event.timestamp,
                },
                updates={
                    "price": event.price,
                    "status": "FILLED",
                    "quantity": event.quantity,
                },
            )
        except Exception as exc:
            log.error("Failed to save order: %s", exc)

    async def _save_order_placed(self, event: OrderPlacedEvent) -> None:
        try:
            await self._upsert_order_row(
                event.order_id,
                data={
                    "order_id": event.order_id,
                    "symbol": event.symbol,
                    "side": event.side,
                    "quantity": event.quantity,
                    "price": event.price,
                    "mode": event.mode,
                    "trading_type": settings.TRADING_TYPE,
                    "leverage": settings.LEVERAGE,
                    "order_type": "LIMIT",
                    "status": "PENDING",
                    "limit_price": event.price,
                    "entry_price": 0.0,
                    "timestamp": event.timestamp,
                },
                updates={},
            )
        except Exception as exc:
            log.error("Failed to save placed order: %s", exc)

    async def _save_order_canceled(self, event: OrderCanceledEvent) -> None:
        try:
            await self._upsert_order_row(
                event.order_id,
                data={},  # fila inexistente → no insertar (faltan campos base)
                updates={"status": "CANCELLED"},
            )
        except Exception as exc:
            log.error("Failed to save canceled order: %s", exc)

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
                            trading_type=settings.TRADING_TYPE,
                            trade_currency=settings.TRADE_CURRENCY,
                            mode=settings.TRADING_MODE,
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
