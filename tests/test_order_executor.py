"""
Tests para OrderExecutor — execute(OrderRequest) MARKET/LIMIT (Fase 1).
"""
import pytest
from unittest.mock import patch

from services.order_executor import (
    OrderPlacement,
    OrderRequest,
    PaperExecutor,
    build_order_params,
    is_limit_crossed,
)


# ---------------------------------------------------------------------------
# is_limit_crossed — función pura compartida (DRY)
# ---------------------------------------------------------------------------
def test_is_limit_crossed_buy_below_market():
    """BUY limit ejecutable cuando el mercado <= límite."""
    assert is_limit_crossed("BUY", 65000.0, 64000.0) is True
    assert is_limit_crossed("BUY", 65000.0, 65000.0) is True
    assert is_limit_crossed("BUY", 65000.0, 66000.0) is False


def test_is_limit_crossed_sell_above_market():
    """SELL limit ejecutable cuando el mercado >= límite."""
    assert is_limit_crossed("SELL", 65000.0, 66000.0) is True
    assert is_limit_crossed("SELL", 65000.0, 65000.0) is True
    assert is_limit_crossed("SELL", 65000.0, 64000.0) is False


def test_is_limit_crossed_invalid_inputs():
    assert is_limit_crossed("BUY", 0.0, 65000.0) is False
    assert is_limit_crossed("BUY", 65000.0, 0.0) is False


# ---------------------------------------------------------------------------
# build_order_params — única fuente del payload a Binance
# ---------------------------------------------------------------------------
def test_build_order_params_market():
    req = OrderRequest(
        symbol="BTCUSDT", side="BUY", quantity=0.001,
        order_type="MARKET", client_order_id="LIVE-ABC",
    )
    params = build_order_params(req)
    assert params["type"] == "MARKET"
    assert "price" not in params
    assert "timeInForce" not in params
    assert params["newClientOrderId"] == "LIVE-ABC"
    assert params["symbol"] == "BTCUSDT"
    assert params["side"] == "BUY"
    assert params["quantity"] == 0.001


def test_build_order_params_limit():
    req = OrderRequest(
        symbol="BTCUSDT", side="BUY", quantity=0.001,
        order_type="LIMIT", price=65000.0, client_order_id="LIVE-DEF",
    )
    params = build_order_params(req)
    assert params["type"] == "LIMIT"
    assert params["price"] == 65000.0
    assert params["timeInForce"] == "GTC"
    assert params["newClientOrderId"] == "LIVE-DEF"


# ---------------------------------------------------------------------------
# PaperExecutor.execute
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_paper_market_always_filled():
    executor = PaperExecutor()
    req = OrderRequest(
        symbol="BTCUSDT", side="BUY", quantity=0.001,
        order_type="MARKET", entry_price=65000.0,
        client_order_id="PAPER-1", market_price=66000.0,
    )
    placement = await executor.execute(req)
    assert placement.status == "FILLED"
    assert placement.fill_price == 65000.0
    assert placement.mode == "PAPER"
    assert placement.order_id == "PAPER-1"


@pytest.mark.asyncio
async def test_paper_limit_not_crossed_returns_new():
    """BUY limit por debajo del mercado → orden working (NEW)."""
    executor = PaperExecutor()
    req = OrderRequest(
        symbol="BTCUSDT", side="BUY", quantity=0.001,
        order_type="LIMIT", price=65000.0,
        client_order_id="PAPER-2", market_price=66000.0,
    )
    placement = await executor.execute(req)
    assert placement.status == "NEW"
    assert placement.fill_price == 0.0
    assert placement.order_id == "PAPER-2"


@pytest.mark.asyncio
async def test_paper_limit_crossed_fills_immediately():
    """BUY limit ya cruzado por el mercado → FILLED al colocar."""
    executor = PaperExecutor()
    req = OrderRequest(
        symbol="BTCUSDT", side="BUY", quantity=0.001,
        order_type="LIMIT", price=65000.0,
        client_order_id="PAPER-3", market_price=64000.0,
    )
    placement = await executor.execute(req)
    assert placement.status == "FILLED"
    assert placement.fill_price == 64000.0  # fill a precio de mercado


@pytest.mark.asyncio
async def test_paper_cancel_is_noop():
    executor = PaperExecutor()
    await executor.cancel("PAPER-4")  # no debe lanzar


# ---------------------------------------------------------------------------
# LiveExecutor._extract_fill_price (puro, sin red)
# ---------------------------------------------------------------------------
def test_extract_fill_price_futures_avg():
    from services.order_executor import LiveExecutor
    req = OrderRequest(symbol="BTCUSDT", side="BUY", quantity=1.0, order_type="LIMIT", price=65000.0)
    assert LiveExecutor._extract_fill_price({"avgPrice": "64999.5"}, req) == 64999.5


def test_extract_fill_price_spot_limit_quotient():
    from services.order_executor import LiveExecutor
    req = OrderRequest(symbol="BTCUSDT", side="BUY", quantity=1.0, order_type="LIMIT", price=65000.0)
    resp = {"executedQty": "2.0", "cummulativeQuoteQty": "130000.0"}
    assert LiveExecutor._extract_fill_price(resp, req) == 65000.0


def test_extract_fill_price_market_fills():
    from services.order_executor import LiveExecutor
    req = OrderRequest(symbol="BTCUSDT", side="BUY", quantity=1.0, order_type="MARKET", entry_price=64000.0)
    resp = {"fills": [{"price": "65123.4"}]}
    assert LiveExecutor._extract_fill_price(resp, req) == 65123.4
