"""
TradingRules — Reglas puras de sizing y filtros de exchange.

SRP: solo cálculos y validaciones deterministas. Sin I/O directo, sin Flet y
sin el singleton `settings` — los datos llegan como argumentos.

OCP: los límites del exchange llegan como datos (`SymbolFilters`), no como
`if symbol == "BTCUSDT"`. Una exchange nueva = un nuevo parser de filtros,
sin tocar BotEngine ni la UI.

DRY: `size_entry()` es la ÚNICA fuente de "¿esta cantidad es operable?".
La UI (Settings) y el motor (BotEngine) llaman a la misma función a través
de `QuantitySizer` — cero lógica duplicada.

DIP: `QuantitySizer` depende del protocolo `SymbolFiltersProvider` (1 método),
nunca de `binance_service`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

# Fallback cuando exchangeInfo no está disponible (Spot USDⓈ-M / error -4164)
MIN_FUTURES_NOTIONAL: float = 50.0

_EPS = 1e-9


# ---------------------------------------------------------------------------
# Filtros de exchange (datos — OCP)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SymbolFilters:
    """Límites de cantidad/precio de un símbolo. Ceros = sin restricción."""

    symbol: str
    min_qty: float = 0.0
    step_size: float = 0.0
    min_notional: float = 0.0
    tick_size: float = 0.0

    @classmethod
    def unknown(cls, symbol: str = "") -> SymbolFilters:
        """Filtros sin información (fail-open: no bloquea el sizing)."""
        return cls(symbol=symbol)

    @classmethod
    def from_exchange_info(cls, info: dict, symbol: str) -> SymbolFilters | None:
        """Parsea `exchangeInfo` de Binance. None si el símbolo no existe.

        Soporta Spot y USDⓈ-M Futures — las claves difieren entre mercados:
        - cantidad: LOT_SIZE y MARKET_LOT_SIZE (una orden MARKET debe pasar
          ambas, se toma el máximo conservador)
        - notional: MIN_NOTIONAL.notional (Futures) o NOTIONAL.minNotional (Spot)
        """
        target = symbol.upper()
        entry = next(
            (s for s in info.get("symbols", []) if s.get("symbol") == target),
            None,
        )
        if entry is None:
            return None

        filters = {f.get("filterType"): f for f in entry.get("filters", [])}

        lot = filters.get("LOT_SIZE") or {}
        market_lot = filters.get("MARKET_LOT_SIZE") or {}

        min_qty = max(_f(lot.get("minQty")), _f(market_lot.get("minQty")))
        step_size = max(_f(lot.get("stepSize")), _f(market_lot.get("stepSize")))

        if step_size <= 0 and min_qty <= 0:
            return None  # sin LOT_SIZE no hay cómo dimensionar

        min_notional = _f(
            (filters.get("MIN_NOTIONAL") or {}).get("notional")
            or (filters.get("NOTIONAL") or {}).get("minNotional")
        )
        tick_size = _f((filters.get("PRICE_FILTER") or {}).get("tickSize"))

        return cls(
            symbol=target,
            min_qty=min_qty,
            step_size=step_size,
            min_notional=min_notional,
            tick_size=tick_size,
        )


def _f(value) -> float:
    """float() tolerante a None / strings vacíos de exchangeInfo."""
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Aritmética de cantidades (pura)
# ---------------------------------------------------------------------------
def floor_to_step(quantity: float, step: float) -> float:
    """Trunca `quantity` al múltiplo de `step` (regla LOT_SIZE)."""
    if step <= 0 or quantity <= 0:
        return quantity
    steps = math.floor(quantity / step + _EPS)
    return round(steps * step, 12)


def min_operable_quantity(price: float, filters: SymbolFilters) -> float:
    """Mínima cantidad operable a `price` (múltiplo de step_size)."""
    needed = filters.min_qty
    if filters.min_notional > 0 and price > 0:
        if filters.step_size > 0:
            notional_steps = math.ceil(
                filters.min_notional / price / filters.step_size - _EPS
            )
            notional_qty = round(notional_steps * filters.step_size, 12)
        else:
            notional_qty = filters.min_notional / price
        needed = max(needed, notional_qty)
    return needed


# ---------------------------------------------------------------------------
# Validación del formulario (SRP — se re-exporta desde ui.settings_sections)
# ---------------------------------------------------------------------------
def validate_amount(
    amount: float,
    trading_type: str,
    min_notional: float = MIN_FUTURES_NOTIONAL,
) -> str | None:
    """Valida el monto de operación. Retorna mensaje de error o None."""
    if amount <= 0:
        return "El monto debe ser mayor a 0."
    if trading_type == "FUTURES" and amount < min_notional:
        return (
            f"En Futures el monto mínimo es {min_notional:g} USDT "
            "(notional de Binance)."
        )
    return None


# ---------------------------------------------------------------------------
# Sizing — única fuente de verdad (DRY)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SizedQuantity:
    """Resultado de dimensionar una entrada. `error` != None => no operable."""

    quantity: float
    notional: float
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def size_entry(
    trade_amount: float,
    price: float,
    filters: SymbolFilters,
    trading_type: str,
) -> SizedQuantity:
    """Calcula la cantidad de una entrada o explica por qué no es operable.

    Reglas, en orden:
      1. sin precio o monto <= 0              → error
      2. qty = floor(amount / price, step)
      3. qty < mín. operable (min_qty / min_notional) → error con números
      4. filtros desconocidos (ceros)         → fail-open, no bloquea
    """
    if price <= 0:
        return SizedQuantity(0.0, 0.0, "Sin precio de mercado para dimensionar la orden.")
    if trade_amount <= 0:
        return SizedQuantity(0.0, 0.0, "El monto debe ser mayor a 0.")

    raw = trade_amount / price
    quantity = floor_to_step(raw, filters.step_size)

    needed = min_operable_quantity(price, filters)
    if quantity < needed:
        return SizedQuantity(
            0.0,
            0.0,
            f"La cantidad {raw:.8f} es menor al mínimo {needed:g} operable en "
            f"{filters.symbol or 'este símbolo'}. Monto mínimo a precio actual: "
            f"{needed * price:,.2f} USDT.",
        )

    notional = quantity * price
    return SizedQuantity(quantity, notional, None)


# ---------------------------------------------------------------------------
# QuantitySizer — colaborador único UI <-> motor (ISP + DIP)
# ---------------------------------------------------------------------------
class SymbolFiltersProvider(Protocol):
    """ISP: 1 método. Satisfecho estructuralmente por SymbolRepository."""

    async def get_symbol_filters(
        self, symbol: str, trading_type: str,
    ) -> SymbolFilters: ...


class QuantitySizer:
    """Cachea los filtros del exchange y expone un único `size()`.

    UI y motor instancian el suyo — ambos delegan en `size_entry()` (DRY).
    """

    def __init__(self, provider: SymbolFiltersProvider | None = None) -> None:
        self._provider = provider
        self._filters: SymbolFilters = SymbolFilters.unknown()

    async def refresh(self, symbol: str, trading_type: str) -> SymbolFilters:
        """Actualiza los filtros cacheados. Fallo de red → fail-open."""
        filters = SymbolFilters.unknown(symbol)
        if self._provider is not None:
            try:
                fetched = await self._provider.get_symbol_filters(
                    symbol, trading_type,
                )
                if fetched is not None:
                    filters = fetched
            except Exception:
                filters = SymbolFilters.unknown(symbol)
        self._filters = filters
        return self._filters

    @property
    def filters(self) -> SymbolFilters:
        return self._filters

    def size(self, trade_amount: float, price: float, trading_type: str) -> SizedQuantity:
        return size_entry(trade_amount, price, self._filters, trading_type)
