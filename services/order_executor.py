"""
OrderExecutor — Protocolo y estrategias para ejecución de órdenes.

Responsabilidades:
- Definir interfaz para ejecutar órdenes (DIP)
- Strategy pattern: Paper vs Live (OCP)
- Eliminar if/else en BotEngine (SRP)

Principios:
- ISP: Interfaz mínima (solo execute_market)
- DIP: BotEngine depende de abstracción, no de binance_client
- OCP: Nuevo modo = nueva clase, no modificar existente
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
class OrderResult:
    """Resultado de una ejecución de orden."""
    order_id: str
    fill_price: float
    mode: str  # "PAPER" | "LIVE"


class OrderExecutor(ABC):
    """Interfaz para ejecución de órdenes (DIP)."""

    @abstractmethod
    async def execute_market(
        self, symbol: str, side: str, quantity: float,
        entry_price: float = 0.0, stop_loss: float = 0.0,
    ) -> OrderResult:
        """Ejecuta una orden MARKET y retorna el resultado."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Cierra recursos (cliente Binance, etc.)."""
        ...


class PaperExecutor(OrderExecutor):
    """Ejecuta órdenes simuladas (sin conexión a Binance)."""

    async def execute_market(
        self, symbol: str, side: str, quantity: float,
        entry_price: float = 0.0, stop_loss: float = 0.0,
    ) -> OrderResult:
        fill_price = entry_price if entry_price > 0 else 0.0
        order_id = generate_order_id("PAPER")

        log.info("[PAPER] %s %s %.6f @ %.4f", side, symbol, quantity, fill_price)

        return OrderResult(
            order_id=order_id,
            fill_price=fill_price,
            mode="PAPER",
        )

    async def close(self) -> None:
        pass


class LiveExecutor(OrderExecutor):
    """Ejecuta órdenes reales en Binance."""

    def __init__(self) -> None:
        self._client = None
        self._leverage_set: bool = False

    async def execute_market(
        self, symbol: str, side: str, quantity: float,
        entry_price: float = 0.0, stop_loss: float = 0.0,
    ) -> OrderResult:
        from services.binance_client import create_client, execute_order

        if not self._client:
            self._client = await create_client()

        if settings.TRADING_TYPE in ("FUTURES", "MARGIN") and not self._leverage_set:
            await self._set_leverage()

        order_params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": quantity,
        }

        response = await execute_order(self._client, **order_params)
        fill_price = float(response.get("fills", [{}])[0].get("price", entry_price))
        order_id = str(response.get("orderId", generate_order_id("LIVE")))

        log.info("[LIVE] %s %s %.6f @ %.4f", side, symbol, quantity, fill_price)

        return OrderResult(
            order_id=order_id,
            fill_price=fill_price,
            mode="LIVE",
        )

    async def _set_leverage(self) -> None:
        """Configura el leverage para Futures/Margin."""
        try:
            if settings.TRADING_TYPE == "FUTURES":
                await self._client.futures_change_leverage(
                    symbol=settings.TRADING_SYMBOL,
                    leverage=settings.LEVERAGE,
                )
            elif settings.TRADING_TYPE == "MARGIN":
                await self._client.change_margin(
                    symbol=settings.TRADING_SYMBOL,
                    leverage=settings.LEVERAGE,
                )
            self._leverage_set = True
            log.info("Leverage set to %dx for %s", settings.LEVERAGE, settings.TRADING_TYPE)
        except Exception as exc:
            log.error("Failed to set leverage: %s", exc)

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
