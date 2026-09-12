"""
Tests para SymbolRepository — Abstracción de acceso a símbolos.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from services.symbol_repository import BinanceSymbolRepository


@pytest.fixture
def mock_service():
    service = AsyncMock()
    service.get_trading_symbols = AsyncMock(return_value=[
        {"symbol": "BTCUSDT", "base_asset": "BTC", "quote_asset": "USDT", "price": "65000.00"},
        {"symbol": "ETHUSDT", "base_asset": "ETH", "quote_asset": "USDT", "price": "3500.00"},
    ])
    service.clear_symbols_cache = MagicMock()
    return service


@pytest.mark.asyncio
async def test_binance_repo_get_symbols(mock_service):
    repo = BinanceSymbolRepository(mock_service)
    symbols = await repo.get_trading_symbols()
    assert len(symbols) == 2
    assert symbols[0]["symbol"] == "BTCUSDT"
    mock_service.get_trading_symbols.assert_awaited_once()


def test_binance_repo_clear_cache(mock_service):
    repo = BinanceSymbolRepository(mock_service)
    repo.clear_cache()
    mock_service.clear_symbols_cache.assert_called_once()
