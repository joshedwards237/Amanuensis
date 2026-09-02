"""§7.3 portability floor item 1: the threading model, asserted rather than described.

§7.3 calls this "the item that would actually corner the project" and no phase
had scheduled it. §6.3 names five threads; what it could not do is *check* that
the code obeys them, and the one rule that matters is the one `indicator.py`'s
preamble already flags as "the single most likely thing to be quietly removed":

> Everything here is main-thread work, and nothing that calls it is on the main
> thread.

Phase 4 tripled the surface that rule governs — a status item, a menu, and a
panel, driven from the OS event tap, the worker and now a socket acceptor. The
test below is generic over all three, and it is generic on purpose: a check
written per-surface is a check the fourth surface does not get.

**Why a deferring queue.** `_FakeMainQueue` runs blocks inline, which is
convenient and hides exactly this defect — the tray shipped with its `NSMenu`
built on the calling thread and every test passed. The real main queue defers.
So does this one, and the assertion is that *nothing touched AppKit before the
queue ran*.
"""

from __future__ import annotations

from typing import Any

import pytest

from amanuensis.config import FeedbackConfig
from amanuensis.controllers.dictation_controller import DictationState
from amanuensis.models.results import ClipboardExposure
from amanuensis.ui import indicator as indicator_module
from amanuensis.ui.overlay import RecordingOverlay
from amanuensis.ui.tray import TrayApp
from test_indicator import _FakeAppKit, _FakeFoundation
from test_overlay_fakes import install as install_panels
from test_tray import _FakeMenu, _FakeMenuItem


class _DeferringQueue:
    """The real main queue does not run your block before returning."""

    def __init__(self) -> None:
        self.blocks: list[Any] = []

    def addOperationWithBlock_(self, block: Any) -> None:
        self.blocks.append(block)

    def drain(self) -> int:
        count = len(self.blocks)
        for block in self.blocks:
            block()
        self.blocks.clear()
        return count


class _TripwireAppKit(_FakeAppKit):
    """Records every AppKit access and whether the main queue was running."""

    def __init__(self) -> None:
        super().__init__()
        self.on_main = False
        self.off_main_touches: list[str] = []

    def touched(self, what: str) -> None:
        if not self.on_main:
            self.off_main_touches.append(what)


@pytest.fixture
def tripwire(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[_TripwireAppKit, _DeferringQueue]:
    fake = _TripwireAppKit()
    install_panels(fake)
    queue = _DeferringQueue()

    class _Menu(_FakeMenu):
        @classmethod
        def alloc(cls) -> _Menu:
            fake.touched("NSMenu.alloc")
            return cls()

    class _Item(_FakeMenuItem):
        @classmethod
        def alloc(cls) -> _Item:
            fake.touched("NSMenuItem.alloc")
            return cls()

    real_panel_alloc = fake.NSPanel.alloc

    class _Panel:
        @staticmethod
        def alloc() -> Any:
            fake.touched("NSPanel.alloc")
            return real_panel_alloc()

    fake.NSMenu = _Menu  # type: ignore[attr-defined]
    fake.NSMenuItem = _Item  # type: ignore[attr-defined]
    fake.NSPanel = _Panel  # type: ignore[attr-defined]

    monkeypatch.setattr(indicator_module, "_appkit", lambda: fake)
    monkeypatch.setattr(indicator_module, "_foundation", lambda: _FakeFoundation(queue))
    monkeypatch.setattr(indicator_module, "_main_queue", lambda: queue)
    return fake, queue


def _drain(fake: _TripwireAppKit, queue: _DeferringQueue) -> int:
    fake.on_main = True
    try:
        return queue.drain()
    finally:
        fake.on_main = False


def test_the_tray_touches_no_appkit_off_the_main_queue(
    tripwire: tuple[_TripwireAppKit, _DeferringQueue],
) -> None:
    fake, queue = tripwire
    tray = TrayApp()
    fake.on_main = True
    tray.show()
    fake.on_main = False
    _drain(fake, queue)

    tray.set_state(DictationState.RECORDING)
    tray.set_error("Accessibility permission was revoked")
    tray.set_clipboard_exposure(ClipboardExposure(detected=True, manager="Maccy"))

    assert fake.off_main_touches == [], fake.off_main_touches
    assert _drain(fake, queue) > 0, "nothing was scheduled — the test proved nothing"


def test_the_overlay_touches_no_appkit_off_the_main_queue(
    tripwire: tuple[_TripwireAppKit, _DeferringQueue],
) -> None:
    fake, queue = tripwire
    overlay = RecordingOverlay(FeedbackConfig())

    overlay.set_state(DictationState.RECORDING)
    overlay.set_state(DictationState.IDLE)
    overlay.hide()

    assert fake.off_main_touches == [], fake.off_main_touches
    assert _drain(fake, queue) > 0, "nothing was scheduled — the test proved nothing"


def test_the_indicator_touches_no_appkit_off_the_main_queue(
    tripwire: tuple[_TripwireAppKit, _DeferringQueue],
) -> None:
    """Phase 2b's surface, still governed by the same rule."""
    fake, queue = tripwire
    from amanuensis.ui.indicator import RecordingIndicator

    indicator = RecordingIndicator()
    fake.on_main = True
    indicator.show()
    fake.on_main = False
    _drain(fake, queue)

    for state in DictationState:
        indicator.set_state(state)

    assert fake.off_main_touches == [], fake.off_main_touches
    assert _drain(fake, queue) > 0, "nothing was scheduled — the test proved nothing"


def test_the_tripwire_itself_catches_an_off_main_touch(
    tripwire: tuple[_TripwireAppKit, _DeferringQueue],
) -> None:
    """The positive control, without which the three tests above pass on a
    tripwire that records nothing.

    This is the failure the tray actually shipped with: `NSMenu.alloc()` called
    from whichever thread reported the state change.
    """
    fake, _queue = tripwire
    fake.NSMenu.alloc()  # type: ignore[attr-defined]
    assert fake.off_main_touches == ["NSMenu.alloc"]
