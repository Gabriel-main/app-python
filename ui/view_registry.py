"""
ViewRegistry — Registro centralizado de vistas.

SRP: Solo crea y almacena vistas.
OCP: Agregar una vista = agregar una línea en register_all().
DIP: Las vistas se inyectan en el Navigator, no se crean en app_layout.
"""
from __future__ import annotations

import flet as ft

from services.binance_service import binance_service
from repositories.order_repository import SQLOrderRepository


class ViewRegistry:
    """Almacena todas las vistas de la app. Se crea UNA vez tras login."""

    def __init__(self) -> None:
        self._views: dict[int, ft.Control] = {}
        self._settings_view: ft.Control | None = None

    def register_all(self) -> None:
        """Crea todas las vistas. Se llama una sola vez tras autenticarse."""
        if self._views:
            return

        from ui.views.dashboard_view import DashboardView
        from ui.views.orders_view import OrdersView
        from ui.views.config_view import ConfigView
        from ui.views.audit_view import AuditView
        from ui.views.settings_view import SettingsView
        from services.symbol_repository import BinanceSymbolRepository

        self._views = {
            0: DashboardView(),
            1: OrdersView(order_repository=SQLOrderRepository()),
            2: ConfigView(),
            3: AuditView(),
        }
        self._settings_view = SettingsView(
            symbol_repository=BinanceSymbolRepository(binance_service)
        )

    def get(self, index: int) -> ft.Control | None:
        """Obtiene una vista por índice. Index 4 = SettingsView."""
        if index == 4:
            return self._settings_view
        return self._views.get(index)

    @property
    def dashboard(self) -> ft.Control:
        return self._views[0]

    def clear(self) -> None:
        """Limpia el registro (para logout)."""
        self._views.clear()
        self._settings_view = None
