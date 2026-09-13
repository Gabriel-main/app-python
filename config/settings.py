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
    # --- Autenticación (desde .env) ---
    APP_USERNAME: str = os.getenv("APP_USERNAME", "")
    APP_PASSWORD: str = os.getenv("APP_PASSWORD", "")

    # --- Sensibles (desde .env) ---
    BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")
    BINANCE_TESTNET: bool = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

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

    # --- Mapping de campos de trading (DRY) ---
    _TRADING_FIELDS: list[str] = [
        "TRADING_SYMBOL", "TRADING_MODE", "TRADING_TYPE", "LEVERAGE",
        "ORDER_TYPE", "LIMIT_PRICE", "TRADE_AMOUNT", "TRADE_CURRENCY",
        "STOP_LOSS", "STOP_LOSS_TYPE", "TIMEFRAME", "TIMEFRAME_UNIT",
        "BOT_MA_FAST", "BOT_MA_SLOW", "BOT_QUANTITY",
    ]

    # --- Mapping: Settings attr → SettingsUpdatedEvent field ---
    _EVENT_FIELD_MAP: dict[str, str] = {
        "TRADING_SYMBOL": "symbol",
        "TRADING_MODE": "mode",
        "TRADING_TYPE": "trading_type",
        "LEVERAGE": "leverage",
        "ORDER_TYPE": "order_type",
        "LIMIT_PRICE": "limit_price",
        "TRADE_AMOUNT": "trade_amount",
        "TRADE_CURRENCY": "trade_currency",
        "STOP_LOSS": "stop_loss",
        "STOP_LOSS_TYPE": "stop_loss_type",
        "TIMEFRAME": "timeframe",
        "TIMEFRAME_UNIT": "timeframe_unit",
    }

    # --- Mapping: DB field → Settings attr ---
    _DB_FIELD_MAP: dict[str, str] = {
        "trading_symbol": "TRADING_SYMBOL",
        "trading_mode": "TRADING_MODE",
        "trading_type": "TRADING_TYPE",
        "leverage": "LEVERAGE",
        "order_type": "ORDER_TYPE",
        "limit_price": "LIMIT_PRICE",
        "trade_amount": "TRADE_AMOUNT",
        "trade_currency": "TRADE_CURRENCY",
        "stop_loss": "STOP_LOSS",
        "stop_loss_type": "STOP_LOSS_TYPE",
        "timeframe": "TIMEFRAME",
        "timeframe_unit": "TIMEFRAME_UNIT",
        "bot_ma_fast": "BOT_MA_FAST",
        "bot_ma_slow": "BOT_MA_SLOW",
        "bot_quantity": "BOT_QUANTITY",
    }

    def has_api_keys(self) -> bool:
        """Devuelve True si las API Keys están configuradas."""
        return bool(self.BINANCE_API_KEY and self.BINANCE_API_SECRET)

    def reload_from_env(self) -> None:
        """Recarga SOLO variables sensibles desde .env."""
        load_dotenv(BASE_DIR / ".env", override=True)
        self.APP_USERNAME = os.getenv("APP_USERNAME", "")
        self.APP_PASSWORD = os.getenv("APP_PASSWORD", "")
        self.BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
        self.BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
        self.BINANCE_TESTNET = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

    def from_event(self, event) -> None:
        """Actualiza campos de trading desde un SettingsUpdatedEvent (DRY)."""
        for attr, event_field in self._EVENT_FIELD_MAP.items():
            setattr(self, attr, getattr(event, event_field))

    def from_dict(self, data: dict) -> None:
        """Actualiza campos de trading desde un diccionario (DRY)."""
        for db_field, attr in self._DB_FIELD_MAP.items():
            if db_field in data:
                setattr(self, attr, data[db_field])

    def to_dict(self) -> dict:
        """Serializa campos de trading a un diccionario (DRY)."""
        return {attr.lower(): getattr(self, attr) for attr in self._TRADING_FIELDS}

    async def load_from_db(self) -> None:
        """Carga configuración de trading desde la base de datos."""
        from services.config_service import config_service
        config = await config_service.load()
        self.from_dict({field: getattr(config, field) for field in self._DB_FIELD_MAP})

    async def save_to_db(self) -> None:
        """Guarda la configuración actual de trading en la base de datos."""
        from services.config_service import config_service
        await config_service.update(**self.to_dict())


# Instancia global singleton
settings = Settings()
