"""
Tests para OrdersView — Historial de órdenes (FILLED / PENDING / CANCELLED).
"""
import asyncio

import pytest

from core.events import OrderCanceledEvent, OrderExecutedEvent, OrderPlacedEvent
from core.update_batcher import update_batcher
from ui.views.orders_view import OrdersView, _MAX_CARDS


class _Repo:
    """Repositorio falso (DIP: la vista solo conoce get_recent_orders)."""

    def __init__(self, orders: list[dict]) -> None:
        self._orders = orders

    async def get_recent_orders(self, limit: int = 100) -> list[dict]:
        return self._orders[:limit]


def _record(order_id: str, status: str = "FILLED", timestamp: float = 1.0, **extra) -> dict:
    record = {
        "order_id": order_id,
        "symbol": "BTCUSDC",
        "side": "BUY",
        "quantity": 0.01,
        "price": 1010.0,
        "mode": "PAPER",
        "status": status,
        "pnl": None,
        "timestamp": timestamp,
    }
    record.update(extra)
    return record


@pytest.fixture(autouse=True)
def _reset_global_batcher():
    yield
    update_batcher._pending.clear()
    if hasattr(update_batcher, "_control_refs"):
        update_batcher._control_refs.clear()
    update_batcher._flush_scheduled = False


async def _drain(view: OrdersView) -> None:
    """Cancela los flashes pendientes para no dejar tareas huérfanas."""
    for card in view._cards.values():
        card.will_unmount()
    await asyncio.sleep(0.01)


# ------------------------------------------------------------------
# Estructura
# ------------------------------------------------------------------
def test_initial_state_shows_loader():
    view = OrdersView()
    assert len(view.controls) == 3
    assert view._body.content is view._loader
    assert view._count_text.value == "0 órdenes"
    assert view.expand is True
    assert view.spacing == 12


def test_only_one_child_expands():
    expanders = [c for c in OrdersView().controls if getattr(c, "expand", False)]
    assert len(expanders) == 1


# ------------------------------------------------------------------
# Filtro
# ------------------------------------------------------------------
def test_matches_accepts_every_status_when_all():
    view = OrdersView()
    for status in ("FILLED", "PENDING", "CANCELLED", "WHATEVER"):
        assert view._matches({"status": status})


def test_matches_is_strict_for_specific_filters():
    view = OrdersView()
    view._filter = "PENDING"
    assert view._matches({"status": "PENDING"})
    assert not view._matches({"status": "FILLED"})
    view._filter = "CANCELLED"
    assert view._matches({"status": "CANCELLED"})
    assert not view._matches({"status": "PENDING"})


def test_filter_change_renders_only_matching_cards():
    view = OrdersView()
    view._loading = False
    view._upsert(_record("a", status="FILLED", timestamp=2.0))
    view._upsert(_record("b", status="PENDING", timestamp=1.0))
    assert [c.order_id for c in view._list_column.controls] == ["a", "b"]

    view._on_filter_changed("PENDING")
    assert [c.order_id for c in view._list_column.controls] == ["b"]
    assert view._count_text.value == "1 orden"
    assert view._body.content is view._list_column

    view._on_filter_changed("ALL")
    assert [c.order_id for c in view._list_column.controls] == ["a", "b"]
    assert view._count_text.value == "2 órdenes"


def test_filter_to_empty_state():
    view = OrdersView()
    view._loading = False
    view._upsert(_record("a", status="FILLED"))
    view._on_filter_changed("PENDING")
    assert view._list_column.controls == []
    assert view._body.content is view._empty
    assert view._count_text.value == "0 órdenes"


# ------------------------------------------------------------------
# Upsert / render
# ------------------------------------------------------------------
def test_upsert_first_order_switches_to_list():
    view = OrdersView()
    view._loading = False
    view._upsert(_record("o1"))
    assert set(view._records) == {"o1"}
    assert len(view._list_column.controls) == 1
    assert view._body.content is view._list_column
    assert view._count_text.value == "1 orden"


def test_upsert_reuses_card_on_status_change():
    view = OrdersView()
    view._loading = False
    view._upsert(_record("o1", status="PENDING"))
    card = view._cards["o1"]
    view._upsert(_record("o1", status="FILLED"))
    assert view._cards["o1"] is card
    assert card.status == "FILLED"
    assert len(view._list_column.controls) == 1


def test_upsert_keeps_pnl_when_new_record_has_none():
    view = OrdersView()
    view._loading = False
    view._upsert(_record("o1", pnl=4.2))
    view._upsert(_record("o1", pnl=None))
    assert view._records["o1"]["pnl"] == 4.2
    assert view._cards["o1"].pnl_text == "+4.20 USDT"


def test_records_are_capped_at_max():
    view = OrdersView()
    view._loading = False
    for i in range(_MAX_CARDS + 5):
        view._upsert(_record(f"o{i}", timestamp=float(i)))
    assert len(view._records) == _MAX_CARDS
    assert "o0" not in view._records
    assert "o4" not in view._records
    assert "o5" in view._records
    assert len(view._list_column.controls) == _MAX_CARDS


# ------------------------------------------------------------------
# Estados del body
# ------------------------------------------------------------------
def test_show_body_transitions_between_states():
    view = OrdersView()
    assert view._body.content is view._loader

    view._loading = False
    view._show_body()
    assert view._body.content is view._empty

    view._load_error = "boom"
    view._show_body()
    assert view._body.content is view._error
    assert "boom" in view._error_text.value

    view._upsert(_record("o1"))
    assert view._body.content is view._list_column

    view._on_filter_changed("CANCELLED")
    assert view._body.content is view._error


# ------------------------------------------------------------------
# Carga desde DB (DIP)
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_load_without_repository_reports_error():
    view = OrdersView()
    await view._load_orders()
    assert view._loading is False
    assert view._load_error
    assert view._body.content is view._error


@pytest.mark.asyncio
async def test_load_populates_list_from_repository():
    view = OrdersView(order_repository=_Repo([_record("db1"), _record("db2")]))
    await view._load_orders()
    assert set(view._records) == {"db1", "db2"}
    assert len(view._list_column.controls) == 2
    assert view._body.content is view._list_column
    assert view._load_error is None
    await _drain(view)


@pytest.mark.asyncio
async def test_load_prefers_live_status_but_takes_db_pnl():
    view = OrdersView(order_repository=_Repo([_record("live", status="FILLED", pnl=5.0)]))
    view._upsert(_record("live", status="PENDING"))
    await view._load_orders()
    assert view._records["live"]["status"] == "PENDING"
    assert view._records["live"]["pnl"] == 5.0
    assert view._cards["live"].status == "PENDING"
    await _drain(view)


# ------------------------------------------------------------------
# Handlers de eventos
# ------------------------------------------------------------------
def _placed(order_id: str, timestamp: float = 10.0) -> OrderPlacedEvent:
    return OrderPlacedEvent(
        order_id=order_id,
        operation_id="OC-1",
        symbol="BTCUSDC",
        side="BUY",
        quantity=0.01,
        price=1010.0,
        mode="PAPER",
        timestamp=timestamp,
    )


def _executed(order_id: str, timestamp: float = 11.0) -> OrderExecutedEvent:
    return OrderExecutedEvent(
        order_id=order_id,
        symbol="BTCUSDC",
        side="BUY",
        quantity=0.01,
        price=1010.0,
        mode="PAPER",
        timestamp=timestamp,
    )


def _canceled(order_id: str, timestamp: float = 12.0) -> OrderCanceledEvent:
    return OrderCanceledEvent(
        order_id=order_id, operation_id="OC-1", timestamp=timestamp
    )


@pytest.mark.asyncio
async def test_placed_event_creates_pending_card():
    view = OrdersView()
    view._loading = False
    await view._on_order_placed(_placed("o1"))
    assert view._records["o1"]["status"] == "PENDING"
    assert view._cards["o1"].status == "PENDING"
    assert view._body.content is view._list_column
    await _drain(view)


@pytest.mark.asyncio
async def test_executed_event_promotes_pending_to_filled():
    view = OrdersView()
    view._loading = False
    await view._on_order_placed(_placed("o1"))
    card = view._cards["o1"]
    await view._on_order_executed(_executed("o1"))
    assert view._cards["o1"] is card
    assert card.status == "FILLED"
    assert len(view._list_column.controls) == 1
    await _drain(view)


@pytest.mark.asyncio
async def test_canceled_event_keeps_card_as_cancelled():
    view = OrdersView()
    view._loading = False
    await view._on_order_placed(_placed("o1"))
    await view._on_order_canceled(_canceled("o1"))
    assert view._cards["o1"].status == "CANCELLED"
    assert [c.order_id for c in view._list_column.controls] == ["o1"]
    assert view._count_text.value == "1 orden"
    await _drain(view)


@pytest.mark.asyncio
async def test_canceled_event_ignores_filled_order():
    view = OrdersView()
    view._loading = False
    await view._on_order_executed(_executed("o1"))
    await view._on_order_canceled(_canceled("o1"))
    assert view._cards["o1"].status == "FILLED"
    await _drain(view)


@pytest.mark.asyncio
async def test_canceled_event_ignores_unknown_order():
    view = OrdersView()
    view._loading = False
    await view._on_order_canceled(_canceled("ghost"))
    assert view._records == {}
    assert view._list_column.controls == []
    view._show_body()
    assert view._body.content is view._empty
