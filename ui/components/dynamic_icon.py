"""
DynamicIcon — ft.Icon cuyo glifo se cambia correctamente en runtime.

Flet 0.86.5: `ft.Icon` NO tiene campo `name` (el campo es `icon`).
Asignar `.name` crea un atributo huérfano que nunca se serializa al
cliente → el glifo queda congelado en el valor inicial.

SRP: un solo lugar sabe cómo mutar un icono en runtime.
DRY: lo usan ConnectionIndicator, BotStatusBar, NotificationToast y
SymbolValidationIndicator (antes cada uno repetía el bug `._icon.name`).
"""
from __future__ import annotations

import flet as ft

from core.update_batcher import update_batcher


class DynamicIcon(ft.Icon):
    """ft.Icon con cambio de glifo/color vía update_batcher (atómico)."""

    def set_icon(self, icon: ft.Icons, color: ft.Color | None = None) -> None:
        """Cambia el glifo (y opcionalmente el color) y marca dirty.

        Usa el campo `icon` — el único que Flet serializa. El batcher
        deduplica marks, así que marcar a sí mismo no cuesta un render extra.
        """
        self.icon = icon
        if color is not None:
            self.color = color
        update_batcher.mark_dirty(self)
