"""
AuditService — Recopila y distribuye eventos de auditoría.

Responsabilidades:
- Suscribirse a eventos relevantes del EventBus
- Convertir eventos a AuditEvent con formato legible
- Mantener ring buffer de los últimos N eventos
- Publicar AuditEvent para que la UI los consuma

Principios:
- SRP: Solo audita, no modifica comportamiento
- OCP: Abierto a agregar nuevas suscripciones sin modificar código existente
- DIP: Depende de EventBus (abstracción), no de implementaciones concretas
- DRY: Registry declarativo elimina handlers repetitivos
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from core.event_bus import event_bus
from core.events import (
    AuditEvent,
    BotSignalEvent,
    BotStateChangedEvent,
    ConnectionStatusEvent,
    InitialOrderEvent,
    OperationInsertedEvent,
    OperationUpdateEvent,
    OrderExecutedEvent,
    PositionUpdateEvent,
    PriceTickEvent,
    SettingsUpdatedEvent,
    StopLossEvent,
    TimeframeCycleEvent,
    TradingLifecycleEvent,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HandlerConfig: configuración declarativa de transformación de eventos
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class HandlerConfig:
    """Configuración inmutable para transformar un evento fuente en AuditEvent."""
    category: str
    action: Callable[[Any], str]
    detail: Callable[[Any], str]
    data: Callable[[Any], dict]
    filter: Callable[[Any], bool] | None = None


# ---------------------------------------------------------------------------
# Funciones de formato (extraídas para DRY)
# ---------------------------------------------------------------------------

def _format_operation_detail(event: OperationUpdateEvent) -> str:
    active = sum(1 for op in event.operations if op.state == "ACTIVE")
    pending = sum(1 for op in event.operations if op.state == "PENDING")
    return f"Operaciones: {active} ACTIVE, {pending} PENDING | Timer: {event.timeframe_remaining:.0f}s"


def _format_operation_data(event: OperationUpdateEvent) -> dict:
    return {
        "operations": [
            {"side": op.side, "state": op.state, "order_id": op.order_id}
            for op in event.operations
        ],
        "active_count": sum(1 for op in event.operations if op.state == "ACTIVE"),
        "pending_count": sum(1 for op in event.operations if op.state == "PENDING"),
        "timeframe_remaining": event.timeframe_remaining,
    }


def _format_position_detail(event: PositionUpdateEvent) -> str:
    pnl = event.unrealized_pnl
    sign = "+" if pnl >= 0 else ""
    return (
        f"{event.side} {event.quantity:.6f} | "
        f"Entry: ${event.entry_price:,.2f} | PnL: {sign}{pnl:.4f}"
    )


def _format_position_data(event: PositionUpdateEvent) -> dict:
    return {
        "symbol": event.symbol,
        "side": event.side,
        "entry_price": event.entry_price,
        "mark_price": event.mark_price,
        "unrealized_pnl": event.unrealized_pnl,
    }


# ---------------------------------------------------------------------------
# Registry declarativo: cada EventType → configuración de transformación
# ---------------------------------------------------------------------------

HANDLER_REGISTRY: dict[type, HandlerConfig] = {
    PriceTickEvent: HandlerConfig(
        category="PRICE",
        action=lambda e: "TICK",
        detail=lambda e: f"{e.symbol} ${e.price:,.2f} ({e.change_pct:+.2f}%)",
        data=lambda e: {
            "symbol": e.symbol,
            "price": e.price,
            "change_pct": e.change_pct,
            "volume": e.volume,
        },
    ),
    BotSignalEvent: HandlerConfig(
        category="SIGNAL",
        filter=lambda e: e.signal != "HOLD",
        action=lambda e: f"{e.signal}_SIGNAL",
        detail=lambda e: (
            f"{e.signal} | MA({e.ma_fast:.2f}) vs MA({e.ma_slow:.2f}) "
            f"| Confianza: {e.confidence:.2%}"
        ),
        data=lambda e: {
            "signal": e.signal,
            "ma_fast": e.ma_fast,
            "ma_slow": e.ma_slow,
            "confidence": e.confidence,
        },
    ),
    OrderExecutedEvent: HandlerConfig(
        category="ORDER",
        action=lambda e: "EXECUTED",
        detail=lambda e: (
            f"{e.side} {e.quantity:.6f} {e.symbol} @ ${e.price:,.2f} [{e.mode}]"
        ),
        data=lambda e: {
            "order_id": e.order_id,
            "symbol": e.symbol,
            "side": e.side,
            "quantity": e.quantity,
            "price": e.price,
            "mode": e.mode,
        },
    ),
    OperationUpdateEvent: HandlerConfig(
        category="OPERATION",
        action=lambda e: "STATE_UPDATE",
        detail=_format_operation_detail,
        data=_format_operation_data,
    ),
    PositionUpdateEvent: HandlerConfig(
        category="POSITION",
        action=lambda e: "PNL_UPDATE",
        detail=_format_position_detail,
        data=_format_position_data,
    ),
    ConnectionStatusEvent: HandlerConfig(
        category="CONNECTION",
        action=lambda e: e.status,
        detail=lambda e: e.message or e.status,
        data=lambda e: {"status": e.status, "message": e.message},
    ),
    BotStateChangedEvent: HandlerConfig(
        category="STATE",
        action=lambda e: "ACTIVATED" if e.is_running else "DEACTIVATED",
        detail=lambda e: f"Bot {('activado' if e.is_running else 'desactivado')} en modo {e.mode}",
        data=lambda e: {"is_running": e.is_running, "mode": e.mode},
    ),
    SettingsUpdatedEvent: HandlerConfig(
        category="CONFIG",
        action=lambda e: "UPDATED",
        detail=lambda e: (
            f"Config actualizada: {e.symbol} | {e.mode} | {e.trading_type}"
        ),
        data=lambda e: {
            "symbol": e.symbol,
            "mode": e.mode,
            "trading_type": e.trading_type,
        },
    ),
    TradingLifecycleEvent: HandlerConfig(
        category="STATE",
        action=lambda e: f"TRADING_{e.action}",
        detail=lambda e: e.detail,
        data=lambda e: e.data,
    ),
    OperationInsertedEvent: HandlerConfig(
        category="OPERATION",
        action=lambda e: "PENDING_INSERTED",
        detail=lambda e: (
            f"SL condición cumplida | {e.active_side} SL=${e.active_sl:,.4f} "
            f"> Pa=${e.pa:,.4f} → Nueva PENDING={e.new_pending_side}"
        ),
        data=lambda e: {
            "active_side": e.active_side,
            "active_sl": e.active_sl,
            "pa": e.pa,
            "new_pending_side": e.new_pending_side,
        },
    ),
    TimeframeCycleEvent: HandlerConfig(
        category="OPERATION",
        action=lambda e: "TIMEFRAME_TICK",
        detail=lambda e: (
            f"Ciclo completado | Pa=${e.pa:,.4f} | "
            f"ACTIVE={e.active_side} | Nueva PENDING={e.new_pending_side}"
        ),
        data=lambda e: {
            "pa": e.pa,
            "active_side": e.active_side,
            "new_pending_side": e.new_pending_side,
            "operations_count": e.operations_count,
        },
    ),
    StopLossEvent: HandlerConfig(
        category="ORDER",
        action=lambda e: "STOP_LOSS_EXECUTED",
        detail=lambda e: (
            f"SL ejecutado | {e.side} {e.quantity:.6f} @ ${e.price:,.4f} | {e.mode}"
        ),
        data=lambda e: {
            "order_id": e.order_id,
            "side": e.side,
            "quantity": e.quantity,
            "price": e.price,
            "mode": e.mode,
        },
    ),
    InitialOrderEvent: HandlerConfig(
        category="ORDER",
        action=lambda e: "INITIAL_ORDER",
        detail=lambda e: (
            f"Orden inicial | {e.side} {e.quantity:.6f} @ ${e.price:,.4f} | {e.order_id}"
        ),
        data=lambda e: {
            "order_id": e.order_id,
            "side": e.side,
            "quantity": e.quantity,
            "price": e.price,
        },
    ),
}


# ---------------------------------------------------------------------------
# AuditService
# ---------------------------------------------------------------------------

class AuditService:
    """Servicio singleton que recopila eventos de auditoría."""

    def __init__(self, max_events: int = 200) -> None:
        self._events: deque[AuditEvent] = deque(maxlen=max_events)
        self._running = False
        self._handlers: dict[type, Callable] = {}

    async def start(self) -> None:
        """Inicia suscripciones a eventos relevantes."""
        if self._running:
            return
        self._running = True

        for event_type, config in HANDLER_REGISTRY.items():
            handler = self._make_handler(config)
            self._handlers[event_type] = handler
            event_bus.subscribe(event_type, handler)

        log.info("AuditService started")

    async def stop(self) -> None:
        """Detiene suscripciones."""
        if not self._running:
            return
        self._running = False

        for event_type, handler in self._handlers.items():
            event_bus.unsubscribe(event_type, handler)
        self._handlers.clear()

        log.info("AuditService stopped")

    def get_recent_events(self, limit: int = 100) -> list[AuditEvent]:
        """Retorna los últimos N eventos de auditoría."""
        return list(self._events)[-limit:]

    def get_events_by_category(self, category: str, limit: int = 100) -> list[AuditEvent]:
        """Retorna eventos filtrados por categoría."""
        filtered = [e for e in self._events if e.category == category]
        return filtered[-limit:]

    # ------------------------------------------------------------------
    # Publicación de eventos
    # ------------------------------------------------------------------

    def _publish(self, event: AuditEvent) -> None:
        """Agrega evento al buffer y publica al EventBus."""
        self._events.append(event)
        event_bus.publish(event)

    # ------------------------------------------------------------------
    # Factory de handlers
    # ------------------------------------------------------------------

    def _make_handler(self, config: HandlerConfig) -> Callable:
        """Genera un handler async a partir de una configuración declarativa."""
        async def handler(event: Any) -> None:
            if config.filter and not config.filter(event):
                return
            self._publish(AuditEvent(
                category=config.category,
                action=config.action(event),
                detail=config.detail(event),
                data=config.data(event),
            ))
        return handler


# Singleton
audit_service = AuditService()
