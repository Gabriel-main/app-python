"""
BinanceClientFactory — Creación de clientes y enrutamiento de órdenes.

Cumple SRP: solo crea clientes y rutea órdenes.
Cumple DRY: una sola implementación reutilizada por BinanceService y BotEngine.
Cumple DIP: ambas capas dependen de esta factoría, no de AsyncClient directamente.
"""
from __future__ import annotations

import logging
from typing import Any

from binance import AsyncClient  # type: ignore

from config.settings import settings

log = logging.getLogger(__name__)


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


async def get_asset_free(asset: str) -> float | None:
    """One-shot: saldo free de un activo (SPOT). None si falla (fail-open).

    Se usa SOLO al despachar una ENTRY SELL en SPOT (no hay polling):
    una consulta por intento de colocación. Si la consulta falla, el
    caller deja pasar la orden y Binance sigue siendo la autoridad final.
    """
    client = None
    try:
        client = await create_client()
        balance = await client.get_asset_balance(asset=asset)
        if not balance:
            return None
        return float(balance.get("free", 0.0) or 0.0)
    except Exception as exc:
        log.warning("get_asset_free(%s) failed: %s", asset, exc)
        return None
    finally:
        if client is not None:
            try:
                await client.close_connection()
            except Exception:
                pass
