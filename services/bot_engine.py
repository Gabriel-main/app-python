"""
Bot Engine — Motor de Trading Dual (OC/OV).

Responsabilidades:
- Al iniciar: crear OC(a) Compra Activa + OV(p) Venta Pendiente
- Calcular SL como distancia fija (porcentaje o USDT) del precio de apertura
- Timer de temporalidad: cada T se evalúan operaciones, se limpian pasadas,
  se mueve pendiente a activa, se crea nueva pendiente
- Trailing stop: SL se mueve con el precio (pero nunca hacia atrás)
- Publicar OperationUpdateEvent en cada cambio de estado
- Ejecutar órdenes reales o paper según TRADING_MODE
- Soportar Spot, Futures y Cross Margin según TRADING_TYPE

Regla: CERO POLLING. Timer maneja la temporalidad, PriceTickEvent maneja los precios.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from typing import Deque, Literal

from core.event_bus import event_bus
from core.events import (
    BotSignalEvent,
    BotStateChangedEvent,
    InitialOrderEvent,
    OperationInsertedEvent,
    OperationState,
    OperationUpdateEvent,
    OrderExecutedEvent,
    PriceTickEvent,
    PositionUpdateEvent,
    SettingsUpdatedEvent,
    StopLossEvent,
    TimeframeCycleEvent,
    TradingLifecycleEvent,
)
from config.settings import settings
from database.db_queue import db_queue

log = logging.getLogger(__name__)


class TradingOperation:
    """Modelo interno de una operación individual."""

    def __init__(
        self,
        side: Literal["BUY", "SELL"],
        state: Literal["ACTIVE", "PENDING", "PAST"],
        entry_price: float,
        stop_loss: float,
        quantity: float,
        order_id: str,
    ) -> None:
        self.side = side
        self.state = state
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.quantity = quantity
        self.order_id = order_id
        self.created_at = time.time()
        self.best_sl = stop_loss  # Mejor SL alcanzado (para trailing stop)

    def to_event(self) -> OperationState:
        return OperationState(
            side=self.side,
            state=self.state,
            entry_price=self.entry_price,
            stop_loss=self.stop_loss,
            quantity=self.quantity,
            order_id=self.order_id,
            timestamp=self.created_at,
        )


class BotEngine:
    """Motor de trading con modelo dual OC/OV."""

    def __init__(self) -> None:
        self._running: bool = False
        self._active: bool = False
        self._current_price: float = 0.0
        self._client = None
        self._leverage_set: bool = False

        # Operaciones
        self._operations: list[TradingOperation] = []

        # MA Buffer (para indicador visual — no afecta operaciones OC/OV)
        self._price_buffer: Deque[float] = deque()
        self._last_signal: str = "HOLD"

        # Timer de temporalidad
        self._timeframe_task: asyncio.Task | None = None
        self._timeframe_start: float = 0.0
        self._timeframe_duration: float = 0.0  # segundos

    # ------------------------------------------------------------------
    # Consulta de estado
    # ------------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        """True si el bot está operando activamente."""
        return self._active

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._active = False

        event_bus.subscribe(PriceTickEvent, self._on_price_tick)
        event_bus.subscribe(BotStateChangedEvent, self._on_bot_state_changed)
        event_bus.subscribe(SettingsUpdatedEvent, self._on_settings_updated)

        # Publicar estado inicial después de que la UI se suscriba
        asyncio.create_task(self._publish_initial_state(), name="initial_state")

        log.info(
            "BotEngine started | Mode: %s | Type: %s | SL: %s %s | TF: %d %s",
            settings.TRADING_MODE, settings.TRADING_TYPE,
            settings.STOP_LOSS, settings.STOP_LOSS_TYPE,
            settings.TIMEFRAME, settings.TIMEFRAME_UNIT,
        )

    async def stop(self) -> None:
        self._running = False
        self._active = False
        self._stop_timeframe_timer()
        self._operations.clear()
        event_bus.unsubscribe(PriceTickEvent, self._on_price_tick)
        event_bus.unsubscribe(BotStateChangedEvent, self._on_bot_state_changed)
        event_bus.unsubscribe(SettingsUpdatedEvent, self._on_settings_updated)
        await self._close_client()
        log.info("BotEngine stopped")

    async def _publish_initial_state(self) -> None:
        """Publica el estado inicial del bot después de que la UI se suscriba."""
        await asyncio.sleep(0.1)
        event_bus.publish(BotStateChangedEvent(
            is_running=self._active,
            mode=settings.TRADING_MODE,
        ))

    # ------------------------------------------------------------------
    # Handlers de eventos
    # ------------------------------------------------------------------

    async def _on_price_tick(self, event: PriceTickEvent) -> None:
        """Recibe un tick, actualiza MA buffer y trailing stop."""
        self._current_price = event.price

        # Alimentar MA buffer (para indicador visual)
        max_len = max(settings.BOT_MA_SLOW, settings.PRICE_BUFFER_SIZE)
        self._price_buffer.append(event.price)
        while len(self._price_buffer) > max_len:
            self._price_buffer.popleft()

        # Publicar BotSignalEvent si tenemos suficientes datos
        if len(self._price_buffer) >= settings.BOT_MA_SLOW:
            self._publish_bot_signal(event.symbol)

        if not self._active or not self._operations:
            return

        # Actualizar trailing stop para operaciones activas
        self._update_trailing_stop(event.price)

        # Insertar nuevas PENDING si se cumplen condiciones del diagrama
        pa = event.price
        sl_dist = self._calculate_sl_distance(pa)
        quantity = self._calculate_quantity(pa)
        self._insert_pending_if_needed(pa, sl_dist, quantity)

        # Publicar PositionUpdateEvent para operaciones activas
        self._publish_position_updates(event.price)

        # Verificar si el precio tocó algún stop loss
        self._check_stop_losses(event.price)

    async def _on_bot_state_changed(self, event: BotStateChangedEvent) -> None:
        """Activa o detiene el bot desde la UI."""
        if event.is_running and not self._active:
            # Iniciar trading
            await self._start_trading()
        elif not event.is_running and self._active:
            # Detener trading
            await self._stop_trading()

        self._active = event.is_running
        log.info("BotEngine active: %s | mode: %s", self._active, event.mode)

    async def _on_settings_updated(self, event: SettingsUpdatedEvent) -> None:
        """Recarga parámetros de estrategia."""
        settings.from_event(event)
        self._leverage_set = False

        log.info(
            "BotEngine settings reloaded: Type: %s | Leverage: %dx | SL: %s %s | TF: %d %s",
            event.trading_type, event.leverage,
            event.stop_loss, event.stop_loss_type,
            event.timeframe, event.timeframe_unit,
        )

    # ------------------------------------------------------------------
    # Indicador visual: MA Crossover (no afecta operaciones OC/OV)
    # ------------------------------------------------------------------

    def _publish_bot_signal(self, symbol: str) -> None:
        """Calcula MA y publica BotSignalEvent para el indicador visual."""
        prices = list(self._price_buffer)
        fast = settings.BOT_MA_FAST
        slow = settings.BOT_MA_SLOW

        ma_fast = sum(prices[-fast:]) / fast
        ma_slow = sum(prices[-slow:]) / slow

        if ma_fast > ma_slow and self._last_signal != "BUY":
            signal = "BUY"
            self._last_signal = signal
        elif ma_fast < ma_slow and self._last_signal != "SELL":
            signal = "SELL"
            self._last_signal = signal
        else:
            signal = "HOLD"

        confidence = min(abs(ma_fast - ma_slow) / ma_slow * 100, 1.0) if ma_slow > 0 else 0.0

        event_bus.publish(BotSignalEvent(
            symbol=symbol,
            signal=signal,
            ma_fast=round(ma_fast, 2),
            ma_slow=round(ma_slow, 2),
            confidence=round(confidence, 4),
        ))

    def _publish_position_updates(self, current_price: float) -> None:
        """Publica PositionUpdateEvent para cada operación activa."""
        for op in self._operations:
            if op.state != "ACTIVE":
                continue

            # Calcular PnL no realizado
            if op.side == "BUY":
                unrealized_pnl = (current_price - op.entry_price) * op.quantity
                side = "LONG"
            else:
                unrealized_pnl = (op.entry_price - current_price) * op.quantity
                side = "SHORT"

            event_bus.publish(PositionUpdateEvent(
                symbol=settings.TRADING_SYMBOL,
                side=side,
                quantity=op.quantity,
                entry_price=op.entry_price,
                mark_price=current_price,
                unrealized_pnl=round(unrealized_pnl, 4),
                leverage=settings.LEVERAGE,
                trading_type=settings.TRADING_TYPE,
            ))

    # ------------------------------------------------------------------
    # Lógica de trading dual (OC/OV)
    # ------------------------------------------------------------------

    async def _start_trading(self) -> None:
        """Inicia las operaciones duales: OC(a) + OV(p)."""
        if self._current_price <= 0:
            log.warning("No price available yet. Waiting for first tick...")
            return

        pa = self._current_price
        sl_dist = self._calculate_sl_distance(pa)
        quantity = self._calculate_quantity(pa)

        buy_op = self._create_operation("BUY", "ACTIVE", pa, sl_dist, quantity)
        sell_op = self._create_operation("SELL", "PENDING", pa, sl_dist, quantity)
        self._operations = [buy_op, sell_op]

        log.info(
            "Trading started | Pa=%.4f | SL dist=%.4f | "
            "BUY(a): Pe=%.4f PSL=%.4f | SELL(p): Pe=%.4f PSL=%.4f",
            pa, sl_dist,
            buy_op.entry_price, buy_op.stop_loss,
            sell_op.entry_price, sell_op.stop_loss,
        )

        event_bus.publish(TradingLifecycleEvent(
            action="STARTED",
            detail=f"Bot iniciado | Pa=${pa:,.4f} | SL dist=${sl_dist:,.4f}",
            data={"pa": pa, "sl_dist": sl_dist, "operations": 2},
        ))

        await self._execute_initial_orders()
        self._publish_update()
        self._start_timeframe_timer()

    async def _stop_trading(self) -> None:
        """Detiene trading: elimina pendientes y apaga timer."""
        self._stop_timeframe_timer()

        # Eliminar operaciones pendientes
        self._operations = [op for op in self._operations if op.state == "ACTIVE"]

        # Marcar activas como past
        for op in self._operations:
            op.state = "PAST"

        self._publish_update()
        self._operations.clear()

        event_bus.publish(TradingLifecycleEvent(
            action="STOPPED",
            detail="Bot detenido por el usuario",
        ))

        log.info("Trading stopped")

    def _calculate_sl_distance(self, pa: float) -> float:
        """Calcula la distancia del SL según tipo (porcentaje o USDT fijo)."""
        if settings.STOP_LOSS_TYPE == "PERCENT":
            return pa * (settings.STOP_LOSS / 100.0)
        else:  # USDT fijo
            return settings.STOP_LOSS

    def _calculate_quantity(self, pa: float) -> float:
        """Calcula la cantidad a operar basada en TRADE_AMOUNT y precio actual."""
        if pa <= 0:
            return 0.0
        return settings.TRADE_AMOUNT / pa

    # ------------------------------------------------------------------
    # Helpers de operaciones (SRP + DRY)
    # ------------------------------------------------------------------

    def _create_operation(
        self,
        side: Literal["BUY", "SELL"],
        state: Literal["ACTIVE", "PENDING"],
        pa: float,
        sl_dist: float,
        quantity: float,
    ) -> TradingOperation:
        """Crea una operación con los parámetros según el modelo dual OC/OV."""
        prefix = "OC" if side == "BUY" else "OV"

        if side == "BUY":
            entry_price = pa + sl_dist  # Pe = Pa + SL
            stop_loss = pa - sl_dist    # PSL = Pa - SL
        else:
            entry_price = pa - sl_dist  # Pe = Pa - SL
            stop_loss = pa + sl_dist    # PSL = Pa + SL

        return TradingOperation(
            side=side,
            state=state,
            entry_price=entry_price,
            stop_loss=stop_loss,
            quantity=quantity,
            order_id=f"{prefix}-{uuid.uuid4().hex[:8].upper()}",
        )

    def _should_insert_pending(self, op: TradingOperation, pa: float) -> bool:
        """Evalúa si se debe insertar una nueva operación PENDING según el diagrama.
        
        Condiciones:
        - BUY: Si SL(OC(a)) > Pa → Insertar OC(p)
        - SELL: Si SL(OV(a)) < Pa → Insertar OV(p)
        """
        if op.state != "ACTIVE":
            return False
        if op.side == "BUY" and op.stop_loss > pa:
            return True
        if op.side == "SELL" and op.stop_loss < pa:
            return True
        return False

    def _insert_pending_if_needed(self, pa: float, sl_dist: float, quantity: float) -> None:
        """Inserta nuevas operaciones PENDING si se cumplen las condiciones del diagrama.
        
        Solo se inserta si no existe ya una PENDING del mismo lado.
        """
        pending_sides = {op.side for op in self._operations if op.state == "PENDING"}

        for op in self._operations:
            if op.state == "ACTIVE" and self._should_insert_pending(op, pa):
                complement_side = "SELL" if op.side == "BUY" else "BUY"
                if complement_side not in pending_sides:
                    new_op = self._create_operation(complement_side, "PENDING", pa, sl_dist, quantity)
                    self._operations.append(new_op)
                    pending_sides.add(complement_side)

                    event_bus.publish(OperationInsertedEvent(
                        active_side=op.side,
                        active_sl=op.stop_loss,
                        pa=pa,
                        new_pending_side=complement_side,
                    ))

                    log.info("Inserted PENDING %s due to SL condition", complement_side)

    # ------------------------------------------------------------------
    # Timer de temporalidad
    # ------------------------------------------------------------------

    def _start_timeframe_timer(self) -> None:
        """Inicia el timer de temporalidad."""
        self._stop_timeframe_timer()

        # Convertir a segundos
        if settings.TIMEFRAME_UNIT == "HOURS":
            self._timeframe_duration = settings.TIMEFRAME * 3600.0
        else:  # MINUTES
            self._timeframe_duration = settings.TIMEFRAME * 60.0

        self._timeframe_start = time.time()
        self._timeframe_task = asyncio.create_task(
            self._timeframe_loop(), name="timeframe_timer"
        )
        log.info("Timeframe timer started: %d %s (%.0fs)",
                 settings.TIMEFRAME, settings.TIMEFRAME_UNIT, self._timeframe_duration)

    def _stop_timeframe_timer(self) -> None:
        """Detiene el timer de temporalidad."""
        if self._timeframe_task:
            self._timeframe_task.cancel()
            self._timeframe_task = None

    async def _timeframe_loop(self) -> None:
        """Loop del timer de temporalidad."""
        try:
            while self._running and self._active:
                remaining = self._timeframe_duration - (time.time() - self._timeframe_start)
                if remaining <= 0:
                    await self._on_timeframe_tick()
                    self._timeframe_start = time.time()
                else:
                    # Publicar progreso cada segundo
                    self._publish_update(remaining)
                    await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass

    async def _on_timeframe_tick(self) -> None:
        """Se ejecuta cuando expira la temporalidad.
        
        Flujo según diagrama:
        1. Actualizar SL de ACTIVE si condición se cumplió (trailing stop)
        2. Eliminar TODAS las operaciones PENDING
        3. Crear NUEVA operación PENDING con datos actualizados
        """
        if not self._operations:
            return

        pa = self._current_price
        sl_dist = self._calculate_sl_distance(pa)
        quantity = self._calculate_quantity(pa)

        log.info("Timeframe tick | Pa=%.4f | Operations: %d", pa, len(self._operations))

        # 1. Encontrar la operación ACTIVE
        active_op = None
        for op in self._operations:
            if op.state == "ACTIVE":
                active_op = op
                break

        if active_op is None:
            log.warning("No ACTIVE operation found during timeframe tick")
            return

        # 2. Actualizar SL de ACTIVE si condición se cumplió (trailing stop)
        self._update_sl_on_tick(active_op, pa, sl_dist)

        # 3. Eliminar TODAS las operaciones PENDING
        self._operations = [op for op in self._operations if op.state != "PENDING"]

        # 4. Crear NUEVA operación PENDING con datos actualizados
        new_pending_side = "SELL" if active_op.side == "BUY" else "BUY"
        new_pending = self._create_operation(new_pending_side, "PENDING", pa, sl_dist, quantity)
        self._operations.append(new_pending)

        log.info("Timeframe update: ACTIVE=%s, NEW PENDING=%s",
                 active_op.order_id, new_pending.order_id)

        event_bus.publish(TimeframeCycleEvent(
            pa=pa,
            active_side=active_op.side,
            new_pending_side=new_pending.side,
            operations_count=len(self._operations),
        ))

        self._publish_update()

    def _update_sl_on_tick(self, op: TradingOperation, pa: float, sl_dist: float) -> None:
        """Actualiza el SL de la operación ACTIVE según condiciones del diagrama.
        
        Condiciones:
        - C (Compra): SLa < SLp → SL se movió favorablemente hacia abajo
        - V (Venta): SLa > SLp → SL se movió favorablemente hacia arriba
        """
        if op.side == "BUY":
            new_sl = pa - sl_dist
            if new_sl < op.stop_loss:
                op.best_sl = min(op.best_sl, new_sl)
                op.stop_loss = new_sl
                log.info("BUY SL updated: %.4f (best=%.4f)", op.stop_loss, op.best_sl)
        else:
            new_sl = pa + sl_dist
            if new_sl > op.stop_loss:
                op.best_sl = max(op.best_sl, new_sl)
                op.stop_loss = new_sl
                log.info("SELL SL updated: %.4f (best=%.4f)", op.stop_loss, op.best_sl)

    # ------------------------------------------------------------------
    # Trailing stop
    # ------------------------------------------------------------------

    def _update_trailing_stop(self, price: float) -> None:
        """Actualiza trailing stop para operaciones activas.
        El SL se mueve con el precio pero nunca hacia atrás."""
        for op in self._operations:
            if op.state != "ACTIVE":
                continue

            if op.side == "BUY" and price > op.entry_price:
                # Precio subió → SL sube (pero no baja)
                new_sl = price - self._calculate_sl_distance(price)
                if new_sl > op.stop_loss:
                    op.stop_loss = new_sl
                    op.best_sl = max(op.best_sl, new_sl)

            elif op.side == "SELL" and price < op.entry_price:
                # Precio bajó → SL baja (pero no sube)
                new_sl = price + self._calculate_sl_distance(price)
                if new_sl < op.stop_loss:
                    op.stop_loss = new_sl
                    op.best_sl = min(op.best_sl, new_sl)

    def _check_stop_losses(self, price: float) -> None:
        """Verifica si el precio tocó algún stop loss."""
        for op in self._operations:
            if op.state != "ACTIVE":
                continue

            triggered = False
            if op.side == "BUY" and price <= op.stop_loss:
                triggered = True
            elif op.side == "SELL" and price >= op.stop_loss:
                triggered = True

            if triggered:
                log.info("STOP LOSS triggered: %s @ %.4f (SL=%.4f)",
                         op.side, price, op.stop_loss)
                asyncio.create_task(
                    self._execute_stop_loss(op, price),
                    name=f"sl_{op.side}_{int(time.time())}",
                )

    async def _execute_stop_loss(self, op: TradingOperation, trigger_price: float) -> None:
        """Ejecuta la orden de stop loss."""
        order_id = f"SL-{uuid.uuid4().hex[:8].upper()}"

        if settings.TRADING_MODE == "PAPER":
            order_event = OrderExecutedEvent(
                order_id=order_id,
                symbol=settings.TRADING_SYMBOL,
                side=op.side,
                quantity=op.quantity,
                price=trigger_price,
                mode="PAPER",
                entry_price=op.entry_price,
                trading_type=settings.TRADING_TYPE,
                leverage=settings.LEVERAGE,
                order_type="MARKET",
                timestamp=time.time(),
            )
            log.info("[PAPER] SL Order %s: %s %.6f @ %.4f",
                     order_id, op.side, op.quantity, trigger_price)
        else:
            order_event = await self._execute_live_sl(op, trigger_price, order_id)
            if order_event is None:
                return

        event_bus.publish(order_event)
        db_queue.enqueue_order(order_event)
        op.state = "PAST"

        event_bus.publish(StopLossEvent(
            order_id=order_id,
            side=op.side,
            quantity=op.quantity,
            price=trigger_price,
            mode=settings.TRADING_MODE,
        ))

        log.info("SL executed, operation marked PAST: %s", op.order_id)

    # ------------------------------------------------------------------
    # Ejecución de órdenes iniciales
    # ------------------------------------------------------------------

    async def _execute_initial_orders(self) -> None:
        """Ejecuta las órdenes iniciales OC(a) y OV(p)."""
        for op in self._operations:
            if settings.TRADING_MODE == "PAPER":
                order_event = OrderExecutedEvent(
                    order_id=op.order_id,
                    symbol=settings.TRADING_SYMBOL,
                    side=op.side,
                    quantity=op.quantity,
                    price=op.entry_price,
                    mode="PAPER",
                    entry_price=op.entry_price,
                    trading_type=settings.TRADING_TYPE,
                    leverage=settings.LEVERAGE,
                    order_type="MARKET",
                    timestamp=time.time(),
                )
                log.info("[PAPER] Initial order %s: %s %.6f @ %.4f",
                         op.order_id, op.side, op.quantity, op.entry_price)
                event_bus.publish(order_event)
                db_queue.enqueue_order(order_event)

                event_bus.publish(InitialOrderEvent(
                    order_id=op.order_id,
                    side=op.side,
                    quantity=op.quantity,
                    price=op.entry_price,
                ))
            else:
                await self._execute_live_initial(op)

    async def _execute_live_initial(self, op: TradingOperation) -> None:
        """Ejecuta una orden real inicial en Binance."""
        from services.binance_client import create_client, execute_order

        try:
            if not self._client:
                self._client = await create_client()

            if settings.TRADING_TYPE in ("FUTURES", "MARGIN") and not self._leverage_set:
                await self._set_leverage()

            order_params = {
                "symbol": settings.TRADING_SYMBOL,
                "side": op.side,
                "type": "MARKET",
                "quantity": op.quantity,
            }

            response = await execute_order(self._client, **order_params)

            fill_price = float(response.get("fills", [{}])[0].get("price", op.entry_price))

            order_event = OrderExecutedEvent(
                order_id=response.get("orderId", op.order_id),
                symbol=settings.TRADING_SYMBOL,
                side=op.side,
                quantity=op.quantity,
                price=fill_price,
                mode="LIVE",
                entry_price=op.entry_price,
                trading_type=settings.TRADING_TYPE,
                leverage=settings.LEVERAGE,
                order_type="MARKET",
                timestamp=time.time(),
            )
            event_bus.publish(order_event)
            db_queue.enqueue_order(order_event)

        except Exception as exc:
            log.error("Live initial order failed: %s", exc)

    async def _execute_live_sl(
        self, op: TradingOperation, trigger_price: float, order_id: str
    ) -> OrderExecutedEvent | None:
        """Ejecuta una orden de stop loss real en Binance."""
        from services.binance_client import create_client, execute_order

        try:
            if not self._client:
                self._client = await create_client()

            order_params = {
                "symbol": settings.TRADING_SYMBOL,
                "side": op.side,
                "type": "MARKET",
                "quantity": op.quantity,
            }

            response = await execute_order(self._client, **order_params)

            fill_price = float(response.get("fills", [{}])[0].get("price", trigger_price))

            return OrderExecutedEvent(
                order_id=response.get("orderId", order_id),
                symbol=settings.TRADING_SYMBOL,
                side=op.side,
                quantity=op.quantity,
                price=fill_price,
                mode="LIVE",
                entry_price=op.entry_price,
                trading_type=settings.TRADING_TYPE,
                leverage=settings.LEVERAGE,
                order_type="MARKET",
                timestamp=time.time(),
            )

        except Exception as exc:
            log.error("Live SL order failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _publish_update(self, remaining: float = 0.0) -> None:
        """Publica el estado actual de las operaciones."""
        event_bus.publish(OperationUpdateEvent(
            operations=[op.to_event() for op in self._operations],
            timeframe_remaining=remaining,
            timeframe_total=self._timeframe_duration,
            timestamp=time.time(),
        ))

    async def _set_leverage(self) -> None:
        """Configura el leverage para Futures/Margin."""
        try:
            if settings.TRADING_TYPE == "FUTURES":
                await self._client.futures_change_leverage(
                    symbol=settings.TRADING_SYMBOL,
                    leverage=settings.LEVERAGE,
                )
            elif settings.TRADING_TYPE == "MARGIN":
                await self._client.change_margin(
                    symbol=settings.TRADING_SYMBOL,
                    leverage=settings.LEVERAGE,
                )
            self._leverage_set = True
            log.info("Leverage set to %dx for %s", settings.LEVERAGE, settings.TRADING_TYPE)
        except Exception as exc:
            log.error("Failed to set leverage: %s", exc)

    async def _close_client(self) -> None:
        if self._client:
            try:
                await self._client.close_connection()
            except Exception:
                pass
            self._client = None


# Instancia global singleton
bot_engine = BotEngine()
