"""
AsyncEventBus — Centro neurálgico de comunicación entre capas.

Implementa el patrón PubSub asíncrono:
- publish(event): empuja el evento a la cola interna
- subscribe(event_type, handler): registra un handler async para un tipo de evento
- unsubscribe(event_type, handler): elimina el handler
- start(): inicia el loop de despacho en background
- stop(): detiene el despacho limpiamente

Reglas:
  - CERO POLLING: el despacho se basa en asyncio.Queue.get() (bloqueo asíncrono real)
  - Los handlers se llaman con asyncio.create_task() para no bloquear el bus
  - Soporte para múltiples suscriptores por tipo de evento
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine, Type

log = logging.getLogger(__name__)


class AsyncEventBus:
    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._subscribers: dict[type, list[Callable]] = defaultdict(list)
        self._running: bool = False
        self._dispatch_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Suscripción
    # ------------------------------------------------------------------
    def subscribe(self, event_type: Type, handler: Callable[..., Coroutine]) -> None:
        """Registra un handler coroutine para un tipo de evento."""
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)
            log.debug("Subscribed %s to %s", handler.__qualname__, event_type.__name__)

    def unsubscribe(self, event_type: Type, handler: Callable[..., Coroutine]) -> None:
        """Elimina un handler previamente registrado."""
        try:
            self._subscribers[event_type].remove(handler)
            log.debug("Unsubscribed %s from %s", handler.__qualname__, event_type.__name__)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Publicación
    # ------------------------------------------------------------------
    def publish(self, event: Any) -> None:
        """Encola un evento para despacho. No bloqueante (fire-and-forget)."""
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            log.warning("EventBus queue full, dropping event: %s", type(event).__name__)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Inicia el loop de despacho como tarea en background."""
        if self._running:
            return
        self._running = True
        self._dispatch_task = asyncio.create_task(self._dispatch_loop(), name="event_bus_dispatch")
        log.info("AsyncEventBus started")

    async def stop(self) -> None:
        """Detiene el despacho limpiamente."""
        self._running = False
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
        log.info("AsyncEventBus stopped")

    # ------------------------------------------------------------------
    # Loop interno
    # ------------------------------------------------------------------
    async def _dispatch_loop(self) -> None:
        """Despacha eventos de la cola a sus suscriptores."""
        while self._running:
            try:
                event = await self._queue.get()
                event_type = type(event)
                handlers = self._subscribers.get(event_type, [])

                for handler in handlers:
                    asyncio.create_task(
                        self._safe_call(handler, event),
                        name=f"event_{event_type.__name__}_{handler.__name__}",
                    )

                self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.exception("Unexpected error in EventBus dispatch loop: %s", exc)

    @staticmethod
    async def _safe_call(handler: Callable, event: Any) -> None:
        """Llama al handler capturando excepciones para no romper el bus."""
        try:
            await handler(event)
        except Exception as exc:
            log.exception(
                "Handler %s raised an exception for event %s: %s",
                handler.__qualname__,
                type(event).__name__,
                exc,
            )


# Instancia global singleton
event_bus = AsyncEventBus()
