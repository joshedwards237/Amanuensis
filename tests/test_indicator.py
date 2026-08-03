"""The minimum recording indicator. §5.4's non-negotiable, at its smallest.

§5.4: *the user must always know whether the mic is live*, and it is stated as
a privacy requirement rather than a polish one — "regardless of where the audio
goes". Phase 2b is the first phase in which a daemon holds the microphone on a
global hotkey, so it is the first phase in which that requirement can be
violated.

This is **not** `TrayApp`, which is Phase 4. It has no menu, no preferences and
no business logic; it renders one of four states into the menu bar and that is
the whole of it. The tests below are therefore about two things and nothing
else:

**Every state renders as something visible.** A state that renders as an empty
title is a menu-bar item the user cannot find, which is the ambiguity §5.4
forbids dressed as a UI detail.

**Updates arrive from other threads.** The controller sets state from the
event-tap thread and from the worker; AppKit may only be touched on the main
thread. The marshalling is asserted, because getting it wrong produces a
status item that is *usually* right — which is worse than one that is never
right, since nobody investigates it.
"""

from __future__ import annotations

from typing import Any

import pytest

from amanuensis.controllers.dictation_controller import DictationState
from amanuensis.ui import indicator as indicator_module
from amanuensis.ui.indicator import RecordingIndicator


class _FakeButton:
    def __init__(self) -> None:
        self.titles: list[str] = []
        self.tooltips: list[str] = []

    def setTitle_(self, value: str) -> None:
        self.titles.append(value)

    def setToolTip_(self, value: str) -> None:
        self.tooltips.append(value)


class _FakeStatusItem:
    def __init__(self) -> None:
        self._button = _FakeButton()

    def button(self) -> _FakeButton:
        return self._button


class _FakeStatusBar:
    def __init__(self) -> None:
        self.items: list[_FakeStatusItem] = []

    def statusItemWithLength_(self, _length: float) -> _FakeStatusItem:
        item = _FakeStatusItem()
        self.items.append(item)
        return item


class _FakeAppKit:
    NSVariableStatusItemLength = -1.0

    def __init__(self) -> None:
        bar = _FakeStatusBar()
        self.bar = bar
        self.NSStatusBar = type(
            "NSStatusBar", (), {"systemStatusBar": staticmethod(lambda: bar)}
        )
        self.runs = 0
        self.stops = 0
        outer = self

        class NSApplication:
            @staticmethod
            def sharedApplication() -> Any:
                return outer

        self.NSApplication = NSApplication
        self.NSApplicationActivationPolicyAccessory = 1

    # -- the shared application ------------------------------------------

    def setActivationPolicy_(self, _policy: int) -> None:
        pass

    def run(self) -> None:
        self.runs += 1

    def stop_(self, _sender: Any) -> None:
        self.stops += 1


class _FakeMainQueue:
    """Runs the block immediately, and records that it was asked to.

    The real one schedules on the main thread's run loop. What the test needs
    to know is that the indicator *went through* it rather than touching
    AppKit from the calling thread.
    """

    def __init__(self) -> None:
        self.blocks = 0

    def addOperationWithBlock_(self, block: Any) -> None:
        self.blocks += 1
        block()


@pytest.fixture
def appkit(monkeypatch: pytest.MonkeyPatch) -> _FakeAppKit:
    fake = _FakeAppKit()
    queue = _FakeMainQueue()
    monkeypatch.setattr(indicator_module, "_appkit", lambda: fake)
    monkeypatch.setattr(indicator_module, "_main_queue", lambda: queue)
    fake.queue = queue  # type: ignore[attr-defined]
    return fake


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", list(DictationState))
def test_every_state_renders_something_visible(
    appkit: _FakeAppKit, state: DictationState
) -> None:
    """A blank title is a menu-bar item the user cannot find."""
    made = RecordingIndicator()
    made.show()
    made.set_state(state)

    title = appkit.bar.items[0].button().titles[-1]
    assert title.strip(), f"{state} rendered as blank"


def test_recording_is_distinguishable_from_idle(appkit: _FakeAppKit) -> None:
    """The one distinction §5.4 actually requires. Everything else here is
    convenience; this is the privacy requirement."""
    made = RecordingIndicator()
    made.show()

    made.set_state(DictationState.IDLE)
    idle = appkit.bar.items[0].button().titles[-1]
    made.set_state(DictationState.RECORDING)
    recording = appkit.bar.items[0].button().titles[-1]

    assert idle != recording


def test_each_state_has_a_tooltip_naming_it(appkit: _FakeAppKit) -> None:
    """The glyph is the requirement; the tooltip is what makes it legible to
    a user who has not read the README."""
    made = RecordingIndicator()
    made.show()
    made.set_state(DictationState.TRANSCRIBING)

    assert "transcrib" in appkit.bar.items[0].button().tooltips[-1].lower()


def test_the_indicator_is_shown_before_the_first_state(appkit: _FakeAppKit) -> None:
    """`show()` draws idle immediately. A status item that appears only once
    the user has dictated does not tell them the daemon is running."""
    made = RecordingIndicator()
    made.show()

    assert appkit.bar.items[0].button().titles == [
        indicator_module.GLYPHS[DictationState.IDLE]
    ]


# ---------------------------------------------------------------------------
# Threads
# ---------------------------------------------------------------------------


def test_state_updates_are_marshalled_to_the_main_thread(
    appkit: _FakeAppKit,
) -> None:
    """AppKit may only be touched on the main thread; the controller sets state
    from the event tap and from the worker. Getting this wrong yields a status
    item that is usually right, which nobody investigates."""
    made = RecordingIndicator()
    made.show()
    before = appkit.queue.blocks  # type: ignore[attr-defined]

    made.set_state(DictationState.RECORDING)

    assert appkit.queue.blocks == before + 1  # type: ignore[attr-defined]


def test_setting_state_before_show_does_not_raise(appkit: _FakeAppKit) -> None:
    """The controller starts before the run loop does. A daemon that crashed
    on an early state change would fail at exactly the moment §5.4 cares
    about."""
    made = RecordingIndicator()
    made.set_state(DictationState.RECORDING)

    assert appkit.bar.items == []


def test_show_is_idempotent(appkit: _FakeAppKit) -> None:
    made = RecordingIndicator()
    made.show()
    made.show()

    assert len(appkit.bar.items) == 1


# ---------------------------------------------------------------------------
# The run loop
# ---------------------------------------------------------------------------


def test_run_uses_an_accessory_activation_policy(appkit: _FakeAppKit) -> None:
    """Accessory, not Regular: a dictation daemon must not take a Dock icon or
    steal focus from the application the user is about to dictate into."""
    made = RecordingIndicator()
    made.show()
    made.run()

    assert appkit.runs == 1


def test_stop_ends_the_run_loop(appkit: _FakeAppKit) -> None:
    made = RecordingIndicator()
    made.show()
    made.stop()

    assert appkit.stops == 1
