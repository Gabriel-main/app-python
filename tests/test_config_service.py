"""
Tests de ConfigService: toda escritura pasa por db_queue.submit() (D2/AG.md).

Ningún método del servicio puede hacer session.add/commit directo fuera
del worker — el gateway único de DB.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from database.models import TradingConfig
from services import config_service as config_module
from services.config_service import _DEFAULTS, config_service


def _mock_session(existing=None):
    session = MagicMock()
    result = MagicMock()
    result.first.return_value = existing
    session.exec = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _mock_ctx(session):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class _SubmitSpy:
    """Fake de db_queue que registra los submits y ejecuta la factory inline."""

    def __init__(self) -> None:
        self.calls: list = []

    async def submit(self, factory):
        self.calls.append(factory)
        return await factory()


@pytest.mark.asyncio
async def test_update_goes_through_submit():
    session = _mock_session(existing=None)
    spy = _SubmitSpy()

    with patch.object(config_module, "get_session", return_value=_mock_ctx(session)), \
         patch.object(config_module, "db_queue", spy):
        config = await config_service.update(trading_symbol="ETHUSDT")

    assert len(spy.calls) == 1
    session.add.assert_called_once()
    session.commit.assert_awaited_once()
    assert config.trading_symbol == "ETHUSDT"


@pytest.mark.asyncio
async def test_save_goes_through_submit():
    session = _mock_session()
    spy = _SubmitSpy()
    config = TradingConfig(**_DEFAULTS)

    with patch.object(config_module, "get_session", return_value=_mock_ctx(session)), \
         patch.object(config_module, "db_queue", spy):
        await config_service.save(config)

    assert len(spy.calls) == 1
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_creates_defaults_through_submit():
    """load() sin config existente crea defaults vía submit (no commit directo)."""
    session = _mock_session(existing=None)
    spy = _SubmitSpy()

    with patch.object(config_module, "get_session", return_value=_mock_ctx(session)), \
         patch.object(config_module, "db_queue", spy):
        config = await config_service.load()

    assert len(spy.calls) == 1
    session.add.assert_called_once()
    session.commit.assert_awaited_once()
    assert config.trading_symbol == _DEFAULTS["trading_symbol"]


@pytest.mark.asyncio
async def test_init_from_env_goes_through_submit():
    session = _mock_session(existing=None)
    spy = _SubmitSpy()

    with patch.object(config_module, "get_session", return_value=_mock_ctx(session)), \
         patch.object(config_module, "db_queue", spy):
        await config_service.init_from_env()

    assert len(spy.calls) == 1
    session.commit.assert_awaited_once()


def test_config_service_commits_match_submits():
    """Invariante: cada session.commit vive detrás de un db_queue.submit.

    Si alguien añade un commit directo (sin submit) o elimina un submit
    dejando el commit, la igualdad se rompe.
    """
    import inspect

    source = inspect.getsource(config_module)
    commits = source.count("await session.commit()")
    submits = source.count("await db_queue.submit(")
    assert commits == submits, (
        f"commits={commits} != submits={submits}: "
        "hay escrituras fuera del gateway db_queue"
    )
