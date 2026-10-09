"""
Tests de PaperBalanceService — contabilidad simétrica ENTRY/EXIT.

Regresión principal: una ENTRADA corta (SELL) ya no acredita la venta
como proceeds (bug que inflaba el wallet en exactamente TRADE_AMOUNT).
"""
import pytest
from unittest.mock import patch

from core.events import OrderExecutedEvent
from services.paper_balance import PAPER_INITIAL_BALANCE, PaperBalanceService


def _make_event(
    *, side, purpose, operation_id="OC-TEST01",
    entry_price=1000.0, stop_loss=990.0, quantity=0.05, price=1000.0,
):
    return OrderExecutedEvent(
        order_id="PAPER-ORD01",
        symbol="BTCUSDT",
        side=side,
        quantity=quantity,
        price=price,
        mode="PAPER",
        entry_price=entry_price,
        stop_loss=stop_loss,
        operation_id=operation_id,
        purpose=purpose,
    )


def _svc():
    return PaperBalanceService()


def _settings_mock(trade_amount=50.0):
    m = patch("services.paper_balance.settings")
    mock = m.start()
    mock.TRADE_AMOUNT = trade_amount
    mock.TRADE_CURRENCY = "USDT"
    return m


# ---------------------------------------------------------------------------
# ENTRY — siempre debita/bloquea, sin importar el lado
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_entry_buy_debits_and_locks():
    stop = _settings_mock()
    try:
        svc = _svc()
        await svc._on_order_executed(
            _make_event(side="BUY", purpose="ENTRY", operation_id="OC-A")
        )
        assert svc.get_balance() == PAPER_INITIAL_BALANCE - 50.0
        assert svc._locked == 50.0
        assert "OC-A" in svc._positions
    finally:
        stop.stop()


@pytest.mark.asyncio
async def test_entry_sell_debits_and_locks_not_credits():
    """REGRESIÓN del +50: la entrada corta NO acredita proceeds."""
    stop = _settings_mock()
    try:
        svc = _svc()
        await svc._on_order_executed(
            _make_event(side="SELL", purpose="ENTRY", operation_id="OV-B")
        )
        assert svc.get_balance() == PAPER_INITIAL_BALANCE - 50.0  # no 10050
        assert svc._locked == 50.0
        assert "OV-B" in svc._positions
    finally:
        stop.stop()


# ---------------------------------------------------------------------------
# EXIT — libera capital + PnL (simétrico largo/corto)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exit_long_releases_capital_with_pnl():
    stop = _settings_mock()
    try:
        svc = _svc()
        await svc._on_order_executed(
            _make_event(side="BUY", purpose="ENTRY", operation_id="OC-L",
                        entry_price=1000.0, stop_loss=990.0)
        )
        await svc._on_order_executed(
            _make_event(side="SELL", purpose="EXIT", operation_id="OC-L",
                        entry_price=1000.0, stop_loss=990.0)
        )
        # pct=1% → resultado=49.5, free=10000-50+49.5
        assert svc.get_balance() == pytest.approx(9999.5, abs=1e-6)
        assert svc._locked == 0.0
        assert svc._positions == {}
    finally:
        stop.stop()


@pytest.mark.asyncio
async def test_exit_short_releases_capital_with_pnl():
    stop = _settings_mock()
    try:
        svc = _svc()
        await svc._on_order_executed(
            _make_event(side="SELL", purpose="ENTRY", operation_id="OV-S",
                        entry_price=1000.0, stop_loss=1010.0)
        )
        await svc._on_order_executed(
            _make_event(side="BUY", purpose="EXIT", operation_id="OV-S",
                        entry_price=1000.0, stop_loss=1010.0)
        )
        # pct=-1% → resultado=49.5 (simétrico al largo)
        assert svc.get_balance() == pytest.approx(9999.5, abs=1e-6)
        assert svc._locked == 0.0
        assert svc._positions == {}
    finally:
        stop.stop()


@pytest.mark.asyncio
async def test_exit_without_position_leaves_balance_unchanged():
    """EXIT huérfano (reinicio/key mismatch) NO debe acreditar proceeds."""
    stop = _settings_mock()
    try:
        svc = _svc()
        await svc._on_order_executed(
            _make_event(side="SELL", purpose="EXIT", operation_id="OC-GHOST")
        )
        assert svc.get_balance() == PAPER_INITIAL_BALANCE
        assert svc._locked == 0.0
    finally:
        stop.stop()


# ---------------------------------------------------------------------------
# Invariante: free + locked se conserva (solo cambia por PnL realizado)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_full_cycle_conserves_free_plus_locked():
    stop = _settings_mock()
    try:
        svc = _svc()
        await svc._on_order_executed(
            _make_event(side="BUY", purpose="ENTRY", operation_id="OC-1")
        )
        # Tras abrir: free+locked sigue siendo 10000
        assert svc.get_balance() + svc._locked == PAPER_INITIAL_BALANCE

        await svc._on_order_executed(
            _make_event(side="SELL", purpose="EXIT", operation_id="OC-1")
        )
        # Tras cerrar: locked liberado, free = inicial + PnL
        assert svc._locked == 0.0
        assert svc.get_balance() == pytest.approx(9999.5, abs=1e-6)
    finally:
        stop.stop()


@pytest.mark.asyncio
async def test_publish_balance_reflects_values():
    stop = _settings_mock()
    with patch("services.paper_balance.event_bus") as bus:
        svc = _svc()
        await svc._on_order_executed(
            _make_event(side="BUY", purpose="ENTRY", operation_id="OC-P")
        )
        published = [
            c.args[0] for c in bus.publish.call_args_list
            if type(c.args[0]).__name__ == "BalanceUpdateEvent"
        ]
        assert published, "debe publicar BalanceUpdateEvent tras cada cambio"
        evt = published[-1]
        assert evt.free == pytest.approx(9950.0, abs=1e-6)
        assert evt.available == pytest.approx(9950.0, abs=1e-6)
    stop.stop()


@pytest.mark.asyncio
async def test_non_paper_mode_is_ignored():
    stop = _settings_mock()
    try:
        svc = _svc()
        live = _make_event(side="SELL", purpose="ENTRY", operation_id="LIVE-1")
        live.mode = "LIVE"
        await svc._on_order_executed(live)
        assert svc.get_balance() == PAPER_INITIAL_BALANCE
    finally:
        stop.stop()


# ---------------------------------------------------------------------------
# E4 — Guard: sin saldo para el capital la ENTRY no debita (nunca free < 0)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_entry_blocked_when_insufficient_free():
    """20000 > 10000: la entrada no debita, no abre posición, free ≥ 0."""
    stop = _settings_mock(trade_amount=20000.0)
    try:
        svc = _svc()
        await svc._on_order_executed(
            _make_event(side="BUY", purpose="ENTRY", operation_id="OC-G")
        )
        assert svc.get_balance() == PAPER_INITIAL_BALANCE
        assert svc._locked == 0.0
        assert "OC-G" not in svc._positions
    finally:
        stop.stop()
