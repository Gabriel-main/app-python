"""
Tests de persistencia de órdenes LIMIT: upsert PENDING → FILLED/CANCELLED.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.events import OrderCanceledEvent, OrderExecutedEvent, OrderPlacedEvent
from database.db_queue import db_queue
from database.models import Order


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


@pytest.mark.asyncio
async def test_save_order_placed_inserts_pending():
    session = _mock_session(existing=None)
    with patch("database.db_queue.get_session", return_value=_mock_ctx(session)):
        await db_queue._save_order_placed(OrderPlacedEvent(
            order_id="LIVE-1", operation_id="OC-1", symbol="BTCUSDT",
            side="BUY", quantity=0.001, price=65000.0, mode="LIVE",
        ))

    session.add.assert_called_once()
    order = session.add.call_args[0][0]
    assert isinstance(order, Order)
    assert order.status == "PENDING"
    assert order.order_type == "LIMIT"
    assert order.limit_price == 65000.0
    assert order.price == 65000.0


@pytest.mark.asyncio
async def test_save_order_fill_updates_existing_pending_row():
    """El fill de una LIMIT working debe actualizar la fila, no duplicarla."""
    existing = Order(
        order_id="LIVE-1", symbol="BTCUSDT", side="BUY", quantity=0.001,
        price=65000.0, mode="LIVE", order_type="LIMIT", status="PENDING",
        limit_price=65000.0,
    )
    session = _mock_session(existing=existing)
    with patch("database.db_queue.get_session", return_value=_mock_ctx(session)):
        await db_queue._save_order(OrderExecutedEvent(
            order_id="LIVE-1", symbol="BTCUSDT", side="BUY", quantity=0.001,
            price=64999.0, mode="LIVE", order_type="LIMIT",
            limit_price=65000.0, entry_price=65100.0,
        ))

    session.add.assert_not_called()   # upsert: no duplica
    assert existing.status == "FILLED"
    assert existing.price == 64999.0  # precio de fill
    assert existing.limit_price == 65000.0  # límite original conservado


@pytest.mark.asyncio
async def test_save_order_market_inserts_filled_directly():
    session = _mock_session(existing=None)
    with patch("database.db_queue.get_session", return_value=_mock_ctx(session)):
        await db_queue._save_order(OrderExecutedEvent(
            order_id="PAPER-2", symbol="BTCUSDT", side="SELL", quantity=0.001,
            price=65100.0, mode="PAPER", order_type="MARKET",
        ))

    session.add.assert_called_once()
    order = session.add.call_args[0][0]
    assert order.status == "FILLED"
    assert order.order_type == "MARKET"


@pytest.mark.asyncio
async def test_save_order_canceled_updates_status():
    existing = Order(
        order_id="LIVE-3", symbol="BTCUSDT", side="BUY", quantity=0.001,
        price=65000.0, mode="LIVE", order_type="LIMIT", status="PENDING",
        limit_price=65000.0,
    )
    session = _mock_session(existing=existing)
    with patch("database.db_queue.get_session", return_value=_mock_ctx(session)):
        await db_queue._save_order_canceled(OrderCanceledEvent(
            order_id="LIVE-3", operation_id="OC-1", reason="bot_stop",
            mode="LIVE",
        ))

    session.add.assert_not_called()
    assert existing.status == "CANCELLED"


@pytest.mark.asyncio
async def test_save_order_canceled_missing_row_skips_insert():
    session = _mock_session(existing=None)
    with patch("database.db_queue.get_session", return_value=_mock_ctx(session)):
        await db_queue._save_order_canceled(OrderCanceledEvent(
            order_id="GHOST", operation_id="OC-1", reason="bot_stop",
            mode="LIVE",
        ))

    session.add.assert_not_called()
    session.commit.assert_not_called()
