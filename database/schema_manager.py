"""
SchemaManager — Sincronización automática del schema de la DB.

Responsabilidades:
- Comparar definiciones de modelos contra schema real de la DB
- Crear tablas nuevas (via create_all)
- Agregar columnas faltantes a tablas existentes (via ALTER TABLE)
- Registrar cambios en log para trazabilidad

Principios:
- SRP: Única responsabilidad de manejar evolución del schema
- OCP: Abierto a agregar tablas/columnas sin modificar código existente
- DIP: Usa SQLAlchemy Inspector (abstracción), no PRAGMA raw
- DRY: Lee definiciones de models.py (single source of truth)
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import SQLModel

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Registry: tabla → clase modelo (single source of truth viene de models.py)
# ---------------------------------------------------------------------------

def _get_model_registry() -> dict[str, Any]:
    """Retorna el registry de modelos importados desde models.py."""
    from database.models import (
        Order,
        Operation,
        Position,
        PriceTick,
        TradingConfig,
    )

    return {
        "trading_config": TradingConfig,
        "price_ticks": PriceTick,
        "orders": Order,
        "positions": Position,
        "operations": Operation,
    }


# ---------------------------------------------------------------------------
# Defaults para columnas que necesitan valor en ALTER TABLE
# ---------------------------------------------------------------------------

_COLUMN_DEFAULTS: dict[str, dict[str, str]] = {
    "orders": {
        "trading_type": "'SPOT'",
        "leverage": "1",
        "order_type": "'MARKET'",
    },
    "positions": {
        "mark_price": "0.0",
        "unrealized_pnl": "0.0",
        "leverage": "1",
        "status": "'OPEN'",
    },
    "operations": {
        "trading_type": "'SPOT'",
        "trade_currency": "'USDT'",
        "mode": "'PAPER'",
    },
}


# ---------------------------------------------------------------------------
# Mapeo de tipos Python → SQL (para ALTER TABLE)
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[type, str] = {
    int: "INTEGER",
    float: "FLOAT",
    str: "VARCHAR",
    bool: "INTEGER",
}


def _python_type_to_sql(python_type: type) -> str:
    """Convierte un tipo Python a su equivalente SQL."""
    return _TYPE_MAP.get(python_type, "VARCHAR")


# ---------------------------------------------------------------------------
# Función sync interna (corre dentro de run_sync — contexto sync)
# ---------------------------------------------------------------------------

def _sync_schema(sync_conn: Any) -> list[str]:
    """Compara modelos vs DB y retorna lista de columnas agregadas."""
    model_registry = _get_model_registry()
    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    columns_added: list[str] = []

    for table_name, model_class in model_registry.items():
        if table_name not in existing_tables:
            continue  # create_all ya la creó

        db_columns = {
            col["name"] for col in inspector.get_columns(table_name)
        }
        model_columns = set(model_class.model_fields.keys())
        model_columns.discard("id")  # SQLModel siempre maneja 'id'

        missing = model_columns - db_columns
        for col_name in sorted(missing):
            field_info = model_class.model_fields.get(col_name)
            if field_info is None:
                continue

            # Tipo SQL
            annotation = field_info.annotation
            if hasattr(annotation, "__origin__"):
                args = getattr(annotation, "__args__", ())
                sql_type = _python_type_to_sql(args[0]) if args else "VARCHAR"
            else:
                sql_type = _python_type_to_sql(annotation)

            # Default
            default_value = _resolve_default(table_name, col_name, field_info)

            # ALTER TABLE
            if default_value is not None:
                col_def = f"{col_name} {sql_type} DEFAULT {default_value}"
            else:
                col_def = f"{col_name} {sql_type}"

            sync_conn.execute(text(
                f"ALTER TABLE {table_name} ADD COLUMN {col_def}"
            ))
            columns_added.append(f"{table_name}.{col_name}")

    return columns_added


def _resolve_default(
    table_name: str, col_name: str, field_info: Any
) -> str | None:
    """Determina el valor default para una columna."""
    # 1. Overrides explícitos
    table_defaults = _COLUMN_DEFAULTS.get(table_name, {})
    if col_name in table_defaults:
        return table_defaults[col_name]

    # 2. Default literal del modelo
    default = field_info.default
    if default is None or default is ...:
        return None
    if isinstance(default, (int, float)):
        return str(default)
    if isinstance(default, str):
        return f"'{default}'"

    # 3. default_factory (time.time, etc.) → sin DEFAULT en SQL
    if hasattr(default, "__func__") or callable(default):
        return None

    return None


# ---------------------------------------------------------------------------
# SchemaManager (pública)
# ---------------------------------------------------------------------------

class SchemaManager:
    """Sincroniza el schema de la DB con las definiciones de modelos."""

    async def sync(self, engine: AsyncEngine) -> None:
        """Crea tablas nuevas + agrega columnas faltantes."""
        async with engine.begin() as conn:
            # 1. Crear tablas nuevas
            await conn.run_sync(SQLModel.metadata.create_all)

            # 2. Detectar y agregar columnas faltantes
            columns_added = await conn.run_sync(_sync_schema)

        if columns_added:
            for col in columns_added:
                log.info("Migrated column: %s", col)
        log.info(
            "Schema sync complete: %d tables, %d columns added",
            len(_get_model_registry()),
            len(columns_added),
        )
