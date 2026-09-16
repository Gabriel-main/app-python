"""
PnLCalculator — Cálculo centralizado de Profit & Loss.

Responsabilidades:
- Calcular porcentaje de SL: ((Pi - SL) / Pi) × 100
- Calcular PnL no realizado (para UI)
- Calcular PnL realizado (para balance)

Principios:
- SRP: Solo cálculos de PnL, nada más
- DRY: Fórmula en un solo lugar
- Funciones puras: Sin estado, sin efectos secundarios
"""
from __future__ import annotations


class PnLCalculator:
    """Calculadora de PnL con fórmula unificada."""

    @staticmethod
    def calc_sl_percentage(entry_price: float, stop_loss: float) -> float:
        """
        Calcula el porcentaje de distancia entre precio de entrada y SL.

        Fórmula: ((Pi - SL) / Pi) × 100

        Returns:
            Porcentaje (ej: 5.0 = 5%)
        """
        if entry_price <= 0 or stop_loss <= 0:
            return 0.0
        return ((entry_price - stop_loss) / entry_price) * 100

    @staticmethod
    def calc_unrealized_pnl(
        capital: float, entry_price: float, stop_loss: float, side: str
    ) -> float:
        """
        Calcula PnL no realizado (flotante) basado en SL actual.

        Retorna el monto ganado/perdido (ej: -5.0 o +5.0).
        """
        pct = PnLCalculator.calc_sl_percentage(entry_price, stop_loss)
        if side == "BUY":
            resultado = capital * (1 - pct / 100)
        else:
            resultado = capital * (1 + pct / 100)
        return resultado - capital

    @staticmethod
    def calc_closed_pnl(
        capital: float, entry_price: float, stop_loss: float, side: str
    ) -> tuple[float, float]:
        """
        Calcula PnL realizado al cerrar posición.

        Returns:
            (resultado, pnl): Monto final y ganancia/pérdida
        """
        pct = PnLCalculator.calc_sl_percentage(entry_price, stop_loss)
        if side == "BUY":
            resultado = capital * (1 - pct / 100)
        else:
            resultado = capital * (1 + pct / 100)
        return resultado, resultado - capital
