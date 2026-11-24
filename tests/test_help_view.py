"""
Tests para HelpView y la guía de Stop Loss.
"""
from unittest.mock import MagicMock, patch

from core.events import NavigateToEvent
from ui.components.settings_sections import OperationParamsSection
from ui.views.help_view import HelpView
from ui.view_registry import ViewRegistry


def test_help_view_initial():
    view = HelpView()
    assert len(view.controls) >= 7
    assert view._back_btn is not None


def test_help_view_back_navigates_to_config():
    view = HelpView()
    with patch("ui.views.help_view.event_bus") as mock_bus:
        view._on_back(MagicMock())
        assert mock_bus.publish.call_count == 1
        event = mock_bus.publish.call_args[0][0]
        assert isinstance(event, NavigateToEvent)
        assert event.index == 2


def test_view_registry_includes_help_view():
    registry = ViewRegistry()
    registry.register_all()
    help_view = registry.get(5)
    assert isinstance(help_view, HelpView)
    registry.clear()
    assert registry.get(5) is None


def test_sl_speed_text_adapts_to_values():
    low_pct = OperationParamsSection._get_sl_speed_text(0.1, "PERCENT")
    assert "MUY RÁPIDO" in low_pct
    assert "0.1%" in low_pct

    high_pct = OperationParamsSection._get_sl_speed_text(5.0, "PERCENT")
    assert "TARDARÁ MÁS" in high_pct
    assert "5%" in high_pct

    low_usdt = OperationParamsSection._get_sl_speed_text(0.1, "USDT")
    assert "MUY RÁPIDO" in low_usdt
    assert "0.1USDT" in low_usdt

    high_usdt = OperationParamsSection._get_sl_speed_text(5.0, "USDT")
    assert "TARDARÁ MÁS" in high_usdt
    assert "5USDT" in high_usdt


def test_params_section_open_help_publishes_event():
    section = OperationParamsSection()
    with patch("ui.components.settings_sections.event_bus") as mock_bus:
        section._on_open_help(MagicMock())
        assert mock_bus.publish.call_count == 1
        event = mock_bus.publish.call_args[0][0]
        assert isinstance(event, NavigateToEvent)
        assert event.index == 5

