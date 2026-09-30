"""
Orders View — Historial de órdenes (FILLED / PENDING / CANCELLED).

Refactorizado para aplicar:
- SRP: Solo orquesta eventos → registros → tarjetas. La presentación
  vive en ViewHeader, SegmentedFilter, OrderCard y EmptyState.
- DIP: Recibe OrderRepositoryProtocol (interfaz) en vez de tocar la DB.
- OCP: El filtro es datos ((clave, etiqueta)); añadir un filtro no
  modifica SegmentedFilter ni esta vista más allá de la tupla.
- DRY: Header y empty state dejan de estar duplicados con las demás vistas.
- PERFORMANCE: Diferencia por (order_id, status); reutiliza OrderCard.
- CERO POLLING: Sin while True / sleep; EventBus + un task one-shot de carga.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import flet as ft

from core.event_bus import event_bus
from core.events import OrderCanceledEvent, OrderExecutedEvent, OrderPlacedEvent
from core.update_batcher import update_batcher
from ui.components.count_text import CountText
from ui.components.empty_state import EmptyState
from ui.components.order_card import OrderCard
from ui.components.segmented_filter import SegmentedFilter
from ui.components.view_header import ViewHeader

if TYPE_CHECKING:
    from repositories.order_repository import OrderRepositoryProtocol

_MAX_CARDS = 200

_FILTERS: tuple[tuple[str, str], ...] = (
    ("ALL", "Todas"),
    ("FILLED", "Ejecutadas"),
    ("PENDING", "Pendientes"),
    ("CANCELLED", "Canceladas"),
)


class OrdersView(ft.Column):
    """Vista de historial de órdenes."""

    def __init__(self, order_repository: "OrderRepositoryProtocol | None" = None) -> None:
        super().__init__()
        self._repository = order_repository
        self._load_task: asyncio.Task | None = None

        self._filter = "ALL"
        self._loading = True
        self._load_error: str | None = None

        self._records: dict[str, dict] = {}
        self._cards: dict[str, OrderCard] = {}

        self._list_column = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO)
        self._loading_ring = ft.ProgressRing(width=32, height=32, stroke_width=3)
        self._count_text = CountText("orden", "órdenes")
        self._filter_control = SegmentedFilter(
            _FILTERS, value="ALL", on_change=self._on_filter_changed
        )

        self._loader = ft.Container(
            content=ft.Row(
                controls=[self._loading_ring],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
        )
        self._empty = EmptyState(
            "Sin órdenes aún.",
            subtitle="El bot ejecutará órdenes cuando detecte señales.",
            icon=ft.Icons.RECEIPT_LONG_OUTLINED,
        )

        self._error_text = ft.Text(
            "", size=12, color=ft.Colors.RED_400, text_align=ft.TextAlign.CENTER
        )
        self._error = ft.Container(
            content=self._error_text,
            alignment=ft.Alignment.CENTER,
            padding=24,
        )

        # Único hijo con expand=True: evita que loader/vacío/lista
        # compitan por el mismo espacio flexible del Column.
        self._body = ft.Container(expand=True, content=self._loader)

        self.controls = [
            ViewHeader("Órdenes", trailing=[self._count_text]),
            self._filter_control,
            self._body,
        ]
        self.spacing = 12
        self.expand = True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def did_mount(self) -> None:
        event_bus.subscribe(OrderExecutedEvent, self._on_order_executed)
        event_bus.subscribe(OrderPlacedEvent, self._on_order_placed)
        event_bus.subscribe(OrderCanceledEvent, self._on_order_canceled)
        self._load_task = asyncio.create_task(self._load_orders(), name="load_orders_view")

    def will_unmount(self) -> None:
        event_bus.unsubscribe(OrderExecutedEvent, self._on_order_executed)
        event_bus.unsubscribe(OrderPlacedEvent, self._on_order_placed)
        event_bus.unsubscribe(OrderCanceledEvent, self._on_order_canceled)
        if self._load_task and not self._load_task.done():
            self._load_task.cancel()

    # ------------------------------------------------------------------
    # Carga inicial desde DB
    # ------------------------------------------------------------------
    async def _load_orders(self) -> None:
        try:
            if not self._repository:
                raise RuntimeError("OrderRepository no inyectado en OrdersView")

            orders = await self._repository.get_recent_orders(_MAX_CARDS)

            for order in orders:
                order_id = order.get("order_id")
                if not order_id:
                    continue
                current = self._records.get(order_id)
                if current is None:
                    self._records[order_id] = order
                elif order.get("pnl") is not None:
                    # El estado en memoria es más fresco que la DB;
                    # la DB solo aporta el PnL calculado al cerrar.
                    current["pnl"] = order["pnl"]

            self._loading = False
            self._rebuild()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._loading = False
            self._load_error = str(exc)
            self._show_body()

    # ------------------------------------------------------------------
    # Actualización reactiva (placed → filled → canceled)
    # ------------------------------------------------------------------
    async def _on_order_executed(self, event: OrderExecutedEvent) -> None:
        self._upsert(self._record_from_executed(event))

    async def _on_order_placed(self, event: OrderPlacedEvent) -> None:
        """Orden LIMIT working: tarjeta con status PENDING (precio = límite)."""
        self._upsert({
            "order_id": event.order_id,
            "symbol": event.symbol,
            "side": event.side,
            "quantity": event.quantity,
            "price": event.price,
            "mode": event.mode,
            "status": "PENDING",
            "pnl": None,
            "timestamp": event.timestamp,
        })

    async def _on_order_canceled(self, event: OrderCanceledEvent) -> None:
        """La tarjeta PENDING pasa a CANCELLED (ya no se elimina).

        Un orden ya FILLED no retrocede a CANCELLED: el fill es definitivo.
        """
        record = self._records.get(event.order_id)
        if record is None or record.get("status") != "PENDING":
            return
        self._upsert({**record, "status": "CANCELLED"})

    @staticmethod
    def _record_from_executed(event: OrderExecutedEvent) -> dict:
        return {
            "order_id": event.order_id,
            "symbol": event.symbol,
            "side": event.side,
            "quantity": event.quantity,
            "price": event.price,
            "mode": event.mode,
            "status": "FILLED",
            "pnl": None,
            "timestamp": event.timestamp,
        }

    def _upsert(self, record: dict) -> None:
        """Actualiza un registro y re-renderiza, pisando el flash si cambia."""
        order_id = record["order_id"]
        previous = self._records.get(order_id)
        if previous is not None and record.get("pnl") is None:
            record = {**record, "pnl": previous.get("pnl")}
        self._records[order_id] = record

        is_new = previous is None
        status_changed = previous is not None and str(previous.get("status")) != str(
            record.get("status")
        )
        flash_ids = (order_id,) if (is_new or status_changed) else ()
        self._rebuild(flash_ids=flash_ids)

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def _matches(self, record: dict) -> bool:
        if self._filter == "ALL":
            return True
        return str(record.get("status") or "FILLED") == self._filter

    def _evict(self) -> None:
        overflow = len(self._records) - _MAX_CARDS
        if overflow <= 0:
            return
        oldest = sorted(self._records.values(), key=lambda r: r.get("timestamp") or 0.0)
        for record in oldest[:overflow]:
            order_id = record["order_id"]
            self._records.pop(order_id, None)
            self._cards.pop(order_id, None)

    def _rebuild(self, *, flash_ids: tuple[str, ...] = ()) -> None:
        self._evict()
        flash = set(flash_ids)

        matching = [r for r in self._records.values() if self._matches(r)]
        matching.sort(key=lambda r: r.get("timestamp") or 0.0, reverse=True)
        matching = matching[:_MAX_CARDS]

        controls: list[ft.Control] = []
        for record in matching:
            order_id = record["order_id"]
            card = self._cards.get(order_id)
            if card is None:
                card = OrderCard(record, flash=order_id in flash)
                self._cards[order_id] = card
            else:
                self._sync_card(card, record, flash=order_id in flash)
            controls.append(card)

        self._list_column.controls = controls
        self._recount_orders()
        self._show_body()
        update_batcher.mark_dirty(self._list_column)

    @staticmethod
    def _sync_card(card: OrderCard, record: dict, *, flash: bool) -> None:
        status = str(record.get("status") or "FILLED")
        if card.status != status:
            card.update_status(status, flash=True)
        elif flash:
            card.flash()
        if record.get("pnl") is not None:
            card.set_pnl(record["pnl"])

    def _recount_orders(self) -> None:
        # CountText pluraliza y se repinta solo si el número cambió (DRY)
        self._count_text.set_count(len(self._list_column.controls))

    def _show_body(self) -> None:
        """Muestra exactamente un estado (loading / lista / vacío / error)."""
        if self._loading:
            target = self._loader
        elif self._list_column.controls:
            target = self._list_column
        elif self._load_error:
            target = self._error
            self._error_text.value = f"Error cargando órdenes: {self._load_error}"
        else:
            target = self._empty

        if self._body.content is target:
            return
        self._body.content = target
        update_batcher.mark_dirty(self._body)

    def _on_filter_changed(self, key: str) -> None:
        self._filter = key
        self._rebuild()
