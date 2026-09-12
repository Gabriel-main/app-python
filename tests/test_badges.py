"""
Tests para Badge — Componente reutilizable de etiqueta.
"""
import flet as ft
from ui.components.badges import Badge


def test_badge_creation():
    badge = Badge("TEST", ft.Colors.WHITE, ft.Colors.BLUE_900)
    assert badge.label == "TEST"
    assert badge.bgcolor == ft.Colors.BLUE_900


def test_badge_custom_size():
    badge = Badge("SMALL", ft.Colors.WHITE, ft.Colors.RED_900, size=8)
    assert badge._label_text.size == 8


def test_badge_custom_border_radius():
    badge = Badge("ROUND", ft.Colors.WHITE, ft.Colors.GREEN_900, border_radius=12)
    assert badge.border_radius == 12


def test_badge_update_label():
    badge = Badge("OLD", ft.Colors.WHITE, ft.Colors.BLUE_900)
    badge.update_label("NEW")
    assert badge.label == "NEW"


def test_badge_update_label_with_color():
    badge = Badge("TEST", ft.Colors.WHITE, ft.Colors.BLUE_900)
    badge.update_label("CHANGED", fg_color=ft.Colors.RED_400, bg_color=ft.Colors.RED_900)
    assert badge.label == "CHANGED"
    assert badge._label_text.color == ft.Colors.RED_400
    assert badge.bgcolor == ft.Colors.RED_900


def test_badge_update_label_partial():
    badge = Badge("TEST", ft.Colors.WHITE, ft.Colors.BLUE_900)
    original_bg = badge.bgcolor
    badge.update_label("NEW", fg_color=ft.Colors.GREEN_400)
    assert badge.label == "NEW"
    assert badge._label_text.color == ft.Colors.GREEN_400
    assert badge.bgcolor == original_bg


def test_badge_default_padding():
    badge = Badge("TEST", ft.Colors.WHITE, ft.Colors.BLUE_900)
    assert badge.padding.left == 8
    assert badge.padding.right == 8
    assert badge.padding.top == 3
    assert badge.padding.bottom == 3
