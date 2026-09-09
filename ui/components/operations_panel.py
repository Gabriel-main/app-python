"""
OperationsPanel — Panel de operaciones dual (OC/OV).

Muestra las operaciones activas, pendientes y pasadas
con entry price, stop loss, y timer de temporalidad.
"""
from __future__ import annotations

import flet as ft

from core.event_bus import event_bus
from core.events import OperationState, OperationUpdateEvent


def _format_time(seconds: float) -> str:
    """Formatea segundos a MM:SS."""
    if seconds <= 0:
        return "0:00"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


def _operation_card(op: OperationState) -> ft.Container:
    """Construye una tarjeta para una operación individual."""
    if op.side == "BUY":
        side_color = ft.Colors.GREEN_400
        side_bg = ft.Colors.GREEN_900
        side_label = "COMPRA"
    else:
        side_color = ft.Colors.RED_400
        side_bg = ft.Colors.RED_900
        side_label = "VENTA"

    state_colors = {
        "ACTIVE": (ft.Colors.GREEN_400, ft.Colors.GREEN_900, "ACTIVA"),
        "PENDING": (ft.Colors.AMBER_400, ft.Colors.AMBER_900, "PENDIENTE"),
        "PAST": (ft.Colors.BLUE_GREY_400, ft.Colors.BLUE_GREY_800, "PASADA"),
    }
    st_color, st_bg, st_label = state_colors.get(op.state, (ft.Colors.WHITE, ft.Colors.GREY_800, op.state))

    return ft.Container(
        bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.WHITE),
        border_radius=10,
        padding=ft.Padding(left=12, right=12, top=10, bottom=10),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.WHITE)),
        content=ft.Column(
            controls=[
                # Fila superior: lado + estado
                ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Text(f"{side_label}", size=11, weight=ft.FontWeight.BOLD, color=side_color),
                            bgcolor=side_bg,
                            border_radius=6,
                            padding=ft.Padding(left=8, right=8, top=3, bottom=3),
                        ),
                        ft.Container(
                            content=ft.Text(st_label, size=10, weight=ft.FontWeight.W_500, color=st_color),
                            bgcolor=st_bg,
                            border_radius=4,
                            padding=ft.Padding(left=6, right=6, top=2, bottom=2),
                        ),
                        ft.Container(expand=True),
                        ft.Text(
                            op.order_id,
                            size=9,
                            color=ft.Colors.BLUE_GREY_500,
                        ),
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
                            spacing=1,
                            expand=True,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text("Stop Loss", size=9, color=ft.Colors.BLUE_GREY_500),
                                ft.Text(f"${op.stop_loss:,.4f}", size=12, color=ft.Colors.RED_400),
                            ],
                            spacing=1,
                            expand=True,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text("Cantidad", size=9, color=ft.Colors.BLUE_GREY_500),
                                ft.Text(f"{op.quantity:.6f}", size=12, color=ft.Colors.WHITE),
                            ],
                            spacing=1,
                            expand=True,
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                        ),
                    ],
                ),
            ],
            spacing=0,
        ),
    )


class OperationsPanel(ft.Container):
    """Panel que muestra las operaciones activas/pendientes y timer de temporalidad."""

    def __init__(self) -> None:
        super().__init__()
        self._operations: list[OperationState] = []
        self._timeframe_remaining: float = 0.0
        self._timeframe_total: float = 0.0

        self._empty_text = ft.Text(
            "Sin operaciones activas.",
            size=12,
            color=ft.Colors.BLUE_GREY_400,
            text_align=ft.TextAlign.CENTER,
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
        """Actualiza el panel con el nuevo estado de operaciones."""
        self._operations = event.operations
        self._timeframe_remaining = event.timeframe_remaining
        self._timeframe_total = event.timeframe_total
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        """Redibuja el panel de operaciones."""
        self._operations_column.controls.clear()

        if not self._operations:
            self._empty_text.visible = True
            self._timer_text.value = ""
            self._timer_bar.value = 0.0
        else:
            self._empty_text.visible = False

            for op in self._operations:
                self._operations_column.controls.append(_operation_card(op))

            # Timer
            if self._timeframe_total > 0:
                progress = self._timeframe_remaining / self._timeframe_total
                self._timer_bar.value = progress
                self._timer_text.value = f"⏱ {_format_time(self._timeframe_remaining)} / {_format_time(self._timeframe_total)}"
            else:
                self._timer_text.value = ""
                self._timer_bar.value = 0.0

        self._operations_column.update()
        self._timer_text.update()
        self._timer_bar.update()
        self._empty_text.update()
