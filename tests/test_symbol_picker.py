"""
Tests para SymbolPicker — Selector de pares de trading con overlay y búsqueda.
"""
import pytest
import flet as ft

from ui.components.symbol_picker import SymbolPicker, SymbolListManager
from core.events import SymbolsListEvent


def test_symbol_picker_init():
    """Inicialización correcta de SymbolPicker con valores por defecto."""
    picker = SymbolPicker(trading_type="SPOT")
    assert picker._mgr.trading_type == "SPOT"
    assert picker.get_selected_symbol() is not None
    assert picker._arrow_icon is not None
    assert picker._overlay is not None


def test_symbol_picker_render_options_no_attribute_errors():
    """_render_options no debe lanzar AttributeError con colores ni iconos."""
    picker = SymbolPicker(trading_type="SPOT")
    picker.set_symbol("BTCUSDT")
    picker._mgr._symbols = [
        {"symbol": "BTCUSDT", "base_asset": "BTC", "quote_asset": "USDT", "price": 65000.0},
        {"symbol": "ETHUSDT", "base_asset": "ETH", "quote_asset": "USDT", "price": 3500.0},
        {"symbol": "SOLUSDT", "base_asset": "SOL", "quote_asset": "USDT", "price": 180.25},
    ]

    picker._render_options()

    # Debe haber generado 3 contenedores de opciones
    assert len(picker._options_column.controls) == 3

    # Verificar que el seleccionado es BTCUSDT
    first_opt = picker._options_column.controls[0]
    assert first_opt.data == "BTCUSDT"

    # Verificar que no seleccionado (ETHUSDT) renderiza correctamente el precio y color WHITE_70
    second_opt = picker._options_column.controls[1]
    assert second_opt.data == "ETHUSDT"
    row = second_opt.content
    assert isinstance(row, ft.Row)
    price_text = row.controls[3]
    assert isinstance(price_text, ft.Text)
    assert price_text.color == ft.Colors.WHITE_70


def test_symbol_picker_render_options_empty_filtered():
    """Si no hay coincidencias en la búsqueda, renderiza el empty state."""
    picker = SymbolPicker(trading_type="SPOT")
    picker._mgr._symbols = [
        {"symbol": "BTCUSDT", "base_asset": "BTC", "quote_asset": "USDT", "price": 65000.0},
    ]
    picker._mgr.set_search_query("NONEXISTENT")
    picker._render_options()

    assert len(picker._options_column.controls) == 1
    empty_container = picker._options_column.controls[0]
    assert isinstance(empty_container, ft.Container)


@pytest.mark.asyncio
async def test_symbol_picker_on_symbols_list_event():
    """Al recibir SymbolsListEvent, actualiza la lista interna y re-renderiza sin errores."""
    picker = SymbolPicker(trading_type="FUTURES")
    event = SymbolsListEvent(
        symbols=[
            {"symbol": "SOLUSDT", "base_asset": "SOL", "quote_asset": "USDT", "price": 185.0},
            {"symbol": "BTCUSDT", "base_asset": "BTC", "quote_asset": "USDT", "price": 65000.0},
        ],
        trading_type="FUTURES"
    )

    await picker._on_symbols_list(event)

    assert len(picker._mgr._symbols) == 2
    assert len(picker._options_column.controls) == 2
