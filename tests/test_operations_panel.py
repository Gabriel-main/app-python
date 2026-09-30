"""
Tests para OperationsPanel — Badge "ENTRADA PENDIENTE" y diff incremental.

Opción C: el badge solo aplica mientras la orden LIMIT de entrada siga
working. En PAST la orden ya fue cancelada, así que no hay nada pendiente.
"""
import flet as ft

from core.events import OperationState
from ui.components.badges import Badge
from ui.components.operations_panel import (
    OperationsPanel,
    _has_pending_entry,
    _operation_card,
    _operation_key,
)


def _op(state="ACTIVE", entry_filled=False, order_id="OP-1", side="BUY"):
    return OperationState(
        side=side,
        state=state,
        entry_price=100.0,
        stop_loss=99.0,
        quantity=0.001,
        order_id=order_id,
        entry_filled=entry_filled,
    )


def _badge_labels(card) -> list[str]:
    """Labels de los badges de la fila superior de la tarjeta."""
    row = card.content.controls[0]
    return [c.label for c in row.controls if isinstance(c, Badge)]


# ---------------------------------------------------------------------------
# _has_pending_entry
# ---------------------------------------------------------------------------
def test_pending_entry_when_active_and_not_filled():
    assert _has_pending_entry(_op(state="ACTIVE", entry_filled=False)) is True


def test_pending_entry_when_pending_and_not_filled():
    assert _has_pending_entry(_op(state="PENDING", entry_filled=False)) is True


def test_no_pending_entry_when_past():
    # Opción C: op terminada => la orden working ya fue cancelada
    assert _has_pending_entry(_op(state="PAST", entry_filled=False)) is False


def test_no_pending_entry_when_filled():
    assert _has_pending_entry(_op(state="ACTIVE", entry_filled=True)) is False


def test_no_pending_entry_when_past_and_filled():
    assert _has_pending_entry(_op(state="PAST", entry_filled=True)) is False


# ---------------------------------------------------------------------------
# _operation_card
# ---------------------------------------------------------------------------
def test_card_shows_pending_badge_when_entry_not_filled():
    labels = _badge_labels(_operation_card(_op(state="ACTIVE", entry_filled=False)))
    assert "ENTRADA PENDIENTE" in labels


def test_card_hides_pending_badge_on_past_operation():
    labels = _badge_labels(_operation_card(_op(state="PAST", entry_filled=False)))
    assert "ENTRADA PENDIENTE" not in labels


def test_card_hides_pending_badge_when_filled():
    labels = _badge_labels(_operation_card(_op(state="ACTIVE", entry_filled=True)))
    assert "ENTRADA PENDIENTE" not in labels


def test_card_always_shows_side_and_state_badges():
    labels = _badge_labels(_operation_card(_op(state="PAST", entry_filled=False)))
    assert "COMPRA" in labels
    assert "PASADA" in labels


# ---------------------------------------------------------------------------
# _operation_key (diff incremental)
# ---------------------------------------------------------------------------
def test_operation_key_includes_state():
    assert _operation_key(_op(state="ACTIVE")) != _operation_key(_op(state="PAST"))


def test_operation_key_includes_entry_filled():
    assert _operation_key(_op(entry_filled=False)) != _operation_key(
        _op(entry_filled=True)
    )


def test_operation_key_includes_order_id():
    assert _operation_key(_op(order_id="A")) != _operation_key(_op(order_id="B"))


# ---------------------------------------------------------------------------
# OperationsPanel._refresh_ui
# ---------------------------------------------------------------------------
def test_refresh_ui_renders_one_card_per_operation():
    panel = OperationsPanel()
    panel._operations = [_op(order_id="A"), _op(order_id="B")]
    panel._refresh_ui()
    assert len(panel._operations_column.controls) == 2


def test_refresh_ui_reuses_card_when_key_unchanged():
    panel = OperationsPanel()
    panel._operations = [_op()]
    panel._refresh_ui()
    first = panel._operations_column.controls[0]
    panel._refresh_ui()
    assert panel._operations_column.controls[0] is first


def test_refresh_ui_rebuilds_when_state_changes():
    panel = OperationsPanel()
    panel._operations = [_op(state="ACTIVE")]
    panel._refresh_ui()
    first = panel._operations_column.controls[0]
    panel._operations = [_op(state="PAST")]
    panel._refresh_ui()
    second = panel._operations_column.controls[0]
    assert second is not first
    assert "ENTRADA PENDIENTE" not in _badge_labels(second)


def test_refresh_ui_clears_cards_when_empty():
    panel = OperationsPanel()
    panel._operations = [_op()]
    panel._refresh_ui()
    panel._operations = []
    panel._refresh_ui()
    assert panel._operations_column.controls == []
    assert panel._empty_text.visible is True
