"""
SymbolRepository — Abstracción para acceso a símbolos de trading.

Aplica DIP: SymbolPicker recibe esta interfaz en vez de importar
binance_service directamente.
"""
from __future__ import annotations

from typing import Protocol

from core.event_bus import event_bus
from core.events import SymbolsListEvent


class SymbolRepository(Protocol):
    """Interfaz para repositorio de símbolos."""

    async def get_trading_symbols(self, trading_type: str = "SPOT", currency: str | None = None) -> list[dict]: ...
    def clear_cache(self) -> None: ...
    async def validate_symbol(
        self, symbol: str, trading_type: str,
    ) -> tuple[bool, list[str]]: ...


class BinanceSymbolRepository:
    """Implementación que delega a BinanceService."""

    def __init__(self, binance_service: object) -> None:
        self._service = binance_service

    async def get_trading_symbols(self, trading_type: str = "SPOT", currency: str | None = None) -> list[dict]:
        return await self._service.get_trading_symbols(trading_type, currency)

    def clear_cache(self) -> None:
        self._service.clear_symbols_cache()

    async def validate_symbol(
        self, symbol: str, trading_type: str,
    ) -> tuple[bool, list[str]]:
        from services.binance_client import create_client
        client = await create_client()
        try:
            return await self._service.validate_symbol_for_market(
                client, symbol, trading_type,
            )
        finally:
            await client.close_connection()


class EventBusSymbolRepository:
    """Implementación que usa EventBus para solicitar símbolos."""

    async def get_trading_symbols(self, trading_type: str = "SPOT", currency: str | None = None) -> list[dict]:
        from services.binance_service import binance_service
        return await binance_service.get_trading_symbols(trading_type, currency)

    def clear_cache(self) -> None:
        from services.binance_service import binance_service
        binance_service.clear_symbols_cache()

    async def validate_symbol(
        self, symbol: str, trading_type: str,
    ) -> tuple[bool, list[str]]:
        from services.binance_client import create_client
        from services.binance_service import binance_service
        client = await create_client()
        try:
            return await binance_service.validate_symbol_for_market(
                client, symbol, trading_type,
            )
        finally:
            await client.close_connection()
