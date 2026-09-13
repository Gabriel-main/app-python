R"""
App Layout — Shell principal con NavigationBar.

Monta la app Flet con:
- Fondo oscuro con gradiente tipo cripto
- NavigationBar inferior con 3 tabs: Dashboard / Órdenes / Configuración
- Gestión del ciclo de vida de los servicios (start/stop)
- Tema oscuro premium con paleta azul-índigo
- Sistema de autenticación con login

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
from core.events import AuthStateChangedEvent, NavigateToEvent
from core.logger import setup_logging
from database.connection import create_db_and_tables
from database.db_queue import db_queue
from services.auth_service import auth_service
from services.binance_service import binance_service
from services.bot_engine import bot_engine
from services.config_service import config_service
from services.audit_service import audit_service
from services.paper_balance import paper_balance
from repositories.order_repository import SQLOrderRepository


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
    # Configurar servicio de autenticación
    # ------------------------------------------------------------------
    auth_service.configure(settings.APP_USERNAME, settings.APP_PASSWORD)

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

    # ------------------------------------------------------------------
    # Contenedor de vistas (placeholder temporal hasta cargar config)
    # ------------------------------------------------------------------
    loading_view = ft.Container(
        expand=True,
        alignment=ft.Alignment(0, 0),
        content=ft.Column(
            controls=[
                ft.ProgressRing(width=40, height=40, stroke_width=3, color=ft.Colors.CYAN_400),
                ft.Text("Cargando configuración...", size=14, color=ft.Colors.BLUE_GREY_400),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=16,
        ),
    )

    view_container = ft.Container(
        content=loading_view,
        expand=True,
        padding=ft.Padding(left=22, right=22, top=18, bottom=8),
    )

    views: list = []
    settings_view_ref = None  # Referencia para navegación index=4
    current_view_index = 0
    is_authenticated = False

    def _navigate(index: int) -> None:
        nonlocal current_view_index
        if not is_authenticated:
            return
        # index=4 es para SettingsView (accedido desde Config)
        if index == 4:
            if settings_view_ref:
                view_container.content = settings_view_ref
                view_container.update()
                current_view_index = 4
            return
        if index == current_view_index:
            return
        current_view_index = index
        if views:
            view_container.content = views[index]
            view_container.update()

            if index == 2:
                views[2].refresh_symbols()

    async def _on_navigate_to(e: NavigateToEvent) -> None:
        _navigate(e.index)

    # ------------------------------------------------------------------
    # Vista de Login
    # ------------------------------------------------------------------
    from ui.views.login_view import LoginView
    login_view = LoginView()

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

    # ------------------------------------------------------------------
    # Manejo de estado de autenticación
    # ------------------------------------------------------------------
    def _show_login() -> None:
        nonlocal is_authenticated
        is_authenticated = False
        nav_bar.visible = False
        view_container.content = login_view
        view_container.update()
        nav_bar.update()

    def _show_main_app() -> None:
        nonlocal is_authenticated, settings_view_ref
        is_authenticated = True
        nav_bar.visible = True
        nav_bar.selected_index = 0
        current_view_index = 0

        # Construir vistas DESPUÉS de autenticar
        from ui.views.dashboard_view import DashboardView
        from ui.views.orders_view import OrdersView
        from ui.views.settings_view import SettingsView
        from ui.views.config_view import ConfigView
        from ui.views.audit_view import AuditView
        from services.symbol_repository import BinanceSymbolRepository

        dashboard = DashboardView()
        orders = OrdersView(order_repository=SQLOrderRepository())
        settings_view_ref = SettingsView(
            symbol_repository=BinanceSymbolRepository(binance_service)
        )
        config_view = ConfigView()
        audit_view = AuditView()

        views.clear()
        views.extend([dashboard, orders, config_view, audit_view])

        view_container.content = dashboard
        view_container.update()
        nav_bar.update()

    async def _on_auth_changed(e: AuthStateChangedEvent) -> None:
        if e.is_authenticated:
            _show_main_app()
        else:
            _show_login()

    # ------------------------------------------------------------------
    # Mostrar login o app según estado
    # ------------------------------------------------------------------
    if auth_service.is_authenticated:
        nav_bar.visible = True
    else:
        nav_bar.visible = False
        view_container.content = login_view

    page.add(
        ft.SafeArea(
            expand=True,
            content=background,
        )
    )

    # After page is added, update if authenticated
    if auth_service.is_authenticated:
        _show_main_app()

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
    await config_service.init_from_env()
    await settings.load_from_db()

    await event_bus.start()
    await db_queue.start()
    await audit_service.start()
    await paper_balance.start()
    await bot_engine.start()
    await binance_service.start()

    event_bus.subscribe(NavigateToEvent, _on_navigate_to)
    event_bus.subscribe(AuthStateChangedEvent, _on_auth_changed)

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
