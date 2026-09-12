"""
BalanceDisplay — Strategy pattern para formatos de balance por trading type.

Extraído de BalanceCard para aplicar OCP + SRP.
Agregar un nuevo trading type = crear clase nueva, no modificar if/elif/else.
"""
from __future__ import annotations

from typing import Protocol

from core.events import BalanceUpdateEvent


def format_amount(value: float) -> str:
    """Formatea un monto con separadores de miles."""
    abs_val = abs(value)
    sign = "-" if value < 0 else ""
    if abs_val >= 1000:
        return f"{sign}${abs_val:,.2f}"
    elif abs_val >= 1:
        return f"{sign}${abs_val:.4f}"
    else:
        return f"{sign}${abs_val:.6f}"


class BalanceDisplayStrategy(Protocol):
    """Interfaz para estrategias de display de balance."""

    def get_labels(self) -> tuple[str, str, str | None]: ...
    def format_values(self, event: BalanceUpdateEvent) -> tuple[str, str, str | None]: ...


class SpotBalanceDisplay:
    """Estrategia para Spot: Disponible / Bloqueado."""

    def get_labels(self) -> tuple[str, str, str | None]:
        return ("Disponible", "Bloqueado", None)

    def format_values(self, event: BalanceUpdateEvent) -> tuple[str, str, str | None]:
        return (format_amount(event.free), format_amount(event.locked), None)


class FuturesBalanceDisplay:
    """Estrategia para Futures: Wallet / Disponible / PnL No Real."""

    def get_labels(self) -> tuple[str, str, str | None]:
        return ("Wallet", "Disponible", "PnL No Real.")

    def format_values(self, event: BalanceUpdateEvent) -> tuple[str, str, str | None]:
        pnl = None
        if event.unrealized_pnl != 0:
            sign = "+" if event.unrealized_pnl >= 0 else ""
            pnl = f"{sign}{format_amount(event.unrealized_pnl)}"
        return (format_amount(event.free), format_amount(event.available), pnl)


class MarginBalanceDisplay:
    """Estrategia para Margin: Net Asset / Prestado / Interés."""

    def get_labels(self) -> tuple[str, str, str | None]:
        return ("Net Asset", "Prestado", "Interés")

    def format_values(self, event: BalanceUpdateEvent) -> tuple[str, str, str | None]:
        interest = format_amount(event.interest) if event.interest > 0 else None
        return (format_amount(event.free), format_amount(event.borrowed), interest)


_STRATEGIES: dict[str, BalanceDisplayStrategy] = {
    "SPOT": SpotBalanceDisplay(),
    "FUTURES": FuturesBalanceDisplay(),
    "MARGIN": MarginBalanceDisplay(),
}


def get_strategy(trading_type: str) -> BalanceDisplayStrategy:
    """Retorna la estrategia para el tipo de trading dado."""
    return _STRATEGIES.get(trading_type, _STRATEGIES["SPOT"])
