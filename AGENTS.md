# AGENTS.md — Sistema Multi-Agente: Trading Bot Flet

## Descripción del Proyecto

App móvil reactiva de trading construida con **Flet (Python)**, conectada a **Binance API**
vía WebSockets en tiempo real, con base de datos local `aiosqlite + SQLModel` y bot engine
de estrategia **MA Crossover** configurable.

---

## Arquitectura de Agentes

### @pyto-flet — Arquitecto y Director
**Rol**: Director del proyecto. Define contratos de datos, coordina el flujo multi-agente,
valida separación de capas y aplica reglas de reactividad.

**Archivos propios**:
- `core/event_bus.py` — AsyncEventBus PubSub
- `core/events.py` — Contratos de datos (dataclasses)
- `core/logger.py` — Logging estructurado
- `main.py` — Punto de entrada

**Reglas obligatorias**:
1. CONTRATOS PRIMERO: Definir eventos antes de código UI o backend
2. CERO POLLING: Prohibir `while True: sleep()` en cualquier capa
3. REACTIVIDAD ATÓMICA: Solo `control.update()`, nunca `page.update()`
4. AISLAMIENTO DE HILOS: I/O en `asyncio.create_task()`
5. SEGURIDAD: API Keys via `.env`, nunca hardcoded

---

### @backend-db — Backend Asíncrono + DB
**Rol**: Implementa servicios de Binance (WebSocket/REST async) y persistencia de datos.

**Archivos propios**:
- `config/settings.py`
- `database/models.py`, `database/connection.py`, `database/db_queue.py`
- `services/binance_service.py`
- `services/bot_engine.py`

**Reglas obligatorias**:
1. Usar exclusivamente `AsyncClient` y `BinanceSocketManager`
2. Publicar inmediatamente al EventBus tras recibir datos de WS
3. Escrituras en DB siempre vía `db_queue` (nunca bloqueantes)
4. Manejo estricto de excepciones + reconexión automática
5. Capas limpias: service ≠ repository ≠ engine

---

### @frontend-flet — UI/UX Reactiva
**Rol**: Construye la interfaz móvil con componentes reactivos suscritos al EventBus.

**Archivos propios**:
- `ui/app_layout.py`
- `ui/views/` — dashboard, orders, settings
- `ui/components/` — widgets atómicos

**Reglas obligatorias**:
1. Navegación con `ft.NavigationBar` (no tabs superiores)
2. Suscribir en `did_mount()`, des-suscribir en `will_unmount()`
3. PROHIBIDO `page.update()` — solo `control.update()` específico
4. Flash verde/rojo en precio con `animate_opacity`
5. `ft.ProgressRing` en estados de carga / `ConnectionIndicator` en error de WS

---

## Contratos de Datos (EventBus)

| Evento | Publicado por | Consumido por |
|--------|--------------|---------------|
| `PriceTickEvent` | `BinanceService` | `BotEngine`, `PriceTicker`, `MiniChart`, `DashboardView` |
| `BotSignalEvent` | `BotEngine` | `BotStatusBar` |
| `OrderExecutedEvent` | `BotEngine` | `OrdersView` |
| `ConnectionStatusEvent` | `BinanceService` | `ConnectionIndicator` |
| `BotStateChangedEvent` | `DashboardView` (botón) | `BotEngine` |
| `SettingsUpdatedEvent` | `SettingsView` | `BinanceService`, `BotEngine` |

---

## Flujo de Datos

```
Binance WS → BinanceService → PriceTickEvent → EventBus
                                                 ├─→ BotEngine → BotSignalEvent → BotStatusBar
                                                 │              └─→ OrderExecutedEvent → OrdersView + DB
                                                 ├─→ PriceTicker (UI)
                                                 └─→ MiniChart (UI)

SettingsView [Guardar] → SettingsUpdatedEvent → BinanceService (restart) + BotEngine (reload)
DashboardView [Toggle] → BotStateChangedEvent → BotEngine (pause/resume)
```

---

## Estructura del Proyecto

```
trading_bot_flet/
├── AGENTS.md
├── .cursorrules
├── main.py
├── .env                    # (gitignored) API keys
├── .env.example            # Template sin secrets
├── config/settings.py
├── core/
│   ├── event_bus.py
│   ├── events.py
│   └── logger.py
├── database/
│   ├── connection.py
│   ├── models.py
│   └── db_queue.py
├── services/
│   ├── binance_service.py
│   └── bot_engine.py
└── ui/
    ├── app_layout.py
    ├── views/
    │   ├── dashboard_view.py
    │   ├── orders_view.py
    │   └── settings_view.py
    └── components/
        ├── price_ticker.py
        ├── mini_chart.py
        ├── order_card.py
        ├── bot_status_bar.py
        └── connection_indicator.py
```
