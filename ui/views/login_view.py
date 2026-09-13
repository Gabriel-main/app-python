"""
Login View — Pantalla de autenticación del usuario.

Muestra formulario de login con usuario y clave.
Valida contra credenciales de .env vía auth_service.
"""
from __future__ import annotations

import flet as ft

from services.auth_service import auth_service


class LoginView(ft.Column):
    """Pantalla de login con usuario y contraseña."""

    def __init__(self) -> None:
        super().__init__()

        self._error_text = ft.Text(
            "",
            size=12,
            color=ft.Colors.RED_400,
            text_align=ft.TextAlign.CENTER,
        )

        self._username_field = ft.TextField(
            label="Usuario",
            hint_text="Ingresa tu usuario",
            prefix_icon=ft.Icons.PERSON_OUTLINE,
            border_radius=12,
            border_color=ft.Colors.with_opacity(0.3, ft.Colors.WHITE),
            focused_border_color=ft.Colors.BLUE_400,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_300),
            text_style=ft.TextStyle(color=ft.Colors.WHITE),
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
            width=300,
            height=55,
            text_size=14,
            content_padding=ft.Padding(left=16, right=16, top=0, bottom=0),
        )

        self._password_field = ft.TextField(
            label="Contraseña",
            hint_text="Ingresa tu contraseña",
            prefix_icon=ft.Icons.LOCK_OUTLINE,
            password=True,
            can_reveal_password=True,
            border_radius=12,
            border_color=ft.Colors.with_opacity(0.3, ft.Colors.WHITE),
            focused_border_color=ft.Colors.BLUE_400,
            label_style=ft.TextStyle(color=ft.Colors.BLUE_GREY_300),
            text_style=ft.TextStyle(color=ft.Colors.WHITE),
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
            width=300,
            height=55,
            text_size=14,
            content_padding=ft.Padding(left=16, right=16, top=0, bottom=0),
        )

        self._login_btn = ft.FilledButton(
            content="Iniciar Sesión",
            icon=ft.Icons.LOGIN,
            on_click=self._on_login,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_700,
                color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.Padding(left=24, right=24, top=14, bottom=14),
            ),
            width=300,
            height=48,
        )

        self._loading_indicator = ft.ProgressRing(
            width=24,
            height=24,
            stroke_width=3,
            visible=False,
            color=ft.Colors.WHITE,
        )

        self.controls = [
            ft.Container(expand=True),
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(
                            ft.Icons.SHIELD_OUTLINED,
                            size=64,
                            color=ft.Colors.BLUE_400,
                        ),
                        ft.Text(
                            "CryptoBot",
                            size=28,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE,
                        ),
                        ft.Text(
                            "Trading Bot de Binance",
                            size=13,
                            color=ft.Colors.BLUE_GREY_400,
                        ),
                        ft.Container(height=30),
                        self._username_field,
                        ft.Container(height=8),
                        self._password_field,
                        ft.Container(height=8),
                        self._error_text,
                        ft.Container(height=12),
                        self._login_btn,
                        ft.Container(
                            content=self._loading_indicator,
                            alignment=ft.Alignment(0, 0),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=0,
                ),
                alignment=ft.Alignment(0, 0),
            ),
            ft.Container(expand=True),
        ]

        self.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        self.expand = True

    def _on_login(self, e: ft.ControlEvent) -> None:
        """Maneja el intento de login."""
        username = self._username_field.value or ""
        password = self._password_field.value or ""

        if not username or not password:
            self._show_error("Ingresa usuario y contraseña")
            return

        self._loading_indicator.visible = True
        self._login_btn.disabled = True
        self._error_text.value = ""
        self.update()

        success = auth_service.login(username, password)

        self._loading_indicator.visible = False
        self._login_btn.disabled = False

        if not success:
            self._show_error("Credenciales incorrectas")
        else:
            self._username_field.value = ""
            self._password_field.value = ""
            self.update()

    def _show_error(self, message: str) -> None:
        """Muestra mensaje de error."""
        self._error_text.value = f"  {message}"
        self._error_text.color = ft.Colors.RED_400
        self.update()

    def clear_fields(self) -> None:
        """Limpia los campos del formulario."""
        self._username_field.value = ""
        self._password_field.value = ""
        self._error_text.value = ""
        self.update()
