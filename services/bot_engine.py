"""
Bot Engine — Estrategia MA Crossover.

Responsabilidades:
- Suscribirse a PriceTickEvent
- Mantener buffer circular de los últimos N precios (collections.deque)
- Calcular MA rápida (BOT_MA_FAST) y MA lenta (BOT_MA_SLOW)
- Detectar cruce alcista/bajista y emitir BotSignalEvent
- En señal BUY/SELL: crear orden y publicar OrderExecutedEvent
- En PAPER mode: simular orden sin llamar a Binance
- En LIVE mode: ejecutar orden real vía API

Regla: CERO POLLING. El motor se dispara exclusivamente por PriceTickEvent.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from typing import Deque

from core.event_bus import event_bus
from core.events import (
    BotSignalEvent,
    BotStateChangedEvent,
    OrderExecutedEvent,
    PriceTickEvent,
    SettingsUpdatedEvent,
)
from config.settings import settings
from database.db_queue import db_queue

log = logging.getLogger(__name__)


class BotEngine:
    """Motor de trading con estrategia MA Crossover."""

    def __init__(self) -> None:
        self._running: bool = False
        self._active: bool = False       # El bot puede estar iniciado pero pausado
        self._price_buffer: Deque[float] = deque()
        self._last_signal: str = "HOLD"  # Para evitar señales duplicadas
        self._client = None              # Binance async client (solo LIVE)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._active = True
        self._price_buffer.clear()
        self._last_signal = "HOLD"

        event_bus.subscribe(PriceTickEvent, self._on_price_tick)
        event_bus.subscribe(BotStateChangedEvent, self._on_bot_state_changed)
        event_bus.subscribe(SettingsUpdatedEvent, self._on_settings_updated)

        log.info(
            "BotEngine started | MA(%d/%d) | Mode: %s",
            settings.BOT_MA_FAST, settings.BOT_MA_SLOW, settings.TRADING_MODE
        )

    async def stop(self) -> None:
        self._running = False
        self._active = False
        event_bus.unsubscribe(PriceTickEvent, self._on_price_tick)
        event_bus.unsubscribe(BotStateChangedEvent, self._on_bot_state_changed)
        event_bus.unsubscribe(SettingsUpdatedEvent, self._on_settings_updated)
        await self._close_client()
        log.info("BotEngine stopped")

    # ------------------------------------------------------------------
    # Handlers de eventos
    # ------------------------------------------------------------------

    async def _on_price_tick(self, event: PriceTickEvent) -> None:
        """Recibe un tick y actualiza el análisis técnico."""
        max_len = max(settings.BOT_MA_SLOW, settings.PRICE_BUFFER_SIZE)
        self._price_buffer.append(event.price)
        # Mantener el buffer al tamaño necesario
        while len(self._price_buffer) > max_len:
            self._price_buffer.popleft()

        if not self._active:
            return

        # Necesitamos al menos MA_SLOW puntos para calcular
        if len(self._price_buffer) < settings.BOT_MA_SLOW:
            return

        signal_event = self._calculate_signal(event.symbol)
        if signal_event:
            event_bus.publish(signal_event)
            if signal_event.signal in ("BUY", "SELL"):
                asyncio.create_task(
                    self._execute_order(signal_event),
                    name=f"order_{signal_event.signal}_{int(time.time())}",
                )

    async def _on_bot_state_changed(self, event: BotStateChangedEvent) -> None:
        """Activa o pausa el bot desde la UI."""
        self._active = event.is_running
        log.info("BotEngine active: %s | mode: %s", self._active, event.mode)

    async def _on_settings_updated(self, event: SettingsUpdatedEvent) -> None:
        """Recarga parámetros de estrategia sin reiniciar el servicio."""
        settings.BOT_MA_FAST = event.ma_fast
        settings.BOT_MA_SLOW = event.ma_slow
        settings.TRADING_MODE = event.mode
        self._price_buffer.clear()
        self._last_signal = "HOLD"
        log.info("BotEngine settings reloaded: MA(%d/%d)", event.ma_fast, event.ma_slow)

    # ------------------------------------------------------------------
    # Estrategia: MA Crossover
    # ------------------------------------------------------------------

    def _calculate_signal(self, symbol: str) -> BotSignalEvent | None:
        """Calcula MAs y emite señal si hay cruce."""
        prices = list(self._price_buffer)
        fast = settings.BOT_MA_FAST
        slow = settings.BOT_MA_SLOW

        ma_fast = sum(prices[-fast:]) / fast
        ma_slow = sum(prices[-slow:]) / slow

        # Cruce alcista: MA rápida supera MA lenta
        if ma_fast > ma_slow and self._last_signal != "BUY":
            signal = "BUY"
        # Cruce bajista: MA rápida cae por debajo de MA lenta
        elif ma_fast < ma_slow and self._last_signal != "SELL":
            signal = "SELL"
        else:
            # Sin cruce nuevo → emitir HOLD sin repetir la señal anterior
            return BotSignalEvent(
                symbol=symbol,
                signal="HOLD",
                ma_fast=round(ma_fast, 2),
                ma_slow=round(ma_slow, 2),
                confidence=abs(ma_fast - ma_slow) / ma_slow,
            )

        self._last_signal = signal
        confidence = min(abs(ma_fast - ma_slow) / ma_slow * 100, 1.0)

        log.info(
            "Signal %s | MA_fast=%.2f | MA_slow=%.2f | confidence=%.2f%%",
            signal, ma_fast, ma_slow, confidence * 100
        )

        return BotSignalEvent(
            symbol=symbol,
            signal=signal,
            ma_fast=round(ma_fast, 2),
            ma_slow=round(ma_slow, 2),
            confidence=round(confidence, 4),
        )

    # ------------------------------------------------------------------
    # Ejecución de órdenes
    # ------------------------------------------------------------------

    async def _execute_order(self, signal: BotSignalEvent) -> None:
        """Ejecuta una orden paper o live según el modo configurado."""
        order_id = f"{'PAPER' if settings.TRADING_MODE == 'PAPER' else 'LIVE'}-{uuid.uuid4().hex[:8].upper()}"

        if settings.TRADING_MODE == "PAPER":
            order_event = OrderExecutedEvent(
                order_id=order_id,
                symbol=signal.symbol,
                side=signal.signal,     # "BUY" | "SELL"
                quantity=settings.BOT_QUANTITY,
                price=signal.ma_fast,   # usamos el precio de la MA rápida
                mode="PAPER",
                timestamp=time.time(),
            )
            log.info("[PAPER] Order %s: %s %.6f @ %.2f",
                     order_id, signal.signal, settings.BOT_QUANTITY, signal.ma_fast)
        else:
            order_event = await self._execute_live_order(signal, order_id)
            if order_event is None:
                return

        event_bus.publish(order_event)
        db_queue.enqueue_order(order_event)

    async def _execute_live_order(
        self, signal: BotSignalEvent, order_id: str
    ) -> OrderExecutedEvent | None:
        """Ejecuta una orden real en Binance."""
        try:
            if not self._client:
                from binance import AsyncClient  # type: ignore
                self._client = await AsyncClient.create(
                    api_key=settings.BINANCE_API_KEY,
                    api_secret=settings.BINANCE_API_SECRET,
                    testnet=settings.BINANCE_TESTNET,
                )

            side_map = {"BUY": "BUY", "SELL": "SELL"}
            response = await self._client.create_order(
                symbol=signal.symbol,
                side=side_map[signal.signal],
                type="MARKET",
                quantity=settings.BOT_QUANTITY,
            )

            fill_price = float(response.get("fills", [{}])[0].get("price", signal.ma_fast))
            return OrderExecutedEvent(
                order_id=response.get("orderId", order_id),
                symbol=signal.symbol,
                side=signal.signal,
                quantity=settings.BOT_QUANTITY,
                price=fill_price,
                mode="LIVE",
                timestamp=time.time(),
            )

        except Exception as exc:
            log.error("Live order failed: %s", exc)
            return None

    async def _close_client(self) -> None:
        if self._client:
            try:
                await self._client.close_connection()
            except Exception:
                pass
            self._client = None


# Instancia global singleton
bot_engine = BotEngine()
