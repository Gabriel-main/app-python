"""
Tests para TradingRules — sizing y filtros de exchange (puros).

Fuente única de "¿esta cantidad es operable?": la comparten la UI (Settings)
y el motor (BotEngine) vía QuantitySizer — por eso se testea aquí, no dos veces.
"""
import pytest

from services.trading_rules import (
    MIN_FUTURES_NOTIONAL,
    QuantitySizer,
    SizedQuantity,
    SymbolFilters,
    effective_min_notional,
    floor_to_step,
    min_operable_quantity,
    size_entry,
    validate_amount,
)

# Payloads reales de exchangeInfo (verificados en vivo contra Binance)
_FUTURES_BTCUSDT = {
    "symbols": [{
        "symbol": "BTCUSDT",
        "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
            {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "1000"},
            {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "120"},
            {"filterType": "MIN_NOTIONAL", "notional": "50"},
        ],
    }],
}

_SPOT_BTCUSDT = {
    "symbols": [{
        "symbol": "BTCUSDT",
        "filters": [
            {"filterType": "LOT_SIZE", "stepSize": "0.00001000", "minQty": "0.00001000"},
            # MARKET_LOT_SIZE en Spot viene con 0: no debe empeorar LOT_SIZE
            {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.00000000", "minQty": "0.00000000"},
            {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
        ],
    }],
}

_FUT = SymbolFilters.from_exchange_info(_FUTURES_BTCUSDT, "BTCUSDT")
_SPOT = SymbolFilters.from_exchange_info(_SPOT_BTCUSDT, "BTCUSDT")


# ---------------------------------------------------------------------------
# SymbolFilters.from_exchange_info (OCP: datos, no ifs por símbolo)
# ---------------------------------------------------------------------------
def test_parse_futures_filters():
    assert _FUT is not None
    assert _FUT.min_qty == 0.001
    assert _FUT.step_size == 0.001
    assert _FUT.min_notional == 50.0
    assert _FUT.tick_size == 0.10


def test_parse_spot_filters_uses_notiona_key():
    assert _SPOT is not None
    assert _SPOT.min_qty == 0.00001
    assert _SPOT.step_size == 0.00001
    assert _SPOT.min_notional == 5.0
    # MARKET_LOT_SIZE en 0 no debe degradar LOT_SIZE
    assert _SPOT.min_qty >= 0.00001


def test_parse_symbol_not_found_returns_none():
    assert SymbolFilters.from_exchange_info(_FUTURES_BTCUSDT, "ETHUSDT") is None
    assert SymbolFilters.from_exchange_info({"symbols": []}, "BTCUSDT") is None


def test_parse_missing_lot_size_returns_none():
    info = {"symbols": [{"symbol": "BTCUSDT", "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
    ]}]}
    assert SymbolFilters.from_exchange_info(info, "BTCUSDT") is None


def test_unknown_filters_are_all_zeros():
    f = SymbolFilters.unknown("BTCUSDT")
    assert f.symbol == "BTCUSDT"
    assert (f.min_qty, f.step_size, f.min_notional, f.tick_size) == (0.0, 0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# floor_to_step / min_operable_quantity
# ---------------------------------------------------------------------------
def test_floor_to_step_truncates():
    assert floor_to_step(0.0007675, 0.001) == 0.0
    assert floor_to_step(0.0019, 0.001) == 0.001
    assert floor_to_step(0.001, 0.001) == 0.001
    assert floor_to_step(10.0, 0.0) == 10.0  # sin step no restringe


def test_min_operable_quantity_from_min_qty():
    assert min_operable_quantity(65192.32, _FUT) == 0.001


def test_min_operable_quantity_from_min_notional():
    # a 40k, 50 USDT exigen 0.00125 → redondeado al step 0.001 → 0.002
    f = SymbolFilters(symbol="BTCUSDT", min_qty=0.0, step_size=0.001, min_notional=50.0)
    assert min_operable_quantity(40000.0, f) == 0.002


def test_min_operable_quantity_unknown_filters_is_zero():
    assert min_operable_quantity(65192.32, SymbolFilters.unknown()) == 0.0


# ---------------------------------------------------------------------------
# size_entry — única fuente de verdad (DRY)
# ---------------------------------------------------------------------------
def test_size_entry_below_min_qty_returns_error_with_numbers():
    # El bug original: 50 USDT / 65192 = 0.0007675 < minQty 0.001
    result = size_entry(50.0, 65192.32, _FUT, "FUTURES")
    assert result.error is not None
    assert result.quantity == 0.0
    assert result.ok is False
    assert "0.001" in result.error            # mínimo operable
    assert "65.19" in result.error             # 0.001 BTC a precio actual
    assert "BTCUSDT" in result.error


def test_size_entry_ok_floors_to_step():
    result = size_entry(1000.0, 65192.32, _FUT, "FUTURES")
    assert result.ok
    assert result.error is None
    assert result.quantity == 0.015           # floor(1000/65192.32, 0.001)
    assert result.notional == pytest.approx(0.015 * 65192.32)


def test_size_entry_exact_min_qty_ok():
    result = size_entry(65.20, 65192.32, _FUT, "FUTURES")
    assert result.ok
    assert result.quantity == 0.001


def test_size_entry_below_min_notional_returns_error():
    # qty floored a 0.001 pero notional 40 < 50
    f = SymbolFilters(symbol="BTCUSDT", min_qty=0.0, step_size=0.001, min_notional=50.0)
    result = size_entry(50.0, 40000.0, f, "FUTURES")
    assert result.error is not None
    assert "80" in result.error  # 0.002 (mín. para 50 USDT) * 40000


def test_size_entry_without_price():
    result = size_entry(50.0, 0.0, _FUT, "FUTURES")
    assert result.error is not None
    assert result.quantity == 0.0


def test_size_entry_without_amount():
    result = size_entry(0.0, 65192.32, _FUT, "FUTURES")
    assert result.error is not None


def test_size_entry_fail_open_with_unknown_filters():
    # Sin exchangeInfo no bloqueamos el bot (fail-open)
    result = size_entry(50.0, 65192.32, SymbolFilters.unknown(), "FUTURES")
    assert result.ok
    assert result.quantity == pytest.approx(50.0 / 65192.32)


def test_size_entry_spot_min_notional_five():
    assert _SPOT is not None
    result = size_entry(5.0, 65000.0, _SPOT, "SPOT")
    assert result.error is not None  # 5/65000 < minQty 0.00001
    assert size_entry(10.0, 65000.0, _SPOT, "SPOT").ok


# ---------------------------------------------------------------------------
# effective_min_notional — mínimo real por símbolo vs fallback global
# ---------------------------------------------------------------------------
def test_effective_min_notional_known_symbol_uses_real_rule():
    # SOLUSDC: la regla real (6) manda, NO el global de 50
    sol = SymbolFilters(symbol="SOLUSDC", step_size=0.01, min_notional=6.0)
    assert effective_min_notional(sol, "FUTURES") == 6.0


def test_effective_min_notional_known_without_rule_is_zero():
    # Filtros parseados pero sin filtro NOTIONAL: no se inventa regla
    f = SymbolFilters(symbol="X", min_qty=1.0, step_size=1.0)
    assert effective_min_notional(f, "FUTURES") == 0.0


def test_effective_min_notional_unknown_futures_falls_back_to_global():
    assert effective_min_notional(SymbolFilters.unknown(), "FUTURES") == MIN_FUTURES_NOTIONAL


def test_effective_min_notional_unknown_spot_is_zero():
    # Spot no tiene mínimo global: fail-open
    assert effective_min_notional(SymbolFilters.unknown(), "SPOT") == 0.0


def test_is_unknown_property():
    assert SymbolFilters.unknown("SOLUSDC").is_unknown is True
    assert _FUT.is_unknown is False
    assert SymbolFilters(symbol="X", min_qty=1.0).is_unknown is False


# ---------------------------------------------------------------------------
# size_entry con fallback (filtros desconocidos + Futures → mínimo global)
# ---------------------------------------------------------------------------
def test_size_entry_unknown_futures_below_global_fallback_is_blocked():
    result = size_entry(6.0, 12.0, SymbolFilters.unknown("SOLUSDC"), "FUTURES")
    assert result.error is not None
    assert "50.00" in result.error  # mínimo global a precio actual


def test_size_entry_unknown_futures_at_global_fallback_passes():
    result = size_entry(50.0, 12.0, SymbolFilters.unknown(), "FUTURES")
    assert result.ok  # 50 ≥ 50: fail-open preservado para ≥ fallback


def test_size_entry_unknown_spot_stays_fail_open():
    result = size_entry(6.0, 12.0, SymbolFilters.unknown(), "SPOT")
    assert result.ok


def test_size_entry_known_symbol_uses_symbol_notional_not_global():
    # Regresión SOLUSDC $6: con filtros reales (6) el monto SÍ es operable
    sol = SymbolFilters(symbol="SOLUSDC", step_size=0.01, min_notional=6.0)
    result = size_entry(6.0, 12.0, sol, "FUTURES")
    assert result.ok
    assert result.quantity == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# validate_amount (migrado desde settings_sections — un solo literal)
# ---------------------------------------------------------------------------
def test_validate_amount():
    assert validate_amount(10.0, "SPOT") is None
    assert validate_amount(50.0, "FUTURES") is None
    assert validate_amount(0.0, "SPOT") is not None
    assert validate_amount(-1.0, "FUTURES") is not None
    err = validate_amount(49.9, "FUTURES")
    assert err is not None and "50" in err
    assert MIN_FUTURES_NOTIONAL == 50.0


def test_validate_amount_custom_min_notional():
    # min_notional solo se aplica a Futures; en Spot la regla por símbolo
    # vive en los filtros (size_entry), no aquí.
    assert validate_amount(49.0, "FUTURES", min_notional=50.0) is not None
    assert validate_amount(51.0, "FUTURES", min_notional=50.0) is None
    assert validate_amount(4.0, "SPOT") is None


def test_validate_amount_with_symbol_notional_not_global():
    # Regresión SOLUSDC $6: mínimo real (6) en vez del global de 50
    assert validate_amount(6.0, "FUTURES", min_notional=6.0) is None
    err = validate_amount(5.0, "FUTURES", min_notional=6.0)
    assert err is not None and "6" in err
    # El default sigue siendo el fallback conservador (contrato intacto)
    assert validate_amount(6.0, "FUTURES") is not None


# ---------------------------------------------------------------------------
# QuantitySizer (ISP + DIP — provider inyectado)
# ---------------------------------------------------------------------------
class _StubProvider:
    def __init__(self, filters):
        self.filters = filters
        self.calls = 0

    async def get_symbol_filters(self, symbol, trading_type):
        self.calls += 1
        return self.filters


class _BrokenProvider:
    async def get_symbol_filters(self, symbol, trading_type):
        raise RuntimeError("sin red")


@pytest.mark.asyncio
async def test_sizer_without_provider_is_fail_open():
    sizer = QuantitySizer()
    await sizer.refresh("BTCUSDT", "FUTURES")
    assert sizer.filters.min_qty == 0.0
    assert sizer.size(50.0, 65192.32, "FUTURES").ok


@pytest.mark.asyncio
async def test_sizer_uses_provider_filters():
    provider = _StubProvider(_FUT)
    sizer = QuantitySizer(provider)
    await sizer.refresh("BTCUSDT", "FUTURES")
    assert provider.calls == 1
    assert sizer.filters.step_size == 0.001
    assert not sizer.size(50.0, 65192.32, "FUTURES").ok


@pytest.mark.asyncio
async def test_sizer_provider_failure_fails_open():
    sizer = QuantitySizer(_BrokenProvider())
    await sizer.refresh("BTCUSDT", "FUTURES")
    assert sizer.filters.min_qty == 0.0
    assert sizer.size(50.0, 65192.32, "FUTURES").ok
