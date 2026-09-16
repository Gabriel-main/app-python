"""
UpdateBatcher — Agrupador centralizado de actualizaciones de UI.

Resuelve el problema de 15+ componentes haciendo update() individualmente
en cada tick de precio, causando ~12-15 renders por tick.

Patrón DRY:
  - mark_dirty(control): agrega un control pendiente de actualización
  - flush(): ejecuta update() de todos los pendientes en un solo batch
  - Se deduplican controles marcados múltiples veces
  - El try/except RuntimeError se centraliza aquí

Uso en componentes:
    from core.update_batcher import update_batcher

    async def _on_price_tick(self, event):
        self._price_text.value = f"${event.price:,.2f}"
        update_batcher.mark_dirty(self._price_text)
        # No necesita try/except — el batcher lo maneja

Reglas:
  - CERO POLLING: flush() se llama via call_soon() del event loop
  - ATÓMICO: un solo render por batch de marks
  - SEGURIDAD: try/except centralizado no rompe el bus
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)


class UpdateBatcher:
    """Agrupa actualizaciones de controles Flet en un solo render batch."""

    def __init__(self) -> None:
        self._pending: set[int] = set()  # ids de controles pendientes
        self._flush_scheduled: bool = False

    def mark_dirty(self, control: Any) -> None:
        """Marca un control para actualización en el próximo flush.
        
        Es síncrono y no bloqueante. Si el control ya está marcado,
        se deduplica automáticamente.
        """
        control_id = id(control)
        self._pending.add(control_id)
        # Guardar referencia fuerte para evitar GC
        if not hasattr(self, '_control_refs'):
            self._control_refs: dict[int, Any] = {}
        self._control_refs[control_id] = control

        if not self._flush_scheduled:
            self._flush_scheduled = True
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.call_soon(self._do_flush)
            except RuntimeError:
                pass

    def _do_flush(self) -> None:
        """Ejecuta update() de todos los controles pendientes."""
        if not self._pending:
            self._flush_scheduled = False
            return

        controls_to_update = []
        for ctrl_id in self._pending:
            ctrl = self._control_refs.pop(ctrl_id, None)
            if ctrl is not None:
                controls_to_update.append(ctrl)

        self._pending.clear()
        self._flush_scheduled = False

        for control in controls_to_update:
            try:
                control.update()
            except RuntimeError:
                # Control desmontado — ignorar silenciosamente
                pass
            except Exception as exc:
                log.warning("UpdateBatcher: error updating %s: %s", type(control).__name__, exc)

    def flush_sync(self) -> None:
        """Flush síncrono forzado (para casos donde no hay event loop)."""
        self._do_flush()

    @property
    def pending_count(self) -> int:
        """Número de controles pendientes de actualización."""
        return len(self._pending)


# Instancia global singleton
update_batcher = UpdateBatcher()
