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


@pytest.mark.asyncio
async def test_binance_repo_get_symbol_price(mock_service):
    mock_service.get_symbol_price = AsyncMock(return_value=84996.0)
    repo = BinanceSymbolRepository(mock_service)
    assert await repo.get_symbol_price("BTCUSDT") == 84996.0
    mock_service.get_symbol_price.assert_awaited_once_with("BTCUSDT")


# ---------------------------------------------------------------------------
# get_max_leverage
# ---------------------------------------------------------------------------
from services.binance_service import BinanceService


def _mock_client(bracket_response):
    client = AsyncMock()
    client.futures_leverage_bracket = AsyncMock(return_value=bracket_response)
    return client


@pytest.mark.asyncio
async def test_get_max_leverage_futures_btcusdt():
    """BTCUSDT en FUTURES: primer bracket tiene initialLeverage=150."""
    response = [{
        "symbol": "BTCUSDT",
        "brackets": [
            {"bracket": 1, "initialLeverage": 150},
            {"bracket": 2, "initialLeverage": 100},
        ],
    }]
    client = _mock_client(response)
    result = await BinanceService.get_max_leverage(client, "BTCUSDT", "FUTURES")
    assert result == 150
    client.futures_leverage_bracket.assert_awaited_once_with(symbol="BTCUSDT")


@pytest.mark.asyncio
async def test_get_max_leverage_futures_lower():
    """Símbolo con máximo menor (ej: 50x)."""
    response = [{
        "symbol": "XRPUSDT",
        "brackets": [
            {"bracket": 1, "initialLeverage": 50},
        ],
    }]
    client = _mock_client(response)
    result = await BinanceService.get_max_leverage(client, "XRPUSDT", "FUTURES")
    assert result == 50


@pytest.mark.asyncio
async def test_get_max_leverage_futures_empty_fallback():
    """Respuesta vacía → fallback 20."""
    client = _mock_client([])
    result = await BinanceService.get_max_leverage(client, "BTCUSDT", "FUTURES")
    assert result == 20


@pytest.mark.asyncio
async def test_get_max_leverage_futures_exception_fallback():
    """Excepción de API → fallback 20."""
    client = AsyncMock()
    client.futures_leverage_bracket = AsyncMock(side_effect=Exception("network"))
    result = await BinanceService.get_max_leverage(client, "BTCUSDT", "FUTURES")
    assert result == 20


@pytest.mark.asyncio
async def test_get_max_leverage_margin():
    """MARGIN retorna 5."""
    client = _mock_client([])
    result = await BinanceService.get_max_leverage(client, "BTCUSDT", "MARGIN")
    assert result == 5


@pytest.mark.asyncio
async def test_get_max_leverage_spot():
    """SPOT retorna 1."""
    client = _mock_client([])
    result = await BinanceService.get_max_leverage(client, "BTCUSDT", "SPOT")
    assert result == 1
