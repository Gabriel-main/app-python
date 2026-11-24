"""
Help View — Guía y Ayuda del Bot.

Explica el funcionamiento del Stop Loss, la velocidad de ejecución
según el valor configurado (ej. 0.1 vs 5.0), la diferencia entre
porcentaje (%) y USDT fijo, y la estrategia dual con trailing stop.
"""
from __future__ import annotations

import flet as ft

from core.event_bus import event_bus
from core.events import NavigateToEvent
from ui.components.view_header import ViewHeader

_CARD_BG = ft.Colors.BLUE_GREY_900
_CARD_WIDTH = 380
_CARD_RADIUS = 14


class HelpView(ft.Column):
    """Vista de ayuda y documentación interactiva del bot."""

    def __init__(self) -> None:
        super().__init__()

        self._back_btn = ft.IconButton(
            icon=ft.Icons.ARROW_BACK_IOS,
            icon_color=ft.Colors.BLUE_400,
            icon_size=20,
            on_click=self._on_back,
            tooltip="Volver a Configuración",
        )

        self.controls = [
            ViewHeader(
                "Guía y Ayuda",
                leading=self._back_btn,
                divider_width=_CARD_WIDTH,
                divider_height=20,
                spacing=16,
            ),
            self._build_speed_card(),
            self._build_type_card(),
            self._build_strategy_card(),
            self._build_trailing_card(),
            self._build_pnl_card(),
            self._build_tips_card(),
            ft.Container(height=24),
        ]

        self.spacing = 12
        self.expand = True
        self.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        self.scroll = ft.ScrollMode.AUTO

    def _on_back(self, e: ft.ControlEvent) -> None:
        """Regresa a la pantalla de Configuración."""
        event_bus.publish(NavigateToEvent(index=2))

    # ------------------------------------------------------------------
    # Tarjeta 1: Velocidad y Tiempos de Ejecución (0.1 vs 5.0)
    # ------------------------------------------------------------------
    def _build_speed_card(self) -> ft.Container:
        return self._make_card(
            title="⏱️ ¿Cómo afecta el valor a la velocidad?",
            accent_color=ft.Colors.AMBER_400,
            content=[
                ft.Text(
                    "El valor de Stop Loss determina directamente qué tan rápido "
                    "se ejecutan y rotan las operaciones del bot:",
                    size=12,
                    color=ft.Colors.BLUE_GREY_200,
                ),
                self._make_highlight_box(
                    title="⚡ Stop Loss Bajo (ej. 0.1% o 0.1 USDT)",
                    color=ft.Colors.CYAN_400,
                    body=(
                        "• La distancia al precio de entrada es muy pequeña.\n"
                        "• El ruido y la volatilidad normal del mercado tocan el "
                        "Stop Loss en segundos o pocos minutos.\n"
                        "• Resultado: Ejecución ultra-rápida (scalping de alta frecuencia). "
                        "Cierra y abre operaciones continuamente."
                    ),
                ),
                self._make_highlight_box(
                    title="⏳ Stop Loss Alto (ej. 2.0% a 5.0% o 5 USDT)",
                    color=ft.Colors.PURPLE_300,
                    body=(
                        "• La distancia al precio es mucho más amplia.\n"
                        "• El mercado necesita un movimiento grande para alcanzar el SL.\n"
                        "• Resultado: Las operaciones tardan mucho más tiempo en salir "
                        "(minutos u horas), dando margen para que se desarrolle una tendencia."
                    ),
                ),
            ],
        )

    # ------------------------------------------------------------------
    # Tarjeta 2: Tipo de Stop Loss (% vs USDT)
    # ------------------------------------------------------------------
    def _build_type_card(self) -> ft.Container:
        return self._make_card(
            title="📊 Tipo de SL: Porcentaje (%) vs USDT",
            accent_color=ft.Colors.CYAN_400,
            content=[
                ft.Text(
                    "Puedes definir el Stop Loss de dos formas según tu preferencia:",
                    size=12,
                    color=ft.Colors.BLUE_GREY_200,
                ),
                self._make_bullet(
                    "Porcentaje (%)",
                    "Se calcula sobre el precio actual del activo:\n"
                    "Distancia = Precio × (SL / 100)\n"
                    "Ejemplo en SOL ($70.00):\n"
                    "• Con 0.1% el SL está a solo $0.07 de distancia.\n"
                    "• Con 1.0% el SL está a $0.70 de distancia.\n"
                    "• Con 5.0% el SL está a $3.50 de distancia.\n"
                    "Ideal para adaptarse automáticamente al precio de cualquier moneda.",
                ),
                self._make_bullet(
                    "USDT Fijo",
                    "Distancia exacta en dólares sin importar el precio:\n"
                    "Ejemplo en SOL ($70.00):\n"
                    "• Con 0.1 USDT el SL está exactamente a $0.10 ($69.90 / $70.10).\n"
                    "• Con 1.0 USDT el SL está a $1.00 de distancia ($69.00 / $71.00).\n"
                    "• Con 5.0 USDT el SL está a $5.00 de distancia ($65.00 / $75.00).\n"
                    "Ideal para un control exacto y numérico en dólares.",
                ),
            ],
        )

    # ------------------------------------------------------------------
    # Tarjeta 3: Estrategia Dual y Rotación
    # ------------------------------------------------------------------
    def _build_strategy_card(self) -> ft.Container:
        return self._make_card(
            title="🔄 Estrategia Dual del Bot",
            accent_color=ft.Colors.GREEN_400,
            content=[
                ft.Text(
                    "El bot mantiene simultáneamente dos operaciones vinculadas:",
                    size=12,
                    color=ft.Colors.BLUE_GREY_200,
                ),
                ft.Text(
                    "1. Operación ACTIVA: La posición abierta en el mercado (COMPRA o VENTA).\n"
                    "2. Operación PENDING: Una orden preparada en la dirección contraria.\n\n"
                    "Cuando el precio toca el Stop Loss de la operación ACTIVA:\n"
                    "• Se ejecuta una orden MARKET opuesta [ CIERRE SL ] para liquidar la posición y registrar el PnL.\n"
                    "• La operación PENDING se promueve inmediatamente a ACTIVA [ ENTRADA ].\n"
                    "• Se genera una nueva orden PENDING contraria.",
                    size=11,
                    color=ft.Colors.BLUE_GREY_300,
                ),
            ],
        )

    # ------------------------------------------------------------------
    # Tarjeta 4: Trailing Stop
    # ------------------------------------------------------------------
    def _build_trailing_card(self) -> ft.Container:
        return self._make_card(
            title="📈 Trailing Stop (Seguimiento Dinámico)",
            accent_color=ft.Colors.LIGHT_BLUE_400,
            content=[
                ft.Text(
                    "El bot ajusta el Stop Loss automáticamente a tu favor:",
                    size=12,
                    color=ft.Colors.BLUE_GREY_200,
                ),
                ft.Text(
                    "• En COMPRA: Si el precio sube, el Stop Loss sube detrás del precio para proteger ganancias.\n"
                    "• En VENTA: Si el precio baja, el Stop Loss baja para asegurar la ganancia.\n"
                    "• El Stop Loss NUNCA retrocede en tu contra; solo avanza cuando hay ganancia.",
                    size=11,
                    color=ft.Colors.BLUE_GREY_300,
                ),
            ],
        )

    # ------------------------------------------------------------------
    # Tarjeta 5: PnL y Cálculo de Rendimiento
    # ------------------------------------------------------------------
    def _build_pnl_card(self) -> ft.Container:
        return self._make_card(
            title="💰 Cálculo de Ganancia y Pérdida (PnL)",
            accent_color=ft.Colors.ORANGE_400,
            content=[
                ft.Text(
                    "Fórmula aplicada al cerrar la posición:",
                    size=12,
                    color=ft.Colors.BLUE_GREY_200,
                ),
                ft.Container(
                    content=ft.Text(
                        "% Variación = ((Precio Entrada - Precio SL) / Precio Entrada) × 100",
                        size=11,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.CYAN_300,
                    ),
                    bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.CYAN_400),
                    border_radius=8,
                    padding=ft.Padding(10, 8, 10, 8),
                ),
                ft.Text(
                    "• En COMPRA: Se resta o suma la variación proporcional al capital invertido.\n"
                    "• En VENTA: Se invierte el sentido para premiar caídas de precio.\n"
                    "• El resultado exacto se muestra en el historial de Órdenes como [ CIERRE SL ].",
                    size=11,
                    color=ft.Colors.BLUE_GREY_300,
                ),
            ],
        )

    # ------------------------------------------------------------------
    # Tarjeta 6: Consejos y Recomendaciones
    # ------------------------------------------------------------------
    def _build_tips_card(self) -> ft.Container:
        return self._make_card(
            title="💡 Consejos de Configuración",
            accent_color=ft.Colors.YELLOW_400,
            content=[
                ft.Text(
                    "• Para pruebas rápidas: Configura 0.1% a 0.3% o 0.1 a 0.2 USDT para ver al bot alternar operaciones con agilidad.\n"
                    "• Para operar con tendencia: Configura entre 1.0% y 3.0% para evitar que el ruido del mercado cierre la posición antes de tiempo.\n"
                    "• Modo Paper: Te permite probar distintas combinaciones de Stop Loss con dinero simulado antes de pasar a modo Live.",
                    size=11,
                    color=ft.Colors.BLUE_GREY_300,
                ),
            ],
        )

    # ------------------------------------------------------------------
    # Helpers de componentes
    # ------------------------------------------------------------------
    @staticmethod
    def _make_card(
        title: str,
        accent_color: ft.Color,
        content: list[ft.Control],
    ) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(title, size=14, weight=ft.FontWeight.W_600, color=accent_color),
                    *content,
                ],
                spacing=8,
            ),
            bgcolor=_CARD_BG,
            border_radius=_CARD_RADIUS,
            padding=ft.Padding.all(16),
            width=_CARD_WIDTH,
        )

    @staticmethod
    def _make_highlight_box(
        title: str,
        color: ft.Color,
        body: str,
    ) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(title, size=12, weight=ft.FontWeight.BOLD, color=color),
                    ft.Text(body, size=11, color=ft.Colors.BLUE_GREY_300),
                ],
                spacing=4,
            ),
            bgcolor=ft.Colors.with_opacity(0.10, color),
            border=ft.Border.all(0.8, ft.Colors.with_opacity(0.3, color)),
            border_radius=8,
            padding=ft.Padding(12, 10, 12, 10),
        )

    @staticmethod
    def _make_bullet(title: str, text: str) -> ft.Column:
        return ft.Column(
            controls=[
                ft.Text(f"• {title}", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                ft.Text(text, size=11, color=ft.Colors.BLUE_GREY_300),
            ],
            spacing=2,
        )

