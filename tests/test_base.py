"""
Tests para EventBusSubscriber — Mixin de lifecycle.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from ui.components.base import EventBusSubscriber


class DummyComponent(EventBusSubscriber):
    """Componente de prueba que usa el mixin."""

    def __init__(self):
        self._event_subscriptions = []
        self.call_count = 0

    async def _handler(self, event):
        self.call_count += 1


def test_setup_subscriptions_empty():
    comp = DummyComponent()
    comp._event_subscriptions = []
    comp._setup_subscriptions()
    comp._teardown_subscriptions()


def test_setup_subscriptions_calls_subscribe():
    comp = DummyComponent()
    mock_handler = AsyncMock()
    comp._event_subscriptions = [(type("TestEvent", (), {}), mock_handler)]

    with patch("ui.components.base.event_bus") as mock_bus:
        comp._setup_subscriptions()
        mock_bus.subscribe.assert_called_once_with(
            comp._event_subscriptions[0][0], mock_handler
        )


def test_teardown_subscriptions_calls_unsubscribe():
    comp = DummyComponent()
    mock_handler = AsyncMock()
    event_type = type("TestEvent", (), {})
    comp._event_subscriptions = [(event_type, mock_handler)]

    with patch("ui.components.base.event_bus") as mock_bus:
        comp._teardown_subscriptions()
        mock_bus.unsubscribe.assert_called_once_with(event_type, mock_handler)


def test_multiple_subscriptions():
    comp = DummyComponent()
    handler1 = AsyncMock()
    handler2 = AsyncMock()
    event1 = type("Event1", (), {})
    event2 = type("Event2", (), {})
    comp._event_subscriptions = [(event1, handler1), (event2, handler2)]

    with patch("ui.components.base.event_bus") as mock_bus:
        comp._setup_subscriptions()
        assert mock_bus.subscribe.call_count == 2

    with patch("ui.components.base.event_bus") as mock_bus:
        comp._teardown_subscriptions()
        assert mock_bus.unsubscribe.call_count == 2
