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

import math
import threading
from collections import deque
from collections.abc import Callable, Sequence
from typing import Any, Final

from amanuensis.config import FeedbackConfig
from amanuensis.controllers.dictation_controller import DictationState

__all__ = [
    "BAR_COUNT",
    "CORNER_RADIUS",
    "MAX_BAR_HEIGHT",
    "RecordingOverlay",
    "bar_heights",
    "frame_for",
    "should_show",
]

#: A pill, not a panel. The first version was 220x44 with the text
#: "● RECORDING" in it, and its user's verdict was "tacky, too square, too big,
#: and it should have no text". The words were doing no work: this thing answers
#: one question and a moving waveform answers it faster than a label you have to
#: read. §5.4 asks for *confidence*, which is a glance, not a sentence.
_WIDTH: Final = 112.0
_HEIGHT: Final = 26.0
#: Half the height, so the ends are fully round rather than rounded-off.
CORNER_RADIUS: Final = _HEIGHT / 2.0
#: Distance from the chosen screen edge.
_MARGIN: Final = 44.0

#: Bars, newest on the right so it reads as motion in one direction.
BAR_COUNT: Final = 7
_BAR_WIDTH: Final = 3.0
_BAR_GAP: Final = 4.0
#: Never zero. A dead-flat pill is indistinguishable from a frozen one, and
#: "is it live or is it broken" is the ambiguity §5.4 exists to remove.
MIN_BAR_HEIGHT: Final = 3.0
MAX_BAR_HEIGHT: Final = 16.0
#: RMS that counts as full deflection. Ordinary speech at a desk microphone
#: sits around 0.05-0.3 in this project's float32 capture, so a ceiling of 0.35
#: keeps normal talking off the clip and leaves headroom for a shout.
_FULL_SCALE: Final = 0.35


def should_show(state: DictationState) -> bool:
    """Is the microphone live *right now*?

    One state, and the enum is not consulted for anything else. See the module
    preamble on why TRANSCRIBING is excluded rather than included.
    """
    return state is DictationState.RECORDING


def bar_heights(levels: Sequence[float]) -> tuple[float, ...]:
    """Recent RMS levels to bar heights, newest last. Pure.

    Every hostile input is handled here rather than at the call site, because
    the call site is the PortAudio callback thread and the values come from
    whatever the device produced: NaN and infinities are real, and a bar of
    height NaN is a panel that draws nothing or crashes drawing it.

    A short history is padded with silence rather than drawn narrow — the first
    few blocks after the key goes down are all there is, and a pill that fills
    in from the left looks like a bug.
    """
    recent = list(levels)[-BAR_COUNT:]
    padded = [0.0] * (BAR_COUNT - len(recent)) + recent

    heights: list[float] = []
    span = MAX_BAR_HEIGHT - MIN_BAR_HEIGHT
    for level in padded:
        if not math.isfinite(level) or level < 0.0:
            level = 0.0
        fraction = min(1.0, level / _FULL_SCALE)
        heights.append(MIN_BAR_HEIGHT + span * fraction)
    return tuple(heights)


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

    def __init__(
        self,
        config: FeedbackConfig | None = None,
        *,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._config = config if config is not None else FeedbackConfig()
        #: Set once the panel has failed. A panel that raised once will raise
        #: every time, and retrying it on every state change turns one defect
        #: into a failure on every dictation.
        self._failed = False
        self._on_error = on_error
        #: Recent audio levels, newest last. Bounded, and read on the main
        #: queue while the PortAudio thread appends — a deque with a maxlen is
        #: atomic enough for both under the GIL, and the alternative is a lock
        #: on the capture thread's hot path.
        self._levels: deque[float] = deque([0.0] * BAR_COUNT, maxlen=BAR_COUNT)
        self._bars: list[Any] = []
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
        if not self._config.overlay or self._failed:
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

    def set_level(self, rms: float) -> None:
        """One audio block's level. Called from the PortAudio thread.

        Cheap on purpose: an append and a main-queue dispatch. That thread has
        a deadline and missing it costs audio, which is the same reason
        `AudioCapture._on_block` does almost nothing.
        """
        if not self._config.overlay or self._failed:
            return
        self._levels.append(rms)
        with self._lock:
            if not self._visible or self._panel is None:
                return
        from amanuensis.ui.indicator import _main_queue

        _main_queue().addOperationWithBlock_(self._draw_bars)

    def _draw_bars(self) -> None:
        """Main thread only. Resize the bar layers in place.

        In place rather than rebuilt: at 16 kHz and 512-sample blocks this runs
        about thirty times a second, and allocating seven layers each time
        would make a recording indicator the most expensive thing in the
        process.
        """
        if not self._bars:
            return
        heights = bar_heights(self._levels)
        for layer, height in zip(self._bars, heights, strict=False):
            frame = layer.frame()
            (x, _y), (width, _h) = frame
            layer.setFrame_(((x, (_HEIGHT - height) / 2.0), (width, height)))

    def hide(self) -> None:
        with self._lock:
            self._visible = False
        from amanuensis.ui.indicator import _main_queue

        _main_queue().addOperationWithBlock_(lambda: self._render(False))

    def _render(self, wanted: bool) -> None:
        """Main thread only — see `set_state`.

        Wrapped, and the reason is not defensiveness in general. This runs
        inside an `NSBlockOperation` on the main queue, where an uncaught
        Python exception crosses the PyObjC bridge as an `NSException` and
        **terminates the process** — which on 2026-09-02 it did, taking down a
        daemon that was holding the microphone, over a panel that is a
        confidence feature by §5.4's own account. macOS's own microphone
        indicator carries the correctness half regardless.

        So the overlay is disabled after a failure rather than retried, and the
        failure is reported through `on_error` — which is `TrayApp.set_error`,
        the surface built in this same phase for exactly this: saying what
        happened in words.
        """
        try:
            self._render_unguarded(wanted)
        except Exception as exc:
            self._failed = True
            if self._on_error is not None:
                self._on_error(f"the recording overlay failed and is off: {exc}")

    def _render_unguarded(self, wanted: bool) -> None:
        panel = self._panel if self._panel is not None else self._build()
        if panel is None:  # pragma: no cover — AppKit returned nil
            return
        if wanted:
            # Reset before showing. A pill that opens holding the previous
            # dictation's levels looks frozen for the first thirty milliseconds,
            # which is exactly the "is it live or is it stuck" ambiguity.
            self._levels.clear()
            self._levels.extend([0.0] * BAR_COUNT)
            self._draw_bars()
            panel.orderFrontRegardless()
        else:
            panel.orderOut_(None)

    def _build(self) -> Any:
        from amanuensis.ui.indicator import _appkit

        appkit = _appkit()
        screen = appkit.NSScreen.mainScreen()
        # `NSScreen.frame()` is an `NSRect`, which PyObjC unpacks as
        # `((x, y), (width, height))` — two elements, nested. `tuple(...)` of
        # it is therefore length 2, not 4, and this line read the framework's
        # shape wrong until a daemon crashed on it.
        (origin_x, origin_y), (width, height) = screen.frame()
        rect = frame_for(
            self._config.overlay_position,
            (float(origin_x), float(origin_y), float(width), float(height)),
        )

        panel = appkit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            appkit.NSMakeRect(*rect),
            appkit.NSWindowStyleMaskBorderless
            | appkit.NSWindowStyleMaskNonactivatingPanel,
            appkit.NSBackingStoreBuffered,
            False,
        )
        # The two flags §5.4's confidence test turns on. Stationary keeps it put
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
        # Transparent window, rounded layer inside: an opaque window cannot
        # have round corners, the corners would be drawn square in black.
        panel.setBackgroundColor_(appkit.NSColor.clearColor())

        container = appkit.NSView.alloc().initWithFrame_(
            appkit.NSMakeRect(0.0, 0.0, _WIDTH, _HEIGHT)
        )
        container.setWantsLayer_(True)
        layer = container.layer()
        layer.setCornerRadius_(CORNER_RADIUS)
        quartz = self._quartz()
        layer.setBackgroundColor_(quartz.CGColorCreateGenericGray(0.0, 0.62))
        panel.setContentView_(container)

        self._bars = self._build_bars(appkit, layer)
        self._panel = panel
        return panel

    @staticmethod
    def _quartz() -> Any:
        """`CALayer` and `CGColorCreateGenericGray`, behind one seam.

        `NSColor(...).CGColor()` also works and emits `ObjCPointerWarning` on
        every call, which would print into the operator's terminal each time
        the daemon starts. Quartz's constructor returns a real `CGColorRef`
        with no warning.
        """
        import Quartz

        return Quartz

    @staticmethod
    def _calayer() -> Any:
        """Import Quartz at the point of use, and behind a seam.

        Same argument the rest of this package makes: `manu --help` must not
        load the Objective-C runtime. It is a method rather than a module
        function so a test can replace it without reaching into globals.
        """
        from Quartz import CALayer

        return CALayer

    def _build_bars(self, appkit: Any, parent: Any) -> list[Any]:
        """Seven `CALayer`s, centred as a group.

        Layers rather than views: nothing here handles an event or draws
        custom content, and a layer's frame can be set thirty times a second
        without the view machinery in the way.
        """
        calayer = self._calayer()
        white = self._quartz().CGColorCreateGenericGray(1.0, 0.92)

        span = BAR_COUNT * _BAR_WIDTH + (BAR_COUNT - 1) * _BAR_GAP
        left = (_WIDTH - span) / 2.0
        bars: list[Any] = []
        for index in range(BAR_COUNT):
            bar = calayer.layer()
            x = left + index * (_BAR_WIDTH + _BAR_GAP)
            bar.setFrame_(
                ((x, (_HEIGHT - MIN_BAR_HEIGHT) / 2.0), (_BAR_WIDTH, MIN_BAR_HEIGHT))
            )
            bar.setCornerRadius_(_BAR_WIDTH / 2.0)
            bar.setBackgroundColor_(white)
            parent.addSublayer_(bar)
            bars.append(bar)
        return bars
