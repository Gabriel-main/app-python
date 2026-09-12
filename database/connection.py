"""
Conexion a la Base de Datos — aiosqlite + SQLModel.

Provee:
- get_engine(): SQLModel engine configurado con aiosqlite
- create_db_and_tables(): crea tablas + sincroniza schema (llamar al inicio)
- get_session(): context manager async para sesiones de DB
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from config.settings import settings
from database.models import Order, Operation, Position, PriceTick, TradingConfig  # noqa: F401 — importar para que SQLModel registre las tablas

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
_engine = None


def get_engine():
    global _engine
    if _engine is None:
        db_url = f"sqlite+aiosqlite:///{settings.DB_PATH}"
        _engine = create_async_engine(
            db_url,
            echo=False,
            connect_args={"check_same_thread": False},
        )
        log.info("DB engine created: %s", db_url)
    return _engine


# ---------------------------------------------------------------------------
# Inicialización
# ---------------------------------------------------------------------------
async def create_db_and_tables() -> None:
    """Crea tablas nuevas + sincroniza columnas faltantes."""
    from database.schema_manager import SchemaManager

    engine = get_engine()
    schema_manager = SchemaManager()
    await schema_manager.sync(engine)


# ---------------------------------------------------------------------------
# Sesión
# ---------------------------------------------------------------------------
@asynccontextmanager
async def get_session() -> AsyncGenerator[SQLModelAsyncSession, None]:
    """Provee una sesión async de SQLModel para operaciones de DB.
    
    NOTA: No hace auto-commit. Cada servicio debe llamar session.commit()
    explícitamente antes de retornar objetos de la sesión.
    """
    engine = get_engine()
    async with SQLModelAsyncSession(engine) as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
