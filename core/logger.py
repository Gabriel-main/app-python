"""
Logger centralizado del proyecto Trading Bot.

Configura un logger estructurado con:
- Formato: timestamp | nivel | módulo | mensaje
- Nivel configurable por variable de entorno LOG_LEVEL (default: INFO)
- Handler de consola con colores (si el terminal lo soporta)
"""
import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Colores ANSI para el terminal
# ---------------------------------------------------------------------------
_COLORS = {
    "DEBUG":    "\033[36m",   # Cyan
    "INFO":     "\033[32m",   # Verde
    "WARNING":  "\033[33m",   # Amarillo
    "ERROR":    "\033[31m",   # Rojo
    "CRITICAL": "\033[35m",   # Magenta
    "RESET":    "\033[0m",
}


class ColorFormatter(logging.Formatter):
    """Formatter que añade colores ANSI al nivel de log."""

    FMT = "%(asctime)s  %(levelname)-8s  %(name)-30s  %(message)s"
    DATE_FMT = "%H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, _COLORS["RESET"])
        reset = _COLORS["RESET"]
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


def setup_logging() -> None:
    """Configura el sistema de logging global. Llamar una vez en main.py."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Evitar duplicar handlers si se llama varias veces
    if root_logger.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # Usar colores solo en terminales que los soporten
    use_color = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    if use_color:
        formatter: logging.Formatter = ColorFormatter(
            fmt=ColorFormatter.FMT, datefmt=ColorFormatter.DATE_FMT
        )
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s  %(levelname)-8s  %(name)-30s  %(message)s",
            datefmt="%H:%M:%S",
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Silenciar loggers muy verbosos de librerías externas
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("binance").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Devuelve un logger con el nombre dado. Usar en cada módulo."""
    return logging.getLogger(name)
