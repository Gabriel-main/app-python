"""
Tests del flujo LIMIT en BotEngine (Fase 2).

Cubre: colocación ENTRY vs EXIT, fill por cruce de tick (PAPER),
idempotencia, gating de SL sin fill, y cancelaciones.
"""
import pytest
from unittest.mock import patch, MagicMock

from core.events import (
    InitialOrderEvent,
    OrderCanceledEvent,
    OrderExecutedEvent,
    OrderFailedEvent,
    OrderPlacedEvent,
    SettingsUpdatedEvent,
)
from services.bot_engine import BotEngine, TradingOperation
from services.order_executor import PaperExecutor
from services.trading_rules import QuantitySizer, SymbolFilters


def _make_settings(
    order_type="LIMIT", limit_price=65000.0, mode="PAPER",
    trade_amount=10.0,
):
    m = MagicMock()
    m.ORDER_TYPE = order_type
    m.LIMIT_PRICE = limit_price
    m.TRADING_MODE = mode
    m.TRADING_SYMBOL = "BTCUSDT"
    m.TRADING_TYPE = "SPOT"
    m.LEVERAGE = 1
    m.TRADE_AMOUNT = trade_amount
    m.STOP_LOSS = 1.01
    m.STOP_LOSS_TYPE = "PERCENT"
    m.TIMEFRAME = 1
    m.TIMEFRAME_UNIT = "MINUTES"

    # Comportamiento real de `settings.from_event`: si no, el mock nunca
    # refleja los nuevos valores y no se puede asertar el límite re-colocado.
    def _from_event(e):
        m.ORDER_TYPE = e.order_type
        m.LIMIT_PRICE = e.limit_price
        m.TRADING_MODE = e.mode
        m.TRADING_SYMBOL = e.symbol
        m.TRADING_TYPE = e.trading_type
        m.LEVERAGE = e.leverage

    m.from_event = _from_event
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


def _engine(sizer=None):
    return BotEngine(executor=PaperExecutor(), sizer=sizer)


class _StubFiltersProvider:
    """Filtros de exchange falsos para inyectar en QuantitySizer (DIP)."""

    def __init__(self, filters: SymbolFilters) -> None:
        self._filters = filters

    async def get_symbol_filters(self, symbol: str, trading_type: str):
        return self._filters


async def _sizer_with(filters: SymbolFilters) -> QuantitySizer:
    sizer = QuantitySizer(_StubFiltersProvider(filters))
    await sizer.refresh("BTCUSDT", "SPOT")
    return sizer


# BTCUSDT FUTURES reales: minQty/stepSize 0.001, minNotional 50
_FUT_FILTERS = SymbolFilters(
    symbol="BTCUSDT", min_qty=0.001, step_size=0.001,
    min_notional=50.0, tick_size=0.10,
)


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


# ---------------------------------------------------------------------------
# Auto-sanado: cancelar por settings debe re-colocar la entrada
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_settings_change_replaces_entry_when_bot_active():
    """Cancelar por settings_changed deja la ACTIVE sin orden → se recoloca."""
    engine = _engine()
    engine._active = True
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        op = _make_op()
        engine._operations = [op]
        await engine._dispatch_order(op, purpose="ENTRY")
        assert len(engine._working_orders) == 1
        bus.publish.reset_mock()   # aislar los eventos de settings_updated

        await engine._on_settings_updated(SettingsUpdatedEvent(
            symbol="BTCUSDT", mode="PAPER", trading_type="SPOT",
            leverage=1, order_type="LIMIT", limit_price=65500.0,  # cambió
        ))

        cancelled = _published(bus, OrderCanceledEvent)
        assert len(cancelled) == 1
        assert cancelled[0].reason == "settings_changed"

        placed = _published(bus, OrderPlacedEvent)
        assert len(placed) == 1
        assert placed[0].price == 65500.0          # con el límite nuevo
        assert placed[0].operation_id == "OC-TEST01"
        assert len(engine._working_orders) == 1   # huérfana → recolocada
        assert op.entry_filled is False


@pytest.mark.asyncio
async def test_settings_update_heals_orphan_without_settings_change():
    """La ACTIVE sin fill y sin orden se recoloca aunque nada se invalidó."""
    engine = _engine()
    engine._active = True
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        op = _make_op()
        engine._operations = [op]          # huérfana: sin orden working

        await engine._on_settings_updated(SettingsUpdatedEvent(
            symbol="BTCUSDT", mode="PAPER", trading_type="SPOT",
            leverage=1, order_type="LIMIT", limit_price=65000.0,  # sin cambio
        ))

        assert len(engine._working_orders) == 1
        assert len(_published(bus, OrderPlacedEvent)) == 1
        assert _published(bus, OrderCanceledEvent) == []


@pytest.mark.asyncio
async def test_settings_update_does_not_heal_when_paused():
    engine = _engine()   # _active es False por defecto
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        engine._operations = [_make_op()]

        await engine._on_settings_updated(SettingsUpdatedEvent(
            symbol="BTCUSDT", mode="PAPER", trading_type="SPOT",
            leverage=1, order_type="LIMIT", limit_price=65000.0,
        ))

        assert engine._working_orders == {}
        assert _published(bus, OrderPlacedEvent) == []


@pytest.mark.asyncio
async def test_settings_update_does_not_duplicate_working_order():
    engine = _engine()
    engine._active = True
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        op = _make_op()
        engine._operations = [op]
        await engine._dispatch_order(op, purpose="ENTRY")
        assert len(engine._working_orders) == 1
        bus.publish.reset_mock()   # aislar los eventos de settings_updated

        await engine._on_settings_updated(SettingsUpdatedEvent(
            symbol="BTCUSDT", mode="PAPER", trading_type="SPOT",
            leverage=1, order_type="LIMIT", limit_price=65000.0,  # sin cambio
        ))

        assert len(engine._working_orders) == 1
        assert _published(bus, OrderPlacedEvent) == []
        assert _published(bus, OrderCanceledEvent) == []


# ---------------------------------------------------------------------------
# Arranque: solo la operación ACTIVE recibe orden
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_initial_orders_dispatches_only_active():
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        active = _make_op(side="BUY", state="ACTIVE")
        pending = TradingOperation(
            side="SELL", state="PENDING",
            entry_price=64900.0, stop_loss=65100.0,
            quantity=0.001, order_id="OV-TEST01",
            entry_filled=False,
        )
        engine._operations = [active, pending]

        await engine._execute_initial_orders()

        placed = _published(bus, OrderPlacedEvent)
        assert len(placed) == 1                      # la PENDING no recibe orden
        assert placed[0].operation_id == "OC-TEST01"
        assert placed[0].side == "BUY"
        assert [w.operation for w in engine._working_orders.values()] == [active]


@pytest.mark.asyncio
async def test_execute_initial_orders_emits_initial_order_event_on_fill():
    """La factory compartida (_initial_order_factory) publica al llenar."""
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings(order_type="MARKET")), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        active = _make_op(side="BUY", state="ACTIVE")
        pending = TradingOperation(
            side="SELL", state="PENDING",
            entry_price=64900.0, stop_loss=65100.0,
            quantity=0.001, order_id="OV-TEST01",
            entry_filled=False,
        )
        engine._operations = [active, pending]

        await engine._execute_initial_orders()

        executed = _published(bus, OrderExecutedEvent)
        assert len(executed) == 1
        initials = _published(bus, InitialOrderEvent)
        assert len(initials) == 1
        assert initials[0].order_id == executed[0].order_id
        assert initials[0].side == "BUY"
        assert active.entry_filled is True
        assert pending.entry_filled is False


# ---------------------------------------------------------------------------
# F4 — Sizing: la única puerta de validación de la cantidad
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_start_trading_blocks_when_quantity_not_operable():
    """El bug original: 50 USDT / 65k = 0.000767 < minQty 0.001 → el bot no arranca."""
    engine = _engine(await _sizer_with(_FUT_FILTERS))
    with patch("services.bot_engine.settings", _make_settings(trade_amount=50.0)), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 65192.32

        started = await engine._start_trading()

        assert started is False
        assert engine._operations == []
        failed = _published(bus, OrderFailedEvent)
        assert len(failed) == 1
        assert failed[0].operation_id == "STARTUP"
        assert "0.001" in failed[0].error


@pytest.mark.asyncio
async def test_start_trading_uses_floored_quantity():
    engine = _engine(await _sizer_with(_FUT_FILTERS))
    with patch("services.bot_engine.settings", _make_settings(trade_amount=1000.0)), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 65192.32

        started = await engine._start_trading()

        assert started is True
        assert len(engine._operations) == 2
        # floor(1000 / 65192.32, 0.001) — no el float crudo
        assert engine._operations[0].quantity == 0.015
        assert _published(bus, OrderFailedEvent) == []
        engine._stop_timeframe_timer()


@pytest.mark.asyncio
async def test_calculate_quantity_floors_to_step():
    engine = _engine(await _sizer_with(_FUT_FILTERS))
    with patch("services.bot_engine.settings", _make_settings(trade_amount=1000.0)):
        assert engine._calculate_quantity(65192.32) == 0.015


@pytest.mark.asyncio
async def test_calculate_quantity_zero_when_not_operable():
    engine = _engine(await _sizer_with(_FUT_FILTERS))
    with patch("services.bot_engine.settings", _make_settings(trade_amount=50.0)):
        assert engine._calculate_quantity(65192.32) == 0.0


@pytest.mark.asyncio
async def test_calculate_quantity_fail_open_without_filters():
    engine = _engine()   # QuantitySizer sin provider → filtros desconocidos
    with patch("services.bot_engine.settings", _make_settings(trade_amount=50.0)):
        await engine._sizer.refresh("BTCUSDT", "SPOT")
        assert engine._calculate_quantity(65192.32) == pytest.approx(50.0 / 65192.32)


def test_insert_pending_skips_zero_quantity():
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus"):
        active = _make_op(side="BUY", state="ACTIVE", entry_filled=True)
        active.stop_loss = 64900.0
        engine._operations = [active]

        engine._insert_pending_if_needed(64000.0, 640.0, 0.0)   # no operable
        assert len(engine._operations) == 1

        engine._insert_pending_if_needed(64000.0, 640.0, 0.001)  # operable
        assert len(engine._operations) == 2


@pytest.mark.asyncio
async def test_timeframe_tick_keeps_existing_quantity_when_sizing_fails():
    """Si el precio se movió y el sizing falla, la PENDING no se crea con 0."""
    engine = _engine(await _sizer_with(_FUT_FILTERS))
    with patch("services.bot_engine.settings", _make_settings(trade_amount=50.0)), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._active = True
        engine._current_price = 65192.32
        active = _make_op(side="BUY", state="ACTIVE", entry_filled=True)
        engine._operations = [active]

        await engine._on_timeframe_tick()

        assert len(engine._operations) == 2
        assert engine._operations[1].quantity == active.quantity


# ---------------------------------------------------------------------------
# F5 — Auto-sanado de la ENTRY (event-driven, con cooldown y tope)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_order_failed_heals_orphan_entry():
    engine = _engine()
    engine._active = True
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        engine._operations = [_make_op()]          # huérfana: sin orden working

        await engine._on_order_failed(
            OrderFailedEvent(operation_id="OC-TEST01", side="BUY", error="boom")
        )

        assert len(engine._working_orders) == 1
        assert engine._heal_attempts == 1
        # El refill LIMIT no cruzado queda como orden working (OrderPlaced)
        assert len(_published(bus, OrderPlacedEvent)) == 1


@pytest.mark.asyncio
async def test_order_failed_respects_cooldown():
    """Un segundo fallo dentro del cooldown no vuelve a despachar (sin bucle)."""
    engine = _engine()
    engine._active = True
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        engine._operations = [_make_op()]
        event = OrderFailedEvent(operation_id="OC-TEST01", side="BUY", error="boom")

        await engine._on_order_failed(event)
        assert len(engine._working_orders) == 1

        engine._working_orders.clear()             # simular que sigue fallando
        await engine._on_order_failed(event)

        assert engine._working_orders == {}        # cooldown lo bloqueó
        assert engine._heal_attempts == 1


@pytest.mark.asyncio
async def test_order_failed_ignored_when_paused():
    engine = _engine()   # _active False por defecto
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        engine._operations = [_make_op()]

        await engine._on_order_failed(
            OrderFailedEvent(operation_id="OC-TEST01", side="BUY", error="boom")
        )

        assert engine._working_orders == {}
        assert engine._heal_attempts == 0


@pytest.mark.asyncio
async def test_order_failed_ignored_for_startup_sizing_error():
    """STARTUP es fallo de sizing: no hay operación que sanar (evita bucle)."""
    engine = _engine()
    engine._active = True
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        engine._operations = [_make_op()]

        await engine._on_order_failed(
            OrderFailedEvent(operation_id="STARTUP", side="BUY", error="muy chico")
        )

        assert engine._working_orders == {}
        assert engine._heal_attempts == 0


@pytest.mark.asyncio
async def test_order_failed_stops_after_max_attempts():
    engine = _engine()
    engine._active = True
    engine._heal_attempts = engine._MAX_HEAL_ATTEMPTS
    engine._last_heal_at = 0.0
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        engine._operations = [_make_op()]

        await engine._on_order_failed(
            OrderFailedEvent(operation_id="OC-TEST01", side="BUY", error="boom")
        )

        assert engine._working_orders == {}
        assert engine._heal_attempts == engine._MAX_HEAL_ATTEMPTS


@pytest.mark.asyncio
async def test_successful_entry_resets_heal_attempts():
    engine = _engine()
    engine._heal_attempts = 3
    with patch("services.bot_engine.settings", _make_settings(order_type="MARKET", limit_price=0.0)), \
         patch("services.bot_engine.event_bus") as bus, \
         patch("services.bot_engine.db_queue"):
        engine._current_price = 66000.0
        op = _make_op()

        result = await engine._dispatch_order(op, purpose="ENTRY")

        assert result is not None
        assert op.entry_filled is True
        assert engine._heal_attempts == 0
