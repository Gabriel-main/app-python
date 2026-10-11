"""
Tests para OrderExecutor — execute(OrderRequest) MARKET/LIMIT (Fase 1).
"""
import pytest
from unittest.mock import AsyncMock, patch

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


def test_build_order_params_requests_full_response():
    """RESULT hace que Futures devuelva status=FILLED + avgPrice para MARKET.

    Sin esto el ACK responde status=NEW y la orden quedaría registrada como
    working con price=0 (violación del contrato de OrderExecutor.execute).
    """
    for order_type, price in (("MARKET", 0.0), ("LIMIT", 65000.0)):
        req = OrderRequest(
            symbol="BTCUSDT", side="BUY", quantity=0.001,
            order_type=order_type, price=price, client_order_id="LIVE-XYZ",
        )
        assert build_order_params(req)["newOrderRespType"] == "RESULT"


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


# ---------------------------------------------------------------------------
# LiveExecutor._ensure_position_mode — Hedge → One-Way (regresión -4061)
# ---------------------------------------------------------------------------
def _api_error(code: int, msg: str):
    from binance.exceptions import BinanceAPIException

    class _FakeResponse:
        pass

    return BinanceAPIException(
        _FakeResponse(), 400, f'{{"code": {code}, "msg": "{msg}"}}',
    )


def _mock_futures_client(dual: str = "false") -> AsyncMock:
    """Cliente Futures mockeado (DRY): posición + leverage en un solo lugar."""
    client = AsyncMock()
    client.futures_get_position_mode = AsyncMock(
        return_value={"dualSidePosition": dual},
    )
    client.futures_change_position_mode = AsyncMock()
    client.futures_change_leverage = AsyncMock()
    return client


def _executor_with_client(dual: str):
    from services.order_executor import LiveExecutor

    ex = LiveExecutor()
    ex._client = _mock_futures_client(dual)
    return ex


def test_is_hedge_mode_normalizes_bool_and_str():
    """dualSidePosition llega como 'true'/'false' (str) o bool según versión."""
    from services.order_executor import LiveExecutor

    assert LiveExecutor._is_hedge_mode({"dualSidePosition": "true"}) is True
    assert LiveExecutor._is_hedge_mode({"dualSidePosition": True}) is True
    assert LiveExecutor._is_hedge_mode({"dualSidePosition": "false"}) is False
    assert LiveExecutor._is_hedge_mode({}) is False


@pytest.mark.asyncio
async def test_position_mode_oneway_is_noop():
    ex = _executor_with_client("false")
    await ex._ensure_position_mode()
    ex._client.futures_change_position_mode.assert_not_awaited()
    assert ex._position_mode_set is True


@pytest.mark.asyncio
async def test_position_mode_hedge_is_switched():
    """Regresión en vivo: cuenta en Hedge → el bot la pone en One-Way."""
    ex = _executor_with_client("true")
    await ex._ensure_position_mode()
    ex._client.futures_change_position_mode.assert_awaited_once_with(
        dualSidePosition="false",
    )
    assert ex._position_mode_set is True


@pytest.mark.asyncio
async def test_position_mode_hedge_with_open_positions_blocks():
    """-4060 (posiciones abiertas): error accionable, bandera sin poner."""
    ex = _executor_with_client("true")
    ex._client.futures_change_position_mode = AsyncMock(
        side_effect=_api_error(-4060, "Position side not valid."),
    )
    with pytest.raises(RuntimeError, match="One-Way"):
        await ex._ensure_position_mode()
    assert ex._position_mode_set is False


@pytest.mark.asyncio
async def test_position_mode_race_4059_is_success():
    """-4059 'No need to change': carrera — ya era One-Way."""
    ex = _executor_with_client("true")
    ex._client.futures_change_position_mode = AsyncMock(
        side_effect=_api_error(-4059, "No need to change position side."),
    )
    await ex._ensure_position_mode()
    assert ex._position_mode_set is True


@pytest.mark.asyncio
async def test_execute_ensures_position_mode_before_leverage():
    """El modo de posición se resuelve ANTES de la primera orden/leverage."""
    from services.order_executor import LiveExecutor

    ex = LiveExecutor()
    mock_client = _mock_futures_client("false")
    order_resp = {
        "status": "FILLED", "avgPrice": "110.0",
        "executedQty": "0.05", "cummulativeQuoteQty": "5.5",
    }
    req = OrderRequest(
        symbol="SOLUSDT", side="BUY", quantity=0.05,
        order_type="MARKET", client_order_id="LIVE-PM01",
        entry_price=110.0,
    )
    with patch("services.binance_client.create_client",
               AsyncMock(return_value=mock_client)), \
         patch("services.binance_client.execute_order",
               AsyncMock(return_value=order_resp)), \
         patch("services.order_executor.settings") as s:
        s.TRADING_TYPE = "FUTURES"
        s.TRADING_SYMBOL = "SOLUSDT"
        s.LEVERAGE = 10
        placement = await ex.execute(req)

    mock_client.futures_get_position_mode.assert_awaited_once()
    mock_client.futures_change_leverage.assert_awaited_once()
    assert placement.status == "FILLED"
    assert placement.fill_price == 110.0
