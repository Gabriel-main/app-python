R"""
App Layout — Shell principal con NavigationBar.

Monta la app Flet con:
- Fondo oscuro con gradiente tipo cripto
- NavigationBar inferior con 3 tabs: Dashboard / Órdenes / Configuración
- Gestión del ciclo de vida de los servicios (start/stop)
- Tema oscuro premium con paleta azul-índigo

Regla: Inicia todos los servicios en on_connect (no en __init__).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import flet as ft

# Añadir la raíz del proyecto al path para imports absolutos
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings
from core.event_bus import event_bus
from core.events import NavigateToEvent
from core.logger import setup_logging
from database.connection import create_db_and_tables
from database.db_queue import db_queue
from services.binance_service import binance_service
from services.bot_engine import bot_engine
from services.config_service import config_service
from services.audit_service import audit_service
from services.paper_balance import paper_balance
from repositories.order_repository import SQLOrderRepository
from ui.views.dashboard_view import DashboardView
from ui.views.orders_view import OrdersView
from ui.views.settings_view import SettingsView
from ui.views.audit_view import AuditView


async def main(page: ft.Page) -> None:
    setup_logging()

    # ------------------------------------------------------------------
    # Configuración de página
    # ------------------------------------------------------------------
    page.title = settings.APP_TITLE
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0a0e1a"  # Azul oscuro profundo
    page.padding = 0
    page.window.width = 400
    page.window.height = 850
    page.window.min_width = 320
    page.window.min_height = 500

    # Tema premium
    page.theme = ft.Theme(
        color_scheme_seed=ft.Colors.BLUE,
        font_family="Roboto",
    )

    # ------------------------------------------------------------------
    # Vistas
    # ------------------------------------------------------------------
    dashboard = DashboardView()
    orders = OrdersView(order_repository=SQLOrderRepository())
    settings_view = SettingsView()
    audit_view = AuditView()

    views = [dashboard, orders, settings_view, audit_view]
    current_view_index = 0

    # Contenedor de vistas (padding lateral aquí para que scrollbar esté al borde)
    view_container = ft.Container(
        content=dashboard,
        expand=True,
        padding=ft.Padding(left=22, right=22, top=18, bottom=8),
    )

    # ------------------------------------------------------------------
    # Barra de navegación inferior
    # ------------------------------------------------------------------
    nav_bar = ft.NavigationBar(
        selected_index=0,
        bgcolor="#111827",
        indicator_color=ft.Colors.with_opacity(0.15, ft.Colors.BLUE_400),
        destinations=[
            ft.NavigationBarDestination(
                icon=ft.Icons.DASHBOARD_OUTLINED,
                selected_icon=ft.Icons.DASHBOARD,
                label="Dashboard",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.LIST_ALT_OUTLINED,
                selected_icon=ft.Icons.LIST_ALT,
                label="Órdenes",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.SETTINGS_OUTLINED,
                selected_icon=ft.Icons.SETTINGS,
                label="Config",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.BUG_REPORT_OUTLINED,
                selected_icon=ft.Icons.BUG_REPORT,
                label="Auditoría",
            ),
        ],
        on_change=lambda e: _navigate(e.control.selected_index),
    )

    def _navigate(index: int) -> None:
        nonlocal current_view_index
        if index == current_view_index:
            return
        current_view_index = index
        view_container.content = views[index]
        view_container.update()

        # Refresh symbols when navigating to Settings
        if index == 2:  # Settings tab
            settings_view.refresh_symbols()

    async def _on_navigate_to(e: NavigateToEvent) -> None:
        """Handler para eventos de navegación desde otros componentes."""
        _navigate(e.index)

    # ------------------------------------------------------------------
    # Layout principal con fondo gradiente
    # ------------------------------------------------------------------
    background = ft.Container(
        expand=True,
        gradient=ft.LinearGradient(
            begin=ft.Alignment(-1, -1),
            end=ft.Alignment(1, 1),
            colors=["#0a0e1a", "#0d1b2a", "#0a1628"],
        ),
        content=ft.Column(
            controls=[
                ft.Container(
                    content=view_container,
                    expand=True,
                ),
                nav_bar,
            ],
            spacing=0,
            expand=True,
        ),
    )

    page.add(
        ft.SafeArea(
            expand=True,
            content=background,
        )
    )

    # ------------------------------------------------------------------
    # Resize handler — propaga tamaño a vistas hijas
    # ------------------------------------------------------------------
    def on_resize(e: ft.ControlEvent) -> None:
        for view in views:
            if hasattr(view, '_on_resize'):
                view._on_resize(page.window.width, page.window.height)

    page.on_resize = on_resize

    # ------------------------------------------------------------------
    # Inicialización de servicios (en orden)
    # ------------------------------------------------------------------
    await create_db_and_tables()
    await config_service.init_from_env()  # Init DB con defaults de .env (primer inicio)
    await settings.load_from_db()         # Cargar config desde DB
    await event_bus.start()
    await db_queue.start()
    await audit_service.start()
    await paper_balance.start()
    await bot_engine.start()
    await binance_service.start()

    # Suscribir a eventos de navegación
    event_bus.subscribe(NavigateToEvent, _on_navigate_to)

    # ------------------------------------------------------------------
    # Limpieza al cerrar
    # ------------------------------------------------------------------
    async def on_disconnect(e: ft.ControlEvent) -> None:
        await binance_service.stop()
        await bot_engine.stop()
        await paper_balance.stop()
        await audit_service.stop()
        await db_queue.stop()
        await event_bus.stop()

    page.on_disconnect = on_disconnect
