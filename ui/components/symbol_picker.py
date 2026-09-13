"""
SymbolPicker — Selector de símbolos con búsqueda y scroll.

Separación SOLID:
- SymbolListManager: estado + lógica de negocio (sin dependencias de Flet)
- SymbolPicker: UI + interacción del usuario (delega al manager)

DIP: Recibe SymbolRepository por constructor, sin fallback a binance_service.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Protocol

import flet as ft

from config.settings import settings
from core.event_bus import event_bus
from core.events import SymbolsListEvent

log = logging.getLogger(__name__)

MAX_VISIBLE_ITEMS = 8
ITEM_HEIGHT = 40
OVERLAY_HEIGHT = MAX_VISIBLE_ITEMS * ITEM_HEIGHT + 56


# ---------------------------------------------------------------------------
# SymbolListManager — Estado + lógica (sin dependencias de Flet)
# ---------------------------------------------------------------------------
class SymbolListManager:
    """Gestiona estado de símbolos: carga, filtrado, selección, auto-select.

    Responsabilidades (SRP):
    - Mantener la lista de símbolos cargados
    - Filtrar por query de búsqueda
    - Validar y auto-seleccionar símbolo al cambiar mercado
    - Prevenir race conditions con generation counter
    """

    def __init__(self, repository: object, initial_symbol: str) -> None:
        self._repository = repository
        self._trading_type = "SPOT"
        self._symbols: list[dict] = []
        self._selection = initial_symbol
        self._search_query = ""
        self._loaded = False
        self._fetch_generation = 0

    @property
    def trading_type(self) -> str:
        return self._trading_type

    @property
    def selection(self) -> str:
        return self._selection

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def filtered_symbols(self) -> list[dict]:
        """Retorna símbolos filtrados por query actual."""
        if not self._search_query:
            return list(self._symbols)
        q = self._search_query.upper()
        return [
            s for s in self._symbols
            if q in s["symbol"].upper() or q in s.get("base_asset", "").upper()
        ]

    def set_search_query(self, query: str) -> None:
        self._search_query = query.strip()

    def set_selection(self, symbol: str) -> None:
        if symbol != self._selection:
            self._selection = symbol

    def set_trading_type(self, trading_type: str) -> bool:
        """Cambia mercado. Retorna True si hubo cambio."""
        if trading_type == self._trading_type:
            return False
        self._trading_type = trading_type
        self._symbols = []
        self._search_query = ""
        self._fetch_generation += 1
        return True

    async def load_symbols(self) -> int:
        """Carga símbolos vía repository. Retorna generation para detectar stale events."""
        gen = self._fetch_generation
        if self._repository:
            await self._repository.get_trading_symbols(self._trading_type)
        else:
            from services.binance_service import binance_service
            await binance_service.get_trading_symbols(self._trading_type)
        return gen

    def accept_event(self, event_symbols: list[dict], event_trading_type: str) -> bool:
        """Procesa SymbolsListEvent. Retorna True si el evento es válido."""
        if event_trading_type != self._trading_type:
            return False
        self._symbols = event_symbols
        self._loaded = True
        self._sync_selection()
        return True

    def _sync_selection(self) -> bool:
        """Valida selección actual. Auto-select si el símbolo no existe en el mercado."""
        if not self._symbols:
            return False
        available = {s["symbol"] for s in self._symbols}
        if self._selection in available:
            return False
        self._selection = self._symbols[0]["symbol"]
        return True


# ---------------------------------------------------------------------------
# SymbolPicker — UI + interacción del usuario
# ---------------------------------------------------------------------------
class SymbolPicker(ft.Container):
    """Selector de símbolo con búsqueda y lista scrollable.

    Delega toda la lógica de estado a SymbolListManager.
    Solo maneja rendering y eventos de usuario.
    """

    def __init__(
        self,
        on_symbol_changed: callable | None = None,
        symbol_repository: object | None = None,
        trading_type: str = "SPOT",
    ) -> None:
        super().__init__()
        self._on_symbol_changed = on_symbol_changed
        self._mgr = SymbolListManager(symbol_repository, settings.TRADING_SYMBOL)
        self._mgr._trading_type = trading_type
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
            scroll=ft.ScrollMode.ALWAYS,
            height=MAX_VISIBLE_ITEMS * ITEM_HEIGHT,
        )

        self._counter_text = ft.Text("", size=10, color=ft.Colors.BLUE_GREY_500)

        self._overlay = ft.Container(
            bgcolor=ft.Colors.with_opacity(0.92, ft.Colors.GREY_900),
            border=ft.Border.all(1, ft.Colors.BLUE_GREY_700),
            border_radius=12,
            padding=ft.Padding(left=8, right=8, top=8, bottom=8),
            visible=False,
            width=280,
            content=ft.Column(
                controls=[
                    self._search_field,
                    ft.Divider(height=1, color=ft.Colors.BLUE_GREY_800),
                    self._counter_text,
                    self._options_column,
                ],
                spacing=0,
            ),
        )

        self._trigger_label = ft.Text(
            value=self._mgr.selection,
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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def did_mount(self) -> None:
        event_bus.subscribe(SymbolsListEvent, self._on_symbols_list)
        asyncio.create_task(self._load_symbols())

    def will_unmount(self) -> None:
        event_bus.unsubscribe(SymbolsListEvent, self._on_symbols_list)

    # ------------------------------------------------------------------
    # Helpers DRY
    # ------------------------------------------------------------------
    def _set_loading(self, visible: bool) -> None:
        self._loading_indicator.visible = visible
        try:
            self._loading_indicator.update()
        except RuntimeError:
            pass

    def _close_overlay(self) -> None:
        self._is_open = False
        self._overlay.visible = False

    # ------------------------------------------------------------------
    # Data loading (delega al manager)
    # ------------------------------------------------------------------
    async def _load_symbols(self) -> None:
        try:
            self._set_loading(True)
            gen = await self._mgr.load_symbols()
            if gen != self._mgr._fetch_generation:
                return
        except Exception as exc:
            log.error("Error loading symbols: %s", exc)
            self._set_loading(False)

    async def _on_symbols_list(self, event: SymbolsListEvent) -> None:
        if not self._mgr.accept_event(event.symbols, event.trading_type):
            return
        self._set_loading(False)
        self._sync_trigger_label()
        self._render_options()
        self.update()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _render_options(self) -> None:
        self._options_column.controls.clear()
        filtered = self._mgr.filtered_symbols
        total = len(filtered)
        self._counter_text.value = f"{total} símbolo{'s' if total != 1 else ''}"

        for s in filtered:
            price = float(s.get("price", 0))
            if price >= 1:
                price_str = f"${price:,.2f}"
            elif price >= 0.01:
                price_str = f"${price:.4f}"
            else:
                price_str = f"${price:.8f}"

            is_selected = s["symbol"] == self._mgr.selection

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

        if not filtered:
            self._options_column.controls.append(
                ft.Container(
                    padding=12,
                    content=ft.Text("Sin resultados", size=13, color=ft.Colors.BLUE_GREY_400, text_align=ft.TextAlign.CENTER),
                )
            )

        self._options_column.update()

    def _sync_trigger_label(self) -> None:
        """Sincroniza el label del trigger con la selección del manager."""
        self._trigger_label.value = self._mgr.selection

    # ------------------------------------------------------------------
    # Event handlers de usuario
    # ------------------------------------------------------------------
    def _on_trigger_click(self, e: ft.ControlEvent) -> None:
        self._is_open = not self._is_open
        self._overlay.visible = self._is_open
        if self._is_open:
            self._search_field.value = ""
            self._mgr.set_search_query("")
            self._render_options()
        self.update()

    def _on_search(self, e: ft.ControlEvent) -> None:
        self._mgr.set_search_query(e.control.value or "")
        self._render_options()

    def _on_search_focus(self, e: ft.ControlEvent) -> None:
        if not self._is_open:
            self._is_open = True
            self._overlay.visible = True
            self.update()

    def _on_option_click(self, e: ft.ControlEvent) -> None:
        symbol = e.control.data
        if symbol and symbol != self._mgr.selection:
            self._mgr.set_selection(symbol)
            self._trigger_label.value = symbol
            log.info("Symbol changed to: %s", symbol)
            if self._on_symbol_changed:
                self._on_symbol_changed(symbol)
        self._close_overlay()
        self.update()

    # ------------------------------------------------------------------
    # API pública (misma interfaz que antes)
    # ------------------------------------------------------------------
    def get_selected_symbol(self) -> str:
        return self._mgr.selection

    def set_symbol(self, symbol: str) -> None:
        self._mgr.set_selection(symbol)
        self._trigger_label.value = symbol

    def set_trading_type(self, trading_type: str) -> None:
        """Cambia el mercado y recarga los símbolos disponibles."""
        if self._mgr.set_trading_type(trading_type):
            self._set_loading(True)
            self._close_overlay()
            asyncio.create_task(self._load_symbols())

    def refresh_symbols(self) -> None:
        self._set_loading(True)
        asyncio.create_task(self._load_symbols())
