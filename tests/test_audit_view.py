"""
Tests para AuditView — modelo ≠ render (fuente de verdad vs. tarjetas).

Cubren el crash `isinstance(c, AuditCard)` (contar desde el modelo en vez
de husmear widgets) y la pérdida de historial al cambiar de filtro.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from core.events import AuditEvent
from core.update_batcher import update_batcher
from ui.views.audit_view import _MAX_EVENTS, AuditView


@pytest.fixture(autouse=True)
def _reset_global_batcher():
    yield
    update_batcher._pending.clear()
    if hasattr(update_batcher, "_control_refs"):
        update_batcher._control_refs.clear()
    update_batcher._flush_scheduled = False


def _event(category: str = "ORDER", action: str = "EXECUTED", timestamp: float = 1.0) -> AuditEvent:
    return AuditEvent(
        timestamp=timestamp, category=category, action=action, detail="detalle"
    )


def _cards(view: AuditView) -> list:
    """Tarjetas visibles (excluye el EmptyState que vive en controls[0])."""
    return [c for c in view._list_column.controls if c is not view._empty_label]


# ---------------------------------------------------------------------------
# Estructura inicial
# ---------------------------------------------------------------------------
def test_initial_state():
    view = AuditView()
    assert view._events == []
    assert view._empty_label.visible is True
    assert view._event_count_text.value == "0 eventos"
    assert view._category_filter == "TODOS"
    assert len(view.controls) == 2


# ---------------------------------------------------------------------------
# Almacenar siempre / pintar solo si coincide
# ---------------------------------------------------------------------------
def test_add_event_appends_card_when_filter_matches():
    view = AuditView()
    view._add_event(_event("ORDER"))

    assert len(view._events) == 1
    assert len(_cards(view)) == 1
    assert view._empty_label.visible is False
    assert view._event_count_text.value == "1 evento"


def test_add_event_stores_event_when_filter_does_not_match():
    """Regresión: el evento se guarda aunque no se pinte."""
    view = AuditView()
    view._category_filter = "ORDER"

    view._add_event(_event("PRICE"))

    assert len(view._events) == 1
    assert len(_cards(view)) == 0
    assert view._empty_label.visible is True
    assert view._event_count_text.count == 0


def test_switching_filter_restores_hidden_events():
    """Regresión clave: volver a TODOS no debe perder lo filtrado."""
    view = AuditView()
    view._category_filter = "ORDER"
    view._add_event(_event("ORDER"))
    view._add_event(_event("PRICE"))
    view._add_event(_event("CONNECTION"))

    view._category_filter = "TODOS"
    view._rebuild_list()

    assert len(view._events) == 3
    assert len(_cards(view)) == 3
    assert view._event_count_text.value == "3 eventos"


def test_switching_to_category_shows_only_its_events():
    view = AuditView()
    for category in ("ORDER", "PRICE", "ORDER", "CONFIG"):
        view._add_event(_event(category))

    view._category_filter = "ORDER"
    view._rebuild_list()

    assert len(_cards(view)) == 2
    assert view._event_count_text.value == "2 eventos"
    assert len(view._events) == 4   # el modelo no se recorta al filtrar


def test_count_comes_from_model_not_widgets():
    """El conteo se deriva de _visible_events(), nunca de isinstance()."""
    view = AuditView()
    view._category_filter = "ORDER"
    for category in ("ORDER", "PRICE", "ORDER", "CONFIG"):
        view._add_event(_event(category))

    view._update_count()

    assert view._event_count_text.count == len(view._visible_events()) == 2


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------
def test_empty_state_hidden_when_last_visible_event_leaves():
    view = AuditView()
    view._add_event(_event("ORDER"))
    assert view._empty_label.visible is False

    view._category_filter = "PRICE"
    view._rebuild_list()

    assert view._empty_label.visible is True
    assert view._event_count_text.value == "0 eventos"


# ---------------------------------------------------------------------------
# Tope del buffer (antes: 2 slices [-200:] duplicados)
# ---------------------------------------------------------------------------
def test_store_is_capped_at_max_events():
    view = AuditView()
    total = _MAX_EVENTS + 50
    for i in range(total):
        view._add_event(_event("ORDER", timestamp=float(i)))

    assert len(view._events) == _MAX_EVENTS
    # 1 EmptyState + hasta _MAX_EVENTS tarjetas
    assert len(view._list_column.controls) <= _MAX_EVENTS + 1
    assert len(_cards(view)) == _MAX_EVENTS
    assert view._event_count_text.count == _MAX_EVENTS


def test_store_cap_drops_cards_when_filtered():
    """Con filtro activo, los eventos que salen también retiran su tarjeta."""
    view = AuditView()
    view._category_filter = "ORDER"
    for i in range(_MAX_EVENTS + 10):
        view._add_event(_event("ORDER", timestamp=float(i)))

    assert len(view._events) == _MAX_EVENTS
    assert len(_cards(view)) == _MAX_EVENTS
    assert view._event_count_text.count == _MAX_EVENTS


def test_store_cap_removes_non_matching_cards_only():
    """Los eventos que nunca se pintaron no dejan tarjetas huérfanas."""
    view = AuditView()
    view._category_filter = "ORDER"
    for i in range(_MAX_EVENTS + 10):
        view._add_event(_event("PRICE", timestamp=float(i)))

    assert len(view._events) == _MAX_EVENTS
    assert _cards(view) == []
    assert view._event_count_text.count == 0


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
def test_did_mount_loads_existing_events():
    existing = [_event("ORDER", timestamp=float(i)) for i in range(3)]
    with patch("ui.views.audit_view.event_bus") as bus, \
         patch("ui.views.audit_view.audit_service") as service:
        service.get_recent_events.return_value = existing

        view = AuditView()
        view.did_mount()

    bus.subscribe.assert_called_once()
    assert len(view._events) == 3
    assert len(_cards(view)) == 3
    assert view._event_count_text.value == "3 eventos"


def test_will_unmount_unsubscribes():
    with patch("ui.views.audit_view.event_bus") as bus:
        view = AuditView()
        view.will_unmount()

    bus.unsubscribe.assert_called_once()


def test_on_audit_event_is_async_and_renders():
    view = AuditView()

    import asyncio
    asyncio.run(view._on_audit_event(_event("ORDER")))

    assert len(_cards(view)) == 1
