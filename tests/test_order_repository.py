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
