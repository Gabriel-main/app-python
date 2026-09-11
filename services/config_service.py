"""
ConfigService — Gestión de configuración de trading en base de datos.

Persiste la configuración de trading (modo, tipo, leverage, etc.)
en SQLite. Las variables sensibles (API keys) se mantienen en .env.
"""
from __future__ import annotations

import logging
from sqlmodel import select

from database.connection import get_session
from database.models import TradingConfig

log = logging.getLogger(__name__)

# Defaults para primer inicio (valores de .env o hardcoded)
_DEFAULTS = {
    "trading_symbol": "BTCUSDT",
    "trading_mode": "PAPER",
    "trading_type": "SPOT",
    "leverage": 1,
    "order_type": "MARKET",
    "limit_price": 0.0,
    "trade_amount": 10.0,
    "trade_currency": "USDT",
    "stop_loss": 1.01,
    "stop_loss_type": "PERCENT",
    "timeframe": 1,
    "timeframe_unit": "MINUTES",
    "bot_ma_fast": 7,
    "bot_ma_slow": 25,
    "bot_quantity": 0.001,
}


class ConfigService:
    """Servicio singleton para gestionar configuración de trading en DB."""

    @staticmethod
    async def load() -> TradingConfig:
        """Carga la configuración desde la DB. Si no existe, crea una con defaults."""
        async with get_session() as session:
            result = await session.exec(select(TradingConfig).limit(1))
            config = result.first()

            if config is None:
                log.info("No TradingConfig found. Creating with defaults...")
                config = TradingConfig(**_DEFAULTS)
                session.add(config)
                await session.commit()
                log.info("TradingConfig created with defaults")

            await session.refresh(config)
            # Forzar carga de atributos antes de salir del context manager
            _ = config.trading_symbol
            _ = config.trading_mode
            _ = config.trading_type
            _ = config.leverage
            _ = config.order_type
            _ = config.limit_price
            _ = config.trade_amount
            _ = config.trade_currency
            _ = config.stop_loss
            _ = config.stop_loss_type
            _ = config.timeframe
            _ = config.timeframe_unit
            _ = config.bot_ma_fast
            _ = config.bot_ma_slow
            _ = config.bot_quantity
            return config

    @staticmethod
    async def save(config: TradingConfig) -> None:
        """Guarda la configuración en la DB."""
        import time
        config.updated_at = time.time()
        async with get_session() as session:
            session.add(config)
            await session.commit()
            log.info("TradingConfig saved")

    @staticmethod
    async def update(**kwargs) -> TradingConfig:
        """Actualiza campos específicos y guarda. Retorna la config actualizada."""
        import time
        async with get_session() as session:
            result = await session.exec(select(TradingConfig).limit(1))
            config = result.first()

            if config is None:
                # Crear con defaults + overrides
                config = TradingConfig(**_DEFAULTS, **kwargs)
            else:
                # Actualizar campos
                for key, value in kwargs.items():
                    if hasattr(config, key):
                        setattr(config, key, value)

            config.updated_at = time.time()
            session.add(config)
            await session.commit()
            await session.refresh(config)
            # Forzar carga de atributos antes de salir del context manager
            _ = config.trading_symbol
            _ = config.trading_mode
            _ = config.trading_type
            _ = config.leverage
            _ = config.order_type
            _ = config.limit_price
            _ = config.trade_amount
            _ = config.trade_currency
            _ = config.stop_loss
            _ = config.stop_loss_type
            _ = config.timeframe
            _ = config.timeframe_unit
            _ = config.bot_ma_fast
            _ = config.bot_ma_slow
            _ = config.bot_quantity
            log.info("TradingConfig updated: %s", list(kwargs.keys()))
            return config

    @staticmethod
    async def init_from_env() -> TradingConfig:
        """Inicializa la DB con valores de .env en el primer inicio."""
        from config.settings import Settings
        import os

        # Leer valores de .env (si existen)
        env_values = {}
        env_map = {
            "TRADING_SYMBOL": "trading_symbol",
            "TRADING_MODE": "trading_mode",
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
            "BOT_MA_FAST": "bot_ma_fast",
            "BOT_MA_SLOW": "bot_ma_slow",
            "BOT_QUANTITY": "bot_quantity",
        }

        for env_key, db_key in env_map.items():
            val = os.getenv(env_key)
            if val is not None:
                # Convertir al tipo correcto
                default = _DEFAULTS[db_key]
                if isinstance(default, int):
                    env_values[db_key] = int(val)
                elif isinstance(default, float):
                    env_values[db_key] = float(val)
                else:
                    env_values[db_key] = val

        async with get_session() as session:
            result = await session.exec(select(TradingConfig).limit(1))
            config = result.first()

            if config is None:
                # Crear con valores de .env (o defaults)
                merged = {**_DEFAULTS, **env_values}
                config = TradingConfig(**merged)
                session.add(config)
                await session.commit()
                await session.refresh(config)
                log.info("TradingConfig initialized from .env")
            else:
                log.info("TradingConfig already exists, skipping init")

            # Forzar carga de atributos antes de salir del context manager
            _ = config.trading_symbol
            _ = config.trading_mode
            _ = config.trading_type
            _ = config.leverage
            _ = config.order_type
            _ = config.limit_price
            _ = config.trade_amount
            _ = config.trade_currency
            _ = config.stop_loss
            _ = config.stop_loss_type
            _ = config.timeframe
            _ = config.timeframe_unit
            _ = config.bot_ma_fast
            _ = config.bot_ma_slow
            _ = config.bot_quantity
            return config


# Instancia singleton
config_service = ConfigService()
