"""
SymbolPicker — Selector de símbolos con búsqueda y scroll.

Refactorizado para aplicar DIP:
- Recibe symbol_repository por constructor
- No importa binance_service directamente
"""
from __future__ import annotations

import asyncio
import logging
import flet as ft

from config.settings import settings
from core.event_bus import event_bus
from core.events import SymbolsListEvent

log = logging.getLogger(__name__)

MAX_VISIBLE_ITEMS = 5
ITEM_HEIGHT = 40
OVERLAY_HEIGHT = MAX_VISIBLE_ITEMS * ITEM_HEIGHT + 56


class SymbolPicker(ft.Container):
    """Selector de símbolo con búsqueda y lista scrollable."""

    def __init__(
        self,
        on_symbol_changed: callable | None = None,
        symbol_repository: object | None = None,
    ) -> None:
        super().__init__()
        self._on_symbol_changed = on_symbol_changed
        self._repository = symbol_repository
        self._symbols: list[dict] = []
        self._filtered: list[dict] = []
        self._loaded = False
        self._is_open = False

        self._search_field = ft.TextField(
            hint_text="Buscar símbolo...",
            hint_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400, size=13),
            text_style=ft.TextStyle(color=ft.Colors.WHITE, size=13),
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.WHITE),
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.CYAN_400,
            border_radius=10,
            content_padding=ft.Padding(left=10, right=10, top=8, bottom=8),
            suffix_icon=ft.Icons.SEARCH,
            suffix_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400),
            on_change=self._on_search,
            on_focus=self._on_search_focus,
            expand=True,
        )

        self._options_column = ft.Column(
            controls=[],
            spacing=2,
            scroll=ft.ScrollMode.AUTO,
            height=MAX_VISIBLE_ITEMS * ITEM_HEIGHT,
        )

        self._overlay = ft.Container(
            bgcolor=ft.Colors.with_opacity(0.92, ft.Colors.GREY_900),
            border=ft.Border.all(1, ft.Colors.BLUE_GREY_700),
            border_radius=12,
            padding=ft.Padding(left=8, right=8, top=8, bottom=8),
            visible=False,
            width=220,
            content=ft.Column(
                controls=[
                    self._search_field,
                    ft.Container(height=4),
                    self._options_column,
                ],
                spacing=0,
            ),
        )

        self._trigger_label = ft.Text(
            value=settings.TRADING_SYMBOL,
            size=14,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.WHITE,
            expand=True,
            text_align=ft.TextAlign.LEFT,
        )

        self._trigger = ft.Container(
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.WHITE),
            border=ft.Border.all(1, ft.Colors.BLUE_GREY_700),
            border_radius=10,
            padding=ft.Padding(left=12, right=8, top=8, bottom=8),
            ink=True,
            on_click=self._on_trigger_click,
            content=ft.Row(
                controls=[
                    self._trigger_label,
                    ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=18, color=ft.Colors.BLUE_GREY_400),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        self._loading_indicator = ft.ProgressRing(
            width=16, height=16, stroke_width=2,
            color=ft.Colors.CYAN_400,
        )
        self._loading_indicator.visible = False

        self.content = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("Símbolo", size=12, color=ft.Colors.BLUE_GREY_400),
                        self._loading_indicator,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                self._trigger,
                self._overlay,
            ],
            spacing=4,
        )

    def did_mount(self) -> None:
        event_bus.subscribe(SymbolsListEvent, self._on_symbols_list)
        asyncio.create_task(self._load_symbols())

    def will_unmount(self) -> None:
        event_bus.unsubscribe(SymbolsListEvent, self._on_symbols_list)

    async def _load_symbols(self) -> None:
        try:
            self._loading_indicator.visible = True
            self._loading_indicator.update()
            if self._repository:
                await self._repository.get_trading_symbols()
            else:
                # Fallback: acceso directo (legacy)
                from services.binance_service import binance_service
                await binance_service.get_trading_symbols()
        except Exception as exc:
            log.error("Error loading symbols: %s", exc)
            self._loading_indicator.visible = False
            self._loading_indicator.update()

    async def _on_symbols_list(self, event: SymbolsListEvent) -> None:
        self._symbols = event.symbols
        self._filtered = list(self._symbols)
        self._loading_indicator.visible = False
        self._loading_indicator.update()
        self._loaded = True
        self._render_options()

    def _render_options(self) -> None:
        self._options_column.controls.clear()
        for s in self._filtered[:MAX_VISIBLE_ITEMS]:
            price = float(s.get("price", 0))
            if price >= 1:
                price_str = f"${price:,.2f}"
            elif price >= 0.01:
                price_str = f"${price:.4f}"
            else:
                price_str = f"${price:.8f}"

            is_selected = s["symbol"] == self.get_selected_symbol()

            opt = ft.Container(
                bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE) if not is_selected
                       else ft.Colors.with_opacity(0.15, ft.Colors.CYAN_700),
                border_radius=8,
                padding=ft.Padding(left=10, right=10, top=6, bottom=6),
                on_click=self._on_option_click,
                data=s["symbol"],
                content=ft.Row(
                    controls=[
                        ft.Text(s["base_asset"], size=13, weight=ft.FontWeight.W_700, color=ft.Colors.WHITE),
                        ft.Text(f" / {s['quote_asset']}", size=11, color=ft.Colors.BLUE_GREY_400),
                        ft.Container(expand=True),
                        ft.Text(price_str, size=12, color=ft.Colors.CYAN_300),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
            self._options_column.controls.append(opt)

        if not self._filtered:
            self._options_column.controls.append(
                ft.Container(
                    padding=12,
                    content=ft.Text("Sin resultados", size=13, color=ft.Colors.BLUE_GREY_400, text_align=ft.TextAlign.CENTER),
                )
            )

        self._options_column.update()

    def _on_trigger_click(self, e: ft.ControlEvent) -> None:
        self._is_open = not self._is_open
        self._overlay.visible = self._is_open
        if self._is_open:
            self._search_field.value = ""
            self._filtered = list(self._symbols)
            self._render_options()
        self.update()

    def _on_search(self, e: ft.ControlEvent) -> None:
        query = (e.control.value or "").strip().upper()
        if not query:
            self._filtered = list(self._symbols)
        else:
            self._filtered = [
                s for s in self._symbols
                if query in s["symbol"].upper() or query in s.get("base_asset", "").upper()
            ]
        self._render_options()

    def _on_search_focus(self, e: ft.ControlEvent) -> None:
        if not self._is_open:
            self._is_open = True
            self._overlay.visible = True
            self.update()

    def _on_option_click(self, e: ft.ControlEvent) -> None:
        symbol = e.control.data
        if symbol and symbol != self.get_selected_symbol():
            self._trigger_label.value = symbol
            log.info("Symbol changed to: %s", symbol)
            if self._on_symbol_changed:
                self._on_symbol_changed(symbol)
        self._is_open = False
        self._overlay.visible = False
        self.update()

    def get_selected_symbol(self) -> str:
        return self._trigger_label.value or settings.TRADING_SYMBOL

    def refresh_symbols(self) -> None:
        self._loading_indicator.visible = True
        self._loading_indicator.update()
        asyncio.create_task(self._load_symbols())
