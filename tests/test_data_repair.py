"""
Tests de DataRepair — saneo idempotente de huérfanos al arranque.

Cubre las tres reparaciones (D1/D3 + PENDING PAPER) con sus gates:
solo casan filas huérfanas (symbol OC/OV, status OPEN, PENDING+PAPER),
nunca tocan datos vivos ni LIVE. Toda escritura vía db_queue.submit
(único gateway, AG.md).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services import data_repair as repair_module
from services.data_repair import DataRepair, data_repair


class _SubmitSpy:
    """Fake de db_queue: registra el submit y ejecuta la factory inline."""

    def __init__(self) -> None:
        self.calls: list = []

    async def submit(self, factory):
        self.calls.append(factory)
        return await factory()


def _session_with_counts(symbol=3, positions=5, orders=1):
    session = MagicMock()
    results = []
    for count in (symbol, positions, orders):
        r = MagicMock()
        r.rowcount = count
        results.append(r)
    session.execute = AsyncMock(side_effect=results)
    session.commit = AsyncMock()
    return session


def _mock_ctx(session):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _executed_statements(session):
    """SQL crudo de cada session.execute, en orden."""
    return [str(call.args[0]) for call in session.execute.call_args_list]


@pytest.mark.asyncio
async def test_run_goes_through_db_queue_submit():
    spy = _SubmitSpy()
    session = _session_with_counts(symbol=0, positions=0, orders=0)

    with patch.object(repair_module, "db_queue", spy), \
         patch.object(repair_module, "get_session",
                      return_value=_mock_ctx(session)):
        counts = await DataRepair().run()

    assert len(spy.calls) == 1          # único gateway de escritura
    assert counts == {
        "symbol_fixed": 0,
        "positions_closed": 0,
        "orders_cancelled": 0,
    }


@pytest.mark.asyncio
async def test_repair_executes_three_statements_in_order():
    session = _session_with_counts(symbol=7, positions=2, orders=3)

    with patch.object(repair_module, "get_session",
                      return_value=_mock_ctx(session)):
        counts = await DataRepair()._repair_all()

    assert session.execute.await_count == 3
    session.commit.assert_awaited_once()
    assert counts == {
        "symbol_fixed": 7,
        "positions_closed": 2,
        "orders_cancelled": 3,
    }


@pytest.mark.asyncio
async def test_symbol_statement_only_touches_oc_ov_prefixes():
    """D1: solo remapea las filas corruptas (symbol IN OC/OV)."""
    session = _session_with_counts()

    with patch.object(repair_module, "get_session",
                      return_value=_mock_ctx(session)), \
         patch.object(repair_module.settings, "TRADING_SYMBOL", "BTCUSDT",
                      create=True):
        await DataRepair()._repair_all()

    stmt, params = session.execute.call_args_list[0].args
    sql = str(stmt)
    assert "operations" in sql
    assert "'OC'" in sql and "'OV'" in sql          # gate de huérfanos
    assert params["sym"] == "BTCUSDT"               # símbolo real


@pytest.mark.asyncio
async def test_positions_statement_closes_open_rows_with_unrealized_pnl():
    """D3: OPEN → CLOSED con closed_pnl = unrealized_pnl (NULL → 0)."""
    session = _session_with_counts()

    with patch.object(repair_module, "get_session",
                      return_value=_mock_ctx(session)):
        await DataRepair()._repair_all()

    stmt = str(session.execute.call_args_list[1].args[0])
    assert "positions" in stmt
    assert "status = 'CLOSED'" in stmt
    assert "COALESCE(unrealized_pnl, 0)" in stmt
    assert "WHERE status = 'OPEN'" in stmt          # solo huérfanas


@pytest.mark.asyncio
async def test_orders_statement_only_cancels_paper_pending():
    """LIVE nunca se toca: el gate mode='PAPER' evita divergir de Binance."""
    session = _session_with_counts()

    with patch.object(repair_module, "get_session",
                      return_value=_mock_ctx(session)):
        await DataRepair()._repair_all()

    stmt = str(session.execute.call_args_list[2].args[0])
    assert "orders" in stmt
    assert "status = 'PENDING'" in stmt
    assert "mode = 'PAPER'" in stmt                 # LIVE intocado


@pytest.mark.asyncio
async def test_repair_is_idempotent_when_nothing_matches():
    """Segunda pasada: los gates no casan ninguna fila → 0 afectadas."""
    clean = _session_with_counts(symbol=0, positions=0, orders=0)

    with patch.object(repair_module, "get_session",
                      return_value=_mock_ctx(clean)):
        counts = await data_repair.run()

    assert sum(counts.values()) == 0
