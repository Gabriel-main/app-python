"""
Trading Bot — Settings & Configuración

Sensibles (BINANCE_API_KEY, etc.) → .env
Trading config (modo, tipo, etc.) → Base de Datos
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Carga el archivo .env desde la raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    # --- Sensibles (desde .env) ---
    BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")
    BINANCE_TESTNET: bool = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    # --- Base de Datos ---
    DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "trading_bot.db"))

    # --- App ---
    APP_TITLE: str = "CryptoBot"
    APP_THEME: str = "dark"
    PRICE_BUFFER_SIZE: int = 60
    RECONNECT_MAX_RETRIES: int = 10
    RECONNECT_BASE_DELAY: float = 2.0

    # --- Trading (se carga desde DB en load_from_db()) ---
    TRADING_SYMBOL: str = "BTCUSDT"
    TRADING_MODE: str = "PAPER"
    TRADING_TYPE: str = "SPOT"
    LEVERAGE: int = 1
    ORDER_TYPE: str = "MARKET"
    LIMIT_PRICE: float = 0.0
    TRADE_AMOUNT: float = 10.0
    TRADE_CURRENCY: str = "USDT"
    STOP_LOSS: float = 1.01
    STOP_LOSS_TYPE: str = "PERCENT"
    TIMEFRAME: int = 1
    TIMEFRAME_UNIT: str = "MINUTES"
    BOT_MA_FAST: int = 7
    BOT_MA_SLOW: int = 25
    BOT_QUANTITY: float = 0.001

    def has_api_keys(self) -> bool:
        """Devuelve True si las API Keys están configuradas."""
        return bool(self.BINANCE_API_KEY and self.BINANCE_API_SECRET)

    def reload_from_env(self) -> None:
        """Recarga SOLO variables sensibles desde .env."""
        load_dotenv(BASE_DIR / ".env", override=True)
        self.BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
        self.BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
        self.BINANCE_TESTNET = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    async def load_from_db(self) -> None:
        """Carga configuración de trading desde la base de datos."""
        from services.config_service import config_service
        config = await config_service.load()

        self.TRADING_SYMBOL = config.trading_symbol
        self.TRADING_MODE = config.trading_mode
        self.TRADING_TYPE = config.trading_type
        self.LEVERAGE = config.leverage
        self.ORDER_TYPE = config.order_type
        self.LIMIT_PRICE = config.limit_price
        self.TRADE_AMOUNT = config.trade_amount
        self.TRADE_CURRENCY = config.trade_currency
        self.STOP_LOSS = config.stop_loss
        self.STOP_LOSS_TYPE = config.stop_loss_type
        self.TIMEFRAME = config.timeframe
        self.TIMEFRAME_UNIT = config.timeframe_unit
        self.BOT_MA_FAST = config.bot_ma_fast
        self.BOT_MA_SLOW = config.bot_ma_slow
        self.BOT_QUANTITY = config.bot_quantity

    async def save_to_db(self) -> None:
        """Guarda la configuración actual de trading en la base de datos."""
        from services.config_service import config_service
        await config_service.update(
            trading_symbol=self.TRADING_SYMBOL,
            trading_mode=self.TRADING_MODE,
            trading_type=self.TRADING_TYPE,
            leverage=self.LEVERAGE,
            order_type=self.ORDER_TYPE,
            limit_price=self.LIMIT_PRICE,
            trade_amount=self.TRADE_AMOUNT,
            trade_currency=self.TRADE_CURRENCY,
            stop_loss=self.STOP_LOSS,
            stop_loss_type=self.STOP_LOSS_TYPE,
            timeframe=self.TIMEFRAME,
            timeframe_unit=self.TIMEFRAME_UNIT,
            bot_ma_fast=self.BOT_MA_FAST,
            bot_ma_slow=self.BOT_MA_SLOW,
            bot_quantity=self.BOT_QUANTITY,
        )


# Instancia global singleton
settings = Settings()
