"""
Tests para EmptyState — Bloque de estado vacío compartido.
"""
import flet as ft
from ui.components.empty_state import EmptyState


def _texts(state: EmptyState) -> list[ft.Text]:
    return [c for c in state.content.controls if isinstance(c, ft.Text)]


def test_title_only_has_single_text():
    state = EmptyState("Sin órdenes aún.")
    assert len(_texts(state)) == 1
    assert _texts(state)[0].value == "Sin órdenes aún."


def test_subtitle_is_appended_after_title():
    state = EmptyState("Título", subtitle="Subtítulo")
    values = [t.value for t in _texts(state)]
    assert values == ["Título", "Subtítulo"]


def test_title_is_centered_with_default_size():
    state = EmptyState("Vacío")
    assert _texts(state)[0].text_align == ft.TextAlign.CENTER
    assert _texts(state)[0].size == 13


def test_title_size_is_configurable():
    state = EmptyState("Vacío", subtitle="Sub", title_size=12)
    assert _texts(state)[0].size == 12
    assert _texts(state)[1].size == 10


def test_icon_is_rendered_before_title_when_given():
    state = EmptyState("Vacío", icon=ft.Icons.RECEIPT_LONG_OUTLINED)
    assert isinstance(state.content.controls[0], ft.Icon)
    assert _texts(state)[0].value == "Vacío"


def test_without_icon_title_is_first_control():
    state = EmptyState("Vacío")
    assert isinstance(state.content.controls[0], ft.Text)


def test_content_is_centered_column():
    state = EmptyState("Vacío")
    assert isinstance(state.content, ft.Column)
    assert state.content.horizontal_alignment == ft.CrossAxisAlignment.CENTER
    assert state.alignment == ft.Alignment.CENTER


def test_block_is_self_centered_inside_parent():
    state = EmptyState("Vacío")
    assert state.padding.top == 16
    assert state.padding.left == 12
