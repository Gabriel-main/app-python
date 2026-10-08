"""
Tests de MarkPriceRow — Mark/Índice/Funding (solo FUTURES).
"""
from datetime import datetime
from unittest.mock import patch

import pytest

from core.events import MarkPriceEvent
from ui.components import mark_price_row as mark_row_module
from ui.components.mark_price_row import MarkPriceRow


def _mark(
    symbol: str = "BTCUSDT",
    mark: float = 84510.1,
    index: float = 84543.7,
    rate: float = 0.0001,
    next_ts: float = 1791129600.0,
) -> MarkPriceEvent:
    return MarkPriceEvent(
        symbol=symbol, mark_price=mark, index_price=index,
        funding_rate=rate, next_funding_ts=next_ts,
    )


def test_visible_only_on_futures():
    with patch.object(mark_row_module.settings, "TRADING_TYPE", "FUTURES"):
        row = MarkPriceRow("BTCUSDT")
        assert row.visible is True

    with patch.object(mark_row_module.settings, "TRADING_TYPE", "SPOT"):
        row = MarkPriceRow("BTCUSDT")
        assert row.visible is False


def test_initial_values():
    row = MarkPriceRow("BTCUSDT")
    assert row._mark_text.value == "---"
    assert row._index_text.value == "---"
    assert row._funding_text.value == "---"


@pytest.mark.asyncio
async def test_mark_price_formats_values():
    row = MarkPriceRow("BTCUSDT")
    await row._on_mark_price(_mark())

    assert row._mark_text.value == "$84,510.10"
    assert row._index_text.value == "$84,543.70"
    expected_time = datetime.fromtimestamp(1791129600.0).strftime("%H:%M")
    assert row._funding_text.value == f"+0.0100% · {expected_time}"
    assert row._funding_text.color is not None


@pytest.mark.asyncio
async def test_negative_funding_uses_red():
    row = MarkPriceRow("BTCUSDT")
    await row._on_mark_price(_mark(rate=-0.0002, next_ts=0.0))
    assert row._funding_text.value.startswith("-0.0200%")
    # Sin timestamp de funding no se muestra el separador
    assert "·" not in row._funding_text.value


@pytest.mark.asyncio
async def test_ignores_other_symbol():
    row = MarkPriceRow("BTCUSDT")
    await row._on_mark_price(_mark(symbol="ETHUSDT"))
    assert row._mark_text.value == "---"
