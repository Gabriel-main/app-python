"""
PaperBalanceService — Saldo simulado para modo PAPER.

Responsabilidades:
- Mantener saldo en memoria (inicia en PAPER_INITIAL_BALANCE)
- Suscribirse a OrderExecutedEvent (solo mode=PAPER)
- Calcular PnL realizado al ejecutar SL
- Publicar BalanceUpdateEvent tras cada cambio

Principios:
- SRP: Solo maneja saldo paper, no ejecuta órdenes
- OCP: Nuevo tipo de operación = nuevo handler, no modificar existente
- DIP: Depende de EventBus (abstracción), no de BotEngine
- DRY: Reutiliza BalanceUpdateEvent existente
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from core.event_bus import event_bus
from core.events import BalanceUpdateEvent, OrderExecutedEvent

log = logging.getLogger(__name__)

# Balance inicial por defecto (USDT)
PAPER_INITIAL_BALANCE: float = 10_000.0


# ---------------------------------------------------------------------------
# Posición abierta (para calcular PnL al cerrar)
# ---------------------------------------------------------------------------

@dataclass
class _OpenPosition:
    side: str            # "BUY" | "SELL"
    entry_price: float
    quantity: float


# ---------------------------------------------------------------------------
# PaperBalanceService
# ---------------------------------------------------------------------------

class PaperBalanceService:
    """Servicio singleton que rastrea el saldo simulado en modo PAPER."""

    def __init__(self, initial_balance: float = PAPER_INITIAL_BALANCE) -> None:
        self._initial_balance = initial_balance
        self._free: float = initial_balance
        self._locked: float = 0.0
        self._positions: dict[str, _OpenPosition] = {}
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        event_bus.subscribe(OrderExecutedEvent, self._on_order_executed)
        log.info("PaperBalanceService started | initial=%.2f USDT", self._free)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        event_bus.unsubscribe(OrderExecutedEvent, self._on_order_executed)
        log.info("PaperBalanceService stopped")

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_balance(self) -> float:
        """Retorna el saldo disponible actual."""
        return round(self._free, 2)

    # ------------------------------------------------------------------
    # Handler
    # ------------------------------------------------------------------

    def _on_order_executed(self, event: OrderExecutedEvent) -> None:
        if event.mode != "PAPER":
            return

        if event.side == "BUY":
            self._handle_buy(event)
        elif event.side == "SELL":
            self._handle_sell(event)

        self._publish_balance()

    def _handle_buy(self, event: OrderExecutedEvent) -> None:
        """BUY: debitar costo de la posición y abrir tracking."""
        cost = event.quantity * event.price
        self._free -= cost
        self._locked += cost

        self._positions[event.order_id] = _OpenPosition(
            side="BUY",
            entry_price=event.entry_price,
            quantity=event.quantity,
        )
        log.debug(
            "PAPER BUY: cost=%.4f, free=%.2f, locked=%.2f",
            cost, self._free, self._locked,
        )

    def _handle_sell(self, event: OrderExecutedEvent) -> None:
        """SELL: cerrar posición, calcular PnL, acreditar."""
        position = self._positions.pop(event.order_id, None)

        if position:
            # Cerrar posición existente: calcular PnL
            pnl = (event.price - position.entry_price) * position.quantity
            cost = position.quantity * position.entry_price
            self._locked -= cost
            self._free += cost + pnl
            log.debug(
                "PAPER SELL (closed): pnl=%.4f, free=%.2f",
                pnl, self._free,
            )
        else:
            # SELL sin posición abierta (PENDING ejecutada)
            proceeds = event.quantity * event.price
            self._free += proceeds
            log.debug(
                "PAPER SELL (new): proceeds=%.4f, free=%.2f",
                proceeds, self._free,
            )

    # ------------------------------------------------------------------
    # Publicación
    # ------------------------------------------------------------------

    def _publish_balance(self) -> None:
        from config.settings import settings
        event_bus.publish(BalanceUpdateEvent(
            asset="USDT",
            trading_type=settings.TRADING_TYPE,
            free=round(self._free, 2),
            locked=round(self._locked, 2),
            available=round(self._free, 2),
        ))


# Singleton
paper_balance = PaperBalanceService()
