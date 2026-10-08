"""
MarkPriceRow — Mark/Index/Funding de Futures (MarkPriceEvent).

Aplica:
- DRY: SymbolAwareSubscriber filtra símbolo
- SRP: solo muestra datos de mark price
- PERFORMANCE: usa update_batcher para un solo render
"""
from __future__ import annotations

import logging
from datetime import datetime

import flet as ft

from config.settings import settings
from core.events import MarkPriceEvent, SettingsUpdatedEvent
from core.update_batcher import update_batcher
from ui.components.base import SymbolAwareSubscriber

log = logging.getLogger(__name__)


class MarkPriceRow(ft.Column, SymbolAwareSubscriber):
    """Bloque Mark / Índice / Funding — solo visible en TRADING_TYPE=FUTURES.

    Incluye su propio divider superior para que la visibilidad del bloque
    (FUTURES vs SPOT) oculte también la separación.
    """

    def __init__(self, symbol: str = "BTCUSDT") -> None:
        super().__init__()
        self._current_symbol = symbol

        self._mark_text = ft.Text(
            "---", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE,
        )
        self._index_text = ft.Text(
            "---", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.TEAL_300,
        )
        self._funding_text = ft.Text(
            "---", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_300,
        )

        def _cell(label: str, value: ft.Text) -> ft.Control:
            return ft.Column(
                controls=[
                    ft.Text(label, size=10, color=ft.Colors.BLUE_GREY_400),
                    value,
                ],
                spacing=2,
                expand=True,
            )

        self._cells = ft.Row(
            controls=[
                _cell("Mark price", self._mark_text),
                _cell("Índice", self._index_text),
                _cell("Funding", self._funding_text),
            ],
            spacing=12,
            wrap=True,
        )

        self.controls = [
            ft.Divider(
                color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
                height=1,
            ),
            self._cells,
        ]
        self.spacing = 8
        self.visible = settings.TRADING_TYPE == "FUTURES"

        self._event_subscriptions = [
            (MarkPriceEvent, self._on_mark_price),
            (SettingsUpdatedEvent, self._on_settings_updated),
        ]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def did_mount(self) -> None:
        self._setup_subscriptions()
        self.sync_symbol()

    def will_unmount(self) -> None:
        self._teardown_subscriptions()

    def _on_symbol_changed(self, symbol: str) -> None:
        self._mark_text.value = "---"
        self._index_text.value = "---"
        self._funding_text.value = "---"
        update_batcher.mark_dirty(self)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    async def _on_mark_price(self, event: MarkPriceEvent) -> None:
        if not self.matches_symbol(event.symbol):
            return

        self._mark_text.value = f"${event.mark_price:,.2f}"
        self._index_text.value = f"${event.index_price:,.2f}"

        funding_pct = event.funding_rate * 100
        sign = "+" if funding_pct >= 0 else ""
        funding = f"{sign}{funding_pct:.4f}%"
        if event.next_funding_ts > 0:
            next_dt = datetime.fromtimestamp(event.next_funding_ts)
            funding += f" · {next_dt.strftime('%H:%M')}"
        self._funding_text.value = funding
        self._funding_text.color = (
            ft.Colors.GREEN_400 if funding_pct >= 0 else ft.Colors.RED_400
        )

        update_batcher.mark_dirty(self)

    async def _on_settings_updated(self, event: SettingsUpdatedEvent) -> None:
        self.visible = settings.TRADING_TYPE == "FUTURES"
        self.sync_symbol()
        update_batcher.mark_dirty(self)
