"""
Config View — Pantalla general de configuración.

Muestra opciones de configuración de la app (no del bot).
Incluye acceso a Ajustes del Bot y botón de cerrar sesión.
"""
from __future__ import annotations

import flet as ft

from core.event_bus import event_bus
from core.events import NavigateToEvent
from services.auth_service import auth_service


class ConfigView(ft.Column):
    """Vista general de configuración de la app."""

    def __init__(self) -> None:
        super().__init__()
        self._page: ft.Page | None = None

        self._logout_btn = ft.FilledButton(
            content="Cerrar Sesión",
            icon=ft.Icons.LOGOUT,
            on_click=self._on_logout,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.RED_800,
                color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.Padding(left=24, right=24, top=14, bottom=14),
            ),
            width=300,
            height=48,
        )

        self.controls = [
            ft.Text(
                "Configuración",
                size=22,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.WHITE,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Container(
                width=380,
                content=ft.Divider(
                    color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
                    height=20,
                ),
            ),
            ft.Container(height=10),
            self._build_menu_item(
                icon=ft.Icons.TUNE,
                title="Ajustes del Bot",
                subtitle="Configurar parámetros de trading",
                on_click=self._on_open_settings,
            ),
            ft.Container(height=20),
            ft.Divider(color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)),
            ft.Container(height=20),
            self._logout_btn,
        ]

        self.spacing = 8
        self.expand = True
        self.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        self.scroll = ft.ScrollMode.AUTO

    def _build_menu_item(
        self,
        icon: ft.Icons,
        title: str,
        subtitle: str,
        on_click,
    ) -> ft.Container:
        """Construye un elemento de menú estilo card."""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(
                            icon,
                            size=24,
                            color=ft.Colors.BLUE_400,
                        ),
                        padding=ft.Padding(12, 12, 12, 12),
                        bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.BLUE_400),
                        border_radius=12,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(
                                title,
                                size=15,
                                weight=ft.FontWeight.W_500,
                                color=ft.Colors.WHITE,
                            ),
                            ft.Text(
                                subtitle,
                                size=12,
                                color=ft.Colors.BLUE_GREY_400,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Icon(
                        ft.Icons.CHEVRON_RIGHT,
                        size=20,
                        color=ft.Colors.BLUE_GREY_600,
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=380,
            padding=ft.Padding(left=16, right=16, top=12, bottom=12),
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
            border_radius=12,
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
            ),
            on_click=on_click,
            ink=True,
        )

    def _on_open_settings(self, e: ft.ControlEvent) -> None:
        """Navega a la vista de Ajustes del Bot."""
        event_bus.publish(NavigateToEvent(index=4))

    def _on_logout(self, e: ft.ControlEvent) -> None:
        """Cierra sesión y vuelve al login."""
        self._show_logout_dialog()

    def _show_logout_dialog(self) -> None:
        """Muestra diálogo de confirmación para cerrar sesión."""
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Cerrar Sesión", color=ft.Colors.WHITE, size=15),
            bgcolor=ft.Colors.BLUE_GREY_900,
            content=ft.Text(
                "¿Estás seguro que deseas cerrar sesión?",
                color=ft.Colors.BLUE_GREY_300,
            ),
            actions=[
                ft.TextButton(
                    "Cancelar",
                    on_click=lambda e: self._close_dialog(dialog),
                ),
                ft.FilledButton(
                    "Cerrar Sesión",
                    on_click=lambda e: self._confirm_logout(dialog),
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.RED_700,
                        color=ft.Colors.WHITE,
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        if self._page:
            self._page.overlay.append(dialog)
            self._page.update()
            dialog.open = True
            dialog.update()

    def _confirm_logout(self, dialog: ft.AlertDialog) -> None:
        """Confirma el cierre de sesión."""
        self._close_dialog(dialog)
        auth_service.logout()

    def _close_dialog(self, dialog: ft.AlertDialog) -> None:
        """Cierra el diálogo."""
        if dialog:
            dialog.open = False
            dialog.update()
            if self._page and dialog in self._page.overlay:
                self._page.overlay.remove(dialog)
                self._page.update()

    def did_mount(self) -> None:
        self._page = self.page

    def will_unmount(self) -> None:
        self._page = None
