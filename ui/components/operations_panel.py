"""
OperationsPanel — Panel de operaciones dual (OC/OV).

Refactorizado para aplicar:
- DRY: Usa SIDE_COLORS, STATE_COLORS, SIDE_LABELS de colors.py
- SRP: Solo maneja visualización de operaciones
- PERFORMANCE: Diff incremental (no recrea widgets en cada tick)
- PERFORMANCE: Usa update_batcher para un solo render por batch
"""
from __future__ import annotations

import flet as ft

from core.event_bus import event_bus
from core.events import OperationState, OperationUpdateEvent
from core.update_batcher import update_batcher
from ui.components.colors import SIDE_COLORS, SIDE_LABELS, STATE_COLORS
from ui.components.badges import Badge
from ui.components.empty_state import EmptyState


def _format_time(seconds: float) -> str:
    """Formatea segundos a MM:SS."""
    if seconds <= 0:
        return "0:00"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


def _operation_key(op: OperationState) -> tuple:
    """Clave de diff de una operación: cambia si cambia id, estado o fill."""
    return (op.order_id, op.state, op.entry_filled)


def _has_pending_entry(op: OperationState) -> bool:
    """True si la entrada LIMIT sigue working (sin posición y op no terminada).

    En PAST la orden working ya fue cancelada (bot stop / timeframe), así que
    no hay entrada pendiente que mostrar.
    """
    return not op.entry_filled and op.state != "PAST"


def _operation_card(op: OperationState) -> ft.Container:
    """Construye una tarjeta para una operación individual."""
    side_fg, side_bg = SIDE_COLORS.get(op.side, (ft.Colors.WHITE, ft.Colors.GREY_800))
    side_label = SIDE_LABELS.get(op.side, op.side)

    st_fg, st_bg, st_label = STATE_COLORS.get(
        op.state, (ft.Colors.WHITE, ft.Colors.GREY_800, op.state)
    )

    badges = [
        Badge(label=side_label, fg_color=side_fg, bg_color=side_bg),
        Badge(label=st_label, fg_color=st_fg, bg_color=st_bg, border_radius=4),
    ]
    if _has_pending_entry(op):
        # Orden LIMIT working: la entrada aún no llenó (sin posición real)
        badges.append(Badge(
            label="ENTRADA PENDIENTE",
            fg_color=ft.Colors.AMBER_400,
            bg_color=ft.Colors.AMBER_900,
            border_radius=4,
        ))

    card = ft.Container(
        bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.WHITE),
        border_radius=10,
        padding=ft.Padding(left=12, right=12, top=10, bottom=10),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.WHITE)),
        content=ft.Column(
            controls=[
                # Fila superior: lado + estado (+ fill pendiente si LIMIT)
                ft.Row(
                    controls=[
                        *badges,
                        ft.Container(expand=True),
                        ft.Text(op.order_id, size=9, color=ft.Colors.BLUE_GREY_500),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=6),
                # Fila de precios
                ft.Row(
                    controls=[
                        ft.Column(
                            controls=[
                                ft.Text("Entry", size=9, color=ft.Colors.BLUE_GREY_500),
                                ft.Text(f"${op.entry_price:,.4f}", size=12, color=ft.Colors.WHITE),
                            ],
                            spacing=1, expand=True,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text("Stop Loss", size=9, color=ft.Colors.BLUE_GREY_500),
                                ft.Text(f"${op.stop_loss:,.4f}", size=12, color=ft.Colors.RED_400),
                            ],
                            spacing=1, expand=True,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text("Cantidad", size=9, color=ft.Colors.BLUE_GREY_500),
                                ft.Text(f"{op.quantity:.6f}", size=12, color=ft.Colors.WHITE),
                            ],
                            spacing=1, expand=True,
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                        ),
                    ],
                ),
            ],
            spacing=0,
        ),
    )
    # Tags para identificar la tarjeta en el diff
    card._op_order_id = op.order_id
    card._op_state = op.state
    card._op_entry_filled = op.entry_filled
    return card


class OperationsPanel(ft.Container):
    """Panel que muestra las operaciones activas/pendientes y timer de temporalidad."""

    def __init__(self) -> None:
        super().__init__()
        self._operations: list[OperationState] = []
        self._timeframe_remaining: float = 0.0
        self._timeframe_total: float = 0.0

        self._empty_text = EmptyState(
            "Sin operaciones activas.",
            subtitle="El bot abrirá una operación al detectar una señal.",
            icon=ft.Icons.SWAP_VERT_OUTLINED,
            title_size=12,
        )

        self._timer_text = ft.Text(
            "",
            size=12,
            color=ft.Colors.CYAN_400,
            weight=ft.FontWeight.W_500,
        )

        self._timer_bar = ft.ProgressBar(
            value=0.0,
            color=ft.Colors.CYAN_400,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
            height=4,
        )

        self._operations_column = ft.Column(spacing=8)

        self.content = ft.Container(
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border_radius=14,
            padding=ft.Padding(left=16, right=16, top=12, bottom=12),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                "🔄 Operaciones",
                                size=14,
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.WHITE,
                            ),
                            ft.Container(expand=True),
                            self._timer_text,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self._timer_bar,
                    ft.Container(height=8),
                    self._operations_column,
                    self._empty_text,
                ],
                spacing=0,
            ),
        )

    def did_mount(self) -> None:
        event_bus.subscribe(OperationUpdateEvent, self._on_operation_update)

    def will_unmount(self) -> None:
        event_bus.unsubscribe(OperationUpdateEvent, self._on_operation_update)

    async def _on_operation_update(self, event: OperationUpdateEvent) -> None:
        """Actualiza el panel con el nuevo estado de operaciones.

        Filtra PAST: el panel muestra solo operaciones vigentes (ACTIVE +
        PENDING). Las terminadas viven en DB (Órdenes/Auditoría) — el
        snapshot completo sigue llegando para db_queue y audit.
        """
        self._operations = [op for op in event.operations if op.state != "PAST"]
        self._timeframe_remaining = event.timeframe_remaining
        self._timeframe_total = event.timeframe_total
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        """Redibuja el panel de operaciones con diff incremental."""
        if not self._operations:
            if self._operations_column.controls:
                self._operations_column.controls.clear()
            self._empty_text.visible = True
            self._timer_text.value = ""
            self._timer_bar.value = 0.0
        else:
            self._empty_text.visible = False

            # Diff incremental: recrear si cambiaron los order_ids, el state
            # o el fill de entrada (sino el badge "ENTRADA PENDIENTE" no se
            # redibujaría: un cambio in-place con el mismo order_id)
            new_keys = {_operation_key(op) for op in self._operations}
            existing_keys = {
                (
                    getattr(c, '_op_order_id', None),
                    getattr(c, '_op_state', None),
                    getattr(c, '_op_entry_filled', None),
                )
                for c in self._operations_column.controls
            }

            if new_keys != existing_keys:
                # Reconstruir solo si hay diff real
                self._operations_column.controls.clear()
                for op in self._operations:
                    self._operations_column.controls.append(_operation_card(op))

            # Timer siempre se actualiza
            if self._timeframe_total > 0:
                progress = self._timeframe_remaining / self._timeframe_total
                self._timer_bar.value = progress
                self._timer_text.value = f"⏱ {_format_time(self._timeframe_remaining)} / {_format_time(self._timeframe_total)}"
            else:
                self._timer_text.value = ""
                self._timer_bar.value = 0.0

        # Batch update: un solo render
        update_batcher.mark_dirty(self._operations_column)
        update_batcher.mark_dirty(self._timer_text)
        update_batcher.mark_dirty(self._timer_bar)
        update_batcher.mark_dirty(self._empty_text)
