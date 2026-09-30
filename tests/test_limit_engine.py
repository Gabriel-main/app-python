"""
Tests del flujo LIMIT en BotEngine (Fase 2).

Cubre: colocación ENTRY vs EXIT, fill por cruce de tick (PAPER),
idempotencia, gating de SL sin fill, y cancelaciones.
"""
import pytest
from unittest.mock import patch, MagicMock

from core.events import (
    OrderCanceledEvent,
    OrderExecutedEvent,
    OrderPlacedEvent,
    SettingsUpdatedEvent,
)
from services.bot_engine import BotEngine, TradingOperation
from services.order_executor import PaperExecutor


def _make_settings(order_type="LIMIT", limit_price=65000.0, mode="PAPER"):
    m = MagicMock()
    m.ORDER_TYPE = order_type
    m.LIMIT_PRICE = limit_price
    m.TRADING_MODE = mode
    m.TRADING_SYMBOL = "BTCUSDT"
    m.TRADING_TYPE = "SPOT"
    m.LEVERAGE = 1
    m.TRADE_AMOUNT = 10.0
    return m


def _published(mock_bus, event_type):
    return [
        c.args[0] for c in mock_bus.publish.call_args_list
        if isinstance(c.args[0], event_type)
    ]


def _make_op(side="BUY", state="ACTIVE", entry_filled=False):
    return TradingOperation(
        side=side, state=state,
        entry_price=65100.0, stop_loss=64900.0,
        quantity=0.001, order_id="OC-TEST01",
        entry_filled=entry_filled,
    )


def _engine():
    return BotEngine(executor=PaperExecutor())


# ---------------------------------------------------------------------------
# Colocación: ENTRY aplica LIMIT, EXIT siempre MARKET
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_entry_limit_registers_working_order():
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue") as db:
        engine._current_price = 66000.0  # mercado por encima del límite BUY
        op = _make_op()

        result = await engine._dispatch_order(op, purpose="ENTRY")

        assert result is None                       # no fill todavía
        assert len(engine._working_orders) == 1     # working registrado
        assert op.entry_filled is False

        placed = _published(bus, OrderPlacedEvent)
        assert len(placed) == 1
        assert placed[0].price == 65000.0
        assert placed[0].operation_id == "OC-TEST01"
        assert placed[0].order_type == "LIMIT"
        db.enqueue_order_placed.assert_called_once()
        assert _published(bus, OrderExecutedEvent) == []


@pytest.mark.asyncio
async def test_exit_always_market_even_with_limit_configured():
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        op = _make_op(entry_filled=True)

        result = await engine._dispatch_order(op, price=64900.0, purpose="EXIT")

        assert result is not None
        assert result.order_type == "MARKET"
        assert engine._working_orders == {}         # MARKET nunca queda working
        assert _published(bus, OrderPlacedEvent) == []


@pytest.mark.asyncio
async def test_entry_market_fills_immediately():
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings(order_type="MARKET", limit_price=0.0)), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        op = _make_op()

        result = await engine._dispatch_order(op, purpose="ENTRY")

        assert result is not None
        assert result.order_type == "MARKET"
        assert op.entry_filled is True
        assert engine._working_orders == {}


# ---------------------------------------------------------------------------
# Fill por cruce de tick (PAPER) — event-driven, sin polling
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_paper_tick_crossing_completes_fill():
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue") as db:
        engine._current_price = 66000.0
        op = _make_op()
        await engine._dispatch_order(op, purpose="ENTRY")

        # Ticker baja al límite → cruce → fill
        engine._check_limit_fills(64999.0)

        executed = _published(bus, OrderExecutedEvent)
        assert len(executed) == 1
        assert executed[0].price == 65000.0         # fill a precio límite
        assert executed[0].order_type == "LIMIT"
        assert executed[0].limit_price == 65000.0
        assert executed[0].operation_id == "OC-TEST01"
        assert op.entry_filled is True
        assert engine._working_orders == {}
        db.enqueue_order.assert_called_once()


@pytest.mark.asyncio
async def test_no_fill_when_tick_does_not_cross():
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        op = _make_op()
        await engine._dispatch_order(op, purpose="ENTRY")

        engine._check_limit_fills(65500.0)  # no cruzó

        assert _published(bus, OrderExecutedEvent) == []
        assert len(engine._working_orders) == 1


@pytest.mark.asyncio
async def test_double_fill_is_idempotent():
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        op = _make_op()
        await engine._dispatch_order(op, purpose="ENTRY")

        engine._check_limit_fills(64999.0)
        engine._check_limit_fills(64000.0)  # segundo cruce: debe ignorarse

        assert len(_published(bus, OrderExecutedEvent)) == 1


# ---------------------------------------------------------------------------
# Gating de SL: sin fill no hay posición → no se dispara SL
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stop_loss_gated_without_entry_fill():
    engine = _engine()
    op = _make_op(entry_filled=False)  # BUY, PSL=64900
    engine._operations = [op]

    engine._check_stop_losses(64500.0)  # cruzaría el SL si hubiera posición

    assert len(engine._sl_tasks) == 0
    assert op.state == "ACTIVE"


# ---------------------------------------------------------------------------
# Cancelaciones (Q1a: esperar fill; cancelar si cambia contexto)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancel_working_orders_publishes_canceled():
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue") as db:
        engine._current_price = 66000.0
        op = _make_op()
        await engine._dispatch_order(op, purpose="ENTRY")

        cancelled = await engine._cancel_working_orders(lambda w: True, "test_reason")

        assert cancelled == 1
        assert engine._working_orders == {}
        events = _published(bus, OrderCanceledEvent)
        assert len(events) == 1
        assert events[0].reason == "test_reason"
        assert events[0].operation_id == "OC-TEST01"
        db.enqueue_order_canceled.assert_called_once()


@pytest.mark.asyncio
async def test_settings_change_cancels_working_orders():
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        op = _make_op()
        await engine._dispatch_order(op, purpose="ENTRY")
        assert len(engine._working_orders) == 1

        await engine._on_settings_updated(SettingsUpdatedEvent(
            symbol="BTCUSDT", mode="PAPER", trading_type="SPOT",
            leverage=1, order_type="LIMIT", limit_price=70000.0,  # cambió
        ))

        assert engine._working_orders == {}
        events = _published(bus, OrderCanceledEvent)
        assert len(events) == 1
        assert events[0].reason == "settings_changed"


@pytest.mark.asyncio
async def test_close_open_positions_skips_unfilled_entries():
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        op = _make_op(entry_filled=False)
        engine._operations = [op]

        await engine._close_open_positions()

        # Sin fill → no se envía orden de cierre (no hay posición)
        assert _published(bus, OrderExecutedEvent) == []


# ---------------------------------------------------------------------------
# Cierre de posiciones: lado invertido + purpose + operation_id correcto
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_stop_loss_inverts_side():
    """Cerrar un BUY debe enviar SELL (no duplicar la posición)."""
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings(order_type="MARKET")), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        op = _make_op(side="BUY", entry_filled=True)
        engine._operations = [op]
        engine._current_price = 66000.0

        await engine._execute_stop_loss(op, 64900.0)

        executed = _published(bus, OrderExecutedEvent)
        assert len(executed) == 1
        assert executed[0].side == "SELL"          # lado invertido para cerrar
        assert executed[0].purpose == "EXIT"
        assert executed[0].operation_id == "OC-TEST01"
        assert op.state == "PAST"


@pytest.mark.asyncio
async def test_close_open_positions_uses_original_operation_id():
    """El cierre al detener el bot debe conservar OC-/OV- (sin prefijo CLOSE-)."""
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings(order_type="MARKET")), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        op = _make_op(side="BUY", entry_filled=True)
        engine._operations = [op]
        engine._current_price = 66000.0

        await engine._close_open_positions()

        executed = _published(bus, OrderExecutedEvent)
        assert len(executed) == 1
        assert executed[0].operation_id == "OC-TEST01"  # sin prefijo CLOSE-
        assert executed[0].side == "SELL"
        assert executed[0].purpose == "EXIT"


@pytest.mark.asyncio
async def test_complete_limit_fill_sets_purpose_entry():
    """El fill de una working order LIMIT siempre es ENTRY (abre posición)."""
    from core.events import OrderFillEvent

    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        op = _make_op()
        await engine._dispatch_order(op, purpose="ENTRY")
        fill_oid = next(iter(engine._working_orders))

        engine._complete_limit_fill(OrderFillEvent(
            order_id=fill_oid, status="FILLED",
            price=65000.0, mode="PAPER",
        ))

        executed = _published(bus, OrderExecutedEvent)
        assert len(executed) == 1
        assert executed[0].purpose == "ENTRY"
        assert executed[0].side == "BUY"
