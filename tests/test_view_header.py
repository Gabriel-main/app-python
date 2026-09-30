"""
Tests para ViewHeader — Header estándar de vista.
"""
import flet as ft
from ui.components.view_header import ViewHeader


def _row(header: ViewHeader) -> ft.Row:
    return header.controls[0]


def _left_column(header: ViewHeader) -> ft.Column:
    controls = _row(header).controls
    return next(c for c in controls if isinstance(c, ft.Column))


def _title(header: ViewHeader) -> ft.Text:
    return _left_column(header).controls[0]


def test_title_uses_shared_style():
    header = ViewHeader("Órdenes")
    title = _title(header)
    assert title.value == "Órdenes"
    assert title.size == 22
    assert title.weight == ft.FontWeight.BOLD
    assert title.color == ft.Colors.WHITE


def test_without_subtitle_title_is_only_child():
    header = ViewHeader("Órdenes")
    assert len(_left_column(header).controls) == 1
    assert _row(header).vertical_alignment == ft.CrossAxisAlignment.CENTER


def test_subtitle_is_second_child_and_aligns_top():
    subtitle = ft.Text("conectado")
    header = ViewHeader("Dashboard", subtitle=subtitle)
    assert _left_column(header).controls == [_title(header), subtitle]
    assert _row(header).vertical_alignment == ft.CrossAxisAlignment.START


def test_without_trailing_there_is_no_spacer_and_title_is_centered():
    header = ViewHeader("Configuración")
    assert not any(isinstance(c, ft.Container) and c.expand for c in _row(header).controls)
    assert _row(header).alignment == ft.MainAxisAlignment.CENTER


def test_with_trailing_adds_expander_and_starts_left():
    trailing = [ft.Text("3 órdenes")]
    header = ViewHeader("Órdenes", trailing=trailing)
    controls = _row(header).controls
    assert any(isinstance(c, ft.Container) and c.expand for c in controls)
    assert _row(header).alignment == ft.MainAxisAlignment.START
    assert controls[-1] is trailing[0]


def test_leading_is_first_control():
    back = ft.IconButton(icon=ft.Icons.ARROW_BACK_IOS)
    header = ViewHeader("Ajustes", leading=back, trailing=[])
    assert _row(header).controls[0] is back


def test_divider_shown_by_default():
    header = ViewHeader("Órdenes")
    assert len(header.controls) == 2
    assert isinstance(header.controls[1], ft.Container) or isinstance(header.controls[1], ft.Divider)


def test_divider_can_be_disabled():
    header = ViewHeader("Dashboard", show_divider=False)
    assert len(header.controls) == 1


def test_divider_fixed_width_is_wrapped_in_container():
    header = ViewHeader("Ajustes", divider_width=380)
    divider = header.controls[1]
    assert isinstance(divider, ft.Container)
    assert divider.width == 380
    assert isinstance(divider.content, ft.Divider)


def test_divider_without_width_is_bare():
    header = ViewHeader("Órdenes")
    assert isinstance(header.controls[1], ft.Divider)


def test_divider_height_is_forwarded():
    header = ViewHeader("Ajustes", divider_width=380, divider_height=20)
    assert header.controls[1].content.height == 20


def test_horizontal_alignment_matches_parent_views():
    assert ViewHeader("X").horizontal_alignment == ft.CrossAxisAlignment.CENTER


def test_spacing_is_forwarded():
    assert ViewHeader("X", spacing=16).spacing == 16
    assert ViewHeader("X").spacing == 12
