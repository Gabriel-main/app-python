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

    async def get_trading_symbols(self) -> list[dict]: ...
    def clear_cache(self) -> None: ...


class BinanceSymbolRepository:
    """Implementación que delega a BinanceService."""

    def __init__(self, binance_service: object) -> None:
        self._service = binance_service

    async def get_trading_symbols(self) -> list[dict]:
        return await self._service.get_trading_symbols()

    def clear_cache(self) -> None:
        self._service.clear_symbols_cache()


class EventBusSymbolRepository:
    """Implementación que usa EventBus para solicitar símbolos."""

    async def get_trading_symbols(self) -> list[dict]:
        from services.binance_service import binance_service
        return await binance_service.get_trading_symbols()

    def clear_cache(self) -> None:
        from services.binance_service import binance_service
        binance_service.clear_symbols_cache()
