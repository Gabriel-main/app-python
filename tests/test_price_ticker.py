"""
Tests de PriceTicker — precio, bid/ask y frescura (STALE).
"""
import pytest

from core.events import ConnectionStatusEvent, PriceTickEvent, TopOfBookEvent
from ui.components.price_ticker import PriceTicker


def _tick(symbol: str = "BTCUSDT", price: float = 84500.0, change: float = -0.43) -> PriceTickEvent:
    return PriceTickEvent(
        symbol=symbol, price=price, change_pct=change,
        volume=1.0, high_24h=1.0, low_24h=1.0,
    )


def _book(symbol: str = "BTCUSDT", bid: float = 84540.2, ask: float = 84540.3) -> TopOfBookEvent:
    return TopOfBookEvent(symbol=symbol, bid=bid, bid_qty=1.0, ask=ask, ask_qty=1.0)


def test_initial_state():
    t = PriceTicker("BTCUSDT")
    assert t._price_text.value == "---"
    assert t._bid_text.value == "Venta ---"
    assert t._ask_text.value == "Compra ---"
    assert t._fresh_chip.content.value == "esperando"
    assert t._stale is False


@pytest.mark.asyncio
async def test_tick_updates_price_and_live_chip():
    t = PriceTicker("BTCUSDT")
    await t._on_price_tick(_tick())
    assert t._price_text.value == "$84,500.00"
    assert t._fresh_chip.content.value == "en vivo"


@pytest.mark.asyncio
async def test_tick_from_other_symbol_is_ignored():
    t = PriceTicker("BTCUSDT")
    await t._on_price_tick(_tick(symbol="ETHUSDT", price=3000.0))
    assert t._price_text.value == "---"
    assert t._fresh_chip.content.value == "esperando"


@pytest.mark.asyncio
async def test_top_of_book_updates_bid_ask():
    t = PriceTicker("BTCUSDT")
    await t._on_top_of_book(_book())
    assert t._bid_text.value == "Venta 84,540.20"
    assert t._ask_text.value == "Compra 84,540.30"


@pytest.mark.asyncio
async def test_top_of_book_filters_symbol():
    t = PriceTicker("BTCUSDT")
    await t._on_top_of_book(_book(symbol="ETHUSDT"))
    assert t._bid_text.value == "Venta ---"


@pytest.mark.asyncio
async def test_stale_dims_price_and_shows_badge():
    t = PriceTicker("BTCUSDT")
    await t._on_price_tick(_tick())

    await t._on_connection_status(ConnectionStatusEvent(status="STALE", message="Sin datos"))
    assert t._stale is True
    assert t._price_text.opacity == 0.4
    assert t._book_row.opacity == 0.4
    assert t._fresh_chip.content.value == "sin datos"
    # El precio NO se borra: se atenúa (la UI no presenta el valor como vivo)
    assert t._price_text.value == "$84,500.00"


@pytest.mark.asyncio
async def test_recover_from_stale_restores_state():
    t = PriceTicker("BTCUSDT")
    await t._on_price_tick(_tick())
    await t._on_connection_status(ConnectionStatusEvent(status="STALE"))
    await t._on_connection_status(ConnectionStatusEvent(status="CONNECTED"))

    assert t._stale is False
    assert t._price_text.opacity == 1.0
    assert t._book_row.opacity == 1.0
    assert t._fresh_chip.content.value == "en vivo"


@pytest.mark.asyncio
async def test_recover_before_first_tick_shows_awaiting():
    t = PriceTicker("BTCUSDT")
    await t._on_connection_status(ConnectionStatusEvent(status="STALE"))
    await t._on_connection_status(ConnectionStatusEvent(status="CONNECTED"))
    assert t._fresh_chip.content.value == "esperando"


@pytest.mark.asyncio
async def test_stale_while_no_price_keeps_awaiting_on_recover():
    """STALE sin tick previo no debe pintar 'en vivo' al recuperarse."""
    t = PriceTicker("BTCUSDT")
    await t._on_connection_status(ConnectionStatusEvent(status="STALE"))
    await t._on_connection_status(ConnectionStatusEvent(status="STALE"))  # duplicado
    await t._on_connection_status(ConnectionStatusEvent(status="CONNECTED"))
    assert t._fresh_chip.content.value == "esperando"


def test_symbol_change_resets_book_and_freshness():
    t = PriceTicker("BTCUSDT")
    t._bid_text.value = "Venta 1.0"
    t._ask_text.value = "Compra 1.0"
    t._stale = True
    t._price_text.opacity = 0.4

    t._on_symbol_changed("ETHUSDT")

    assert t._bid_text.value == "Venta ---"
    assert t._ask_text.value == "Compra ---"
    assert t._fresh_chip.content.value == "esperando"
    assert t._stale is False
    assert t._price_text.opacity == 1.0
