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
from core.update_batcher import update_batcher

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
        self._currency = settings.TRADE_CURRENCY
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
        self.invalidate()
        return True

    def set_currency(self, currency: str) -> bool:
        """Cambia moneda. Retorna True si hubo cambio."""
        if currency == self._currency:
            return False
        self._currency = currency
        self.invalidate()
        return True

    def invalidate(self) -> None:
        """Limpia estado y descarta eventos stale. Fuente única de invalidación."""
        self._symbols = []
        self._search_query = ""
        self._fetch_generation += 1

    async def load_symbols(self) -> int:
        """Carga símbolos vía repository. Retorna generation para detectar stale events."""
        gen = self._fetch_generation
        if self._repository:
            await self._repository.get_trading_symbols(self._trading_type, self._currency)
        else:
            from services.binance_service import binance_service
            await binance_service.get_trading_symbols(self._trading_type, self._currency)
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
    Solo maneja rendering y eventos de usuario con diseño UI/UX premium.
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

        # --- Campo de búsqueda ---
        self._search_field = ft.TextField(
            hint_text="Buscar símbolo (ej: BTC, ETH)...",
            hint_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_400, size=12),
            text_style=ft.TextStyle(color=ft.Colors.WHITE, size=13),
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.WHITE),
            border_color=ft.Colors.BLUE_GREY_700,
            focused_border_color=ft.Colors.CYAN_400,
            border_radius=10,
            content_padding=ft.Padding(left=10, right=10, top=9, bottom=9),
            prefix_icon=ft.Icons.SEARCH,
            on_change=self._on_search,
            on_focus=self._on_search_focus,
            expand=True,
        )

        # --- Lista de opciones scrollable ---
        self._options_column = ft.Column(
            controls=[],
            spacing=4,
            scroll=ft.ScrollMode.AUTO,
            height=280,
        )

        self._counter_text = ft.Text("", size=11, color=ft.Colors.BLUE_GREY_300)
        self._market_pill_text = ft.Text(self._mgr.trading_type, size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_300)
        self._market_pill = ft.Container(
            content=self._market_pill_text,
            bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.CYAN_400),
            border_radius=6,
            padding=ft.Padding(left=6, right=6, top=2, bottom=2),
        )

        # --- Dropdown panel flotante ---
        self._overlay = ft.Container(
            bgcolor="#101726",
            border=ft.Border.all(1, ft.Colors.with_opacity(0.35, ft.Colors.CYAN_400)),
            border_radius=14,
            padding=ft.Padding(left=12, right=12, top=12, bottom=10),
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=16,
                color=ft.Colors.BLACK_54,
                offset=ft.Offset(0, 6),
            ),
            visible=False,
            content=ft.Column(
                controls=[
                    self._search_field,
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.TOKEN_OUTLINED, size=13, color=ft.Colors.CYAN_400),
                                        self._counter_text,
                                    ],
                                    spacing=4,
                                ),
                                self._market_pill,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding(top=6, bottom=6),
                    ),
                    ft.Divider(height=1, thickness=1, color=ft.Colors.with_opacity(0.12, ft.Colors.BLUE_GREY_700)),
                    ft.Container(height=4),
                    self._options_column,
                ],
                spacing=2,
            ),
        )

        # --- Componentes del trigger selector ---
        self._trigger_label = ft.Text(
            value=self._mgr.selection,
            size=14,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.WHITE,
        )
        self._trigger_quote = ft.Text(
            value=f"/{self._mgr._currency}",
            size=11,
            color=ft.Colors.BLUE_GREY_400,
        )
        self._trigger_badge_text = ft.Text(
            value=self._mgr.trading_type,
            size=10,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.CYAN_300,
        )
        self._trigger_badge = ft.Container(
            content=self._trigger_badge_text,
            bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.CYAN_400),
            border_radius=6,
            padding=ft.Padding(left=6, right=6, top=2, bottom=2),
        )
        self._arrow_icon = ft.Icon(
            ft.Icons.KEYBOARD_ARROW_DOWN,
            size=20,
            color=ft.Colors.BLUE_GREY_400,
        )

        self._trigger = ft.Container(
            bgcolor=ft.Colors.GREY_900,
            border=ft.Border.all(1, ft.Colors.BLUE_GREY_700),
            border_radius=10,
            padding=ft.Padding(left=12, right=10, top=8, bottom=8),
            ink=True,
            on_click=self._on_trigger_click,
            content=ft.Row(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Container(
                                width=26,
                                height=26,
                                border_radius=13,
                                bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.CYAN_400),
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(
                                    ft.Icons.CURRENCY_EXCHANGE,
                                    size=15,
                                    color=ft.Colors.CYAN_300,
                                ),
                            ),
                            self._trigger_label,
                            self._trigger_quote,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                    ),
                    ft.Row(
                        controls=[
                            self._trigger_badge,
                            self._arrow_icon,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        self._loading_indicator = ft.ProgressRing(
            width=14,
            height=14,
            stroke_width=2,
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
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self._sync_trigger_label()

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
        update_batcher.mark_dirty(self._loading_indicator)

    def _close_overlay(self) -> None:
        self._is_open = False
        self._overlay.visible = False
        self._arrow_icon.name = ft.Icons.KEYBOARD_ARROW_DOWN
        self._arrow_icon.color = ft.Colors.BLUE_GREY_400
        self._trigger.border = ft.Border.all(1, ft.Colors.BLUE_GREY_700)

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
        update_batcher.mark_dirty(self)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _render_options(self) -> None:
        self._options_column.controls.clear()
        filtered = self._mgr.filtered_symbols
        total = len(filtered)
        self._counter_text.value = f"{total} par{'es' if total != 1 else ''} disponible{'s' if total != 1 else ''}"

        for s in filtered:
            price = float(s.get("price", 0))
            if price >= 1000:
                price_str = f"${price:,.2f}"
            elif price >= 1:
                price_str = f"${price:.2f}"
            elif price >= 0.01:
                price_str = f"${price:.4f}"
            else:
                price_str = f"${price:.8f}"

            is_selected = s["symbol"] == self._mgr.selection
            base = s.get("base_asset", "")
            quote = s.get("quote_asset", "")
            avatar_txt = base[:2] if len(base) >= 2 else base

            avatar = ft.Container(
                width=24,
                height=24,
                border_radius=12,
                bgcolor=ft.Colors.with_opacity(0.18, ft.Colors.CYAN_400) if is_selected else ft.Colors.with_opacity(0.08, ft.Colors.WHITE),
                alignment=ft.Alignment(0, 0),
                content=ft.Text(
                    avatar_txt,
                    size=9,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.CYAN_300 if is_selected else ft.Colors.BLUE_GREY_300,
                ),
            )

            row_controls = [
                avatar,
                ft.Row(
                    controls=[
                        ft.Text(base, size=13, weight=ft.FontWeight.W_700, color=ft.Colors.WHITE),
                        ft.Text(f"/{quote}", size=11, color=ft.Colors.BLUE_GREY_400),
                    ],
                    spacing=2,
                ),
                ft.Container(expand=True),
                ft.Text(
                    price_str,
                    size=12,
                    weight=ft.FontWeight.W_600 if is_selected else ft.FontWeight.NORMAL,
                    color=ft.Colors.CYAN_300 if is_selected else ft.Colors.WHITE_70,
                ),
            ]

            if is_selected:
                row_controls.append(
                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=15, color=ft.Colors.CYAN_400)
                )

            opt = ft.Container(
                bgcolor=ft.Colors.with_opacity(0.14, ft.Colors.CYAN_700) if is_selected
                        else ft.Colors.with_opacity(0.04, ft.Colors.WHITE),
                border=ft.Border.all(
                    1,
                    ft.Colors.with_opacity(0.4, ft.Colors.CYAN_400) if is_selected
                    else ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
                ),
                border_radius=8,
                padding=ft.Padding(left=10, right=10, top=7, bottom=7),
                on_click=self._on_option_click,
                data=s["symbol"],
                ink=True,
                content=ft.Row(
                    controls=row_controls,
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
            )
            self._options_column.controls.append(opt)

        if not filtered:
            query = self._mgr._search_query
            self._options_column.controls.append(
                ft.Container(
                    padding=ft.Padding(left=12, right=12, top=24, bottom=24),
                    alignment=ft.Alignment(0, 0),
                    content=ft.Column(
                        controls=[
                            ft.Icon(ft.Icons.SEARCH_OFF, size=32, color=ft.Colors.BLUE_GREY_500),
                            ft.Text(
                                f'Sin resultados para "{query}"' if query else "No hay símbolos disponibles",
                                size=13,
                                weight=ft.FontWeight.W_500,
                                color=ft.Colors.BLUE_GREY_300,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Text(
                                "Intenta con BTC, ETH, SOL, XRP...",
                                size=11,
                                color=ft.Colors.BLUE_GREY_500,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=4,
                    ),
                )
            )

        try:
            self._options_column.update()
        except RuntimeError:
            pass
        update_batcher.mark_dirty(self._counter_text)

    def _sync_trigger_label(self) -> None:
        """Sincroniza el label del trigger con la selección del manager."""
        symbol = self._mgr.selection
        quote = self._mgr._currency
        base = symbol[:-len(quote)] if quote and symbol.endswith(quote) else symbol
        self._trigger_label.value = base
        self._trigger_quote.value = f"/{quote}"
        self._trigger_badge_text.value = self._mgr.trading_type
        self._market_pill_text.value = self._mgr.trading_type

        # Color según tipo de mercado
        if self._mgr.trading_type == "FUTURES":
            badge_bg = ft.Colors.with_opacity(0.15, ft.Colors.AMBER_400)
            badge_fg = ft.Colors.AMBER_300
        elif self._mgr.trading_type == "MARGIN":
            badge_bg = ft.Colors.with_opacity(0.15, ft.Colors.PURPLE_400)
            badge_fg = ft.Colors.PURPLE_300
        else:
            badge_bg = ft.Colors.with_opacity(0.15, ft.Colors.CYAN_400)
            badge_fg = ft.Colors.CYAN_300

        self._trigger_badge.bgcolor = badge_bg
        self._trigger_badge_text.color = badge_fg
        self._market_pill.bgcolor = badge_bg
        self._market_pill_text.color = badge_fg

    # ------------------------------------------------------------------
    # Event handlers de usuario
    # ------------------------------------------------------------------
    def _on_trigger_click(self, e: ft.ControlEvent) -> None:
        self._is_open = not self._is_open
        self._overlay.visible = self._is_open
        self._arrow_icon.name = (
            ft.Icons.KEYBOARD_ARROW_UP if self._is_open else ft.Icons.KEYBOARD_ARROW_DOWN
        )
        self._arrow_icon.color = (
            ft.Colors.CYAN_400 if self._is_open else ft.Colors.BLUE_GREY_400
        )
        self._trigger.border = ft.Border.all(
            1, ft.Colors.CYAN_400 if self._is_open else ft.Colors.BLUE_GREY_700
        )
        if self._is_open:
            self._search_field.value = ""
            self._mgr.set_search_query("")
            self._render_options()
        update_batcher.mark_dirty(self)

    def _on_search(self, e: ft.ControlEvent) -> None:
        self._mgr.set_search_query(e.control.value or "")
        self._render_options()

    def _on_search_focus(self, e: ft.ControlEvent) -> None:
        if not self._is_open:
            self._is_open = True
            self._overlay.visible = True
            self._arrow_icon.name = ft.Icons.KEYBOARD_ARROW_UP
            self._arrow_icon.color = ft.Colors.CYAN_400
            self._trigger.border = ft.Border.all(1, ft.Colors.CYAN_400)
            update_batcher.mark_dirty(self)

    def _on_option_click(self, e: ft.ControlEvent) -> None:
        symbol = e.control.data
        if symbol and symbol != self._mgr.selection:
            self._mgr.set_selection(symbol)
            self._sync_trigger_label()
            log.info("Symbol changed to: %s", symbol)
            if self._on_symbol_changed:
                self._on_symbol_changed(symbol)
        self._close_overlay()
        update_batcher.mark_dirty(self)

    # ------------------------------------------------------------------
    # API pública (misma interfaz que antes)
    # ------------------------------------------------------------------
    def get_selected_symbol(self) -> str:
        return self._mgr.selection

    def set_symbol(self, symbol: str) -> None:
        self._mgr.set_selection(symbol)
        self._sync_trigger_label()
        update_batcher.mark_dirty(self._trigger)

    def set_trading_type(self, trading_type: str) -> None:
        """Cambia el mercado y recarga los símbolos disponibles."""
        if self._mgr.set_trading_type(trading_type):
            self._sync_trigger_label()
            self._trigger_reload()

    def set_currency(self, currency: str) -> None:
        """Cambia la moneda y recarga los símbolos disponibles."""
        if self._mgr.set_currency(currency):
            self._sync_trigger_label()
            self._trigger_reload()

    def _trigger_reload(self) -> None:
        """Muestra loading, cierra overlay, dispara reload async. Fuente única."""
        self._set_loading(True)
        self._close_overlay()
        asyncio.create_task(self._load_symbols())

    def refresh_symbols(self) -> None:
        self._trigger_reload()
