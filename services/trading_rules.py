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
from dataclasses import dataclass, replace
from typing import Protocol

# Fallback cuando exchangeInfo no está disponible (Spot USDⓈ-M / error -4164).
# NO es el mínimo universal de Futures: el real es por símbolo (BTC≈50, SOL≈6)
# y vive en SymbolFilters.min_notional. Ver effective_min_notional().
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

    @property
    def is_unknown(self) -> bool:
        """True si no se resolvió exchangeInfo (todos los límites en cero)."""
        return self.min_qty <= 0 and self.step_size <= 0 and self.min_notional <= 0

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
# Mínimo notional aplicable (fuente única del "¿qué mínimo uso?" — DRY)
# ---------------------------------------------------------------------------
def effective_min_notional(filters: SymbolFilters, trading_type: str) -> float:
    """Mínimo notional aplicable para `filters` en `trading_type`.

    - Filtros conocidos → regla real del símbolo (0 = el exchange no impone
      mínimo; es válido, no se sustituye).
    - Filtros desconocidos + FUTURES → MIN_FUTURES_NOTIONAL (fallback
      conservador: sin exchangeInfo mejor no operar por debajo del global).
    - Filtros desconocidos + SPOT/MARGIN → 0 (no existe mínimo global;
      fail-open, la regla por símbolo vive en los filtros cuando llegan).

    Único punto de decisión: lo consumen la validación sin precio
    (validate_amount) y el sizing con precio (size_entry).
    """
    if not filters.is_unknown:
        return filters.min_notional
    return MIN_FUTURES_NOTIONAL if trading_type == "FUTURES" else 0.0


# ---------------------------------------------------------------------------
# Validación del formulario (SRP — se re-exporta desde ui.settings_sections)
# ---------------------------------------------------------------------------
def validate_amount(
    amount: float,
    trading_type: str,
    min_notional: float = MIN_FUTURES_NOTIONAL,
) -> str | None:
    """Valida el monto SIN precio de mercado. Retorna mensaje o None.

    `min_notional` debe ser el mínimo real del símbolo cuando el caller lo
    conoce — resolverlo con `effective_min_notional(filters, trading_type)`.
    El default es el fallback global (solo correcto si los filtros del
    símbolo son desconocidos).
    """
    if amount <= 0:
        return "El monto debe ser mayor a 0."
    if trading_type == "FUTURES" and amount < min_notional:
        return (
            f"En Futures el monto mínimo es {min_notional:g} USDT "
            "(notional de Binance)."
        )
    return None


# ---------------------------------------------------------------------------
# Validación de fondos (SRP — pre-flight de saldo, consume BalanceUpdateEvent)
# ---------------------------------------------------------------------------
def validate_funds(
    amount: float,
    trading_type: str,
    leverage: int,
    free: float | None,
    available: float | None,
    mode: str,
    asset: str = "USDT",
) -> str | None:
    """Valida que el usuario cubra la operación. Retorna mensaje o None.

    Reglas (la misma que aplica Binance al colocar la orden):
    - PAPER: debita el capital completo → `amount <= free`.
    - LIVE FUTURES: cobra MARGEN = amount ÷ leverage →
      `amount / leverage <= available` (availableBalance de la cuenta).
    - LIVE SPOT/MARGIN: consume `free` → `amount <= free`.
    - `free`/`available` en None = saldo aún desconocido → fail-open
      (no bloquea; Binance sigue siendo la autoridad final).
    - `amount <= 0` → None (ya lo cubre validate_amount, sin doble error).
    """
    if amount <= 0:
        return None

    if mode == "PAPER":
        # paper_balance debita settings.TRADE_AMOUNT completo, sin leverage
        if free is None:
            return None
        required, have, label = amount, free, "Saldo"
    elif trading_type == "FUTURES":
        if available is None:
            return None
        lev = max(leverage, 1)
        required = amount / lev
        have, label = available, "Margen"
    else:  # LIVE SPOT / MARGIN
        if free is None:
            return None
        required, have, label = amount, free, "Saldo"

    if have >= required:
        return None
    if label == "Margen":
        return (
            f"Margen insuficiente: necesitas {required:,.2f} {asset} "
            f"({amount:g} ÷ {lev}x) y tienes {have:,.2f} {asset}."
        )
    return (
        f"Saldo insuficiente: necesitas {required:,.2f} {asset} "
        f"y tienes {have:,.2f} {asset}."
    )


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
      2. resolver notional aplicable          → fallback si filtros desconocidos
      3. qty = floor(amount / price, step)
      4. qty < mín. operable (min_qty / min_notional) → error con números
      5. filtros desconocidos en SPOT         → fail-open, no bloquea
    """
    if price <= 0:
        return SizedQuantity(0.0, 0.0, "Sin precio de mercado para dimensionar la orden.")
    if trade_amount <= 0:
        return SizedQuantity(0.0, 0.0, "El monto debe ser mayor a 0.")

    # Fallback: filtros desconocidos en Futures exigen el mínimo global.
    # (SPOT desconocido → 0, conserva el fail-open documentado.)
    effective = effective_min_notional(filters, trading_type)
    if effective != filters.min_notional:
        filters = replace(filters, min_notional=effective)

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
