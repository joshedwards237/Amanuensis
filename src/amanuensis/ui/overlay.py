"""The §5.4 recording affordance: a panel that survives full screen.

Why this exists at all is worth stating, because the requirement it satisfies
was already met. The Phase 2b glyph fills on press and empties on release, and
that was confirmed against a running daemon. Its first user then said a glyph is
not enough to be confident the microphone is live — a requirement met to the
letter and reported inadequate by the person using it, which §5.4 records as
worth more than one argued into the spec.

**The condition is full screen with the menu bar hidden**, which is where the
glyph is not merely small but *absent*, and which is ordinary for the writing
and coding this product is for. §5.4's confidence test — written before this
file existed, deliberately — is exactly that case. Two AppKit flags decide
whether this module passes it or repeats the failure it was built to fix:
`CanJoinAllSpaces` and `FullScreenAuxiliary`. Without the second, the panel is
invisible in precisely the case the criterion names.

**It shows only while RECORDING, and TRANSCRIBING is the trap.** Transcribing is
the longest state, it looks busy, and carrying the panel through it is the
natural thing to do. The microphone is already closed by then, so a panel that
stayed up would tell the user they were being recorded when they were not. For a
privacy affordance, an over-report is not the safe direction — it is the
direction that teaches people to ignore it.

**It never takes focus.** It appears over the application the user is dictating
into; taking key focus would send their keystrokes somewhere else, from
specifically the window that is about to receive the transcript. So:
`orderFrontRegardless`, never `makeKeyAndOrderFront_`, and mouse events ignored
so it cannot swallow a click either.

What it deliberately does not do: carry error text (that is `TrayApp`, which has
a menu and therefore room for words), animate, or offer any control. It answers
one question.
"""

from __future__ import annotations

import threading
from typing import Any, Final

from amanuensis.config import FeedbackConfig
from amanuensis.controllers.dictation_controller import DictationState

__all__ = ["RecordingOverlay", "frame_for", "should_show"]

#: Panel geometry. Small enough to sit out of the way, large enough to read
#: without looking for it — the whole complaint about the glyph was that it
#: required looking.
_WIDTH: Final = 220.0
_HEIGHT: Final = 44.0
#: Distance from the chosen screen edge.
_MARGIN: Final = 48.0

_LABEL: Final = "● RECORDING"


def should_show(state: DictationState) -> bool:
    """Is the microphone live *right now*?

    One state, and the enum is not consulted for anything else. See the module
    preamble on why TRANSCRIBING is excluded rather than included.
    """
    return state is DictationState.RECORDING


def frame_for(
    position: str, screen: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    """Panel rect for a screen rect, in AppKit's origin-at-bottom-left space.

    Takes the screen as a tuple rather than an `NSScreen` so it is a function
    rather than a thing needing a framework — the geometry is where an
    off-screen panel comes from, and it should be testable at a second display
    on a small display without a second display or a small display.
    """
    screen_x, screen_y, screen_width, screen_height = screen
    width = min(_WIDTH, screen_width)
    height = min(_HEIGHT, screen_height)
    margin = min(_MARGIN, max(0.0, (screen_height - height) / 2))

    x = screen_x + (screen_width - width) / 2
    if position == "top":
        y = screen_y + screen_height - height - margin
    else:
        # Anything else is a caller bug — config validation rejects it — and a
        # daemon holding the microphone should not die of one.
        y = screen_y + margin
    return (x, y, width, height)


class RecordingOverlay:
    """A borderless panel, shown while the microphone is open."""

    def __init__(self, config: FeedbackConfig | None = None) -> None:
        self._config = config if config is not None else FeedbackConfig()
        self._panel: Any | None = None
        self._visible = False
        #: Guards `_panel` and `_visible`. Set from the event tap and the
        #: worker, drawn on the main queue — the indicator's shape exactly.
        self._lock = threading.Lock()

    @property
    def visible(self) -> bool:
        return self._visible

    def set_state(self, state: DictationState) -> None:
        """Safe from any thread, and safe before anything is shown."""
        if not self._config.overlay:
            return
        wanted = should_show(state)
        with self._lock:
            if wanted == self._visible:
                return
            self._visible = wanted
        # `vad_auto` can flip this repeatedly with no user action, so the panel
        # is created once and re-ordered — never rebuilt per transition, which
        # would leave a pile of them on screen.
        from amanuensis.ui.indicator import _main_queue

        _main_queue().addOperationWithBlock_(lambda: self._render(wanted))

    def hide(self) -> None:
        with self._lock:
            self._visible = False
        from amanuensis.ui.indicator import _main_queue

        _main_queue().addOperationWithBlock_(lambda: self._render(False))

    def _render(self, wanted: bool) -> None:
        """Main thread only — see `set_state`."""
        panel = self._panel if self._panel is not None else self._build()
        if panel is None:  # pragma: no cover — AppKit returned nil
            return
        if wanted:
            panel.orderFrontRegardless()
        else:
            panel.orderOut_(None)

    def _build(self) -> Any:
        from amanuensis.ui.indicator import _appkit

        appkit = _appkit()
        screen = appkit.NSScreen.mainScreen()
        rect = frame_for(self._config.overlay_position, tuple(screen.frame()))

        panel = appkit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            appkit.NSMakeRect(*rect),
            appkit.NSWindowStyleMaskBorderless
            | appkit.NSWindowStyleMaskNonactivatingPanel,
            appkit.NSBackingStoreBuffered,
            False,
        )
        # The two flags the confidence test turns on. Stationary keeps it put
        # when the user swipes between spaces rather than sliding it around.
        panel.setCollectionBehavior_(
            appkit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | appkit.NSWindowCollectionBehaviorFullScreenAuxiliary
            | appkit.NSWindowCollectionBehaviorStationary
        )
        panel.setLevel_(appkit.NSStatusWindowLevel)
        # It sits over the window about to receive the transcript. It must not
        # take a click, and it must never take key focus.
        panel.setIgnoresMouseEvents_(True)
        panel.setOpaque_(False)
        panel.setHasShadow_(True)

        label = appkit.NSTextField.alloc().initWithFrame_(appkit.NSMakeRect(*rect))
        label.setStringValue_(_LABEL)
        panel.setContentView_(label)

        self._panel = panel
        return panel
