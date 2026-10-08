"""
Tests del ciclo de vida de BinanceService (T1.4).

Cubre: restarts concurrentes serializados por el lock (sin doble stream).
"""
import asyncio
from unittest.mock import patch

import pytest

from services.binance_service import BinanceService


async def _fake_reconnect(self, runner, publish_status: bool = True):
    """Runner infinito reemplazado en tests (sin red)."""
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        raise


async def _noop_async(self) -> None:
    return None


def _no_sync(self) -> None:
    return None


@pytest.mark.asyncio
async def test_concurrent_restarts_leave_single_stream_task():
    """Dos SettingsUpdatedEvent solapados no deben dejar dos streams vivos."""
    svc = BinanceService()

    with patch("services.binance_service.event_bus"), \
         patch.object(BinanceService, "_run_with_reconnect", _fake_reconnect), \
         patch.object(BinanceService, "_start_balance_loop", _no_sync), \
         patch.object(BinanceService, "_stop_balance_loop", _no_sync), \
         patch.object(BinanceService, "_start_user_stream", _no_sync), \
         patch.object(BinanceService, "_stop_user_stream", _noop_async):

        await asyncio.gather(svc.restart(), svc.restart(), svc.restart())

        alive = [
            t for t in asyncio.all_tasks()
            if t.get_name() == "binance_stream" and not t.done()
        ]
        assert len(alive) == 1, f"streams vivos: {len(alive)} (esperado 1)"
        assert svc._running is True

        await svc.stop()
        assert not [
            t for t in asyncio.all_tasks()
            if t.get_name() == "binance_stream" and not t.done()
        ]


@pytest.mark.asyncio
async def test_restart_lock_serializes_execution():
    """El lock garantiza que dos restarts nunca se superpongan."""
    svc = BinanceService()
    active = 0
    max_active = 0

    async def _tracked_reconnect(self, runner, publish_status: bool = True):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            active -= 1
            raise

    with patch("services.binance_service.event_bus"), \
         patch.object(BinanceService, "_run_with_reconnect", _tracked_reconnect), \
         patch.object(BinanceService, "_start_balance_loop", _no_sync), \
         patch.object(BinanceService, "_stop_balance_loop", _no_sync), \
         patch.object(BinanceService, "_start_user_stream", _no_sync), \
         patch.object(BinanceService, "_stop_user_stream", _noop_async):

        await asyncio.gather(svc.restart(), svc.restart())

        await svc.stop()

    # Solo un runner puede estar activo en cualquier momento
    assert max_active <= 1


# ---------------------------------------------------------------------------
# Balance event-driven (D1-A): OrderExecutedEvent → _refresh_balance
# ---------------------------------------------------------------------------
from unittest.mock import AsyncMock  # noqa: E402

import time  # noqa: E402

from core.events import BalanceUpdateEvent, OrderExecutedEvent  # noqa: E402


def _executed(order_id: str = "LIVE-1") -> OrderExecutedEvent:
    return OrderExecutedEvent(
        order_id=order_id, symbol="BTCUSDT", side="BUY",
        quantity=0.001, price=65000.0, mode="LIVE", order_type="MARKET",
    )


@pytest.mark.asyncio
async def test_on_order_executed_forces_balance_refresh_in_live():
    """En LIVE, una orden invalida la caché y publica saldo fresco."""
    svc = BinanceService()
    svc._balance_cache = BalanceUpdateEvent(asset="USDT", trading_type="SPOT", free=1.0)
    svc._balance_cache_time = time.time()

    fresh = BalanceUpdateEvent(asset="USDT", trading_type="SPOT", free=99.0)
    seen_cache: list = []

    async def _fake_get_balance(asset: str = "USDT"):
        seen_cache.append(svc._balance_cache)   # debe ser None (cache invalidada)
        return fresh

    with patch("services.binance_service.settings") as m, \
         patch("services.binance_service.event_bus") as bus:
        m.TRADING_MODE = "LIVE"
        with patch.object(svc, "get_balance", _fake_get_balance):
            await svc._on_order_executed(_executed())

    assert seen_cache == [None]                 # force=True invalidó la caché
    published = [c.args[0] for c in bus.publish.call_args_list]
    assert fresh in published


@pytest.mark.asyncio
async def test_on_order_executed_skips_refresh_in_paper():
    """En PAPER, PaperBalance ya publica — BinanceService no duplica."""
    svc = BinanceService()

    with patch("services.binance_service.settings") as m, \
         patch("services.binance_service.event_bus") as bus:
        m.TRADING_MODE = "PAPER"
        gb = AsyncMock()
        with patch.object(svc, "get_balance", gb):
            await svc._on_order_executed(_executed())

        gb.assert_not_awaited()
        bus.publish.assert_not_called()
