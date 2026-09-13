"""
Base — Mixins de lifecycle para suscripciones al EventBus.

Elimina la repetición de did_mount() / will_unmount() con
subscribe / unsubscribe que aparece en 10+ componentes.

SymbolAwareSubscriber agrega filtrado y sincronización de símbolo (DRY).
"""
from __future__ import annotations

from typing import Any, Callable, Coroutine, Type

from core.event_bus import event_bus
from config.settings import settings


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


class SymbolAwareSubscriber(EventBusSubscriber):
    """Mixin que agrega filtrado y sincronización de símbolo (DRY).

    Elimina la duplicación del patrón:
        if event.symbol != self._current_symbol: return
        self._current_symbol = settings.TRADING_SYMBOL

    Los componentes que hereden deben:
        1. Llamar super().__init__() al final de su __init__
        2. Implementar _on_symbol_changed(symbol) para resetear estado
        3. Usar self.matches_symbol(event.symbol) en handlers de precio
    """

    _current_symbol: str = ""

    def sync_symbol(self) -> None:
        """Sincroniza el símbolo actual desde settings. Llama _on_symbol_changed si cambió."""
        new_symbol = settings.TRADING_SYMBOL
        if new_symbol != self._current_symbol:
            self._current_symbol = new_symbol
            self._on_symbol_changed(new_symbol)

    def _on_symbol_changed(self, symbol: str) -> None:
        """Override en componentes hijos para resetear estado al cambiar símbolo."""

    def matches_symbol(self, event_symbol: str) -> bool:
        """Retorna True si el evento corresponde al símbolo actual."""
        return event_symbol == self._current_symbol
