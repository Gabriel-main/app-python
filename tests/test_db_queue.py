"""
Tests del DBQueueWorker con dos carriles (A2).

Regresión principal: una orden crítica JAMÁS se descarta aunque la cola
descartable (ticks / updates) esté llena — el bug raíz de head-of-line.
"""
import asyncio
import inspect
import logging
import time
from unittest.mock import AsyncMock

import pytest

from core.events import (
    OrderCanceledEvent,
    OrderExecutedEvent,
    OrderPlacedEvent,
    PriceTickEvent,
)
from database.db_queue import _CRITICAL, _DROPPABLE, DBQueueWorker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tick(price: float = 65000.0) -> PriceTickEvent:
    return PriceTickEvent(
        symbol="BTCUSDT", price=price, change_pct=0.1,
        volume=1.0, high_24h=price * 1.01, low_24h=price * 0.99,
    )


def _order(order_id: str = "LIVE-1") -> OrderExecutedEvent:
    return OrderExecutedEvent(
        order_id=order_id, symbol="BTCUSDT", side="BUY",
        quantity=0.001, price=65000.0, mode="PAPER", order_type="MARKET",
    )


def _placed(order_id: str = "LIVE-2") -> OrderPlacedEvent:
    return OrderPlacedEvent(
        order_id=order_id, operation_id="OC-1", symbol="BTCUSDT",
        side="BUY", quantity=0.001, price=65000.0, mode="PAPER",
    )


def _canceled(order_id: str = "LIVE-3") -> OrderCanceledEvent:
    return OrderCanceledEvent(
        order_id=order_id, operation_id="OC-1", reason="bot_stop", mode="PAPER",
    )


async def _wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("timeout esperando la condición")
        await asyncio.sleep(0.005)


# ---------------------------------------------------------------------------
# F2 — Política de carriles
# ---------------------------------------------------------------------------

def test_order_survives_full_droppable_queue():
    """Bug raíz: la orden no puede descartarse por culpa de los ticks."""
    w = DBQueueWorker(droppable_maxsize=5)
    for i in range(5):
        assert w.enqueue(_tick(price=float(i))) is True
    assert w._droppable.full()

    order = _order()
    assert w.enqueue(order) is True          # nunca lanza QueueFull
    assert w._critical.qsize() == 1
    assert w._droppable.qsize() == 5         # intacta


def test_droppable_drops_oldest_keeps_freshest():
    w = DBQueueWorker(droppable_maxsize=3)
    for i in range(5):
        w.enqueue(_tick(price=float(i)))

    assert w._droppable.qsize() == 3
    kept = []
    while (item := w._pop()) is not None:
        kept.append(item)
    assert [e.price for e in kept] == [2.0, 3.0, 4.0]


def test_all_order_events_go_to_critical_lane():
    """FILLED, PENDING y CANCELLED comparten carril crítico, nunca el descartable."""
    w = DBQueueWorker(droppable_maxsize=1)
    w.enqueue(_tick())                                # descartable a tope

    for event in (_order(), _placed(), _canceled()):
        assert w.enqueue(event) is True

    assert w._critical.qsize() == 3
    assert w._droppable.qsize() == 1


def test_critical_has_priority_over_droppable():
    w = DBQueueWorker(droppable_maxsize=10)
    tick, order = _tick(), _order()
    w.enqueue(tick)
    w.enqueue(order)

    assert w._pop() is order     # las órdenes se drenan antes que los ticks
    assert w._pop() is tick


def test_routes_registry_maps_lane_and_saver():
    w = DBQueueWorker()
    expected = {
        OrderExecutedEvent: (_CRITICAL, w._save_order),
        OrderPlacedEvent: (_CRITICAL, w._save_order_placed),
        OrderCanceledEvent: (_CRITICAL, w._save_order_canceled),
        PriceTickEvent: (_DROPPABLE, w._save_tick),
    }
    for event_type, (lane, saver) in expected.items():
        got_lane, got_saver = w._routes[event_type]
        assert got_lane == lane
        assert got_saver == saver

    # Invariante: NINGÚN evento de orden puede vivir en el carril descartable.
    critical = {t for t, (lane, _) in w._routes.items() if lane == _CRITICAL}
    assert critical == {OrderExecutedEvent, OrderPlacedEvent, OrderCanceledEvent}


# ---------------------------------------------------------------------------
# F3 — Worker: prioridad, wakeup, sin polling
# ---------------------------------------------------------------------------

def test_worker_loop_has_no_polling():
    """CERO POLLING: el loop espera en Event.wait(), jamás en sleep."""
    source = inspect.getsource(DBQueueWorker._worker_loop)
    assert "sleep" not in source
    assert "_wakeup.wait()" in source


def test_enqueue_sets_wakeup():
    w = DBQueueWorker()
    w._wakeup.clear()
    w.enqueue(_order())
    assert w._wakeup.is_set()


@pytest.mark.asyncio
async def test_worker_wakes_on_enqueue_and_persists():
    w = DBQueueWorker()
    saved: list = []

    async def spy(event):
        saved.append(event)

    w._routes[OrderExecutedEvent] = (_CRITICAL, spy)

    await w.start()
    try:
        await asyncio.sleep(0.05)            # reposo: nada debe procesarse
        assert saved == []

        order = _order()
        w.enqueue(order)
        await _wait_until(lambda: len(saved) == 1)
        assert saved[0] is order
    finally:
        await w.stop()


@pytest.mark.asyncio
async def test_stop_leaves_no_orphan_task():
    w = DBQueueWorker()
    await w.start()
    task = w._task
    await w.stop()
    assert task.done()
    assert task not in asyncio.all_tasks()


# ---------------------------------------------------------------------------
# Enrutado
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_dispatches_to_registered_saver():
    w = DBQueueWorker()
    spy = AsyncMock()
    w._routes[OrderExecutedEvent] = (_CRITICAL, spy)

    await w._process(_order())
    spy.assert_awaited_once()


def test_enqueue_unknown_event_returns_false(caplog):
    w = DBQueueWorker()
    with caplog.at_level(logging.DEBUG, logger="database.db_queue"):
        assert w.enqueue(object()) is False
    assert w._critical.empty()
    assert w._droppable.empty()
    assert "sin ruta" in caplog.text


# ---------------------------------------------------------------------------
# Observabilidad: logs con throttle
# ---------------------------------------------------------------------------

def test_backlog_alarm_logs_once(caplog):
    w = DBQueueWorker(critical_high_water=2)
    w._last_backlog_log = -1e9

    with caplog.at_level(logging.WARNING, logger="database.db_queue"):
        for i in range(3):
            w.enqueue(_order(order_id=f"LIVE-{i}"))

    alarms = [r for r in caplog.records if "critical backlog" in r.getMessage()]
    assert len(alarms) == 1


def test_droppable_drop_logs_throttled(caplog):
    w = DBQueueWorker(droppable_maxsize=1)
    w._last_drop_log = -1e9

    with caplog.at_level(logging.WARNING, logger="database.db_queue"):
        for i in range(10):
            w.enqueue(_tick(price=float(i)))

    drops = [r for r in caplog.records if "descartable" in r.getMessage()]
    assert len(drops) == 1
    assert w._dropped == 9                  # 10 encolados - 1 conservado
    assert w._droppable.qsize() == 1
    assert w._pop().price == 9.0             # se conserva lo más fresco
