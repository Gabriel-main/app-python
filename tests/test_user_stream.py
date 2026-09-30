"""
Tests del parseo del user data stream (executionReport) → OrderFillEvent.
"""
from core.events import OrderFillEvent
from services.binance_service import BinanceService


def test_parse_filled_futures_uses_avg_price():
    msg = {
        "e": "executionReport", "c": "LIVE-ABC", "X": "FILLED",
        "ap": "64999.5", "z": "0.001", "Z": "64.99",
    }
    fill = BinanceService._parse_execution_report(msg)
    assert isinstance(fill, OrderFillEvent)
    assert fill.status == "FILLED"
    assert fill.order_id == "LIVE-ABC"
    assert fill.price == 64999.5
    assert fill.mode == "LIVE"
    assert fill.source == "USER_STREAM"


def test_parse_filled_spot_uses_cumulative_quotient():
    # Spot no trae ap → Z/z (cumulative quote / cumulative qty)
    msg = {
        "e": "executionReport", "c": "LIVE-SPOT", "X": "FILLED",
        "ap": "0", "z": "2.0", "Z": "130000.0",
    }
    fill = BinanceService._parse_execution_report(msg)
    assert fill is not None
    assert fill.price == 65000.0
    assert fill.quantity == 2.0


def test_parse_filled_falls_back_to_last_fill_price():
    msg = {"e": "executionReport", "c": "LIVE-L", "X": "FILLED", "z": "0", "Z": "0", "L": "65123.0"}
    fill = BinanceService._parse_execution_report(msg)
    assert fill is not None
    assert fill.price == 65123.0


def test_parse_canceled():
    msg = {"e": "executionReport", "c": "LIVE-CXL", "X": "CANCELED"}
    fill = BinanceService._parse_execution_report(msg)
    assert fill is not None
    assert fill.status == "CANCELED"


def test_parse_new_ignored():
    """NEW no abre posición: se ignora hasta el FILLED."""
    msg = {"e": "executionReport", "c": "LIVE-NEW", "X": "NEW"}
    assert BinanceService._parse_execution_report(msg) is None


def test_parse_partially_filled_ignored():
    msg = {"e": "executionReport", "c": "LIVE-PART", "X": "PARTIALLY_FILLED", "z": "0.5"}
    assert BinanceService._parse_execution_report(msg) is None


def test_parse_non_execution_report_ignored():
    msg = {"e": "markPriceUpdate", "c": "X"}
    assert BinanceService._parse_execution_report(msg) is None


def test_parse_missing_client_order_id_ignored():
    msg = {"e": "executionReport", "c": "", "X": "FILLED"}
    assert BinanceService._parse_execution_report(msg) is None
