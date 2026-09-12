"""
Base — Mixin de lifecycle para suscripciones al EventBus.

Elimina la repetición de did_mount() / will_unmount() con
subscribe / unsubscribe que aparece en 10+ componentes.
"""
from __future__ import annotations

from typing import Any, Callable, Coroutine, Type

from core.event_bus import event_bus


class EventBusSubscriber:
    """Mixin: declaración de suscripciones + lifecycle automático.

    Los componentes que hereden de esta clase deben definir:
        _event_subscriptions = [(EventType, handler_method), ...]

    Y llamar a _setup_subscriptions() / _teardown_subscriptions()
    en sus did_mount() / will_unmount().
    """

    _event_subscriptions: list[tuple[Type, Callable[..., Coroutine]]] = []

    def _setup_subscriptions(self) -> None:
        """Suscribe todos los handlers declarados en _event_subscriptions."""
        for event_type, handler in self._event_subscriptions:
            event_bus.subscribe(event_type, handler)

    def _teardown_subscriptions(self) -> None:
        """Des-suscribe todos los handlers declarados en _event_subscriptions."""
        for event_type, handler in self._event_subscriptions:
            event_bus.unsubscribe(event_type, handler)
