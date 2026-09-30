"""
Tests para SegmentedFilter — Filtros en chips segmentados.
"""
import flet as ft
from ui.components.segmented_filter import _IDLE_BG, _IDLE_FG, _SELECTED_BG, _SELECTED_FG
from ui.components.segmented_filter import SegmentedFilter

OPTIONS = (
    ("ALL", "Todas"),
    ("FILLED", "Ejecutadas"),
    ("PENDING", "Pendientes"),
    ("CANCELLED", "Canceladas"),
)


def _chips(filter_control: SegmentedFilter) -> list[ft.Container]:
    return filter_control.controls[0].content.controls


def test_one_chips_row_wraps_all_options():
    control = SegmentedFilter(OPTIONS, value="ALL")
    assert len(control.controls) == 1
    assert len(_chips(control)) == len(OPTIONS)


def test_chips_expand_evenly():
    control = SegmentedFilter(OPTIONS, value="ALL")
    assert all(chip.expand for chip in _chips(control))


def test_initial_value_is_painted_on_selected_chip():
    control = SegmentedFilter(OPTIONS, value="PENDING")
    selected, idle = _chips(control)[2], _chips(control)[0]
    assert control.value == "PENDING"
    assert selected.bgcolor == _SELECTED_BG
    assert selected.content.color == _SELECTED_FG
    assert idle.bgcolor == _IDLE_BG
    assert idle.content.color == _IDLE_FG


def test_setter_repaints_previous_chip():
    control = SegmentedFilter(OPTIONS, value="ALL")
    control.value = "CANCELLED"
    assert control.value == "CANCELLED"
    assert _chips(control)[0].bgcolor == _IDLE_BG
    assert _chips(control)[3].bgcolor == _SELECTED_BG


def test_setter_ignores_unknown_key():
    control = SegmentedFilter(OPTIONS, value="ALL")
    control.value = "NOPE"
    assert control.value == "ALL"
    assert _chips(control)[0].bgcolor == _SELECTED_BG


def test_setter_ignores_repeated_value():
    control = SegmentedFilter(OPTIONS, value="ALL")
    control.value = "ALL"
    assert control.value == "ALL"


def test_chip_click_selects_and_notifies():
    received: list[str] = []
    control = SegmentedFilter(OPTIONS, value="ALL", on_change=received.append)
    _chips(control)[1].on_click(None)
    assert received == ["FILLED"]
    assert control.value == "FILLED"


def test_click_without_callback_still_selects():
    control = SegmentedFilter(OPTIONS, value="ALL")
    _chips(control)[3].on_click(None)
    assert control.value == "CANCELLED"


def test_labels_are_visible_and_truncated_to_one_line():
    control = SegmentedFilter(OPTIONS, value="ALL")
    for chip, (_key, label) in zip(_chips(control), OPTIONS):
        assert chip.content.value == label
        assert chip.content.max_lines == 1
