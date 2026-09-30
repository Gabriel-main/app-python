"""
BinanceClientFactory — Creación de clientes y enrutamiento de órdenes.

Cumple SRP: solo crea clientes y rutea órdenes.
Cumple DRY: una sola implementación reutilizada por BinanceService y BotEngine.
Cumple DIP: ambas capas dependen de esta factoría, no de AsyncClient directamente.
"""
from __future__ import annotations

from typing import Any

from binance import AsyncClient  # type: ignore

from config.settings import settings


async def create_client() -> AsyncClient:
    """Crea un AsyncClient con la configuración actual (API keys + testnet)."""
    return await AsyncClient.create(
        api_key=settings.BINANCE_API_KEY,
        api_secret=settings.BINANCE_API_SECRET,
        testnet=settings.BINANCE_TESTNET,
    )


async def execute_order(client: AsyncClient, **params: Any) -> dict:
    """Ejecuta una orden según TRADING_TYPE (Spot/Futures/Margin)."""
    if settings.TRADING_TYPE == "FUTURES":
        return await client.futures_create_order(**params)
    elif settings.TRADING_TYPE == "MARGIN":
        return await client.margin_create_order(**params)
    else:
        return await client.create_order(**params)


async def cancel_order(client: AsyncClient, symbol: str, client_order_id: str) -> dict:
    """Cancela una orden abierta por clientOrderId según TRADING_TYPE.

    DRY: mismo enrutado por TRADING_TYPE que execute_order.
    El bot usa clientOrderId (newClientOrderId) como id canónico.
    """
    if settings.TRADING_TYPE == "FUTURES":
        return await client.futures_cancel_order(symbol=symbol, origClientOrderId=client_order_id)
    elif settings.TRADING_TYPE == "MARGIN":
        return await client.margin_cancel_order(symbol=symbol, origClientOrderId=client_order_id)
    else:
        return await client.cancel_order(symbol=symbol, origClientOrderId=client_order_id)
