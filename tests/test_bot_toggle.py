"""
Tests para BotToggle — Botón ON/OFF del bot.
"""
from unittest.mock import patch
import flet as ft
from ui.components.bot_toggle import BotToggle


def test_toggle_initial_state():
    toggle = BotToggle()
    assert toggle.is_active is False


def test_toggle_initial_content():
    toggle = BotToggle()
    assert "Iniciar" in toggle.content


def test_toggle_initial_icon():
    toggle = BotToggle()
    assert toggle.icon == ft.Icons.PLAY_CIRCLE


def test_toggle_initial_color():
    toggle = BotToggle()
    assert toggle.style.bgcolor == ft.Colors.GREEN_800


def test_toggle_click_publishes_event():
    from unittest.mock import patch, MagicMock
    toggle = BotToggle()
    with patch("ui.components.bot_toggle.event_bus") as mock_bus:
        with patch("ui.components.bot_toggle.settings") as mock_settings:
            mock_settings.TRADING_MODE = "PAPER"
            toggle._on_click(None)
            mock_bus.publish.assert_called_once()
            event = mock_bus.publish.call_args[0][0]
            assert event.is_running is True
            assert event.mode == "PAPER"


def test_toggle_appearance_when_active():
    toggle = BotToggle()
    toggle._active = False
    toggle._active = True
    toggle._update_appearance()
    assert "Detener" in toggle.content
    assert toggle.style.bgcolor == ft.Colors.RED_800
    assert toggle.icon == ft.Icons.PAUSE_CIRCLE


def test_toggle_appearance_when_inactive():
    toggle = BotToggle()
    toggle._active = True
    toggle._active = False
    toggle._update_appearance()
    assert "Iniciar" in toggle.content
    assert toggle.style.bgcolor == ft.Colors.GREEN_800
    assert toggle.icon == ft.Icons.PLAY_CIRCLE


def test_toggle_double_click_returns_inactive():
    toggle = BotToggle()
    with patch("ui.components.bot_toggle.event_bus"):
        with patch("ui.components.bot_toggle.settings") as mock_settings:
            mock_settings.TRADING_MODE = "PAPER"
            toggle._on_click(None)  # ON
            toggle._on_click(None)  # OFF
            assert toggle.is_active is False
