"""
Tests para AuditService — ChangedFilter y el registry declarativo.

El problema: OperationUpdateEvent (1/s desde el loop de temporalidad) y
PositionUpdateEvent (cada 2s) llenaban el ring buffer de 200 con ruido y
expulsaban las órdenes/señales que sí interesan.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from core.events import (
    OperationState,
    OperationUpdateEvent,
    PositionUpdateEvent,
)
from services.audit_service import (
    HANDLER_REGISTRY,
    _OPERATION_STRUCTURE,
    _POSITION_OPEN,
    ChangedFilter,
    audit_service,
)


@pytest.fixture(autouse=True)
def _reset_filters():
    _OPERATION_STRUCTURE.reset()
    _POSITION_OPEN.reset()
    yield
    _OPERATION_STRUCTURE.reset()
    _POSITION_OPEN.reset()


def _op(side: str = "BUY", state: str = "ACTIVE", order_id: str = "OC-1") -> OperationState:
    return OperationState(
        side=side, state=state, entry_price=65000.0, stop_loss=64000.0,
        quantity=0.001, order_id=order_id,
    )


def _operation_update(operations, remaining: float = 60.0) -> OperationUpdateEvent:
    return OperationUpdateEvent(
        operations=operations, timeframe_remaining=remaining, timeframe_total=60.0
    )


def _position_update(
    entry_price: float = 65000.0,
    side: str = "LONG",
    symbol: str = "BTCUSDT",
) -> PositionUpdateEvent:
    return PositionUpdateEvent(
        symbol=symbol, side=side, quantity=0.001, entry_price=entry_price,
        mark_price=entry_price + 10, unrealized_pnl=0.5, leverage=1,
        trading_type="FUTURES",
    )


# ---------------------------------------------------------------------------
# ChangedFilter (genérico, reutilizable)
# ---------------------------------------------------------------------------
def test_changed_filter_passes_first_event():
    f = ChangedFilter(lambda e: e)
    assert f(1) is True


def test_changed_filter_blocks_same_value():
    f = ChangedFilter(lambda e: e)
    f(1)
    assert f(1) is False


def test_changed_filter_passes_after_change():
    f = ChangedFilter(lambda e: e)
    f(1)
    assert f(2) is True


def test_changed_filter_keeps_state_per_identity():
    f = ChangedFilter(lambda e: e[1], id_of=lambda e: e[0])
    assert f(("A", 1)) is True     # primera vez para A
    assert f(("B", 1)) is True     # B tiene estado propio
    assert f(("A", 1)) is False    # A sin cambio
    assert f(("B", 1)) is False    # B sin cambio
    assert f(("A", 2)) is True     # cambió solo A
    assert f(("B", 1)) is False    # B sigue intacto


def test_changed_filter_reset_clears_state():
    f = ChangedFilter(lambda e: e)
    f(1)
    f.reset()
    assert f(1) is True


# ---------------------------------------------------------------------------
# OPERATION: solo la estructura de operaciones importa
# ---------------------------------------------------------------------------
def test_operation_filtered_when_only_timer_changes():
    """Regresión: el timer del timeframe cambiaba en cada segundo."""
    events = [
        _operation_update([_op()], remaining=60.0),
        _operation_update([_op()], remaining=59.0),
        _operation_update([_op()], remaining=1.0),
    ]
    results = [_OPERATION_STRUCTURE(e) for e in events]
    assert results == [True, False, False]


def test_operation_passes_when_structure_changes():
    _OPERATION_STRUCTURE(_operation_update([_op()]))

    assert _OPERATION_STRUCTURE(
        _operation_update([_op(state="PENDING")])
    ) is True
    assert _OPERATION_STRUCTURE(
        _operation_update([_op(state="PENDING"), _op(side="SELL", order_id="OV-1")])
    ) is True
    assert _OPERATION_STRUCTURE(_operation_update([])) is True


def test_operation_passes_for_different_order_ids():
    _OPERATION_STRUCTURE(_operation_update([_op(order_id="OC-1")]))
    assert _OPERATION_STRUCTURE(_operation_update([_op(order_id="OC-2")])) is True


# ---------------------------------------------------------------------------
# POSITION: solo la apertura de posición importa
# ---------------------------------------------------------------------------
def test_position_filtered_when_entry_unchanged():
    results = [
        _POSITION_OPEN(_position_update()),
        _POSITION_OPEN(_position_update(entry_price=65000.0)),
    ]
    assert results == [True, False]


def test_position_passes_for_new_position_key():
    _POSITION_OPEN(_position_update(symbol="BTCUSDT", side="LONG"))
    assert _POSITION_OPEN(_position_update(symbol="ETHUSDT", side="LONG")) is True
    assert _POSITION_OPEN(_position_update(symbol="BTCUSDT", side="SHORT")) is True


def test_position_passes_when_entry_changes():
    _POSITION_OPEN(_position_update(entry_price=65000.0))
    assert _POSITION_OPEN(_position_update(entry_price=66000.0)) is True


# ---------------------------------------------------------------------------
# Integración con el registry y el handler
# ---------------------------------------------------------------------------
def test_registry_uses_the_change_filters():
    assert HANDLER_REGISTRY[OperationUpdateEvent].filter is _OPERATION_STRUCTURE
    assert HANDLER_REGISTRY[PositionUpdateEvent].filter is _POSITION_OPEN


def test_price_ticks_are_still_skipped():
    from core.events import PriceTickEvent

    tick = PriceTickEvent(
        symbol="BTCUSDT", price=65000.0, change_pct=0.1,
        volume=1.0, high_24h=66000.0, low_24h=64000.0,
    )
    assert HANDLER_REGISTRY[PriceTickEvent].filter(tick) is False


def test_bot_signals_still_require_a_cross():
    from core.events import BotSignalEvent

    cfg = HANDLER_REGISTRY[BotSignalEvent]
    quiet = BotSignalEvent(
        symbol="BTCUSDT", signal="HOLD", changed=True,
        ma_fast=1.0, ma_slow=2.0, confidence=0.5,
    )
    crossed = BotSignalEvent(
        symbol="BTCUSDT", signal="BUY", changed=True,
        ma_fast=2.0, ma_slow=1.0, confidence=0.9,
    )
    assert cfg.filter(quiet) is False
    assert cfg.filter(crossed) is True


@pytest.mark.asyncio
async def test_operation_handler_publishes_only_on_change():
    config = HANDLER_REGISTRY[OperationUpdateEvent]
    handler = audit_service._make_handler(config)
    same_shape = [
        _operation_update([_op()], remaining=60.0),
        _operation_update([_op()], remaining=58.0),
        _operation_update([_op(state="PENDING")], remaining=57.0),
    ]

    with patch.object(audit_service, "_publish") as publish:
        for event in same_shape:
            await handler(event)

    assert publish.call_count == 2


@pytest.mark.asyncio
async def test_position_handler_publishes_only_on_open():
    config = HANDLER_REGISTRY[PositionUpdateEvent]
    handler = audit_service._make_handler(config)

    with patch.object(audit_service, "_publish") as publish:
        await handler(_position_update(entry_price=65000.0))
        await handler(_position_update(entry_price=65000.0))
        await handler(_position_update(entry_price=65000.0))
        await handler(_position_update(entry_price=67000.0))

    assert publish.call_count == 2
