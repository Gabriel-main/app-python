"""
Tests para Stats24H — Componente reactivo de estadísticas 24h.
"""
import flet as ft
from ui.components.stats_24h import Stats24H


def test_stats_creation():
    stats = Stats24H("BTCUSDT")
    assert stats._symbol == "BTCUSDT"


def test_stats_initial_values():
    stats = Stats24H()
    assert stats._high_text.value == "---"
    assert stats._low_text.value == "---"
    assert stats._vol_text.value == "---"


def test_stats_update_symbol():
    stats = Stats24H("BTCUSDT")
    stats.update_symbol("ETHUSDT")
    assert stats._symbol == "ETHUSDT"


def test_stats_resize_small():
    stats = Stats24H()
    stats._on_resize(320, 600)
    assert stats._high_text.style.size == 11


def test_stats_resize_normal():
    stats = Stats24H()
    stats._on_resize(400, 800)
    assert stats._high_text.style.size == 13


def test_stats_has_container_styling():
    stats = Stats24H()
    assert stats.border_radius == 14
    assert stats.padding.left == 16


def test_stats_row_has_3_columns():
    stats = Stats24H()
    row = stats.content
    assert isinstance(row, ft.Row)
    assert len(row.controls) == 5  # 3 columns + 2 dividers
