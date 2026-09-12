"""
BaseLayout — Interfaz abstracta para layouts del dashboard.

Aplica:
- OCP: Nuevos layouts extienden esta clase, no la modifican
- ISP: Interfaz mínima para construir layouts
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import flet as ft


class DashboardLayout(ABC):
    """Interfaz para estrategias de layout del dashboard."""

    @abstractmethod
    def build(self, components: dict[str, Any]) -> ft.Control:
        """Construye el layout con los componentes dados.

        Args:
            components: Diccionario con los componentes del dashboard.
                       Keys esperadas: header, price_section, stats,
                       balance, bot_status, bot_toggle, operations.

        Returns:
            ft.Control: Control de Flet con el layout ensamblado.
        """
        ...

    @abstractmethod
    def get_breakpoint(self) -> float:
        """Retorna el ancho mínimo (px) para usar layout horizontal."""
        ...
