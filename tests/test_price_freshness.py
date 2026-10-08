"""
Tests de frescura de precio y nuevos streams (Alcance B).

Cubre:
- PriceTickEvent.exchange_ts desde el campo E de Binance
- Parsers de @bookTicker y @markPrice@1s
- Transición CONNECTED → STALE → CONNECTED (solo en cambios)
- Demultiplex de combined streams y coarteo de TopOfBookEvent
- Mock: bid/ask y mark sintéticos para PAPER
"""
import asyncio
import time

import pytest
from unittest.mock import patch

from core.events import (
    ConnectionStatusEvent,
    MarkPriceEvent,
    PriceTickEvent,
    TopOfBookEvent,
)
from services.binance_service import (
    BOOK_TICKER_MIN_INTERVAL_S,
    BinanceService,
)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def test_tick_includes_exchange_ts_from_binance_E():
    svc = BinanceService()
    ev = svc._parse_binance_ticker({
        "s": "BTCUSDT", "c": "84502.40", "P": "-0.43",
        "q": "1", "h": "1", "l": "1", "E": 1791123565921,
    })
    assert ev.exchange_ts == pytest.approx(1791123565.921)
    assert ev.price == 84502.40
    assert isinstance(ev, PriceTickEvent)


def test_tick_falls_back_to_local_time_without_E():
    svc = BinanceService()
    before = time.time()
    ev = svc._parse_binance_ticker({"s": "BTCUSDT", "c": "1.0"})
    after = time.time()
    assert before <= ev.exchange_ts <= after


def test_parse_book_ticker():
    ev = BinanceService._parse_book_ticker({
        "s": "BTCUSDT", "b": "84540.2", "B": "1.5", "a": "84540.3", "A": "2.0",
    })
    assert isinstance(ev, TopOfBookEvent)
    assert ev.bid == 84540.2
    assert ev.ask == 84540.3
    assert ev.bid_qty == 1.5
    assert ev.ask_qty == 2.0
    assert ev.symbol == "BTCUSDT"


def test_parse_book_ticker_invalid_returns_none():
    assert BinanceService._parse_book_ticker({"s": "X", "b": "not-a-number"}) is None


def test_parse_mark_price():
    ev = BinanceService._parse_mark_price({
        "e": "markPriceUpdate", "E": 1791123565921, "s": "BTCUSDT",
        "p": "84510.1", "i": "84543.7", "r": "0.0001", "T": 1791129600000,
    })
    assert isinstance(ev, MarkPriceEvent)
    assert ev.mark_price == 84510.1
    assert ev.index_price == 84543.7
    assert ev.funding_rate == 0.0001
    assert ev.next_funding_ts == pytest.approx(1791129600.0)
    assert ev.exchange_ts == pytest.approx(1791123565.921)


def test_parse_mark_price_invalid_returns_none():
    assert BinanceService._parse_mark_price({"s": "X", "p": "abc"}) is None


# ---------------------------------------------------------------------------
# Transición STALE (push, solo en cambios)
# ---------------------------------------------------------------------------

def test_stale_publishes_only_on_transition():
    svc = BinanceService()
    with patch("services.binance_service.event_bus") as bus, \
         patch("services.binance_service.settings") as m:
        m.TRADING_SYMBOL = "BTCUSDT"
        m.TRADING_TYPE = "FUTURES"
        svc._connection_status = "CONNECTED"

        svc._publish_stale()
        svc._publish_stale()  # duplicado → sin segundo evento

        events = [c.args[0] for c in bus.publish.call_args_list]
        stale = [e for e in events if isinstance(e, ConnectionStatusEvent)]
        assert len(stale) == 1
        assert stale[0].status == "STALE"
        assert "Sin datos" in stale[0].message
        assert svc._connection_status == "STALE"

        svc._recover_from_stale()
        svc._recover_from_stale()  # duplicado → sin segundo evento

        events = [c.args[0] for c in bus.publish.call_args_list]
        conn = [e for e in events if isinstance(e, ConnectionStatusEvent)]
        assert [e.status for e in conn] == ["STALE", "CONNECTED"]
        assert svc._connection_status == "CONNECTED"


def test_recover_without_stale_is_noop():
    svc = BinanceService()
    with patch("services.binance_service.event_bus") as bus:
        svc._connection_status = "CONNECTED"
        svc._recover_from_stale()
        assert bus.publish.call_count == 0


def test_status_message_for_stale():
    svc = BinanceService()
    svc._connection_status = "STALE"
    assert "Sin datos" in svc._get_status_message()


# ---------------------------------------------------------------------------
# Demultiplex y coarteo de bookTicker
# ---------------------------------------------------------------------------

def test_dispatch_book_mark_demux():
    svc = BinanceService()
    with patch("services.binance_service.event_bus") as bus:
        svc._last_book_pub = 0.0
        svc._dispatch_book_mark({
            "stream": "btcusdt@bookTicker",
            "data": {"s": "BTCUSDT", "b": "1", "B": "1", "a": "2", "A": "1"},
        })
        svc._dispatch_book_mark({
            "stream": "btcusdt@markPrice@1s",
            "data": {
                "e": "markPriceUpdate", "s": "BTCUSDT",
                "p": "3", "i": "4", "r": "0.0001", "T": 0,
            },
        })
        events = [c.args[0] for c in bus.publish.call_args_list]
        assert any(isinstance(e, TopOfBookEvent) for e in events)
        assert any(isinstance(e, MarkPriceEvent) for e in events)


def test_book_ticker_throttle_drops_bursts():
    svc = BinanceService()
    with patch("services.binance_service.event_bus") as bus:
        # Ventana abierta → el mensaje se descarta (coarteo al receipt)
        svc._last_book_pub = time.monotonic()
        svc._publish_top_of_book({"s": "BTCUSDT", "b": "1", "a": "2"})
        assert bus.publish.call_count == 0

        # Ventana cerrada → publica
        svc._last_book_pub = time.monotonic() - (BOOK_TICKER_MIN_INTERVAL_S + 0.05)
        svc._publish_top_of_book({"s": "BTCUSDT", "b": "5", "a": "6"})
        assert bus.publish.call_count == 1
        published = bus.publish.call_args_list[0].args[0]
        assert isinstance(published, TopOfBookEvent)
        assert published.bid == 5.0


def test_unknown_stream_is_ignored():
    svc = BinanceService()
    with patch("services.binance_service.event_bus") as bus:
        svc._dispatch_book_mark({"stream": "btcusdt@aggTrade", "data": {"e": "aggTrade"}})
        assert bus.publish.call_count == 0


# ---------------------------------------------------------------------------
# Mock (PAPER): UI completa sin red
# ---------------------------------------------------------------------------

def test_mock_book_mark_futures():
    svc = BinanceService()
    with patch("services.binance_service.event_bus") as bus, \
         patch("services.binance_service.settings") as m:
        m.TRADING_SYMBOL = "BTCUSDT"
        m.TRADING_TYPE = "FUTURES"
        svc._publish_mock_book_mark(84500.0)

        events = [c.args[0] for c in bus.publish.call_args_list]
        book = [e for e in events if isinstance(e, TopOfBookEvent)]
        mark = [e for e in events if isinstance(e, MarkPriceEvent)]
        assert len(book) == 1 and len(mark) == 1
        assert book[0].bid == 84499.5
        assert book[0].ask == 84500.5
        assert mark[0].mark_price == 84500.0
        assert mark[0].index_price == 84500.0


def test_mock_book_mark_spot_skips_mark_event():
    svc = BinanceService()
    with patch("services.binance_service.event_bus") as bus, \
         patch("services.binance_service.settings") as m:
        m.TRADING_SYMBOL = "BTCUSDT"
        m.TRADING_TYPE = "SPOT"
        svc._publish_mock_book_mark(100.0)

        events = [c.args[0] for c in bus.publish.call_args_list]
        assert any(isinstance(e, TopOfBookEvent) for e in events)
        assert not any(isinstance(e, MarkPriceEvent) for e in events)


# ---------------------------------------------------------------------------
# Integración: loop _run_live_stream → STALE por silencio → recuperación
# ---------------------------------------------------------------------------

class _FakeSocket:
    """Socket falso: entrega mensajes encolados, se silencia a pedido."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def recv(self):
        return await self._queue.get()

    def feed(self, msg: dict) -> None:
        self._queue.put_nowait(msg)


class _FakeClient:
    async def close_connection(self):
        pass


def _ticker_msg(price: str = "84502.40") -> dict:
    return {
        "e": "24hrTicker", "E": 1791123565921, "s": "BTCUSDT",
        "c": price, "P": "-0.43", "q": "1", "h": "1", "l": "1",
    }


async def _wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condición no alcanzada a tiempo")


@pytest.mark.asyncio
async def test_live_stream_emits_stale_on_silence_and_recovers():
    """Silencio > umbral → STALE; primer tick posterior → CONNECTED."""
    from services import binance_service as bs

    svc = bs.BinanceService()
    svc._running = True
    fake_socket = _FakeSocket()

    class _FakeManager:
        def __init__(self, client, max_queue_size=100):
            assert max_queue_size >= 5000, "colas pequeñas rebotan en ráfagas"

        def individual_symbol_ticker_futures_socket(self, symbol):
            return fake_socket

        def symbol_ticker_socket(self, symbol):
            return fake_socket

    with patch("services.binance_service.event_bus") as bus, \
         patch("services.binance_service.settings") as m, \
         patch("services.binance_service.db_queue"), \
         patch.object(bs, "TICK_STALE_AFTER_S", 0.1), \
         patch("binance.BinanceSocketManager", _FakeManager), \
         patch("services.binance_client.create_client", _make_client), \
         patch.object(BinanceService, "_validate_symbol", _always_true):

        m.TRADING_SYMBOL = "BTCUSDT"
        m.TRADING_TYPE = "FUTURES"

        def statuses():
            return [
                c.args[0].status
                for c in bus.publish.call_args_list
                if isinstance(c.args[0], ConnectionStatusEvent)
            ]

        task = asyncio.create_task(svc._run_live_stream())
        try:
            # 1) tick inicial → CONNECTED + PriceTickEvent
            fake_socket.feed(_ticker_msg())
            await _wait_until(
                lambda: "CONNECTED" in statuses()
                and any(
                    isinstance(c.args[0], PriceTickEvent)
                    for c in bus.publish.call_args_list
                )
            )

            # 2) silencio > umbral → STALE (una sola vez)
            await _wait_until(lambda: "STALE" in statuses(), timeout=2.0)
            assert statuses().count("STALE") == 1
            await asyncio.sleep(0.3)
            assert statuses().count("STALE") == 1  # sin spam durante el silencio

            # 3) tick posterior → CONNECTED (recuperación única)
            fake_socket.feed(_ticker_msg(price="84510.00"))
            await _wait_until(lambda: statuses().count("CONNECTED") == 2)
            assert statuses()[-1] == "CONNECTED"
        finally:
            svc._running = False
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


async def _make_client():
    return _FakeClient()


async def _always_true(self, client) -> bool:
    return True
