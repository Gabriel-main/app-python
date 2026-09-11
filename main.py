"""
Main — Punto de entrada de la aplicación Trading Bot.

Inicializa el sistema de logging y lanza la app Flet.
"""
import sys
from pathlib import Path

# Asegurar que el directorio del proyecto esté en el path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import flet as ft
from ui.app_layout import main

if __name__ == "__main__":
    ft.run(main, host="0.0.0.0", port=8551)
