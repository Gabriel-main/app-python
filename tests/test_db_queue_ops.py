"""
Tests de persistencia de operaciones y posiciones en DBQueueWorker.

Regresiones de los bugs huérfanos:
- symbol: la fila debe guardar EL SÍMBOLO REAL (op.symbol / fallback
  TRADING_SYMBOL) — jamás el prefijo OC/OV del order_id ni el de
  operations[0] (360 filas históricas corruptas).
- pnl: solo se llena con cierre real (SL); None no pisa un valor ya
  persistido.
- positions: _save_position_update refresca quantity/entry_price al
  re-entrar; _save_position_closed es el ÚNICO camino a CLOSED.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.events import (
    OperationState,
    OperationUpdateEvent,
    PositionClosedEvent,
    PositionUpdateEvent,
)
from database.db_queue import db_queue
from database.models import Operation, Position


def _mock_session(existing=None):
    session = MagicMock()
    result = MagicMock()
    result.first.return_value = existing
    session.exec = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _mock_ctx(session):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _op_state(order_id="OC-1", symbol="BTCUSDT", state="ACTIVE",
              pnl=None, side="BUY"):
    return OperationState(
        side=side, state=state, entry_price=65100.0, stop_loss=64900.0,
        quantity=0.001, order_id=order_id, symbol=symbol, pnl=pnl,
    )


def _update(*ops):
    return OperationUpdateEvent(operations=list(ops))


def _settings(symbol="BTCUSDT", trading_type="SPOT", mode="PAPER",
               currency="USDT"):
    m = MagicMock()
    m.TRADING_SYMBOL = symbol
    m.TRADING_TYPE = trading_type
    m.TRADING_MODE = mode
    m.TRADE_CURRENCY = currency
    return m


def _pos_event(side="LONG", quantity=0.002, entry=65000.0):
    return PositionUpdateEvent(
        symbol="BTCUSDT", side=side, quantity=quantity, entry_price=entry,
        mark_price=entry + 5, unrealized_pnl=0.4, leverage=1,
        trading_type="FUTURES",
    )


# ---------------------------------------------------------------------------
# operations: symbol real (regresión del bug OC/OV)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_symbol_is_real_even_with_oc_prefix_order_id():
    """El símbolo persistido NUNCA deriva del prefijo del order_id."""
    existing = Operation(
        order_id="OC-1", symbol="OC", side="BUY", state="ACTIVE",
        entry_price=65100.0, stop_loss=64900.0, quantity=0.001,
    )
    session = _mock_session(existing=existing)
    with patch("database.db_queue.get_session", return_value=_mock_ctx(session)), \
         patch("database.db_queue.settings", _settings()):
        await db_queue._save_operation_update(_update(_op_state()))

    assert existing.symbol == "BTCUSDT"
    session.add.assert_not_called()   # update, no insert


@pytest.mark.asyncio
async def test_symbol_falls_back_to_trading_symbol_when_empty():
    session = _mock_session(existing=None)
    with patch("database.db_queue.get_session", return_value=_mock_ctx(session)), \
         patch("database.db_queue.settings", _settings(symbol="ETHUSDT")):
        await db_queue._save_operation_update(
            _update(_op_state(symbol=""))
        )

    new_op = session.add.call_args[0][0]
    assert new_op.symbol == "ETHUSDT"


@pytest.mark.asyncio
async def test_symbol_not_taken_from_first_operation():
    """Regresión: symbol debe venir de CADA op, no de operations[0]."""
    first = Operation(
        order_id="OC-1", symbol="STALE", side="BUY", state="ACTIVE",
        entry_price=65100.0, stop_loss=64900.0, quantity=0.001,
    )
    second = Operation(
        order_id="OV-2", symbol="STALE", side="SELL", state="ACTIVE",
        entry_price=64900.0, stop_loss=65100.0, quantity=0.001,
    )
    session = MagicMock()
    results = []
    for existing in (first, second):
        r = MagicMock()
        r.first.return_value = existing
        results.append(r)
    session.exec = AsyncMock(side_effect=results)
    session.add = MagicMock()
    session.commit = AsyncMock()

    with patch("database.db_queue.get_session", return_value=_mock_ctx(session)), \
         patch("database.db_queue.settings", _settings(symbol="BTCUSDT")):
        await db_queue._save_operation_update(_update(
            _op_state(order_id="OC-1", symbol="BTCUSDT"),
            _op_state(order_id="OV-2", symbol="ETHUSDT", side="SELL"),
        ))

    assert first.symbol == "BTCUSDT"
    assert second.symbol == "ETHUSDT"


# ---------------------------------------------------------------------------
# operations: pnl (D2) — solo con cierre real
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pnl_persisted_on_past_close():
    existing = Operation(
        order_id="OC-1", symbol="BTCUSDT", side="BUY", state="ACTIVE",
        entry_price=65100.0, stop_loss=64900.0, quantity=0.001,
        pnl=None, closed_at=None,
    )
    session = _mock_session(existing=existing)
    with patch("database.db_queue.get_session", return_value=_mock_ctx(session)), \
         patch("database.db_queue.settings", _settings()):
        await db_queue._save_operation_update(
            _update(_op_state(state="PAST", pnl=-0.42))
        )

    assert existing.pnl == pytest.approx(-0.42)
    assert existing.state == "PAST"
    assert existing.closed_at is not None   # se marca en la transición a PAST


@pytest.mark.asyncio
async def test_none_pnl_does_not_erase_persisted_value():
    """Retiro por stop (Q3): pnl None no debe pisar un valor ya guardado."""
    existing = Operation(
        order_id="OC-1", symbol="BTCUSDT", side="BUY", state="PAST",
        entry_price=65100.0, stop_loss=64900.0, quantity=0.001,
        pnl=0.75, closed_at=123.0,
    )
    session = _mock_session(existing=existing)
    with patch("database.db_queue.get_session", return_value=_mock_ctx(session)), \
         patch("database.db_queue.settings", _settings()):
        await db_queue._save_operation_update(_update(_op_state(state="PAST")))

    assert existing.pnl == pytest.approx(0.75)
    assert existing.closed_at == 123.0     # no se re-borra


@pytest.mark.asyncio
async def test_insert_carries_symbol_and_pnl():
    session = _mock_session(existing=None)
    with patch("database.db_queue.get_session", return_value=_mock_ctx(session)), \
         patch("database.db_queue.settings", _settings()):
        await db_queue._save_operation_update(
            _update(_op_state(order_id="OV-9", side="SELL",
                              state="PAST", pnl=1.25))
        )

    new_op = session.add.call_args[0][0]
    assert isinstance(new_op, Operation)
    assert new_op.symbol == "BTCUSDT"
    assert new_op.pnl == pytest.approx(1.25)
    session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# positions: update refresca quantity/entry_price (bug stale)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_position_update_refreshes_quantity_and_entry_price():
    stale = Position(
        symbol="BTCUSDT", side="LONG", quantity=0.001, entry_price=60000.0,
        mark_price=65000.0, unrealized_pnl=5.0, leverage=1,
        trading_type="FUTURES", status="OPEN",
    )
    session = _mock_session(existing=stale)
    with patch("database.db_queue.get_session", return_value=_mock_ctx(session)):
        await db_queue._save_position_update(_pos_event(
            quantity=0.002, entry=65000.0,
        ))

    assert stale.quantity == pytest.approx(0.002)
    assert stale.entry_price == pytest.approx(65000.0)
    assert stale.mark_price == pytest.approx(65005.0)
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_position_update_inserts_when_no_open_row():
    session = _mock_session(existing=None)
    with patch("database.db_queue.get_session", return_value=_mock_ctx(session)):
        await db_queue._save_position_update(_pos_event())

    new_pos = session.add.call_args[0][0]
    assert isinstance(new_pos, Position)
    assert new_pos.status == "OPEN"


# ---------------------------------------------------------------------------
# positions: cierre — único camino a CLOSED
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_position_closed_marks_row_closed():
    row = Position(
        symbol="BTCUSDT", side="LONG", quantity=0.001, entry_price=65000.0,
        mark_price=65200.0, unrealized_pnl=0.9, leverage=1,
        trading_type="FUTURES", status="OPEN",
    )
    session = _mock_session(existing=row)
    event = PositionClosedEvent(
        symbol="BTCUSDT", side="LONG", closed_price=65300.0, closed_pnl=1.1,
    )
    with patch("database.db_queue.get_session", return_value=_mock_ctx(session)):
        await db_queue._save_position_closed(event)

    assert row.status == "CLOSED"
    assert row.closed_price == pytest.approx(65300.0)
    assert row.closed_pnl == pytest.approx(1.1)
    assert row.closed_at == event.timestamp
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_position_closed_without_open_row_is_noop():
    """Idempotente: sin fila OPEN no inserta ni committea."""
    session = _mock_session(existing=None)
    event = PositionClosedEvent(
        symbol="BTCUSDT", side="SHORT", closed_price=64900.0,
    )
    with patch("database.db_queue.get_session", return_value=_mock_ctx(session)):
        await db_queue._save_position_closed(event)

    session.add.assert_not_called()
    session.commit.assert_not_called()
