"""
App Layout — Shell principal con NavigationBar y login.

Monta la app Flet con:
- Sistema de autenticación con login
- AnimatedSwitcher para transiciones de login
- Navegación directa (sin animación) entre vistas
- NavigationBar inferior con 4 tabs
- Tema oscuro premium con paleta azul-índigo

Refactorizado para aplicar SOLID:
- SRP: view_registry crea vistas, navigator maneja transiciones
- OCP: agregar vista = 1 línea en ViewRegistry.register_all()
- DIP: app_layout orquesta, no instancia widgets directamente
- DRY: _update_nav_bar() elimina repetición
"""
from __future__ import annotations

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
from ui.view_registry import ViewRegistry
from ui.navigator import Navigator


async def main(page: ft.Page) -> None:
    setup_logging()

    # ------------------------------------------------------------------
    # Configuración de página
    # ------------------------------------------------------------------
    page.title = settings.APP_TITLE
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0a0e1a"
    page.padding = 0
    page.window.width = 400
    page.window.height = 850
    page.window.min_width = 320
    page.window.min_height = 500

    page.theme = ft.Theme(
        color_scheme_seed=ft.Colors.BLUE,
        font_family="Roboto",
    )

    # ------------------------------------------------------------------
    # Configurar autenticación
    # ------------------------------------------------------------------
    auth_service.configure(settings.APP_USERNAME, settings.APP_PASSWORD)

    # ------------------------------------------------------------------
    # Barra de navegación
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
        on_change=lambda e: _on_nav_change(e.control.selected_index),
    )

    # ------------------------------------------------------------------
    # AnimatedSwitcher + ViewRegistry + Navigator
    # ------------------------------------------------------------------
    from ui.views.login_view import LoginView
    login_view = LoginView()

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

    animated_switcher = ft.AnimatedSwitcher(
        content=loading_view,
        duration=500,
        transition=ft.AnimatedSwitcherTransition.FADE,
        switch_in_curve=ft.AnimationCurve.EASE_IN_OUT,
        switch_out_curve=ft.AnimationCurve.EASE_IN_OUT,
        expand=True,
    )

    view_container = ft.Container(
        content=animated_switcher,
        expand=True,
        padding=ft.Padding(left=22, right=22, top=18, bottom=8),
    )

    view_registry = ViewRegistry()
    navigator = Navigator(animated_switcher)

    # ------------------------------------------------------------------
    # Funciones auxiliares (DRY)
    # ------------------------------------------------------------------
    def _update_nav_bar(visible: bool) -> None:
        """Actualiza visibilidad de la barra de navegación."""
        nav_bar.visible = visible
        nav_bar.update()

    # ------------------------------------------------------------------
    # Layout principal
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
                ft.Container(content=view_container, expand=True),
                nav_bar,
            ],
            spacing=0,
            expand=True,
        ),
    )

    # ------------------------------------------------------------------
    # Handlers de navegación
    # ------------------------------------------------------------------
    def _on_nav_change(index: int) -> None:
        if not auth_service.is_authenticated:
            return
        view = view_registry.get(index)
        if view:
            navigator.navigate_to(index, view)
            if index == 4:
                view.refresh_symbols()

    async def _on_navigate_to(e: NavigateToEvent) -> None:
        _on_nav_change(e.index)

    # ------------------------------------------------------------------
    # Manejo de autenticación
    # ------------------------------------------------------------------
    def _show_login() -> None:
        navigator.reset()
        _update_nav_bar(False)
        navigator.navigate_to(-1, login_view, animate=True)

    def _show_main_app() -> None:
        view_registry.register_all()
        _update_nav_bar(True)
        nav_bar.selected_index = 0
        navigator.navigate_to(0, view_registry.dashboard, animate=True)

    def _clear_overlay() -> None:
        """Limpia diálogos del overlay después de logout."""
        page.overlay.clear()
        page.update()

    async def _on_auth_changed(e: AuthStateChangedEvent) -> None:
        if e.is_authenticated:
            _show_main_app()
        else:
            _show_login()
            _clear_overlay()

    # ------------------------------------------------------------------
    # Estado inicial (antes de agregar a page)
    # ------------------------------------------------------------------
    if auth_service.is_authenticated:
        nav_bar.visible = False
    else:
        nav_bar.visible = False
        animated_switcher.content = login_view

    page.add(ft.SafeArea(expand=True, content=background))

    if auth_service.is_authenticated:
        _show_main_app()

    # ------------------------------------------------------------------
    # Resize handler
    # ------------------------------------------------------------------
    def on_resize(e: ft.ControlEvent) -> None:
        for idx in range(4):
            view = view_registry.get(idx)
            if view and hasattr(view, '_on_resize'):
                view._on_resize(page.window.width, page.window.height)

    page.on_resize = on_resize

    # ------------------------------------------------------------------
    # Inicialización de servicios
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
