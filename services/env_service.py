"""
EnvService — Persistencia de variables sensibles en .env.

Cumple SRP: solo maneja lectura/escritura de .env.
Cumple OCP: nuevo campo = agregar al dict, no modificar método.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class EnvService:
    """Servicio para leer/escribir variables sensibles en .env."""

    @staticmethod
    def _read_lines() -> list[str]:
        if _ENV_PATH.exists():
            return _ENV_PATH.read_text(encoding="utf-8").splitlines()
        return []

    @staticmethod
    def _write_lines(lines: list[str]) -> None:
        _ENV_PATH.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _set_var(lines: list[str], key: str, val: str) -> list[str]:
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={val}"
                return lines
        lines.append(f"{key}={val}")
        return lines

    @classmethod
    def save_sensitive(cls, api_key: str, api_secret: str) -> None:
        """Escribe SOLO API keys en .env."""
        lines = cls._read_lines()
        lines = cls._set_var(lines, "BINANCE_API_KEY", api_key)
        lines = cls._set_var(lines, "BINANCE_API_SECRET", api_secret)
        cls._write_lines(lines)

    @classmethod
    def rollback(cls, snapshot: dict[str, Any]) -> None:
        """Restaura .env a los valores del snapshot."""
        lines = cls._read_lines()
        for key, value in snapshot.items():
            lines = cls._set_var(lines, key, str(value))
        cls._write_lines(lines)
