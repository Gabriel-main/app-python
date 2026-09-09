"""
Trading Bot — Settings & Configuración
Carga variables de entorno desde .env con python-dotenv.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Carga el archivo .env desde la raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    # --- Binance API ---
    BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")
    BINANCE_TESTNET: bool = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    # --- Trading ---
    TRADING_SYMBOL: str = os.getenv("TRADING_SYMBOL", "BTCUSDT")
    TRADING_MODE: str = os.getenv("TRADING_MODE", "PAPER")  # "PAPER" | "LIVE"

    # --- Estrategia Bot: MA Crossover ---
    BOT_MA_FAST: int = int(os.getenv("BOT_MA_FAST", "7"))
    BOT_MA_SLOW: int = int(os.getenv("BOT_MA_SLOW", "25"))
    BOT_QUANTITY: float = float(os.getenv("BOT_QUANTITY", "0.001"))  # BTC por orden

    # --- Base de Datos ---
    DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "trading_bot.db"))

    # --- App ---
    APP_TITLE: str = "CryptoBot"
    APP_THEME: str = "dark"
    PRICE_BUFFER_SIZE: int = 60   # ticks en memoria para el mini-chart
    RECONNECT_MAX_RETRIES: int = 10
    RECONNECT_BASE_DELAY: float = 2.0  # segundos, backoff exponencial

    def has_api_keys(self) -> bool:
        """Devuelve True si las API Keys están configuradas."""
        return bool(self.BINANCE_API_KEY and self.BINANCE_API_SECRET)

    def reload_from_env(self) -> None:
        """Recarga la configuración desde el entorno (útil después de guardar desde UI)."""
        load_dotenv(BASE_DIR / ".env", override=True)
        self.BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
        self.BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
        self.TRADING_SYMBOL = os.getenv("TRADING_SYMBOL", "BTCUSDT")
        self.TRADING_MODE = os.getenv("TRADING_MODE", "PAPER")
        self.BOT_MA_FAST = int(os.getenv("BOT_MA_FAST", "7"))
        self.BOT_MA_SLOW = int(os.getenv("BOT_MA_SLOW", "25"))
        self.BOT_QUANTITY = float(os.getenv("BOT_QUANTITY", "0.001"))


# Instancia global singleton
settings = Settings()
