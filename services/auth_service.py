"""
AuthService — Gestión de autenticación simple (un solo usuario).

Valida credenciales contra variables de entorno APP_USERNAME/APP_PASSWORD.
Publica AuthStateChangedEvent al cambiar estado de sesión.
"""
from __future__ import annotations

import logging

from core.event_bus import event_bus
from core.events import AuthStateChangedEvent, LogoutRequestedEvent

log = logging.getLogger(__name__)


class AuthService:
    """Servicio de autenticación singleton."""

    def __init__(self) -> None:
        self._is_authenticated: bool = False
        self._username: str = ""
        self._password: str = ""

    def configure(self, username: str, password: str) -> None:
        """Configura las credenciales desde settings."""
        self._username = username
        self._password = password

    @property
    def is_authenticated(self) -> bool:
        return self._is_authenticated

    def login(self, username: str, password: str) -> bool:
        """
        Valida credenciales y actualiza estado.
        Devuelve True si son correctas.
        """
        if not self._username or not self._password:
            log.warning("Credenciales no configuradas en .env")
            return False

        if username == self._username and password == self._password:
            self._is_authenticated = True
            log.info("Autenticación exitosa")
            event_bus.publish(AuthStateChangedEvent(is_authenticated=True))
            return True

        log.warning("Credenciales incorrectas")
        return False

    def logout(self) -> None:
        """Cierra sesión y publica evento."""
        self._is_authenticated = False
        log.info("Sesión cerrada")
        event_bus.publish(AuthStateChangedEvent(is_authenticated=False))
        event_bus.publish(LogoutRequestedEvent())

    def check_credentials_configured(self) -> bool:
        """Devuelve True si las credenciales están configuradas en .env."""
        return bool(self._username and self._password)


# Instancia singleton
auth_service = AuthService()
