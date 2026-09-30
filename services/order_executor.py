"""
OrderExecutor — Protocolo y estrategias para ejecución de órdenes.

Responsabilidades:
- Definir interfaz única de ejecución (ISP): execute(OrderRequest)
- Strategy pattern: Paper vs Live (OCP)
- Eliminar if/else en BotEngine (SRP)

Principios:
- ISP: un solo método execute() cubre MARKET y LIMIT
- DIP: BotEngine depende de abstracción, no de binance_client
- OCP: nuevo modo = nueva clase, no modificar existente
- DRY: build_order_params / is_limit_crossed son la única fuente
  de construcción de params y de lógica de cruce, compartida por
  PaperExecutor, LiveExecutor y BotEngine.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import uuid
import logging

from config.settings import settings

log = logging.getLogger(__name__)


def generate_order_id(prefix: str = "ORDER") -> str:
    """
    Genera un order_id único usando UUID4.

    Principios:
    - SRP: Solo genera IDs, nada más
    - DRY: Una sola implementación reutilizada
    - Función pura: Sin estado, sin efectos secundarios
    """
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


@dataclass
class OrderRequest:
    """Parámetros normalizados de una orden a ejecutar."""
    symbol: str
    side: str                            # "BUY" | "SELL"
    quantity: float
    order_type: str = "MARKET"           # "MARKET" | "LIMIT"
    price: float = 0.0                   # precio límite (solo LIMIT)
    entry_price: float = 0.0             # Pe teórica para fill de referencia
    stop_loss: float = 0.0               # PSL
    client_order_id: str = ""            # id canónico generado por el bot
    market_price: float = 0.0            # último precio (para sim paper)


@dataclass
class OrderPlacement:
    """Resultado de colocar una orden: o está llenada o sigue working."""
    order_id: str                        # clientOrderId (id canónico)
    status: str                          # "FILLED" | "NEW"
    fill_price: float = 0.0              # precio de fill (0 si NEW)
    mode: str = "PAPER"                  # "PAPER" | "LIVE"


def is_limit_crossed(side: str, limit_price: float, market_price: float) -> bool:
    """Función pura: ¿el mercado ya cruzó el precio límite?.

    Única fuente de la lógica de cruce (DRY) — la comparten
    PaperExecutor (fill instantáneo) y BotEngine (fill por tick PAPER).

    - BUY  limit es ejecutable cuando market <= limit
    - SELL limit es ejecutable cuando market >= limit
    """
    if limit_price <= 0 or market_price <= 0:
        return False
    if side == "BUY":
        return market_price <= limit_price
    return market_price >= limit_price


def build_order_params(request: OrderRequest) -> dict:
    """Construye los params del exchange para una orden (DRY).

    Única fuente de verdad del payload enviado a Binance: type,
    price, timeInForce y newClientOrderId.

    `newOrderRespType=RESULT` (válido en Spot/Futures/Margin) hace que el
    exchange devuelva la orden completa: `status=FILLED` y `avgPrice` para
    una MARKET. Sin él, el ACK de Futures responde `status=NEW` y la orden
    quedaría registrada como "working" con price=0 — `is_limit_crossed`
    nunca la llenaría (violación del contrato de OrderExecutor.execute).
    """
    params: dict = {
        "symbol": request.symbol,
        "side": request.side,
        "quantity": request.quantity,
        "newClientOrderId": request.client_order_id,
        "newOrderRespType": "RESULT",
    }
    if request.order_type == "LIMIT":
        params.update({
            "type": "LIMIT",
            "price": request.price,
            "timeInForce": "GTC",
        })
    else:
        params["type"] = "MARKET"
    return params


class OrderExecutor(ABC):
    """Interfaz para ejecución de órdenes (DIP)."""

    @abstractmethod
    async def execute(self, request: OrderRequest) -> OrderPlacement:
        """Ejecuta una orden MARKET o LIMIT y retorna su colocación.

        MARKET siempre retorna status="FILLED".
        LIMIT retorna status="NEW" (working) o "FILLED" si el mercado
        ya la cruzó en el momento de la colocación.
        """
        ...

    @abstractmethod
    async def cancel(self, client_order_id: str) -> None:
        """Cancela una orden working por clientOrderId.

        Lanza excepción si el exchange rechaza la cancelación — el
        caller decide (la orden pudo haber llenado ya: no perder el fill).
        PaperExecutor es no-op (la orden solo existe en el registro del motor).
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Cierra recursos (cliente Binance, etc.)."""
        ...

    def invalidate_leverage(self) -> None:
        """Marca que el leverage debe re-aplicarse en el exchange.

        Override en LiveExecutor. No-op en PaperExecutor.
        """


class PaperExecutor(OrderExecutor):
    """Ejecuta órdenes simuladas (sin conexión a Binance)."""

    async def execute(self, request: OrderRequest) -> OrderPlacement:
        if request.order_type == "LIMIT":
            if is_limit_crossed(request.side, request.price, request.market_price):
                # Marketable: el mercado ya está del otro lado → fill inmediato
                fill_price = request.market_price if request.market_price > 0 else request.price
                log.info(
                    "[PAPER] %s %s %.6f LIMIT %.4f FILLED @ %.4f",
                    request.side, request.symbol, request.quantity,
                    request.price, fill_price,
                )
                return OrderPlacement(
                    order_id=request.client_order_id,
                    status="FILLED",
                    fill_price=fill_price,
                    mode="PAPER",
                )
            log.info(
                "[PAPER] %s %s %.6f LIMIT %.4f NEW (esperando cruce)",
                request.side, request.symbol, request.quantity, request.price,
            )
            return OrderPlacement(
                order_id=request.client_order_id,
                status="NEW",
                fill_price=0.0,
                mode="PAPER",
            )

        fill_price = request.entry_price if request.entry_price > 0 else 0.0
        log.info(
            "[PAPER] %s %s %.6f MARKET @ %.4f",
            request.side, request.symbol, request.quantity, fill_price,
        )
        return OrderPlacement(
            order_id=request.client_order_id,
            status="FILLED",
            fill_price=fill_price,
            mode="PAPER",
        )

    async def cancel(self, client_order_id: str) -> None:
        """No-op: la orden PAPER solo vive en el registro del BotEngine."""
        log.info("[PAPER] cancel %s (registro local)", client_order_id)

    async def close(self) -> None:
        pass


class LiveExecutor(OrderExecutor):
    """Ejecuta órdenes reales en Binance."""

    def __init__(self) -> None:
        self._client = None
        self._leverage_set: bool = False

    async def execute(self, request: OrderRequest) -> OrderPlacement:
        from services.binance_client import create_client, execute_order

        if not self._client:
            self._client = await create_client()

        if settings.TRADING_TYPE in ("FUTURES", "MARGIN") and not self._leverage_set:
            await self._set_leverage()

        params = build_order_params(request)
        response = await execute_order(self._client, **params)

        exchange_status = str(response.get("status", "NEW"))
        if exchange_status in ("FILLED",):
            status = "FILLED"
        elif exchange_status in ("NEW", "PARTIALLY_FILLED"):
            status = "NEW"
        else:
            # CANCELED/EXPIRED/REJECTED en la misma llamada → tratar como no fill
            status = "NEW"

        fill_price = self._extract_fill_price(response, request)

        if request.order_type == "MARKET" and status != "FILLED":
            # Contrato de OrderExecutor.execute (LSP): una MARKET siempre
            # retorna FILLED. Con newOrderRespType=RESULT no debería ocurrir.
            log.error(
                "[LIVE] MARKET %s %s returned %s instead of FILLED",
                request.side, request.client_order_id, exchange_status,
            )

        log.info(
            "[LIVE] %s %s %.6f %s -> %s (exchange=%s) @ %.4f",
            request.side, request.symbol, request.quantity,
            request.order_type, status, exchange_status, fill_price,
        )
        return OrderPlacement(
            order_id=request.client_order_id,
            status=status,
            fill_price=fill_price,
            mode="LIVE",
        )

    @staticmethod
    def _extract_fill_price(response: dict, request: OrderRequest) -> float:
        """Precio promedio de fill desde la respuesta del exchange (DRY)."""
        # Futures reporta avgPrice directo
        avg = float(response.get("avgPrice", 0) or 0)
        if avg > 0:
            return avg
        # Spot FILLED reporta fills solo en MARKET; LIMIT llenada usa cociente
        fills = response.get("fills") or []
        if fills:
            return float(fills[0].get("price", 0) or 0)
        executed = float(response.get("executedQty", 0) or 0)
        cumulative = float(response.get("cummulativeQuoteQty", 0) or 0)
        if executed > 0 and cumulative > 0:
            return cumulative / executed
        return request.price if request.order_type == "LIMIT" else request.entry_price

    async def _set_leverage(self) -> None:
        """Configura el leverage para Futures/Margin.

        Lanza excepción si falla — el caller (_dispatch_order) publica
        OrderFailedEvent y aborta la orden.
        """
        if settings.TRADING_TYPE == "FUTURES":
            await self._client.futures_change_leverage(
                symbol=settings.TRADING_SYMBOL,
                leverage=settings.LEVERAGE,
            )
        elif settings.TRADING_TYPE == "MARGIN":
            # Binance Cross Margin solo acepta 3x o 5x
            effective = 5 if settings.LEVERAGE >= 5 else 3
            await self._client.set_margin_max_leverage(
                maxLeverage=effective,
            )
        self._leverage_set = True
        log.info(
            "Leverage set to %dx for %s",
            settings.LEVERAGE, settings.TRADING_TYPE,
        )

    def invalidate_leverage(self) -> None:
        """Marca que el leverage debe re-aplicarse en Binance."""
        self._leverage_set = False

    async def cancel(self, client_order_id: str) -> None:
        """Cancela una orden working en Binance por clientOrderId."""
        from services.binance_client import cancel_order

        if not self._client:
            # Sin cliente nunca se envió orden → nada que cancelar
            return
        await cancel_order(self._client, settings.TRADING_SYMBOL, client_order_id)
        log.info("[LIVE] cancel %s OK", client_order_id)

    async def close(self) -> None:
        """Cierra la conexión a Binance."""
        if self._client:
            try:
                await self._client.close_connection()
            except Exception:
                pass
            self._client = None


def create_executor(mode: str) -> OrderExecutor:
    """Factory method para crear el executor según el modo (DIP)."""
    if mode == "LIVE":
        return LiveExecutor()
    return PaperExecutor()
