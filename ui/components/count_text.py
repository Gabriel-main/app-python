"""
CountText — Contador pluralizado con repaint atómico.

Elimina la triplicación del patrón "f-string de plural + mark_dirty" que
vivía en OrdersView, AuditView y PositionsPanel (el tercero no hacía el
mark_dirty y su contador quedaba congelado).

Principios aplicados:
- SRP: Solo cuenta y se repinta. No sabe cómo filtra ni qué cuenta el dueño.
- OCP: Nuevas unidades = nuevos pares (singular, plural).
- DRY: El plural y el update_batcher viven en UN solo lugar.
- REACTIVIDAD: set_count() se pinta con update_batcher (control.update()).
  Si el número no cambió, no hay render — evita repintar en cada tick.
"""
from __future__ import annotations

import flet as ft

from core.update_batcher import update_batcher

_DEFAULT_SIZE = 11
_DEFAULT_COLOR = ft.Colors.BLUE_GREY_400


class CountText(ft.Text):
    """Etiqueta de conteo "N unidad(es)" con repaint automático.

    Args:
        singular: Forma para count == 1 (ej. "orden").
        plural: Forma para count != 1 (ej. "órdenes").
        count: Valor inicial (0 por defecto → usa la forma plural).
        size: Tamaño de fuente (11, igual que los contadores previos).
        color: Color de fuente.
    """

    def __init__(
        self,
        singular: str,
        plural: str,
        *,
        count: int = 0,
        size: int = _DEFAULT_SIZE,
        color: ft.Colors = _DEFAULT_COLOR,
    ) -> None:
        super().__init__(self._format(count, singular, plural), size=size, color=color)
        self._singular = singular
        self._plural = plural
        self._count = count

    @staticmethod
    def _format(count: int, singular: str, plural: str) -> str:
        return f"{count} {singular if count == 1 else plural}"

    @property
    def count(self) -> int:
        """Último conteo aplicado."""
        return self._count

    def set_count(self, count: int) -> None:
        """Actualiza el conteo y repinta solo si cambió."""
        if count == self._count:
            return
        self._count = count
        self.value = self._format(count, self._singular, self._plural)
        update_batcher.mark_dirty(self)
