"""
ApiKeyManager — Gestión segura de API keys en UI.

Responsabilidades:
- Enmascarar API keys para visualización
- Proveer estado de configuración (configurado/no configurado)
- Info text para guiar al usuario

Principios:
- SRP: Solo manejo de API keys en UI
- OCP: Nuevo comportamiento = nueva clase
- DIP: SettingsView depende de esta abstracción
- DRY: Lógica de enmascaramiento en un solo lugar
"""
from __future__ import annotations

import flet as ft

from config.settings import settings


class ApiKeyManager:
    """Gestiona la visualización segura de API keys en la UI."""

    # Longitud mínima para enmascarar (si es más corta, mostrar todo oculto)
    _MIN_MASK_LENGTH = 8

    @staticmethod
    def mask_key(key: str) -> str:
        """
        Enmascara la API key mostrando solo primeros y últimos 4 caracteres.

        Ejemplo: "abcdef1234567890" → "abcd...7890"
        """
        if not key or len(key) < ApiKeyManager._MIN_MASK_LENGTH:
            return "••••••••"
        return f"{key[:4]}...{key[-4:]}"

    @staticmethod
    def is_configured() -> bool:
        """Retorna True si las API keys están configuradas."""
        return settings.has_api_keys()

    @staticmethod
    def get_status_text() -> str:
        """Retorna texto de estado para mostrar en UI."""
        if ApiKeyManager.is_configured():
            return "API keys configuradas en .env"
        return "API keys no configuradas en .env"

    @staticmethod
    def get_info_text() -> ft.Text:
        """Retorna componente Text con información sobre API keys."""
        return ft.Text(
            "Las API keys se configuran en el archivo .env",
            size=11,
            color=ft.Colors.BLUE_GREY_400,
            italic=True,
        )
