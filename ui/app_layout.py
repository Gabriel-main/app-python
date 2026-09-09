"""
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
from core.logger import setup_logging
from database.connection import create_db_and_tables
from database.db_queue import db_queue
from services.binance_service import binance_service
from services.bot_engine import bot_engine
from ui.views.dashboard_view import DashboardView
from ui.views.orders_view import OrdersView
from ui.views.settings_view import SettingsView


async def main(page: ft.Page) -> None:
    setup_logging()

    # ------------------------------------------------------------------
    # Configuración de página
    # ------------------------------------------------------------------
    page.title = settings.APP_TITLE
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0a0e1a"  # Azul oscuro profundo
    page.padding = ft.Padding(left=16, right=16, top=0, bottom=0)
    page.window.width = 400
    page.window.height = 850

    # Tema premium
    page.theme = ft.Theme(
        color_scheme_seed=ft.Colors.BLUE,
        font_family="Roboto",
    )

    # ------------------------------------------------------------------
    # Vistas
    # ------------------------------------------------------------------
    dashboard = DashboardView()
    orders = OrdersView()
    settings_view = SettingsView()

    views = [dashboard, orders, settings_view]
    current_view_index = 0

    # Contenedor de vistas
    view_container = ft.Container(
        content=dashboard,
        expand=True,
        padding=ft.Padding(left=0, right=0, top=16, bottom=8),
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
                view_container,
                nav_bar,
            ],
            spacing=0,
            expand=True,
        ),
    )

    page.add(background)

    # ------------------------------------------------------------------
    # Inicialización de servicios (en orden)
    # ------------------------------------------------------------------
    await create_db_and_tables()
    await event_bus.start()
    await db_queue.start()
    await bot_engine.start()
    await binance_service.start()

    # ------------------------------------------------------------------
    # Limpieza al cerrar
    # ------------------------------------------------------------------
    async def on_disconnect(e: ft.ControlEvent) -> None:
        await binance_service.stop()
        await bot_engine.stop()
        await db_queue.stop()
        await event_bus.stop()

    page.on_disconnect = on_disconnect
