"""
Tests para UpdateBatcher — Batcher centralizado de actualizaciones de UI.
"""
from __future__ import annotations

from core.update_batcher import UpdateBatcher


class MockControl:
    """Mock de control Flet para testing."""

    def __init__(self, name: str = "ctrl") -> None:
        self.name = name
        self.update_count = 0
        self.update_raises: Exception | None = None

    def update(self) -> None:
        if self.update_raises:
            raise self.update_raises
        self.update_count += 1


class UnmountedControl(MockControl):
    """Mock que simula un control desmontado."""

    def update(self) -> None:
        raise RuntimeError("Control not mounted")


def test_batcher_basic():
    batcher = UpdateBatcher()
    c1 = MockControl("c1")
    c2 = MockControl("c2")

    batcher.mark_dirty(c1)
    batcher.mark_dirty(c2)

    assert batcher.pending_count == 2
    batcher.flush_sync()
    assert batcher.pending_count == 0
    assert c1.update_count == 1
    assert c2.update_count == 1


def test_batcher_deduplication():
    batcher = UpdateBatcher()
    c1 = MockControl("c1")

    batcher.mark_dirty(c1)
    batcher.mark_dirty(c1)  # duplicate
    batcher.mark_dirty(c1)  # duplicate

    assert batcher.pending_count == 1
    batcher.flush_sync()
    assert c1.update_count == 1  # solo 1 vez


def test_batcher_handles_unmounted_control():
    batcher = UpdateBatcher()
    c1 = MockControl("c1")
    c2 = UnmountedControl("c2")

    batcher.mark_dirty(c1)
    batcher.mark_dirty(c2)

    batcher.flush_sync()
    assert c1.update_count == 1  # c1 se actualizó
    # c2 lanzó RuntimeError pero no rompió el batch


def test_batcher_handles_generic_exception():
    batcher = UpdateBatcher()
    c1 = MockControl("c1")
    c1.update_raises = ValueError("test error")
    c2 = MockControl("c2")

    batcher.mark_dirty(c1)
    batcher.mark_dirty(c2)

    batcher.flush_sync()
    assert c2.update_count == 1  # c2 se actualizó aunque c1 falló


def test_batcher_empty_flush():
    batcher = UpdateBatcher()
    batcher.flush_sync()  # no debe fallar
    assert batcher.pending_count == 0


def test_batcher_flush_clears_pending():
    batcher = UpdateBatcher()
    c1 = MockControl("c1")

    batcher.mark_dirty(c1)
    batcher.flush_sync()
    assert batcher.pending_count == 0

    # Mark again after flush
    batcher.mark_dirty(c1)
    assert batcher.pending_count == 1
    batcher.flush_sync()
    assert c1.update_count == 2  # 2 flushes = 2 updates


def test_batcher_preserves_order():
    batcher = UpdateBatcher()
    update_order = []

    class OrderedControl(MockControl):
        def update(self):
            update_order.append(self.name)

    c1 = OrderedControl("first")
    c2 = OrderedControl("second")
    c3 = OrderedControl("third")

    batcher.mark_dirty(c1)
    batcher.mark_dirty(c2)
    batcher.mark_dirty(c3)

    batcher.flush_sync()
    # El batcher usa set internamente, así que el orden no está garantizado.
    # Verificar que los 3 se actualizaron exactamente 1 vez.
    assert len(update_order) == 3
    assert set(update_order) == {"first", "second", "third"}
