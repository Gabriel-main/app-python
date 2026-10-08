"""
DataRepair — Reparación idempotente de huérfanos en DB al arranque.

Se ejecuta UNA vez por sesión, DESPUÉS de `settings.load_from_db()` y
ANTES de `bot_engine.start()` (app_layout), vía `db_queue.submit()` —
único gateway de escritura (AG.md).

Repara tres clases de huérfanos históricos:

1. `operations.symbol` = 'OC'/'OV': bug de derivar el símbolo del prefijo
   del order_id (360 filas). → símbolo real (settings.TRADING_SYMBOL).
2. `positions` con status='OPEN' de sesiones anteriores: el espejo de
   posiciones es por-sesión (se re-crea en el próximo tick), así que al
   arrancar toda fila OPEN se cierra → CLOSED con closed_pnl =
   COALESCE(unrealized_pnl, 0) (D3) y closed_price = mark_price.
3. `orders` PAPER con status='PENDING': LIMIT working de una sesión que
   murió sin fill ni cancel (el fill solo se resuelve en memoria vía
   `_working_orders`). → CANCELLED. LIVE no se toca (divergiría de Binance).

Idempotente: cada sentencia solo afecta filas que aún casan con el patrón
de huérfano; tras la primera ejecución las siguientes encuentran 0 filas.
"""
from __future__ import annotations

import logging
import time

from sqlalchemy import text

from config.settings import settings
from database.connection import get_session
from database.db_queue import db_queue

log = logging.getLogger(__name__)


class DataRepair:
    """Saneo de datos al arranque (SRP: solo reparación, nada de trading)."""

    async def run(self) -> dict[str, int]:
        """Ejecuta todas las reparaciones serializadas en el worker.

        Returns:
            Conteo de filas afectadas por reparación (para el log).
        """
        counts = await db_queue.submit(self._repair_all)
        total = sum(counts.values())
        if total:
            log.info(
                "DataRepair: operations.symbol=%d, positions OPEN→CLOSED=%d, "
                "orders PAPER PENDING→CANCELLED=%d",
                counts["symbol_fixed"], counts["positions_closed"],
                counts["orders_cancelled"],
            )
        else:
            log.debug("DataRepair: nada que reparar")
        return counts

    async def _repair_all(self) -> dict[str, int]:
        """Corre dentro del worker (una sesión, un commit)."""
        now = time.time()
        async with get_session() as session:
            # 1. symbol OC/OV → símbolo real (D1)
            result = await session.execute(
                text(
                    "UPDATE operations SET symbol = :sym "
                    "WHERE symbol IN ('OC', 'OV')"
                ),
                {"sym": settings.TRADING_SYMBOL},
            )
            symbol_fixed = result.rowcount or 0

            # 2. posiciones OPEN stale → CLOSED (D3: pnl = unrealized_pnl)
            result = await session.execute(
                text(
                    "UPDATE positions SET status = 'CLOSED', "
                    "closed_price = mark_price, "
                    "closed_pnl = COALESCE(unrealized_pnl, 0), "
                    "closed_at = :now "
                    "WHERE status = 'OPEN'"
                ),
                {"now": now},
            )
            positions_closed = result.rowcount or 0

            # 3. PENDING PAPER → CANCELLED (LIVE intocado)
            result = await session.execute(
                text(
                    "UPDATE orders SET status = 'CANCELLED' "
                    "WHERE status = 'PENDING' AND mode = 'PAPER'"
                )
            )
            orders_cancelled = result.rowcount or 0

            await session.commit()

        return {
            "symbol_fixed": symbol_fixed,
            "positions_closed": positions_closed,
            "orders_cancelled": orders_cancelled,
        }


# Instancia singleton
data_repair = DataRepair()
