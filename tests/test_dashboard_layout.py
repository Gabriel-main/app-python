"""
Tests del layout del dashboard (T2.3 — overflow en pantallas angostas).

Cubren:
- StatCard: ítems de fila con expand (ancho acotado) + texto no_wrap/ELLIPSIS
  para que valores largos de balance/stats trunquen en vez de desbordar.
- ResponsiveLayout: stats+balance en ResponsiveRow con col xs:12 / sm:6
  (stacked en <600px, lado a lado en >=600px).
"""
from __future__ import annotations

import flet as ft

from ui.components.stat_card import StatCard
from ui.layouts.responsive_layout import ResponsiveDashboardLayout


def _value_texts(card: StatCard) -> list[ft.Text]:
    """Valores de datos (Column items de la fila interna)."""
    data_row = card.content.controls[2]
    return [
        item.controls[1]
        for item in data_row.controls
        if isinstance(item, ft.Column)
    ]


def _stat_card() -> StatCard:
    return StatCard(
        title="Estadísticas 24h",
        rows=[
            ("Máx 24h", ft.Text("---", size=12)),
            ("Mín 24h", ft.Text("---", size=12)),
        ],
    )


# ---------------------------------------------------------------------------
# StatCard — anti-overflow
# ---------------------------------------------------------------------------
def test_stat_card_header_title_expands_without_spacer():
    """El título absorbe el espacio libre (sin Container spacer que compita)."""
    card = _stat_card()

    title, *extras = card.content.controls[0].controls
    assert title is card._title
    assert card._title.expand is True
    assert card._title.no_wrap is True
    assert card._title.overflow == ft.TextOverflow.ELLIPSIS
    assert not any(
        isinstance(c, ft.Container) and c.expand for c in extras
    ), "no debe quedar un spacer flex en el header"


def test_stat_card_row_items_are_expand_bounded():
    """Cada ítem de fila va en un Column con expand → ancho acotado."""
    card = _stat_card()
    data_row = card.content.controls[2]

    items = [c for c in data_row.controls if isinstance(c, ft.Column)]
    assert len(items) == 2
    for item in items:
        assert item.expand is True


def test_stat_card_value_texts_truncate_instead_of_overflow():
    """Los valores (externos a StatCard) quedan con no_wrap + ELLIPSIS."""
    card = _stat_card()

    for text in _value_texts(card):
        assert text.no_wrap is True
        assert text.max_lines == 1
        assert text.overflow == ft.TextOverflow.ELLIPSIS


def test_stat_card_label_texts_truncate():
    card = _stat_card()
    data_row = card.content.controls[2]

    labels = [
        item.controls[0]
        for item in data_row.controls
        if isinstance(item, ft.Column)
    ]
    assert all(lb.no_wrap is True for lb in labels)
    assert all(lb.overflow == ft.TextOverflow.ELLIPSIS for lb in labels)


# ---------------------------------------------------------------------------
# ResponsiveLayout — stacking de stats+balance
# ---------------------------------------------------------------------------
def _components() -> dict:
    return {
        "header": ft.Text("header"),
        "divider": ft.Divider(),
        "price_section": ft.Text("price"),
        "stats": ft.Text("stats"),
        "balance": ft.Text("balance"),
        "bot_status": ft.Text("status"),
        "operations": ft.Text("ops"),
        "bot_toggle": ft.Button("toggle"),
    }


def test_stats_and_balance_use_responsive_row():
    layout = ResponsiveDashboardLayout()
    root = layout.build(_components())

    responsive_rows = [
        c for c in root.controls if isinstance(c, ft.ResponsiveRow)
    ]
    assert len(responsive_rows) == 1

    row = responsive_rows[0]
    assert len(row.controls) == 2
    for wrapper in row.controls:
        assert isinstance(wrapper, ft.Container)
        assert wrapper.col == {"xs": 12, "sm": 6}


def test_breakpoint_is_600():
    assert ResponsiveDashboardLayout().get_breakpoint() == 600.0
