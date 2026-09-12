"""
Layouts — Paquete de layouts responsivos para el dashboard.

Proporciona estrategias de layout extensibles (OCP) que separan
la estructura visual de la lógica de negocio.
"""
from ui.layouts.base_layout import DashboardLayout
from ui.layouts.responsive_layout import ResponsiveDashboardLayout

__all__ = ["DashboardLayout", "ResponsiveDashboardLayout"]
