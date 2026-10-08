"""
Tests de AppLayout (D3 + T3.8 — limpieza de sesión en logout).

Cubre el contrato AG.md: LogoutRequestedEvent → AppLayout (pausa bot,
view_registry.clear(), overlay) y que AuthService.logout() sí lo publica
(antes: el evento se publicaba y nadie lo consumía).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.events import (
    AuthStateChangedEvent,
    BotStateChangedEvent,
    LogoutRequestedEvent,
)
from services.auth_service import auth_service
from ui import app_layout


def _published(mock_bus) -> list:
    return [c.args[0] for c in mock_bus.publish.call_args_list]


def test_cleanup_session_pauses_bot_clears_registry_and_overlay():
    registry = MagicMock()
    overlay = MagicMock()

    with patch.object(app_layout, "bot_engine") as bot, \
         patch.object(app_layout, "event_bus") as bus, \
         patch.object(app_layout, "settings"):
        bot.is_active = True
        app_layout._cleanup_session(registry, overlay)

    pauses = [e for e in _published(bus) if isinstance(e, BotStateChangedEvent)]
    assert len(pauses) == 1
    assert pauses[0].is_running is False
    registry.clear.assert_called_once()
    overlay.assert_called_once()


def test_cleanup_session_skips_bot_pause_when_bot_inactive():
    registry = MagicMock()
    overlay = MagicMock()

    with patch.object(app_layout, "bot_engine") as bot, \
         patch.object(app_layout, "event_bus") as bus, \
         patch.object(app_layout, "settings"):
        bot.is_active = False
        app_layout._cleanup_session(registry, overlay)

    assert not any(isinstance(e, BotStateChangedEvent) for e in _published(bus))
    registry.clear.assert_called_once()   # la limpieza de sesión no depende del bot
    overlay.assert_called_once()


def test_logout_publishes_logout_requested_event():
    """Contrato: logout() publica AuthStateChangedEvent(False) Y LogoutRequestedEvent."""
    with patch("services.auth_service.event_bus") as bus:
        auth_service.logout()

    events = _published(bus)
    assert auth_service.is_authenticated is False
    assert any(
        isinstance(e, AuthStateChangedEvent) and e.is_authenticated is False
        for e in events
    )
    assert any(isinstance(e, LogoutRequestedEvent) for e in events)


def test_cleanup_session_is_idempotent():
    """Doble logout no debe explotar (clear/overlay son idempotentes)."""
    registry = MagicMock()
    overlay = MagicMock()

    with patch.object(app_layout, "bot_engine") as bot, \
         patch.object(app_layout, "event_bus"), \
         patch.object(app_layout, "settings"):
        bot.is_active = False
        app_layout._cleanup_session(registry, overlay)
        app_layout._cleanup_session(registry, overlay)

    assert registry.clear.call_count == 2
    assert overlay.call_count == 2
