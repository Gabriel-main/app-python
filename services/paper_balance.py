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

from config.settings import settings
from core.event_bus import event_bus
from core.events import BalanceUpdateEvent, OrderExecutedEvent
from services.pnl_calculator import PnLCalculator

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
    stop_loss: float = 0.0    # Precio de stop loss (PSL)
    capital: float = 0.0      # Capital invertido en la operación


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

    async def _on_order_executed(self, event: OrderExecutedEvent) -> None:
        if event.mode != "PAPER":
            return

        # purpose distingue apertura (debita/bloquea) de cierre (libera+PnL).
        # Sin este campo, una entrada corta acredita la venta como proceeds
        # e infla el wallet (bug del +monto).
        if event.purpose == "EXIT":
            self._handle_exit(event)
        else:
            self._handle_entry(event)

        self._publish_balance()

    @staticmethod
    def _position_key(event: OrderExecutedEvent) -> str:
        """Clave de posición: operation_id (OC-/OV-) con fallback a order_id."""
        return event.operation_id or event.order_id

    def _handle_entry(self, event: OrderExecutedEvent) -> None:
        """ENTRY (BUY o SELL): debitar capital, bloquearlo y trackear posición.

        Simétrico para largo y corto: abrir posición siempre consume margen,
        sin importar el lado.
        """
        capital = settings.TRADE_AMOUNT  # Capital invertido
        self._free -= capital
        self._locked += capital

        self._positions[self._position_key(event)] = _OpenPosition(
            side=event.side,
            entry_price=event.entry_price,
            quantity=event.quantity,
            stop_loss=event.stop_loss,
            capital=capital,
        )
        log.debug(
            "PAPER ENTRY %s: capital=%.4f, free=%.2f, locked=%.2f",
            event.side, capital, self._free, self._locked,
        )

    def _handle_exit(self, event: OrderExecutedEvent) -> None:
        """EXIT: cerrar posición, calcular PnL con fórmula unificada.

        Si no hay posición trackeada (p.ej. tras reinicio) NO toca el saldo:
        acreditar proceeds sin débito previo inflaría el wallet.
        """
        position = self._positions.pop(self._position_key(event), None)

        if position is None:
            log.warning(
                "PAPER EXIT sin posición trackeada (%s) — saldo sin cambios",
                self._position_key(event),
            )
            return

        resultado, pnl = PnLCalculator.calc_closed_pnl(
            capital=position.capital,
            entry_price=position.entry_price,
            stop_loss=position.stop_loss,
            side=position.side,
        )

        self._locked -= position.capital
        self._free += resultado
        log.debug(
            "PAPER EXIT %s: pnl=%.4f, free=%.2f, locked=%.2f",
            position.side, pnl, self._free, self._locked,
        )

    # ------------------------------------------------------------------
    # Publicación
    # ------------------------------------------------------------------

    def _publish_balance(self) -> None:
        event_bus.publish(BalanceUpdateEvent(
            asset="USDT",
            trading_type=settings.TRADING_TYPE,
            free=round(self._free, 2),
            locked=round(self._locked, 2),
            available=round(self._free, 2),
        ))


# Singleton
paper_balance = PaperBalanceService()
