"""
SoundManager — Gestor de sonido multiplataforma y no intrusivo.

Reproduce sonidos de notificación para órdenes ejecutadas y errores
usando los reproductores de audio del sistema operativo (Linux, macOS, Windows).

Ventajas:
- CERO errores de Flutter: No inyecta controles desconocidos ('Unknown control: Audio')
  en el árbol de widgets de Flet.
- CERO polling y no bloqueante: Ejecuta la reproducción en tareas asyncio independientes.
- Multiplataforma:
  * Linux: pw-play (PipeWire), aplay (ALSA), paplay (PulseAudio), canberra-gtk-play
  * macOS: afplay
  * Windows: winsound (librería estándar de Python)
  * Fallback seguro: Si no hay dispositivo de audio, falla en silencio sin romper la UI.
"""
from __future__ import annotations

import asyncio
import logging
import platform
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import flet as ft

log = logging.getLogger(__name__)

# Directorio de sonidos en assets/sounds/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SOUNDS_DIR = _PROJECT_ROOT / "assets" / "sounds"
_SUCCESS_SOUND = _SOUNDS_DIR / "order_success.wav"
_ERROR_SOUND = _SOUNDS_DIR / "order_error.wav"


class SoundManager:
    """Gestiona la reproducción de sonidos de notificación sin interferir con Flutter."""

    def __init__(self) -> None:
        self._enabled: bool = True
        self._player: str | None = self._detect_system_player()
        self._system: str = platform.system().lower()
        self._play_task: asyncio.Task | None = None

    def _detect_system_player(self) -> str | None:
        """Detecta el comando CLI de reproducción disponible en el sistema."""
        system = platform.system().lower()
        if system == "linux":
            for cmd in ("pw-play", "aplay", "paplay", "canberra-gtk-play"):
                path = shutil.which(cmd)
                if path:
                    log.info("SoundManager: reproductor detectado -> %s", path)
                    return path
        elif system == "darwin":
            return shutil.which("afplay")
        return None

    def mount(self, page: ft.Page | None = None) -> None:
        """Punto de montaje para compatibilidad de ciclo de vida con app_layout.
        
        No agrega controles a page.overlay para evitar el error 'Unknown control: Audio'
        en clientes de Flet que no compilan el plugin C++ de audio.
        """
        log.debug("SoundManager: inicializado (player: %s)", self._player)

    def remount(self, page: ft.Page | None = None) -> None:
        """Punto de re-montaje tras overlay.clear() en logout."""
        pass

    def play_success(self) -> None:
        """Dispara sonido de orden ejecutada en una tarea asíncrona no bloqueante."""
        if not self._enabled:
            return
        self._trigger_play(_SUCCESS_SOUND, "sound_success")

    def play_error(self) -> None:
        """Dispara sonido de error en una tarea asíncrona no bloqueante."""
        if not self._enabled:
            return
        self._trigger_play(_ERROR_SOUND, "sound_error")

    def _trigger_play(self, file_path: Path, task_name: str) -> None:
        """Cancela la reproducción anterior si sigue viva y lanza la nueva."""
        if self._play_task and not self._play_task.done():
            self._play_task.cancel()
        try:
            self._play_task = asyncio.create_task(
                self._play_file(file_path), name=task_name
            )
        except RuntimeError:
            # Sin event loop activo (ej. durante ciertas llamadas sincrónicas)
            pass

    async def _play_file(self, file_path: Path) -> None:
        """Reproduce un archivo WAV usando el reproductor nativo del SO."""
        if not file_path.exists():
            log.debug("SoundManager: archivo no encontrado: %s", file_path)
            return

        try:
            if self._system == "windows":
                import winsound
                winsound.PlaySound(
                    str(file_path),
                    winsound.SND_FILENAME | winsound.SND_ASYNC,
                )
                return

            if self._player:
                args = [self._player, str(file_path)]
                if "aplay" in self._player:
                    args = [self._player, "-q", str(file_path)]
                elif "canberra-gtk-play" in self._player:
                    args = [self._player, "-f", str(file_path)]

                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                try:
                    await asyncio.wait_for(proc.wait(), timeout=1.5)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.debug("SoundManager: fallo en reproducción: %s", exc)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def is_mounted(self) -> bool:
        return True


# Instancia singleton global
sound_manager = SoundManager()
