"""
Tests para ModeBadge — Badge de modo (PAPER/LIVE).
"""
import flet as ft
from ui.components.mode_badge import ModeBadge


def test_mode_badge_initial_paper():
    badge = ModeBadge("PAPER")
    assert badge.mode == "PAPER"
    assert badge._text.value == "PAPER"


def test_mode_badge_initial_live():
    badge = ModeBadge("LIVE")
    assert badge.mode == "LIVE"
    assert badge._text.value == "LIVE"


def test_mode_badge_update_to_live():
    badge = ModeBadge("PAPER")
    badge.update_mode("LIVE")
    assert badge.mode == "LIVE"
    assert badge._text.value == "LIVE"
    assert badge._text.color == ft.Colors.RED_400


def test_mode_badge_update_to_paper():
    badge = ModeBadge("LIVE")
    badge.update_mode("PAPER")
    assert badge.mode == "PAPER"
    assert badge._text.value == "PAPER"
    assert badge._text.color == ft.Colors.AMBER_400


def test_mode_badge_default_tooltip():
    badge = ModeBadge()
    assert "Paper" in badge.tooltip
    assert "Live" in badge.tooltip


def test_mode_badge_styling():
    badge = ModeBadge("PAPER")
    assert badge.border_radius == 6
    assert badge.padding.left == 10
    assert badge.padding.right == 10
