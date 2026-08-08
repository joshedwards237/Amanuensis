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
from amanuensis.ui.indicator import _TOOLTIPS, GLYPHS, RecordingIndicator


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
        self.NSEventTypeApplicationDefined = 15
        self.posted: list[dict[str, Any]] = []

        class NSEvent:
            @staticmethod
            def otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(  # noqa: E501
                event_type: int, *_rest: Any
            ) -> str:
                return f"event-{event_type}"

        self.NSEvent = NSEvent
        self.NSMakePoint = staticmethod(lambda x, y: (x, y))

    # -- the shared application ------------------------------------------

    def setActivationPolicy_(self, _policy: int) -> None:
        pass

    def run(self) -> None:
        self.runs += 1

    def stop_(self, _sender: Any) -> None:
        self.stops += 1

    def postEvent_atStart_(self, event: Any, at_start: bool) -> None:
        self.posted.append({"event": event, "at_start": at_start})


class _FakeFoundation:
    def __init__(self, queue: Any) -> None:
        self._queue = queue
        self.timers: list[dict[str, Any]] = []
        outer = self

        class NSTimer:
            @staticmethod
            def scheduledTimerWithTimeInterval_repeats_block_(
                interval: float, repeats: bool, block: Any
            ) -> str:
                outer.timers.append(
                    {"interval": interval, "repeats": repeats, "block": block}
                )
                return "timer"

        class NSOperationQueue:
            @staticmethod
            def mainQueue() -> Any:
                return queue

        self.NSTimer = NSTimer
        self.NSOperationQueue = NSOperationQueue


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
    foundation = _FakeFoundation(queue)
    monkeypatch.setattr(indicator_module, "_appkit", lambda: fake)
    monkeypatch.setattr(indicator_module, "_foundation", lambda: foundation)
    fake.queue = queue  # type: ignore[attr-defined]
    fake.timers = foundation.timers  # type: ignore[attr-defined]
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


def test_stop_wakes_a_loop_with_no_events_to_dequeue(appkit: _FakeAppKit) -> None:
    """Found by running it, not by reading about it.

    `NSApplication.stop_` does not end the loop; it sets a flag that is checked
    the next time the loop *dequeues an event*. An idle dictation daemon has no
    events — nothing is clicked, nothing is dragged — so Ctrl-C and SIGTERM
    both did exactly nothing, and the only way to stop a process holding the
    microphone was `kill -9`.

    Posting a synthetic application-defined event is the documented idiom for
    this, and `atStart=True` puts it at the head of the queue so the flag is
    seen on the very next pass.
    """
    made = RecordingIndicator()
    made.show()
    made.stop()

    assert appkit.stops == 1
    assert appkit.posted, "stop() must post an event or the loop never notices"
    assert appkit.posted[-1]["at_start"] is True


def test_run_installs_a_timer_so_python_can_run(appkit: _FakeAppKit) -> None:
    """Without this, Ctrl-C does not work. Found by running it.

    CPython executes a signal handler between bytecodes on the main thread —
    and the main thread is blocked inside `NSApplication.run()`, which is a C
    call that does not return until the loop ends. So SIGINT and SIGTERM are
    recorded and never delivered: the handler that would stop the daemon
    cannot run until the daemon has already stopped.

    A repeating timer with a Python callback breaks the deadlock by returning
    to the interpreter on every tick, which is where the pending handler
    finally runs. The interval is a latency/wakeup trade and is deliberately
    short — this is the only way to stop a process that holds the microphone.
    """
    made = RecordingIndicator()
    made.show()
    made.run()

    assert appkit.timers, "run() must yield to the interpreter or Ctrl-C is dead"
    assert appkit.timers[-1]["repeats"] is True
    assert appkit.timers[-1]["interval"] <= 0.5


def test_every_state_has_a_glyph_and_a_tooltip() -> None:
    """Asserted over the enum rather than by naming the states.

    A fifth state arrived in the §5.7 fix — `RECOVERED` — and a hand-maintained
    table would have rendered it as whatever `.get` returned. This is the same
    failure shape as `restore_ms` having no column: an amendment that did not
    reach the thing that displays it.
    """
    for state in DictationState:
        assert state in GLYPHS, f"{state} has no glyph"
        assert state in _TOOLTIPS, f"{state} has no tooltip"


def test_recovery_is_not_shown_as_success() -> None:
    """§5.4: what reached the cursor was decoded without the vocabulary bias
    the user configured, so it is systematically worse at the proper nouns
    `initial_prompt` exists for. Folding that into idle would leave them
    reading substituted text with no signal."""
    assert GLYPHS[DictationState.RECOVERED] != GLYPHS[DictationState.IDLE]
    assert GLYPHS[DictationState.RECOVERED] != GLYPHS[DictationState.ERROR]
