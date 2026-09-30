"""
Binance Service — WebSocket y REST async.

Responsabilidades:
- Conectar al stream <symbol>@ticker vía BinanceSocketManager
- Publicar PriceTickEvent al EventBus en cada mensaje recibido
- Publicar ConnectionStatusEvent en cada cambio de estado
- Reconexión automática con backoff exponencial
- Suscribirse a SettingsUpdatedEvent para reconectar con nuevo símbolo/keys
- Soportar Spot, Futures y Cross Margin según TRADING_TYPE
- Consultar y publicar saldos de cuenta (auto-refresh)

En PAPER mode sin API keys: usa un simulador de ticks (MockTickGenerator).
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
import time

from core.event_bus import event_bus
from core.events import (
    BalanceUpdateEvent,
    ConnectionStatusEvent,
    ConnectionStatusRequestEvent,
    ConnectionStatusSnapshotEvent,
    OrderFillEvent,
    PriceTickEvent,
    SettingsUpdatedEvent,
    SymbolsListEvent,
)
from config.settings import settings
from database.db_queue import db_queue

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mock Tick Generator (cuando no hay API keys)
# ---------------------------------------------------------------------------

class MockTickGenerator:
    """Simula un stream de ticks de precio para desarrollo/paper trading."""

    _BASE_PRICES: dict[str, float] = {
        "BTCUSDT": 65_000.0,
        "ETHUSDT": 3_500.0,
        "BNBUSDT": 600.0,
        "SOLUSDT": 150.0,
        "XRPUSDT": 0.60,
        "ADAUSDT": 0.45,
        "DOGEUSDT": 0.12,
    }

    def __init__(self) -> None:
        self._base_price = 65_000.0
        self._tick_count = 0

    def reset_for_symbol(self, symbol: str) -> None:
        """Reset del precio base al cambiar de símbolo."""
        self._base_price = self._BASE_PRICES.get(symbol, 100.0)
        self._tick_count = 0

    def next_tick(self, symbol: str) -> PriceTickEvent:
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
        self._user_stream_task: asyncio.Task | None = None
        self._client = None
        self._mock = MockTickGenerator()
        self._retry_count: int = 0
        self._connection_status: str = "DISCONNECTED"

        # Balance auto-refresh
        self._balance_task: asyncio.Task | None = None
        self._balance_interval: float = 30.0  # segundos

        # Cache de símbolos (por mercado + moneda)
        self._symbols_cache: dict[str, list[dict]] = {}
        self._symbols_cache_time: dict[str, float] = {}

        # Cache de saldo
        self._balance_cache: BalanceUpdateEvent | None = None
        self._balance_cache_time: float = 0.0

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._retry_count = 0
        event_bus.subscribe(SettingsUpdatedEvent, self._on_settings_updated)
        event_bus.subscribe(ConnectionStatusRequestEvent, self._on_status_request)
        self._stream_task = asyncio.create_task(
            self._run_with_reconnect(self._run_ticker_stream), name="binance_stream"
        )
        self._start_user_stream()
        self._start_balance_loop()
        log.info("BinanceService starting for symbol: %s", settings.TRADING_SYMBOL)

    def _start_user_stream(self) -> None:
        """Arranca el user data stream solo en LIVE con API keys (Q3a)."""
        if not (settings.TRADING_MODE == "LIVE" and settings.has_api_keys()):
            return
        self._user_stream_task = asyncio.create_task(
            self._run_with_reconnect(self._run_user_stream, publish_status=False),
            name="binance_user_stream",
        )
        log.info("User data stream task started (%s)", settings.TRADING_TYPE)

    async def _stop_user_stream(self) -> None:
        if self._user_stream_task:
            self._user_stream_task.cancel()
            try:
                await self._user_stream_task
            except asyncio.CancelledError:
                pass
            self._user_stream_task = None

    async def stop(self) -> None:
        self._running = False
        event_bus.unsubscribe(SettingsUpdatedEvent, self._on_settings_updated)
        event_bus.unsubscribe(ConnectionStatusRequestEvent, self._on_status_request)
        self._stop_balance_loop()
        await self._stop_user_stream()
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
        await self._close_client()
        log.info("BinanceService stopped")

    # ------------------------------------------------------------------
    # Estado de conexión (para ConnectionIndicator)
    # ------------------------------------------------------------------

    async def _on_status_request(self, event: ConnectionStatusRequestEvent) -> None:
        """Responde con el estado actual de conexión."""
        event_bus.publish(ConnectionStatusSnapshotEvent(
            status=self._connection_status,
            message=self._get_status_message(),
        ))

    def _get_status_message(self) -> str:
        """Genera el mensaje según el estado actual."""
        messages = {
            "CONNECTING":   f"Conectando a {settings.TRADING_SYMBOL}...",
            "CONNECTED":    f"Conectado a {settings.TRADING_SYMBOL} ({settings.TRADING_TYPE})",
            "DISCONNECTED": "Desconectado",
            "RECONNECTING": f"Reintentando... (intento {self._retry_count})",
        }
        return messages.get(self._connection_status, self._connection_status)

    async def restart(self) -> None:
        """Reinicia el servicio (usado tras cambio de configuración)."""
        await self.stop()
        self._balance_cache = None
        self._balance_cache_time = 0.0
        self._running = True
        self._retry_count = 0
        event_bus.subscribe(SettingsUpdatedEvent, self._on_settings_updated)
        # Fix: stop() desuscribe ConnectionStatusRequestEvent — re-suscribir
        # aquí, si no, cualquier cambio de settings rompe el snapshot del
        # ConnectionIndicator.
        event_bus.subscribe(ConnectionStatusRequestEvent, self._on_status_request)
        self._start_balance_loop()
        self._stream_task = asyncio.create_task(
            self._run_with_reconnect(self._run_ticker_stream), name="binance_stream"
        )
        self._start_user_stream()

    # ------------------------------------------------------------------
    # Loop con reconexión automática (backoff exponencial)
    # ------------------------------------------------------------------

    async def _run_ticker_stream(self) -> None:
        """Selecciona live/mock según modo y keys (un solo punto de ramificación)."""
        if settings.TRADING_MODE == "LIVE" and settings.has_api_keys():
            await self._run_live_stream()
        else:
            await self._run_mock_stream()

    async def _run_with_reconnect(
        self,
        runner,
        *,
        publish_status: bool = True,
    ) -> None:
        """Loop de reconexión genérico (DRY) para ticker y user stream.

        Cada task mantiene su propio contador de reintentos (los loops no
        interfieren entre sí). `publish_status=False` evita que el user
        stream pise el estado de conexión del ticker en la UI.
        """
        retry = 0
        while self._running:
            try:
                if publish_status:
                    self._connection_status = "CONNECTING"
                    event_bus.publish(ConnectionStatusEvent(
                        status="CONNECTING",
                        message=f"Conectando a {settings.TRADING_SYMBOL}..."
                    ))
                await runner()
                # Si llegamos aquí es porque el stream terminó normalmente
                retry = 0

            except asyncio.CancelledError:
                break
            except Exception as exc:
                retry += 1
                if publish_status:
                    self._retry_count = retry
                delay = min(
                    settings.RECONNECT_BASE_DELAY ** retry,
                    60.0
                )
                log.error(
                    "%s error (retry %d): %s. Waiting %.1fs...",
                    getattr(runner, "__name__", "stream"), retry, exc, delay
                )
                if publish_status:
                    self._connection_status = "RECONNECTING"
                    event_bus.publish(ConnectionStatusEvent(
                        status="RECONNECTING",
                        message=f"Reintentando en {delay:.0f}s... (intento {retry})"
                    ))
                if retry > settings.RECONNECT_MAX_RETRIES:
                    log.critical(
                        "Max retries exceeded for %s. Stopping.",
                        getattr(runner, "__name__", "stream"),
                    )
                    if publish_status:
                        self._connection_status = "DISCONNECTED"
                        event_bus.publish(ConnectionStatusEvent(
                            status="DISCONNECTED",
                            message="Máximo de reintentos alcanzado."
                        ))
                    break
                await asyncio.sleep(delay)

    # ------------------------------------------------------------------
    # Stream real (Binance WebSocket) — según TRADING_TYPE
    # ------------------------------------------------------------------

    async def _run_live_stream(self) -> None:
        from binance import BinanceSocketManager  # type: ignore
        from binance.exceptions import BinanceAPIException, BinanceRequestException  # type: ignore
        from services.binance_client import create_client

        try:
            self._client = await create_client()

            # Validar símbolo en el mercado seleccionado (SRP: validación separada)
            if not await self._validate_symbol(self._client):
                return

            log.info(
                "Creating %s stream for %s...",
                settings.TRADING_TYPE, settings.TRADING_SYMBOL,
            )

            bm = BinanceSocketManager(self._client)
            symbol_lower = settings.TRADING_SYMBOL.lower()

            # Seleccionar stream según TRADING_TYPE (OCP: un solo punto de ramificación)
            if settings.TRADING_TYPE == "FUTURES":
                stream_context = bm.individual_symbol_ticker_futures_socket(symbol_lower)
            else:  # SPOT / MARGIN
                stream_context = bm.symbol_ticker_socket(symbol_lower)

            async with stream_context as ts:
                self._connection_status = "CONNECTED"
                event_bus.publish(ConnectionStatusEvent(
                    status="CONNECTED",
                    message=f"Conectado a {settings.TRADING_SYMBOL} ({settings.TRADING_TYPE})"
                ))
                log.info("WebSocket connected: %s@ticker (%s)", symbol_lower, settings.TRADING_TYPE)

                while self._running:
                    try:
                        msg = await asyncio.wait_for(ts.recv(), timeout=15.0)
                    except asyncio.TimeoutError:
                        log.warning("No messages in 15s for %s. Stream may be silent.", settings.TRADING_SYMBOL)
                        continue

                    if msg.get("e") == "error":
                        raise Exception(f"WS Error: {msg}")

                    log.debug("Raw WS msg: %s", msg)

                    # Futures messages are wrapped: {"stream": "...", "data": {...}}
                    if "data" in msg:
                        msg = msg["data"]

                    tick = self._parse_binance_ticker(msg)
                    event_bus.publish(tick)
                    db_queue.enqueue_tick(tick)

        except (BinanceAPIException, BinanceRequestException) as exc:
            log.error("Binance API exception (%s): %s", settings.TRADING_TYPE, exc)
            raise
        except Exception as exc:
            log.error("Stream error (%s): %s", settings.TRADING_TYPE, exc)
            raise
        finally:
            await self._close_client()

    # ------------------------------------------------------------------
    # User data stream — fills de órdenes LIMIT en LIVE (Q3a)
    # ------------------------------------------------------------------

    async def _run_user_stream(self) -> None:
        """User data stream (executionReport) → OrderFillEvent.

        Event-driven: la librería gestiona listenKey/keepalive internamente
        (python-binance, sin timers ni polls nuestros — CERO POLLING).
        Cliente propio y local: no comparte self._client con el ticker.
        """
        from binance import BinanceSocketManager  # type: ignore
        from services.binance_client import create_client

        client = await create_client()
        try:
            bm = BinanceSocketManager(client)

            # OCP: un solo punto de ramificación por mercado
            if settings.TRADING_TYPE == "FUTURES":
                stream_context = bm.futures_user_socket()
            elif settings.TRADING_TYPE == "MARGIN":
                stream_context = bm.margin_socket()
            else:  # SPOT
                stream_context = bm.user_socket()

            async with stream_context as ts:
                log.info(
                    "User data stream connected (%s, %s)",
                    settings.TRADING_TYPE, settings.TRADING_SYMBOL,
                )
                while self._running:
                    try:
                        msg = await asyncio.wait_for(ts.recv(), timeout=15.0)
                    except asyncio.TimeoutError:
                        continue  # keepalive interno de la librería

                    if msg.get("e") == "error":
                        raise Exception(f"User WS error: {msg}")

                    if "data" in msg:
                        msg = msg["data"]

                    fill = self._parse_execution_report(msg)
                    if fill is not None:
                        event_bus.publish(fill)
                        log.info(
                            "User stream: %s %s @ %.4f",
                            fill.status, fill.order_id, fill.price,
                        )
        finally:
            try:
                await client.close_connection()
            except Exception:
                pass

    @staticmethod
    def _parse_execution_report(msg: dict) -> OrderFillEvent | None:
        """Parsea un executionReport a OrderFillEvent (función pura — testeable).

        Campos Binance: e=evento, c=clientOrderId, X=status, ap=avgPrice
        (futures), L=last fill price, z=cumulative qty, Z=cumulative quote.
        Solo interesan FILLED/CANCELED: NEW/PARTIALLY_FILLED se ignoran
        (un fill parcial no abre posición completa).
        """
        if msg.get("e") != "executionReport":
            return None

        client_order_id = str(msg.get("c") or "")
        if not client_order_id:
            return None

        status_raw = str(msg.get("X") or "")
        if status_raw == "FILLED":
            status = "FILLED"
        elif status_raw in ("CANCELED", "EXPIRED", "REJECTED"):
            status = "CANCELED"
        else:
            return None  # NEW / PARTIALLY_FILLED

        avg = float(msg.get("ap", 0) or 0)
        if avg <= 0:
            executed = float(msg.get("z", 0) or 0)
            cumulative = float(msg.get("Z", 0) or 0)
            if executed > 0 and cumulative > 0:
                avg = cumulative / executed
        if avg <= 0:
            avg = float(msg.get("L", 0) or 0)

        quantity = float(msg.get("z", 0) or 0) or float(msg.get("q", 0) or 0)

        return OrderFillEvent(
            order_id=client_order_id,
            status=status,
            price=avg,
            quantity=quantity,
            mode="LIVE",
            source="USER_STREAM",
        )

    @staticmethod
    def _normalize_price(ticker: dict, trading_type: str) -> str:
        """Extrae el precio de un ticker según el mercado (DRY)."""
        if trading_type == "FUTURES":
            return ticker.get("lastPrice", "0.00000000")
        return ticker.get("price", "0.00000000")

    @staticmethod
    async def validate_symbol_for_market(
        client, symbol: str, trading_type: str,
    ) -> tuple[bool, list[str]]:
        """Valida si un símbolo existe en un mercado. Retorna (existe, disponibles)."""
        symbol_upper = symbol.upper()
        try:
            if trading_type == "FUTURES":
                info = await client.futures_exchange_info()
            else:
                info = await client.get_exchange_info()
            symbols = [s["symbol"] for s in info.get("symbols", [])]
            return symbol_upper in symbols, symbols
        except Exception as exc:
            log.error("Failed to validate symbol: %s", exc)
            return False, []

    @staticmethod
    async def get_max_leverage(client, symbol: str, trading_type: str) -> int:
        """Obtiene el leverage máximo permitido por Binance para un símbolo.

        FUTURES: consulta GET /fapi/v1/leverageBracket → initialLeverage
                 del bracket con mayor tier (ej: BTCUSDT=125, SOLUSDT=100).
        MARGIN:  Binance Cross Margin solo permite 3x o 5x.
        SPOT:    leverage no aplica → 1.

        Fallback en excepción: 20 (conservador).
        """
        if trading_type == "SPOT":
            return 1
        if trading_type == "MARGIN":
            return 5
        try:
            brackets = await client.futures_leverage_bracket(symbol=symbol.upper())
            if brackets and isinstance(brackets, list):
                # Respuesta: [{symbol: ..., brackets: [{bracket:1, initialLeverage:150, ...}, ...]}]
                # El primer bracket tiene el leverage máximo.
                inner = brackets[0].get("brackets", [])
                if inner:
                    return int(inner[0].get("initialLeverage", 20))
        except Exception as exc:
            log.error("Failed to get max leverage for %s: %s", symbol, exc)
        return 20

    async def _validate_symbol(self, client) -> bool:
        """Valida que el símbolo exista en el mercado seleccionado."""
        exists, _ = await self.validate_symbol_for_market(
            client, settings.TRADING_SYMBOL, settings.TRADING_TYPE,
        )
        if not exists:
            log.warning(
                "Symbol %s not found in %s",
                settings.TRADING_SYMBOL, settings.TRADING_TYPE,
            )
            self._connection_status = "DISCONNECTED"
            event_bus.publish(ConnectionStatusEvent(
                status="DISCONNECTED",
                message=f"{settings.TRADING_SYMBOL} no existe en {settings.TRADING_TYPE}.",
            ))
        return exists

    # ------------------------------------------------------------------
    # Stream simulado (Paper mode sin keys)
    # ------------------------------------------------------------------

    async def _run_mock_stream(self) -> None:
        log.warning("No API keys found. Running MOCK tick generator.")
        self._connection_status = "CONNECTED"
        event_bus.publish(ConnectionStatusEvent(
            status="CONNECTED",
            message="Modo Simulación (Sin API Keys)"
        ))
        self._mock.reset_for_symbol(settings.TRADING_SYMBOL)
        interval = 1.5
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

    # ------------------------------------------------------------------
    # Consulta de símbolos (USDT/USDC) con precios
    # ------------------------------------------------------------------

    def clear_symbols_cache(self) -> None:
        """Limpia el caché de símbolos para forzar recarga."""
        self._symbols_cache = {}
        self._symbols_cache_time = {}

    async def get_trading_symbols(self, trading_type: str = "SPOT", currency: str | None = None) -> list[dict]:
        """Obtiene símbolos disponibles (USDT/USDC) con precios actuales.
        Cache de 60 segundos por mercado para evitar rate limits."""
        currency = currency or settings.TRADE_CURRENCY
        cache_key = f"{trading_type}_{currency}"
        now = time.time()
        if cache_key in self._symbols_cache and (now - self._symbols_cache_time.get(cache_key, 0)) < 60.0:
            cached = self._symbols_cache[cache_key]
            event_bus.publish(SymbolsListEvent(symbols=cached, trading_type=trading_type))
            return cached

        from services.binance_client import create_client

        client = None
        try:
            client = await create_client()

            if trading_type == "FUTURES":
                exchange_info = await client.futures_exchange_info()
                all_prices = await client.futures_ticker()
            else:  # SPOT / MARGIN
                exchange_info = await client.get_exchange_info()
                all_prices = await client.get_all_tickers()

            price_map = {
                t["symbol"]: self._normalize_price(t, trading_type)
                for t in all_prices
            }

            deduped: dict[str, dict] = {}
            for s in exchange_info["symbols"]:
                if s["quoteAsset"] == currency and s["status"] == "TRADING":
                    if trading_type == "FUTURES" and s.get("contractType") != "PERPETUAL":
                        continue
                    symbol = s["symbol"]
                    deduped[symbol] = {
                        "symbol": symbol,
                        "base_asset": s["baseAsset"],
                        "quote_asset": s["quoteAsset"],
                        "price": price_map.get(symbol, "0.00000000"),
                    }
            results = list(deduped.values())

            # Ordenar por precio descendente (BTC primero)
            results.sort(key=lambda x: float(x["price"]), reverse=True)

            self._symbols_cache[cache_key] = results
            self._symbols_cache_time[cache_key] = now

            event_bus.publish(SymbolsListEvent(symbols=results, trading_type=trading_type))
            log.info("Loaded %d %s %s symbols from Binance", len(results), currency, trading_type)
            return results

        except Exception as exc:
            log.error("Error fetching %s symbols: %s", trading_type, exc)
            return self._symbols_cache.get(cache_key, [])
        finally:
            if client:
                try:
                    await client.close_connection()
                except Exception:
                    pass

    async def get_symbol_price(self, symbol: str) -> float:
        """Obtiene el precio actual de un símbolo específico."""
        from services.binance_client import create_client

        client = None
        try:
            client = await create_client()
            ticker = await client.get_symbol_ticker(symbol=symbol)
            return float(ticker.get("price", 0))
        except Exception as exc:
            log.error("Error fetching price for %s: %s", symbol, exc)
            return 0.0
        finally:
            if client:
                try:
                    await client.close_connection()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Consulta de saldo (Account Balance)
    # ------------------------------------------------------------------

    async def get_balance(self, asset: str = "USDT") -> BalanceUpdateEvent:
        """Consulta el saldo según TRADING_TYPE actual. Cache de 5 segundos."""
        now = time.time()
        if self._balance_cache and (now - self._balance_cache_time) < 5.0:
            return self._balance_cache

        # En PAPER mode o sin API keys, retornar saldo mock
        if settings.TRADING_MODE == "PAPER" or not settings.has_api_keys():
            from services.paper_balance import paper_balance
            balance = paper_balance.get_balance()
            event = BalanceUpdateEvent(
                asset=asset,
                trading_type=settings.TRADING_TYPE,
                free=balance,
                available=balance,
            )
            self._balance_cache = event
            self._balance_cache_time = now
            return event

        from services.binance_client import create_client

        client = None
        try:
            client = await create_client()

            event = BalanceUpdateEvent(
                asset=asset,
                trading_type=settings.TRADING_TYPE,
                free=0.0,
            )

            if settings.TRADING_TYPE == "FUTURES":
                balances = await client.futures_account_balance()
                entry = next((b for b in balances if b["asset"] == asset), None)
                if entry:
                    event.free = float(entry.get("balance", 0))
                    event.available = float(entry.get("availableBalance", 0))
                    event.unrealized_pnl = float(entry.get("crossUnPnl", 0))

            elif settings.TRADING_TYPE == "MARGIN":
                account = await client.get_margin_account()
                entry = next(
                    (a for a in account.get("userAssets", []) if a["asset"] == asset),
                    None,
                )
                if entry:
                    event.free = float(entry.get("free", 0))
                    event.locked = float(entry.get("locked", 0))
                    event.borrowed = float(entry.get("borrowed", 0))
                    event.interest = float(entry.get("interest", 0))
                event.margin_level = float(account.get("marginLevel", 0))

            else:  # SPOT
                balance = await client.get_asset_balance(asset=asset)
                if balance:
                    event.free = float(balance.get("free", 0))
                    event.locked = float(balance.get("locked", 0))

            self._balance_cache = event
            self._balance_cache_time = now
            return event

        except Exception as exc:
            log.error("Error fetching balance: %s", exc)
            return BalanceUpdateEvent(
                asset=asset,
                trading_type=settings.TRADING_TYPE,
                free=0.0,
            )
        finally:
            if client:
                try:
                    await client.close_connection()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Balance auto-refresh loop
    # ------------------------------------------------------------------

    def _start_balance_loop(self) -> None:
        """Inicia el loop de auto-refresh de saldo."""
        self._stop_balance_loop()
        # 30s en LIVE, 60s en PAPER
        self._balance_interval = 30.0 if settings.TRADING_MODE == "LIVE" else 60.0
        self._balance_task = asyncio.create_task(
            self._balance_loop(), name="balance_loop"
        )
        log.info("Balance loop started (interval: %.0fs)", self._balance_interval)

    def _stop_balance_loop(self) -> None:
        """Detiene el loop de auto-refresh de saldo."""
        if self._balance_task:
            self._balance_task.cancel()
            self._balance_task = None

    async def _balance_loop(self) -> None:
        """Loop que consulta y publica saldo periódicamente."""
        try:
            # Primera consulta inmediata
            balance = await self.get_balance()
            event_bus.publish(balance)

            while self._running:
                await asyncio.sleep(self._balance_interval)
                if not self._running:
                    break
                balance = await self.get_balance()
                event_bus.publish(balance)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.error("Balance loop error: %s", exc)


# Instancia global singleton
binance_service = BinanceService()
