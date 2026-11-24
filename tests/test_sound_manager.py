"""
Tests para SoundManager y reproducción de sonido en notificaciones.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from core.events import OrderExecutedEvent, OrderFailedEvent
from ui.components.notification_toast import NotificationToast
from ui.components.sound_manager import SoundManager, sound_manager


def test_sound_files_exist_and_non_empty():
    """Verifica que los archivos de sonido estén generados y no vacíos."""
    success_path = Path("assets/sounds/order_success.wav")
    error_path = Path("assets/sounds/order_error.wav")

    assert success_path.exists(), "order_success.wav debe existir"
    assert success_path.stat().st_size > 1000, "order_success.wav no debe estar vacío"

    assert error_path.exists(), "order_error.wav debe existir"
    assert error_path.stat().st_size > 1000, "order_error.wav no debe estar vacío"


def test_sound_manager_does_not_pollute_overlay():
    """Verifica que mount y remount NO agreguen controles desconocidos al overlay de Flet."""
    sm = SoundManager()
    mock_page = MagicMock()
    mock_page.overlay = []

    sm.mount(mock_page)
    assert len(mock_page.overlay) == 0, "No debe inyectar controles al overlay para evitar 'Unknown control: Audio'"

    sm.remount(mock_page)
    assert len(mock_page.overlay) == 0


@pytest.mark.asyncio
async def test_sound_manager_play_file_invokes_player():
    """Verifica que _play_file ejecute el proceso de reproducción del SO."""
    sm = SoundManager()
    sm._player = "/usr/bin/pw-play"

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_proc = MagicMock()
        mock_proc.wait = AsyncMock()
        mock_exec.return_value = mock_proc

        await sm._play_file(Path("assets/sounds/order_success.wav"))
        mock_exec.assert_called_once()
        args = mock_exec.call_args[0]
        assert args[0] == "/usr/bin/pw-play"
        assert "order_success.wav" in args[1]


def test_sound_manager_disabled():
    """Verifica que si enabled=False no se reproduzca ningún sonido."""
    sm = SoundManager()
    sm.enabled = False

    with patch.object(sm, "_play_file") as mock_play:
        sm.play_success()
        sm.play_error()
        mock_play.assert_not_called()


@pytest.mark.asyncio
async def test_notification_toast_triggers_sound_on_order_executed():
    """Verifica que al ejecutarse una orden se invoque sound_manager.play_success()."""
    toast = NotificationToast()
    event = OrderExecutedEvent(
        order_id="TEST-1",
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.01,
        price=65000.0,
        mode="PAPER",
    )

    with patch("ui.components.notification_toast.sound_manager") as mock_sm:
        try:
            await toast._on_order_executed(event)
            mock_sm.play_success.assert_called_once()
            mock_sm.play_error.assert_not_called()
        finally:
            if toast._hide_task and not toast._hide_task.done():
                toast._hide_task.cancel()


@pytest.mark.asyncio
async def test_notification_toast_triggers_sound_on_order_failed():
    """Verifica que al fallar una orden se invoque sound_manager.play_error()."""
    toast = NotificationToast()
    event = OrderFailedEvent(
        operation_id="TEST-FAIL",
        side="SELL",
        error="Saldo insuficiente para la operación",
    )

    with patch("ui.components.notification_toast.sound_manager") as mock_sm:
        try:
            await toast._on_order_failed(event)
            mock_sm.play_error.assert_called_once()
            mock_sm.play_success.assert_not_called()
        finally:
            if toast._hide_task and not toast._hide_task.done():
                toast._hide_task.cancel()
