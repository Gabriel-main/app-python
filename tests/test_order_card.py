"""
Tests para OrderCard — Tarjeta de orden (FILLED / PENDING / CANCELLED).
"""
import asyncio

import flet as ft

from ui.components.colors import STATUS_COLORS
from ui.components.order_card import _CARD_BG, OrderCard


def _record(**overrides) -> dict:
    record = {
        "order_id": "abc-1",
        "symbol": "BTCUSDC",
        "side": "BUY",
        "quantity": 0.01,
        "price": 1010.0,
        "mode": "PAPER",
        "status": "FILLED",
        "pnl": None,
        "timestamp": 1_700_000_000,
    }
    record.update(overrides)
    return record


def test_card_exposes_order_id_and_status():
    card = OrderCard(_record())
    assert card.order_id == "abc-1"
    assert card.status == "FILLED"
    assert card._flash_task is None


def test_status_chip_uses_shared_palette():
    color, label = STATUS_COLORS["PENDING"]
    card = OrderCard(_record(status="PENDING"))
    assert card._status_chip.content.value == label
    assert card._status_chip.content.color == color
    assert card._status_chip.border.top.color == color


def test_update_status_changes_chip_in_place():
    card = OrderCard(_record(status="PENDING"))
    chip = card._status_chip
    card.update_status("CANCELLED")
    color, label = STATUS_COLORS["CANCELLED"]
    assert card.status == "CANCELLED"
    assert card._status_chip is chip
    assert chip.content.value == label
    assert chip.content.color == color


def test_unknown_status_falls_back_to_grey():
    card = OrderCard(_record(status="WEIRD"))
    assert card._status_chip.content.color == ft.Colors.BLUE_GREY_400
    assert card._status_chip.content.value == "WEIRD"


def test_pnl_shows_placeholder_when_missing():
    assert OrderCard(_record()).pnl_text == "---"
    assert OrderCard(_record(pnl=None)).pnl_text == "---"


def test_set_pnl_formats_positive_and_negative():
    card = OrderCard(_record())
    card.set_pnl(12.5)
    assert card.pnl_text == "+12.50 USDT"
    assert card._pnl.color == ft.Colors.GREEN_400
    card.set_pnl(-3.0)
    assert card.pnl_text == "-3.00 USDT"
    assert card._pnl.color == ft.Colors.RED_400


def test_set_pnl_is_idempotent():
    card = OrderCard(_record())
    card.set_pnl(1.0)
    card._pnl.value = "TAMPERED"
    card.set_pnl(1.0)
    assert card.pnl_text == "TAMPERED"


def test_flash_without_event_loop_leaves_card_visible():
    card = OrderCard(_record(), flash=True)
    card.update_status("CANCELLED", flash=True)
    card.flash()
    assert card.opacity == 1.0
    assert card._flash_task is None


def test_flash_runs_as_single_cancelled_task_per_call():
    async def scenario():
        card = OrderCard(_record(), flash=True)
        first = card._flash_task
        card.flash()
        second = card._flash_task
        card.will_unmount()
        await asyncio.gather(first, second, return_exceptions=True)
        return card, first, second

    card, first, second = asyncio.run(scenario())
    assert first is not None
    assert second is not None
    assert second is not first
    assert second is card._flash_task
    assert second.cancelled()
    assert card.opacity == 1.0
    assert card.bgcolor == _CARD_BG


def test_will_unmount_cancels_running_flash():
    async def scenario():
        card = OrderCard(_record(), flash=True)
        card.will_unmount()
        await asyncio.gather(card._flash_task, return_exceptions=True)
        return card

    card = asyncio.run(scenario())
    assert card.opacity == 1.0
    assert card.bgcolor == _CARD_BG
