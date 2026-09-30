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
from dataclasses import dataclass
from typing import Callable, Deque, Literal

from core.event_bus import event_bus
from core.events import (
    BotSignalEvent,
    BotStateChangedEvent,
    InitialOrderEvent,
    OperationInsertedEvent,
    OperationState,
    OperationUpdateEvent,
    OrderCanceledEvent,
    OrderExecutedEvent,
    OrderFailedEvent,
    OrderFillEvent,
    OrderPlacedEvent,
    PriceTickEvent,
    PositionUpdateEvent,
    SettingsUpdatedEvent,
    StopLossEvent,
    TimeframeCycleEvent,
    TradingLifecycleEvent,
)
from config.settings import settings
from database.db_queue import db_queue
from services.order_executor import (
    OrderExecutor,
    OrderPlacement,
    OrderRequest,
    create_executor,
    generate_order_id,
    is_limit_crossed,
)
from services.pnl_calculator import PnLCalculator

log = logging.getLogger(__name__)


@dataclass
class WorkingOrder:
    """Orden LIMIT colocada y aún sin llenar (working).

    Vive en BotEngine._working_orders — la única fuente de verdad de
    órdenes en vuelo, compartida por ambas fuentes de fill (user stream
    LIVE y cruce de ticks PAPER).
    """
    order_id: str                      # clientOrderId (id canónico)
    operation: TradingOperation        # referencia a la operación OC/OV
    symbol: str
    side: str
    quantity: float
    limit_price: float
    mode: str                          # "PAPER" | "LIVE"
    success_event_factory: Callable | None = None


class TradingOperation:
    """Modelo interno de una operación individual.

    State Pattern: las transiciones de estado son validadas centralizadamente.
    """

    # Transiciones válidas: PENDING → ACTIVE → PAST (estado terminal)
    _VALID_TRANSITIONS: dict[str, frozenset[str]] = {
        "PENDING": frozenset({"ACTIVE", "PAST"}),
        "ACTIVE": frozenset({"PAST"}),
        "PAST": frozenset(),
    }

    def __init__(
        self,
        side: Literal["BUY", "SELL"],
        state: Literal["ACTIVE", "PENDING", "PAST"],
        entry_price: float,
        stop_loss: float,
        quantity: float,
        order_id: str,
        entry_filled: bool = False,
    ) -> None:
        self.side = side
        self.state = state
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.quantity = quantity
        self.order_id = order_id
        self.created_at = time.time()
        self.best_sl = stop_loss  # Mejor SL alcanzado (para trailing stop)
        # False mientras la orden de entrada siga working (sin posición:
        # SL/PnL no aplican hasta el fill)
        self.entry_filled = entry_filled

    def transition_to(self, new_state: str) -> bool:
        """Transición de estado validada. Retorna False si es inválida."""
        allowed = self._VALID_TRANSITIONS.get(self.state, frozenset())
        if new_state not in allowed:
            log.warning(
                "Invalid state transition %s → %s for %s (skipped)",
                self.state, new_state, self.order_id,
            )
            return False
        self.state = new_state
        return True

    def promote_to_active(self) -> bool:
        """PENDING → ACTIVE: promoción de pendiente a operación activa."""
        return self.transition_to("ACTIVE")

    def mark_as_past(self) -> bool:
        """ACTIVE/PENDING → PAST: operación completada."""
        return self.transition_to("PAST")

    def to_event(self) -> OperationState:
        return OperationState(
            side=self.side,
            state=self.state,
            entry_price=self.entry_price,
            stop_loss=self.stop_loss,
            quantity=self.quantity,
            order_id=self.order_id,
            entry_filled=self.entry_filled,
            timestamp=self.created_at,
        )


class BotEngine:
    """Motor de trading con modelo dual OC/OV."""

    # Throttle: mínimo intervalo entre position updates (segundos)
    _POSITION_UPDATE_MIN_INTERVAL: float = 2.0
    # Throttle: delta mínimo de PnL para forzar update
    _POSITION_PNL_DELTA_THRESHOLD: float = 0.001  # 0.1%

    def __init__(self, executor: OrderExecutor | None = None) -> None:
        self._running: bool = False
        self._active: bool = False
        self._current_price: float = 0.0
        self._executor: OrderExecutor | None = executor  # Se crea en start() (Fase 3)

        # Operaciones
        self._operations: list[TradingOperation] = []

        # Órdenes LIMIT working (id canónico → WorkingOrder).
        # Única fuente de verdad de fills: pop() idempotente := "primer ganador".
        self._working_orders: dict[str, WorkingOrder] = {}

        # MA Buffer (para indicador visual — no afecta operaciones OC/OV)
        self._price_buffer: Deque[float] = deque()
        self._last_signal: str = "HOLD"

        # Timer de temporalidad
        self._timeframe_task: asyncio.Task | None = None
        self._timeframe_start: float = 0.0
        self._timeframe_duration: float = 0.0  # segundos

        # Throttle de position updates
        self._last_position_update_time: float = 0.0
        self._last_position_pnl: float = 0.0

        # Tracking de tareas de stop loss (para cleanup al detener)
        self._sl_tasks: set[asyncio.Task] = set()

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

        # Fase 3: crear executor aquí (después de settings.load_from_db())
        if self._executor is None:
            self._executor = create_executor(settings.TRADING_MODE)

        event_bus.subscribe(PriceTickEvent, self._on_price_tick)
        event_bus.subscribe(BotStateChangedEvent, self._on_bot_state_changed)
        event_bus.subscribe(SettingsUpdatedEvent, self._on_settings_updated)
        event_bus.subscribe(OrderFillEvent, self._on_order_fill)

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

        # Cancelar órdenes LIMIT working ANTES de cerrar el executor
        if self._working_orders:
            await self._cancel_working_orders(lambda w: True, "engine_stop")

        self._stop_timeframe_timer()
        self._operations.clear()

        # Cancelar tareas de SL pendientes
        for task in self._sl_tasks:
            task.cancel()
        self._sl_tasks.clear()

        event_bus.unsubscribe(PriceTickEvent, self._on_price_tick)
        event_bus.unsubscribe(BotStateChangedEvent, self._on_bot_state_changed)
        event_bus.unsubscribe(SettingsUpdatedEvent, self._on_settings_updated)
        event_bus.unsubscribe(OrderFillEvent, self._on_order_fill)
        if self._executor is not None:
            await self._executor.close()
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

        # Fill de órdenes LIMIT PAPER por cruce de precio (event-driven,
        # impulsado por PriceTickEvent — sin polling). Debe ir ANTES del
        # trailing/SL: si el fill abre posición, el SL del mismo tick aplica.
        if settings.TRADING_MODE == "PAPER":
            self._check_limit_fills(event.price)

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
            # Iniciar trading — solo activar si realmente arrancó
            started = await self._start_trading()
            self._active = started
            log.info("BotEngine active: %s | mode: %s", self._active, event.mode)
            return
        elif not event.is_running and self._active:
            # Detener trading
            await self._stop_trading()

        self._active = event.is_running
        log.info("BotEngine active: %s | mode: %s", self._active, event.mode)

    async def _on_settings_updated(self, event: SettingsUpdatedEvent) -> None:
        """Recarga parámetros de estrategia, recrea executor si cambió el modo,
        y invalida leverage si cambió leverage o símbolo."""
        old_mode = settings.TRADING_MODE
        old_leverage = settings.LEVERAGE
        old_symbol = settings.TRADING_SYMBOL
        old_trading_type = settings.TRADING_TYPE
        old_order_type = settings.ORDER_TYPE
        old_limit_price = settings.LIMIT_PRICE

        # Cancelar órdenes LIMIT working ANTES de aplicar los nuevos settings
        # (el cancel de LIVE usa settings.TRADING_SYMBOL — debe seguir siendo
        # el símbolo con el que se colocó la orden)
        settings_invalidated = (
            event.order_type != old_order_type
            or event.limit_price != old_limit_price
            or event.symbol != old_symbol
            or event.trading_type != old_trading_type
            or event.mode != old_mode
        )
        if settings_invalidated and self._working_orders:
            await self._cancel_working_orders(
                lambda w: True, "settings_changed",
            )

        settings.from_event(event)

        # Recrear executor si PAPER ↔ LIVE cambió
        if event.mode != old_mode and self._executor is not None:
            await self._executor.close()
            self._executor = create_executor(event.mode)
            log.info("Executor recreated: %s → %s", old_mode, event.mode)

        # Re-aplicar leverage en Binance si cambió leverage o símbolo
        if (
            (event.leverage != old_leverage or event.symbol != old_symbol)
            and self._executor is not None
        ):
            self._executor.invalidate_leverage()
            log.info(
                "Leverage invalidated: %dx → %dx | symbol: %s → %s",
                old_leverage, event.leverage, old_symbol, event.symbol,
            )

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
        """Publica PositionUpdateEvent para cada operación activa con throttle."""
        now = time.time()
        elapsed = now - self._last_position_update_time

        # Calcular PnL total actual (solo ops con posición real: entry filled)
        total_pnl = 0.0
        for op in self._operations:
            if op.state == "ACTIVE" and op.entry_filled:
                pnl = PnLCalculator.calc_unrealized_pnl(
                    capital=settings.TRADE_AMOUNT,
                    entry_price=op.entry_price,
                    stop_loss=op.stop_loss,
                    side=op.side,
                )
                total_pnl += pnl

        # Throttle: solo publicar si pasó el intervalo mínimo O el PnL cambió significativamente
        pnl_delta = abs(total_pnl - self._last_position_pnl)
        pnl_threshold = abs(self._last_position_pnl) * self._POSITION_PNL_DELTA_THRESHOLD

        if elapsed < self._POSITION_UPDATE_MIN_INTERVAL and pnl_delta < pnl_threshold:
            return

        self._last_position_update_time = now
        self._last_position_pnl = total_pnl

        for op in self._operations:
            if op.state != "ACTIVE" or not op.entry_filled:
                continue

            if op.side == "BUY":
                side = "LONG"
            else:
                side = "SHORT"

            unrealized_pnl = PnLCalculator.calc_unrealized_pnl(
                capital=settings.TRADE_AMOUNT,
                entry_price=op.entry_price,
                stop_loss=op.stop_loss,
                side=op.side,
            )

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

    async def _start_trading(self) -> bool:
        """Inicia las operaciones duales: OC(a) + OV(p). Retorna True si arrancó."""
        if self._current_price <= 0:
            log.warning("No price available yet. Waiting for first tick...")
            event_bus.publish(OrderFailedEvent(
                operation_id="STARTUP",
                side="BUY",
                error="No price available yet — bot activado sin precio",
                mode=settings.TRADING_MODE,
            ))
            return False

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
        return True

    async def _stop_trading(self) -> None:
        """Detiene trading: cancela órdenes working, cierra posiciones y apaga timer."""
        self._stop_timeframe_timer()

        # Cancelar órdenes LIMIT working ANTES de cerrar posiciones
        # (las ops sin fill no se cierran: no hay posición)
        if self._working_orders:
            await self._cancel_working_orders(lambda w: True, "bot_stop")

        # Cerrar posiciones abiertas
        await self._close_open_positions()

        # Eliminar operaciones pendientes
        self._operations = [op for op in self._operations if op.state == "ACTIVE"]

        # Marcar activas como past (State Pattern: transición validada)
        for op in self._operations:
            op.mark_as_past()

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

        # 3. Eliminar TODAS las operaciones PENDING (y cancelar sus órdenes
        #    LIMIT working asociadas — sus operaciones dejan de existir)
        discarded_ids = {
            op.order_id for op in self._operations if op.state == "PENDING"
        }
        self._operations = [op for op in self._operations if op.state != "PENDING"]
        if discarded_ids:
            await self._cancel_working_orders(
                lambda w: w.operation.order_id in discarded_ids,
                "timeframe_expired",
            )

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
            if not op.entry_filled:
                # Sin fill de entrada no hay posición: el SL no aplica aún
                continue

            triggered = False
            if op.side == "BUY" and price <= op.stop_loss:
                triggered = True
            elif op.side == "SELL" and price >= op.stop_loss:
                triggered = True

            if triggered:
                log.info("STOP LOSS triggered: %s @ %.4f (SL=%.4f)",
                         op.side, price, op.stop_loss)
                task = asyncio.create_task(
                    self._execute_stop_loss(op, price),
                    name=f"sl_{op.side}_{int(time.time())}",
                )
                self._sl_tasks.add(task)
                task.add_done_callback(self._sl_tasks.discard)

    async def _execute_stop_loss(self, op: TradingOperation, trigger_price: float) -> None:
        """Ejecuta la orden de stop loss (EXIT → siempre MARKET) y promueve."""
        order_event = await self._dispatch_order(
            op, trigger_price,
            success_event_factory=lambda e: StopLossEvent(
                order_id=e.order_id,
                side=op.side,
                quantity=op.quantity,
                price=trigger_price,
                mode=settings.TRADING_MODE,
            ),
            purpose="EXIT",
        )
        if order_event is None:
            return

        # State Pattern: transición validada ACTIVE → PAST
        op.mark_as_past()

        # Fase 1: promover PENDING → ACTIVE
        promoted = self._promote_pending_to_active()
        if promoted:
            # Ejecutar la entrada de la nueva ACTIVE (puede quedar working)
            await self._dispatch_order(promoted, purpose="ENTRY")
            self._publish_update()

        log.info("SL executed, operation marked PAST: %s", op.order_id)

    def _promote_pending_to_active(self) -> TradingOperation | None:
        """Promueve la primera PENDING a ACTIVE (State Pattern).

        Retorna la operación promovida o None si no hay PENDING.
        """
        for op in self._operations:
            if op.state == "PENDING" and op.promote_to_active():
                log.info("PENDING promoted to ACTIVE: %s", op.order_id)
                return op
        return None

    # ------------------------------------------------------------------
    # Ejecución de órdenes (Template Method + DIP)
    # ------------------------------------------------------------------

    def _build_order_request(
        self,
        op: TradingOperation,
        price: float,
        purpose: str,
        market_price: float,
    ) -> OrderRequest:
        """Único punto de decisión MARKET vs LIMIT (DRY).

        ENTRY usa settings.ORDER_TYPE (LIMIT solo si LIMIT_PRICE > 0).
        EXIT (stop loss / cierre manual) es siempre MARKET por urgencia.
        """
        order_type = "MARKET"
        limit_price = 0.0
        if (
            purpose == "ENTRY"
            and settings.ORDER_TYPE == "LIMIT"
            and settings.LIMIT_PRICE > 0
        ):
            order_type = "LIMIT"
            limit_price = settings.LIMIT_PRICE

        # 2a: la orden de cierre usa el lado OPUESTO al de la operación
        # (cerrar un BUY = SELL; cerrar un SELL = BUY). Evita duplicar
        # posición en vez de cerrarla.
        side = op.side
        if purpose == "EXIT":
            side = "SELL" if op.side == "BUY" else "BUY"

        prefix = "PAPER" if settings.TRADING_MODE == "PAPER" else "LIVE"
        return OrderRequest(
            symbol=settings.TRADING_SYMBOL,
            side=side,
            quantity=op.quantity,
            order_type=order_type,
            price=limit_price,
            entry_price=op.entry_price if price == 0 else price,
            stop_loss=op.stop_loss,
            client_order_id=generate_order_id(prefix),
            market_price=market_price,
        )

    def _build_order_event(
        self, op: TradingOperation, placement: OrderPlacement,
        request: OrderRequest, purpose: str,
    ) -> OrderExecutedEvent:
        """Factory method para OrderExecutedEvent (DRY).

        `request.side` es el lado EFECTIVO de la orden (invertido en EXIT),
        distinto de `op.side` (lado de la operación). `purpose` distingue
        apertura/cierre para que paper_balance no acredite cierres como ventas.
        """
        return OrderExecutedEvent(
            order_id=placement.order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=op.quantity,
            price=placement.fill_price,
            mode=placement.mode,
            entry_price=op.entry_price,
            stop_loss=op.stop_loss,
            trading_type=settings.TRADING_TYPE,
            leverage=settings.LEVERAGE,
            order_type=request.order_type,
            limit_price=request.price if request.order_type == "LIMIT" else 0.0,
            operation_id=op.order_id,  # OC-xxx / OV-xxx (Fase 4)
            purpose=purpose,
            timestamp=time.time(),
        )

    async def _dispatch_order(
        self,
        op: TradingOperation,
        price: float = 0.0,
        success_event_factory=None,
        purpose: str = "EXIT",
    ) -> OrderExecutedEvent | None:
        """Template Method: ejecuta → registra/publica → persiste → maneja errores.

        Elimina la duplicación de execute+publish+enqueue en los 4 call sites.
        En caso de fallo publica OrderFailedEvent (nunca silencioso).

        Args:
            op: Operación a ejecutar.
            price: Precio de fill forzado (0 = usar entry_price).
            success_event_factory: Callable opcional que recibe OrderExecutedEvent
                                   y retorna un evento extra (StopLossEvent, etc.).
                                   Para LIMIT working se difiere hasta el fill.
            purpose: "ENTRY" (aplica ORDER_TYPE) | "EXIT" (siempre MARKET).

        Returns:
            OrderExecutedEvent si quedó FILLED, None si falló o si quedó
            working (LIMIT NEW — el fill llega después por OrderFillEvent).
        """
        if self._executor is None:
            event_bus.publish(OrderFailedEvent(
                operation_id=op.order_id,
                side=op.side,
                error="Executor not initialized",
                mode=settings.TRADING_MODE,
            ))
            return None

        request = self._build_order_request(op, price, purpose, self._current_price)
        try:
            placement = await self._executor.execute(request)
        except Exception as exc:
            log.error("Order execution failed: %s", exc)
            event_bus.publish(OrderFailedEvent(
                operation_id=op.order_id,
                side=op.side,
                error=str(exc),
                mode=settings.TRADING_MODE,
            ))
            return None

        # INVARIANTE: registrar ANTES de cualquier await. Tras execute()
        # este bloque corre síncrono hasta el siguiente await, cerrando la
        # ventana fill-vs-registro (los handlers del bus corren en tasks
        # paralelas y solo se intercalan cuando este task hace await).
        if placement.status == "NEW":
            self._working_orders[placement.order_id] = WorkingOrder(
                order_id=placement.order_id,
                operation=op,
                symbol=request.symbol,
                side=op.side,
                quantity=op.quantity,
                limit_price=request.price,
                mode=placement.mode,
                success_event_factory=success_event_factory,
            )
            placed_event = OrderPlacedEvent(
                order_id=placement.order_id,
                operation_id=op.order_id,
                symbol=request.symbol,
                side=op.side,
                quantity=op.quantity,
                price=request.price,
                mode=placement.mode,
            )
            event_bus.publish(placed_event)
            db_queue.enqueue_order_placed(placed_event)
            self._publish_update()
            log.info(
                "LIMIT working: %s %s @ %.4f",
                op.side, placement.order_id, request.price,
            )
            return None

        if purpose == "ENTRY":
            op.entry_filled = True

        order_event = self._build_order_event(op, placement, request, purpose)
        event_bus.publish(order_event)
        db_queue.enqueue_order(order_event)

        if success_event_factory is not None:
            event_bus.publish(success_event_factory(order_event))

        return order_event

    # ------------------------------------------------------------------
    # Ciclo de vida de órdenes LIMIT (fill / cancel — event-driven)
    # ------------------------------------------------------------------

    async def _on_order_fill(self, event: OrderFillEvent) -> None:
        """Handler del bus: notificaciones crudas del user stream (LIVE)."""
        if event.status == "FILLED":
            self._complete_limit_fill(event)
        else:
            self._complete_exchange_cancel(event)

    def _complete_limit_fill(self, fill: OrderFillEvent) -> None:
        """Convierte un fill crudo en OrderExecutedEvent (camino único PAPER/LIVE).

        Síncrono a propósito: pop + mutaciones sin await = atómico en el
        event loop; fills duplicados son idempotentes (pop → None).
        """
        working = self._working_orders.pop(fill.order_id, None)
        if working is None:
            log.info("OrderFillEvent ignored (unknown/finished): %s", fill.order_id)
            return

        op = working.operation
        if op.state != "PAST":
            op.entry_filled = True
        else:
            log.warning(
                "Fill for PAST operation %s — position tracked by balance",
                op.order_id,
            )

        # 2d: las working orders solo son ENTRY por diseño (EXIT es siempre
        # MARKET y nunca queda NEW), así que el fill siempre abre posición.
        order_event = OrderExecutedEvent(
            order_id=fill.order_id,
            symbol=working.symbol,
            side=op.side,
            quantity=working.quantity,
            price=fill.price,
            mode=fill.mode,
            entry_price=op.entry_price,
            stop_loss=op.stop_loss,
            trading_type=settings.TRADING_TYPE,
            leverage=settings.LEVERAGE,
            order_type="LIMIT",
            limit_price=working.limit_price,
            operation_id=op.order_id,
            purpose="ENTRY",
            timestamp=fill.timestamp,
        )
        event_bus.publish(order_event)
        db_queue.enqueue_order(order_event)

        if working.success_event_factory is not None:
            event_bus.publish(working.success_event_factory(order_event))

        self._publish_update()
        log.info(
            "LIMIT fill: %s %s @ %.4f (op=%s)",
            op.side, fill.order_id, fill.price, op.order_id,
        )

    def _complete_exchange_cancel(self, fill: OrderFillEvent) -> None:
        """Cancelación detectada en el exchange (CANCELED en executionReport)."""
        working = self._working_orders.pop(fill.order_id, None)
        if working is None:
            return
        cancelled_event = OrderCanceledEvent(
            order_id=fill.order_id,
            operation_id=working.operation.order_id,
            reason="exchange_canceled",
            mode=fill.mode,
        )
        event_bus.publish(cancelled_event)
        db_queue.enqueue_order_canceled(cancelled_event)
        self._publish_update()
        log.info("Exchange canceled order: %s", fill.order_id)

    def _check_limit_fills(self, price: float) -> None:
        """PAPER: completa los fills cuyo límite fue cruzado por el tick.

        Impulsado por PriceTickEvent (push, sin polling). Usa la misma
        función pura is_limit_crossed que PaperExecutor (DRY).
        """
        if not self._working_orders:
            return
        crossed = [
            (oid, w) for oid, w in self._working_orders.items()
            if is_limit_crossed(w.side, w.limit_price, price)
        ]
        for oid, w in crossed:
            self._complete_limit_fill(OrderFillEvent(
                order_id=oid,
                status="FILLED",
                price=w.limit_price,
                quantity=w.quantity,
                mode="PAPER",
                source="PAPER_TICK",
            ))

    async def _cancel_working_orders(
        self,
        predicate: Callable[[WorkingOrder], bool],
        reason: str,
    ) -> int:
        """Cancela órdenes working que cumplan predicate (DRY — único punto).

        LIVE: cancela en el exchange ANTES del pop. Si el fill gana la
        carrera durante el await, el fill hace pop primero y esta
        cancelación se vuelve no-op (el fill nunca se pierde). Si el
        exchange rechaza, la orden queda registrada a la espera de su
        fill/cancel real.
        """
        targets = [
            (oid, w) for oid, w in self._working_orders.items() if predicate(w)
        ]
        cancelled = 0
        for oid, w in targets:
            if w.mode == "LIVE" and self._executor is not None:
                try:
                    await self._executor.cancel(oid)
                except Exception as exc:
                    log.warning(
                        "Cancel failed for %s (%s) — leaving registered",
                        oid, exc,
                    )
                    continue

            if self._working_orders.pop(oid, None) is None:
                continue  # el fill ganó la carrera durante el await

            cancelled_event = OrderCanceledEvent(
                order_id=oid,
                operation_id=w.operation.order_id,
                reason=reason,
                mode=w.mode,
            )
            event_bus.publish(cancelled_event)
            db_queue.enqueue_order_canceled(cancelled_event)
            cancelled += 1

        if cancelled:
            self._publish_update()
            log.info("Cancelled %d working LIMIT orders (%s)", cancelled, reason)
        return cancelled

    async def _execute_initial_orders(self) -> None:
        """Ejecuta las órdenes iniciales OC(a) y OV(p) (ENTRY)."""
        for op in self._operations:
            await self._dispatch_order(
                op,
                success_event_factory=lambda e, _op=op: InitialOrderEvent(
                    order_id=e.order_id,
                    side=_op.side,
                    quantity=_op.quantity,
                    price=e.price,
                ),
                purpose="ENTRY",
            )

    async def _close_open_positions(self) -> None:
        """Cierra todas las posiciones abiertas al detener el bot."""
        for op in self._operations:
            if op.state != "ACTIVE":
                continue
            if not op.entry_filled:
                # Sin fill no hay posición que cerrar (solo había orden
                # working — ya cancelada por el caller)
                continue

            log.info("Closing position: %s %s", op.side, op.order_id)

            # 2c: pasar el op ORIGINAL (no un close_op con prefijo CLOSE-).
            # Así event.operation_id == op.order_id y paper_balance encuentra
            # la posición por su clave (OC-/OV-). El lado lo invierte
            # _build_order_request(vía purpose="EXIT").
            await self._dispatch_order(op, self._current_price, purpose="EXIT")

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


# Instancia global singleton
bot_engine = BotEngine()
