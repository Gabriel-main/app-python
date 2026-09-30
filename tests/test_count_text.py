"""
Tests para CountText — Contador pluralizado con repaint atómico (DRY).

Centraliza lo que antes se triplicaba en OrdersView, AuditView y
PositionsPanel: plural (regular e irregular) + update_batcher.
"""
from __future__ import annotations

import pytest

from core.update_batcher import update_batcher
from ui.components.count_text import CountText


@pytest.fixture(autouse=True)
def _reset_global_batcher():
    yield
    _clear()


def _clear() -> None:
    update_batcher._pending.clear()
    if hasattr(update_batcher, "_control_refs"):
        update_batcher._control_refs.clear()
    update_batcher._flush_scheduled = False


# ---------------------------------------------------------------------------
# Pluralización
# ---------------------------------------------------------------------------
def test_initial_value_is_plural_zero():
    text = CountText("evento", "eventos")
    assert text.value == "0 eventos"
    assert text.count == 0


def test_singular_for_one():
    text = CountText("evento", "eventos")
    text.set_count(1)
    assert text.value == "1 evento"
    assert text.count == 1


def test_plural_for_many():
    text = CountText("evento", "eventos")
    text.set_count(5)
    assert text.value == "5 eventos"
    assert text.count == 5


def test_irregular_plural_orders():
    """Órdenes no es "orden + es": el patrón vive en un solo lugar."""
    text = CountText("orden", "órdenes")
    text.set_count(1)
    assert text.value == "1 orden"
    text.set_count(2)
    assert text.value == "2 órdenes"


def test_positions_plural():
    text = CountText("posición", "posiciones")
    text.set_count(1)
    assert text.value == "1 posición"
    text.set_count(3)
    assert text.value == "3 posiciones"


def test_default_style_matches_previous_counters():
    text = CountText("evento", "eventos")
    assert text.size == 11
    assert text.color is not None


# ---------------------------------------------------------------------------
# Repaint atómico (sin renders inútiles)
# ---------------------------------------------------------------------------
def test_change_marks_dirty():
    text = CountText("evento", "eventos")
    text.set_count(3)
    assert update_batcher.pending_count == 1
    assert update_batcher._control_refs.get(id(text)) is text


def test_same_count_does_not_mark_dirty():
    text = CountText("evento", "eventos")
    text.set_count(3)
    _clear()

    text.set_count(3)

    assert update_batcher.pending_count == 0
    assert text.value == "3 eventos"


def test_back_to_previous_count_marks_dirty_again():
    text = CountText("evento", "eventos")
    text.set_count(3)
    text.set_count(4)
    _clear()

    text.set_count(3)   # 4 → 3 sí cambia

    assert update_batcher.pending_count == 1
    assert text.value == "3 eventos"
