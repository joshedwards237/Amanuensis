"""Is the microphone live? A glyph in the menu bar, and nothing else.

§5.4 makes unambiguous recording state **non-negotiable**, and grounds it in
privacy rather than polish: a dictation tool that is vague about whether it is
listening is a privacy problem *regardless of where the audio goes*. Phase 2b
is the first phase in which a daemon holds the microphone on a global hotkey,
which makes it the first phase in which that can be violated — so this exists
now rather than in Phase 4 with the rest of the tray.

**This is not `TrayApp`.** No menu, no preferences, no history, no quit item,
no business logic (§6.2). It maps four states to four glyphs and draws them.
Phase 4's `TrayApp` renders the same states with a menu attached, and the
resolution follows Phase 2a's precedent exactly — that gate needed a clipboard
indicator the Phase 4 tray was going to own, and built the minimum surface
rather than importing the phase.

**§5.4 says "visible without the tray menu open", so the state is in the title
rather than behind a click.** A menu-bar item whose state can only be read by
opening it is the requirement restated as its own violation.

**Everything here is main-thread work, and nothing that calls it is on the main
thread.** AppKit is not thread-safe; the controller sets state from the OS
event tap and from the worker. `set_state` therefore hands a block to the main
queue rather than touching the status item, which is the single most likely
thing to be quietly removed by someone who tests it once on the main thread and
sees it work.

The activation policy is `Accessory`. `Regular` would give a dictation daemon a
Dock icon and let it take focus — from, specifically, the application the user
is about to dictate into.
"""

from __future__ import annotations

import threading
from typing import Any, Final

from amanuensis.controllers.dictation_controller import DictationState

__all__ = ["GLYPHS", "RecordingIndicator"]

#: How often the run loop hands control back to Python. This is the *only*
#: thing that lets a signal handler run while the daemon is idle, so it is a
#: liveness knob rather than a performance one — see `run`. Four wakeups a
#: second on an otherwise sleeping process is not a cost worth optimising
#: against the ability to stop a process that holds the microphone.
_WAKEUP_INTERVAL_S: Final = 0.25

#: One per §5.4 state. Chosen to be distinguishable at a glance and in
#: monochrome — the menu bar is rendered in the system's accent-free style and
#: a colour-only distinction would be invisible to a substantial fraction of
#: users, on a control whose whole job is to be read without effort.
GLYPHS: Final[dict[DictationState, str]] = {
    DictationState.IDLE: "○",
    DictationState.RECORDING: "●",
    DictationState.TRANSCRIBING: "◐",
    DictationState.ERROR: "⚠",
}

#: The glyph is the requirement; this is what makes it legible to a user who
#: has not read the README and is hovering to find out.
_TOOLTIPS: Final[dict[DictationState, str]] = {
    DictationState.IDLE: "Amanuensis — idle, the microphone is not live",
    DictationState.RECORDING: "Amanuensis — RECORDING, the microphone is live",
    DictationState.TRANSCRIBING: "Amanuensis — transcribing, the microphone is closed",
    DictationState.ERROR: "Amanuensis — something failed; see the terminal",
}


def _appkit() -> Any:
    """Import Cocoa at the point of use, never at module import.

    Same argument `injection/macos.py` makes, and the seam the tests replace —
    a test that created a real `NSStatusItem` would put a glyph in the
    developer's menu bar and leave it there.
    """
    import AppKit

    return AppKit


def _foundation() -> Any:
    """Import Foundation at the point of use. `NSTimer` and the main queue."""
    import Foundation

    return Foundation


def _main_queue() -> Any:
    """The main thread's operation queue. The only safe route into AppKit."""
    return _foundation().NSOperationQueue.mainQueue()


class RecordingIndicator:
    """One status item, four states, no menu."""

    def __init__(self) -> None:
        self._item: Any | None = None
        self._state = DictationState.IDLE
        #: Guards `_item` only. The status item is created on the main thread
        #: and read by whichever thread reports a state change; the lock is
        #: held for a read and nothing else.
        self._lock = threading.Lock()

    @property
    def state(self) -> DictationState:
        return self._state

    def show(self) -> None:
        """Create the status item and draw the idle state. Main thread only.

        Idempotent, and it draws immediately rather than waiting for the first
        state change: a status item that appears only once the user has
        dictated does not tell them the daemon is running, which is half of
        what §5.4 asks the indicator to communicate.
        """
        with self._lock:
            if self._item is not None:
                return
            appkit = _appkit()
            self._item = appkit.NSStatusBar.systemStatusBar().statusItemWithLength_(
                appkit.NSVariableStatusItemLength
            )
        self._draw(self._state)

    def set_state(self, state: DictationState) -> None:
        """Record and render. Safe to call from any thread.

        Called before `show()` during daemon start — the controller comes up
        before the run loop does — and that must not raise. A daemon that
        crashed on an early state change would fail at precisely the moment
        §5.4 is about.
        """
        self._state = state
        with self._lock:
            if self._item is None:
                return
        _main_queue().addOperationWithBlock_(lambda: self._draw(state))

    def run(self) -> None:
        """Run the AppKit loop. Blocks. Main thread only.

        This is the reason §6.3 puts the tray on the main thread: a macOS
        status item requires it, and everything else in the daemon is
        arranged around that one fact.
        """
        appkit = _appkit()
        app = appkit.NSApplication.sharedApplication()
        app.setActivationPolicy_(appkit.NSApplicationActivationPolicyAccessory)
        # Without this timer, Ctrl-C does not work. CPython runs a signal
        # handler between bytecodes on the main thread, and the main thread is
        # about to block inside `run()` — a C call that does not return until
        # the loop ends. SIGINT would be recorded and never delivered: the
        # handler that stops the daemon cannot run until the daemon has
        # stopped. Every tick returns to the interpreter, which is where the
        # pending handler finally runs.
        _foundation().NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            _WAKEUP_INTERVAL_S, True, lambda _timer: None
        )
        app.run()

    def stop(self) -> None:
        """Ask the AppKit loop to end. Returns immediately.

        **`stop_` alone does not end the loop.** It sets a flag that
        `NSApplication` checks the next time it *dequeues an event* — and an
        idle dictation daemon has no events, because nothing is being clicked
        or dragged. Found by running it: Ctrl-C and SIGTERM both did exactly
        nothing, and the only way to stop a process holding the microphone was
        `kill -9`. That is §5.4's ambiguity with the escape hatch removed.

        Posting a synthetic application-defined event is the documented fix.
        `atStart=True` puts it at the head of the queue so the flag is seen on
        the very next pass rather than behind whatever else is waiting.
        """
        appkit = _appkit()
        app = appkit.NSApplication.sharedApplication()
        app.stop_(None)
        wake = appkit.NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(  # noqa: E501
            appkit.NSEventTypeApplicationDefined,
            appkit.NSMakePoint(0, 0),
            0,
            0.0,
            0,
            None,
            0,
            0,
            0,
        )
        app.postEvent_atStart_(wake, True)

    def _draw(self, state: DictationState) -> None:
        """Touch the status item. Main thread only — see `set_state`."""
        item = self._item
        if item is None:
            return
        button = item.button()
        if button is None:  # pragma: no cover — AppKit may return nil
            return
        button.setTitle_(GLYPHS[state])
        button.setToolTip_(_TOOLTIPS[state])
