"""
Tests para OrderRepository — Acceso a datos de órdenes.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from repositories.order_repository import SQLOrderRepository


@pytest.mark.asyncio
async def test_get_recent_orders_empty():
    repo = SQLOrderRepository()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_session.exec = AsyncMock(return_value=mock_result)

    with patch("repositories.order_repository.get_session") as mock_get:
        mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get.return_value.__aexit__ = AsyncMock(return_value=False)
        orders = await repo.get_recent_orders()
        assert orders == []


@pytest.mark.asyncio
async def test_save_from_event():
    from core.events import OrderExecutedEvent
    repo = SQLOrderRepository()
    mock_session = AsyncMock()

    event = OrderExecutedEvent(
        order_id="test-001",
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.001,
        price=65000.0,
        mode="PAPER",
    )

    with patch("repositories.order_repository.get_session") as mock_get:
        mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get.return_value.__aexit__ = AsyncMock(return_value=False)
        await repo.save_from_event(event)
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
