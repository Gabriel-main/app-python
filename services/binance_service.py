"""
Binance Service — WebSocket y REST async.

Responsabilidades:
- Conectar al stream <symbol>@ticker vía BinanceSocketManager
- Publicar PriceTickEvent al EventBus en cada mensaje recibido
- Publicar ConnectionStatusEvent en cada cambio de estado
- Reconexión automática con backoff exponencial
- Suscribirse a SettingsUpdatedEvent para reconectar con nuevo símbolo/keys

En PAPER mode sin API keys: usa un simulador de ticks (MockTickGenerator).
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
import time
import uuid

from core.event_bus import event_bus
from core.events import (
    ConnectionStatusEvent,
    PriceTickEvent,
    SettingsUpdatedEvent,
)
from config.settings import settings
from database.db_queue import db_queue

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mock Tick Generator (cuando no hay API keys)
# ---------------------------------------------------------------------------

class MockTickGenerator:
    """Simula un stream de ticks de precio para desarrollo/paper trading."""

    def __init__(self) -> None:
        self._base_price = 65_000.0
        self._tick_count = 0

    def next_tick(self, symbol: str) -> PriceTickEvent:
        # Simulación de movimiento de precio tipo random walk con sinusoide
        self._tick_count += 1
        noise = random.gauss(0, 50)
        wave = math.sin(self._tick_count * 0.1) * 200
        self._base_price = max(1_000, self._base_price + noise + wave * 0.05)

        return PriceTickEvent(
            symbol=symbol,
            price=round(self._base_price, 2),
            change_pct=round(random.uniform(-3.0, 3.0), 2),
            volume=round(random.uniform(1_000_000, 5_000_000), 2),
            high_24h=round(self._base_price * 1.02, 2),
            low_24h=round(self._base_price * 0.98, 2),
            timestamp=time.time(),
        )


# ---------------------------------------------------------------------------
# Binance Service
# ---------------------------------------------------------------------------

class BinanceService:
    """Gestiona la conexión WebSocket a Binance y publica eventos al bus."""

    def __init__(self) -> None:
        self._running: bool = False
        self._stream_task: asyncio.Task | None = None
        self._client = None
        self._mock = MockTickGenerator()
        self._retry_count: int = 0

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._retry_count = 0
        event_bus.subscribe(SettingsUpdatedEvent, self._on_settings_updated)
        self._stream_task = asyncio.create_task(
            self._run_with_reconnect(), name="binance_stream"
        )
        log.info("BinanceService starting for symbol: %s", settings.TRADING_SYMBOL)

    async def stop(self) -> None:
        self._running = False
        event_bus.unsubscribe(SettingsUpdatedEvent, self._on_settings_updated)
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
        await self._close_client()
        log.info("BinanceService stopped")

    async def restart(self) -> None:
        """Reinicia el servicio (usado tras cambio de configuración)."""
        await self.stop()
        self._running = True
        self._retry_count = 0
        self._stream_task = asyncio.create_task(
            self._run_with_reconnect(), name="binance_stream"
        )

    # ------------------------------------------------------------------
    # Loop con reconexión automática (backoff exponencial)
    # ------------------------------------------------------------------

    async def _run_with_reconnect(self) -> None:
        while self._running:
            try:
                event_bus.publish(ConnectionStatusEvent(
                    status="CONNECTING",
                    message=f"Conectando a {settings.TRADING_SYMBOL}..."
                ))
                if settings.has_api_keys():
                    await self._run_live_stream()
                else:
                    await self._run_mock_stream()
                # Si llegamos aquí es porque el stream terminó normalmente
                self._retry_count = 0

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._retry_count += 1
                delay = min(
                    settings.RECONNECT_BASE_DELAY ** self._retry_count,
                    60.0
                )
                log.error(
                    "BinanceService error (retry %d): %s. Waiting %.1fs...",
                    self._retry_count, exc, delay
                )
                event_bus.publish(ConnectionStatusEvent(
                    status="RECONNECTING",
                    message=f"Reintentando en {delay:.0f}s... (intento {self._retry_count})"
                ))
                if self._retry_count > settings.RECONNECT_MAX_RETRIES:
                    log.critical("Max retries exceeded. Stopping BinanceService.")
                    event_bus.publish(ConnectionStatusEvent(
                        status="DISCONNECTED",
                        message="Máximo de reintentos alcanzado."
                    ))
                    break
                await asyncio.sleep(delay)

    # ------------------------------------------------------------------
    # Stream real (Binance WebSocket)
    # ------------------------------------------------------------------

    async def _run_live_stream(self) -> None:
        from binance import AsyncClient, BinanceSocketManager  # type: ignore
        from binance.exceptions import BinanceAPIException, BinanceRequestException  # type: ignore

        try:
            self._client = await AsyncClient.create(
                api_key=settings.BINANCE_API_KEY,
                api_secret=settings.BINANCE_API_SECRET,
                testnet=settings.BINANCE_TESTNET,
            )
            bm = BinanceSocketManager(self._client)
            symbol_lower = settings.TRADING_SYMBOL.lower()

            async with bm.symbol_ticker_socket(symbol_lower) as ts:
                event_bus.publish(ConnectionStatusEvent(
                    status="CONNECTED",
                    message=f"Conectado a {settings.TRADING_SYMBOL}"
                ))
                log.info("WebSocket connected: %s@ticker", symbol_lower)

                async for msg in ts:
                    if not self._running:
                        break
                    if msg.get("e") == "error":
                        raise Exception(f"WS Error: {msg}")

                    tick = self._parse_binance_ticker(msg)
                    event_bus.publish(tick)
                    db_queue.enqueue_tick(tick)

        except (BinanceAPIException, BinanceRequestException) as exc:
            log.error("Binance API exception: %s", exc)
            raise
        finally:
            await self._close_client()

    # ------------------------------------------------------------------
    # Stream simulado (Paper mode sin keys)
    # ------------------------------------------------------------------

    async def _run_mock_stream(self) -> None:
        log.warning("No API keys found. Running MOCK tick generator.")
        event_bus.publish(ConnectionStatusEvent(
            status="CONNECTED",
            message="Modo Simulación (Sin API Keys)"
        ))
        interval = 1.5  # segundos entre ticks simulados
        while self._running:
            tick = self._mock.next_tick(settings.TRADING_SYMBOL)
            event_bus.publish(tick)
            db_queue.enqueue_tick(tick)
            await asyncio.sleep(interval)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_binance_ticker(self, msg: dict) -> PriceTickEvent:
        return PriceTickEvent(
            symbol=msg.get("s", settings.TRADING_SYMBOL),
            price=float(msg.get("c", 0)),       # close price (current)
            change_pct=float(msg.get("P", 0)),  # price change %
            volume=float(msg.get("q", 0)),       # quote asset volume
            high_24h=float(msg.get("h", 0)),
            low_24h=float(msg.get("l", 0)),
            timestamp=time.time(),
        )

    async def _close_client(self) -> None:
        if self._client:
            try:
                await self._client.close_connection()
            except Exception:
                pass
            self._client = None

    async def _on_settings_updated(self, event: SettingsUpdatedEvent) -> None:
        """Reacciona a cambios de configuración desde la UI."""
        log.info("Settings updated. Restarting BinanceService...")
        await self.restart()


# Instancia global singleton
binance_service = BinanceService()
