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
        self._client = None
        self._mock = MockTickGenerator()
        self._retry_count: int = 0

        # Balance auto-refresh
        self._balance_task: asyncio.Task | None = None
        self._balance_interval: float = 30.0  # segundos

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
        self._start_balance_loop()
        log.info("BinanceService starting for symbol: %s", settings.TRADING_SYMBOL)

    async def stop(self) -> None:
        self._running = False
        event_bus.unsubscribe(SettingsUpdatedEvent, self._on_settings_updated)
        self._stop_balance_loop()
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
        self._balance_cache = None
        self._balance_cache_time = 0.0
        self._running = True
        self._retry_count = 0
        event_bus.subscribe(SettingsUpdatedEvent, self._on_settings_updated)
        self._start_balance_loop()
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
                if settings.TRADING_MODE == "LIVE" and settings.has_api_keys():
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
    # Stream real (Binance WebSocket) — según TRADING_TYPE
    # ------------------------------------------------------------------

    async def _run_live_stream(self) -> None:
        from binance import BinanceSocketManager, FuturesType  # type: ignore
        from binance.exceptions import BinanceAPIException, BinanceRequestException  # type: ignore
        from services.binance_client import create_client

        try:
            self._client = await create_client()
            log.info(
                "Creating %s stream for %s...",
                settings.TRADING_TYPE, settings.TRADING_SYMBOL,
            )

            bm = BinanceSocketManager(self._client)
            symbol_lower = settings.TRADING_SYMBOL.lower()

            # Seleccionar stream según TRADING_TYPE
            if settings.TRADING_TYPE == "FUTURES":
                stream_context = bm._get_futures_socket(
                    f"{symbol_lower}@ticker",
                    futures_type=FuturesType.USD_M,
                    category="market",
                )
            elif settings.TRADING_TYPE == "MARGIN":
                stream_context = bm.symbol_ticker_socket(symbol_lower)
            else:  # SPOT
                stream_context = bm.symbol_ticker_socket(symbol_lower)

            async with stream_context as ts:
                event_bus.publish(ConnectionStatusEvent(
                    status="CONNECTED",
                    message=f"Conectado a {settings.TRADING_SYMBOL} ({settings.TRADING_TYPE})"
                ))
                log.info("WebSocket connected: %s@ticker (%s)", symbol_lower, settings.TRADING_TYPE)

                while self._running:
                    msg = await ts.recv()
                    if msg.get("e") == "error":
                        raise Exception(f"WS Error: {msg}")

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
    # Stream simulado (Paper mode sin keys)
    # ------------------------------------------------------------------

    async def _run_mock_stream(self) -> None:
        log.warning("No API keys found. Running MOCK tick generator.")
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

    _symbols_cache: list[dict] | None = None
    _symbols_cache_time: float = 0.0

    def clear_symbols_cache(self) -> None:
        """Limpia el caché de símbolos para forzar recarga."""
        self._symbols_cache = None
        self._symbols_cache_time = 0.0

    async def get_trading_symbols(self) -> list[dict]:
        """Obtiene símbolos disponibles (USDT/USDC) con precios actuales.
        Cache de 60 segundos para evitar rate limits."""
        now = time.time()
        if self._symbols_cache and (now - self._symbols_cache_time) < 60.0:
            return self._symbols_cache

        from services.binance_client import create_client

        client = None
        try:
            client = await create_client()

            exchange_info = await client.get_exchange_info()
            all_prices = await client.get_all_tickers()
            price_map = {t["symbol"]: t["price"] for t in all_prices}

            currency = settings.TRADE_CURRENCY
            results = []
            for s in exchange_info["symbols"]:
                if s["quoteAsset"] == currency and s["status"] == "TRADING":
                    symbol = s["symbol"]
                    results.append({
                        "symbol": symbol,
                        "base_asset": s["baseAsset"],
                        "quote_asset": s["quoteAsset"],
                        "price": price_map.get(symbol, "0.00000000"),
                    })

            # Ordenar por precio descendente (BTC primero)
            results.sort(key=lambda x: float(x["price"]), reverse=True)

            self._symbols_cache = results
            self._symbols_cache_time = now

            event_bus.publish(SymbolsListEvent(symbols=results))
            log.info("Loaded %d %s symbols from Binance", len(results), currency)
            return results

        except Exception as exc:
            log.error("Error fetching symbols: %s", exc)
            return self._symbols_cache or []
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

    _balance_cache: BalanceUpdateEvent | None = None
    _balance_cache_time: float = 0.0

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
