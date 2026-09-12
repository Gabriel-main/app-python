"""
SettingsPersistence — Abstracción para persistencia de configuración.

Aplica DIP: SettingsView recibe esta interfaz en vez de llamar
EnvService directamente.
"""
from __future__ import annotations

from typing import Protocol


class SettingsPersistence(Protocol):
    """Interfaz para persistencia de settings sensibles."""

    def save_sensitive(self, api_key: str, api_secret: str) -> None: ...
    def rollback(self, snapshot: dict) -> None: ...


class EnvSettingsPersistence:
    """Implementación con .env files via EnvService."""

    def save_sensitive(self, api_key: str, api_secret: str) -> None:
        from services.env_service import EnvService
        EnvService.save_sensitive(api_key, api_secret)

    def rollback(self, snapshot: dict) -> None:
        from services.env_service import EnvService
        EnvService.rollback(snapshot)
