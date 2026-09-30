"""
Tests del indicador MA Crossover (BotSignalEvent).

Cubre que `signal` sea el estado ACTUAL de la relación MA (nivel, no borde),
que `changed` marque la transición para auditoría, el filtro de `AuditService`
y la fórmula de confianza (fracción 0.0–1.0, no siempre 1.0).
"""
import pytest
from unittest.mock import MagicMock, patch

from core.events import BotSignalEvent
from services.audit_service import HANDLER_REGISTRY
from services.bot_engine import BotEngine
from services.order_executor import PaperExecutor


def _make_settings(fast=3, slow=5):
    m = MagicMock()
    m.BOT_MA_FAST = fast
    m.BOT_MA_SLOW = slow
    return m


def _engine():
    return BotEngine(executor=PaperExecutor())


def _published(mock_bus):
    return [
        c.args[0] for c in mock_bus.publish.call_args_list
        if isinstance(c.args[0], BotSignalEvent)
    ]


def _feed(engine, prices):
    engine._price_buffer.clear()
    engine._price_buffer.extend(prices)


def _signal(signal, changed):
    return BotSignalEvent(
        symbol="BTCUSDT", signal=signal,
        ma_fast=1.0, ma_slow=1.0, confidence=0.0, changed=changed,
    )


def test_signal_is_current_state_not_single_tick_edge():
    """Mientras dure la relación MA, cada tick publica el mismo estado."""
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus:
        # MA(3)=130 > MA(5)=120 → estado BUY sostenido
        _feed(engine, [100, 110, 120, 130, 140])

        for _ in range(5):
            engine._publish_bot_signal("BTCUSDT")

        events = _published(bus)
        assert len(events) == 5
        assert [e.signal for e in events] == ["BUY"] * 5
        assert [e.changed for e in events] == [True, False, False, False, False]
        assert all(e.ma_fast == 130.0 for e in events)
        assert all(e.ma_slow == 120.0 for e in events)


def test_signal_transitions_to_sell_when_fast_crosses_below():
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus:
        engine._last_signal = "BUY"
        # MA(3)=110 < MA(5)=120 → SELL
        _feed(engine, [140, 130, 120, 110, 100])

        engine._publish_bot_signal("BTCUSDT")

        events = _published(bus)
        assert len(events) == 1
        assert events[0].signal == "SELL"
        assert events[0].changed is True


def test_signal_is_hold_when_moving_averages_are_tied():
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus:
        # MA(3) == MA(5) → todos los valores iguales
        _feed(engine, [100, 100, 100, 100, 100])

        engine._publish_bot_signal("BTCUSDT")

        events = _published(bus)
        assert events[0].signal == "HOLD"


def test_audit_filter_keeps_one_event_per_crossover():
    f = HANDLER_REGISTRY[BotSignalEvent].filter

    assert f(_signal("BUY", True)) is True     # cruce → auditar
    assert f(_signal("BUY", False)) is False   # mismo estado → dedupe
    assert f(_signal("HOLD", True)) is False   # HOLD nunca se audita
    assert f(_signal("SELL", True)) is True    # cruce inverso → auditar


def test_confidence_is_a_fraction_not_always_one():
    engine = _engine()
    with patch("services.bot_engine.settings", _make_settings()), \
         patch("services.bot_engine.event_bus") as bus:
        # 130 vs 120 → 8.33% (la fórmula anterior daba min(8.33, 1.0)=1.0)
        _feed(engine, [100, 110, 120, 130, 140])

        engine._publish_bot_signal("BTCUSDT")

        event = _published(bus)[0]
        assert event.confidence == pytest.approx(10.0 / 120.0, abs=1e-3)
        assert event.confidence < 1.0
