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

**Only RECORDING draws the active form, and TRANSCRIBING is the trap.**
Transcribing is the longest state, it looks busy, and carrying the recording
appearance through it is the natural thing to do. The microphone is already
closed by then, so a panel that kept it would tell the user they were being
recorded when they were not. For a privacy affordance, an over-report is not the
safe direction — it is the direction that teaches people to ignore it.

**The pill is persistent as of 2026-09-17, and that moves the hazard.** It used
to be absent when idle; it is now a narrow pill carrying a static dot, widening
to the full pill with live bars while recording. What this buys is liveness:
gate finding 1 was a panel that had stopped drawing, which looked exactly like a
panel with no reason to draw, for days. What it costs is that the user's
discrimination changes from *presence versus absence* — the easiest kind — to
*state A versus state B*, which is the direction of §5.4's own named failure.

Two rules follow, and both are load-bearing rather than stylistic:

* **The two forms differ on width *and* motion, never motion alone.** A frozen
  render is indistinguishable from a resting one, so a motion-only distinction
  reintroduces finding 1 wearing a new costume. Width survives a frozen render.
  This is the same argument that already forbids `MIN_BAR_HEIGHT = 0`.
* **Levels are ignored while idle, not merely unfed.** The capture thread and
  the state thread are different threads, so a level published microseconds
  after the microphone closed can still arrive at an idle panel. Honouring it
  would twitch the idle pill, and a twitching idle pill reads as recording.

`[feedback] overlay_idle = false` restores the previous behaviour exactly.

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
from enum import Enum
from typing import Any, Final

from amanuensis.config import FeedbackConfig
from amanuensis.controllers.dictation_controller import DictationState

__all__ = [
    "ACTIVE_HEIGHT",
    "ACTIVE_WIDTH",
    "BAR_COUNT",
    "CONTROL_SIZE",
    "CORNER_RADIUS",
    "IDLE_HEIGHT",
    "IDLE_WIDTH",
    "LATCHED_WIDTH",
    "MAX_BAR_HEIGHT",
    "OVERLAY_FAILURE_LIMIT",
    "PANEL_HEIGHT",
    "PANEL_WIDTH",
    "PILL_BORDER_WIDTH",
    "TRANSITION_SECONDS",
    "OverlayMode",
    "RecordingOverlay",
    "as_rect",
    "bar_heights",
    "control_frame",
    "frame_for",
    "is_recording",
    "mode_for",
    "pill_frame",
]

#: A pill, not a panel. The first version was 220x44 with the text
#: "● RECORDING" in it, and its user's verdict was "tacky, too square, too big,
#: and it should have no text". The words were doing no work: this thing answers
#: one question and a moving waveform answers it faster than a label you have to
#: read. §5.4 asks for *confidence*, which is a glance, not a sentence.
_WIDTH: Final = 72.0
_HEIGHT: Final = 22.0
#: The recording form. This is also the **window's** size, in both states: the
#: window is built at the larger of the two and never resized, and the pill
#: layer inside it is what changes. See `pill_frame`.
ACTIVE_WIDTH: Final = _WIDTH
ACTIVE_HEIGHT: Final = _HEIGHT
#: The latched form: the recording pill with a ✕ and a ✓ either side of the
#: bars (§5.2, spec `overlay-controls.md` S5). 114 is the spec's number.
LATCHED_WIDTH: Final = 114.0

#: **The window is built at the widest form and never resized**, so it is this
#: wide in every state — see `pill_frame`. Everything drawn inside is positioned
#: in this coordinate space, which is why the bars do not move when the pill
#: changes width: they are children of the container, not of the pill.
PANEL_WIDTH: Final = LATCHED_WIDTH
PANEL_HEIGHT: Final = _HEIGHT

#: The two controls. 16 px is the spec's number and is the smallest thing S6's
#: reachability criterion is willing to judge.
CONTROL_SIZE: Final = 16.0
#: Smaller than the box it sits in: a glyph set at its frame's height overflows
#: its own line box and is clipped at the top on some fonts.
_CONTROL_FONT_SIZE: Final = 12.0
#: `CATextLayer` renders at 1x unless told, and 1x text on a Retina display
#: reads as broken rather than as plain.
_RETINA_SCALE: Final = 2.0
#: Distance from the panel's centre to each control's centre. Sized so both sit
#: inside the latched pill and outside the bars, with the bars' half-span
#: (19.5) and the control's half-width (8) both cleared.
_CONTROL_OFFSET: Final = 36.0
#: The idle form. A short pill — wider than it is tall, and thinner than the
#: recording form — revised 2026-09-17 from a 22x22 circle on the operator's
#: verdict after seeing it on screen.
#:
#: Both axes shrink rather than one. Length alone reads as a pill sliding out
#: sideways; changing both makes it read as the same object inflating, which is
#: what tells the user the two forms are one thing in two states rather than two
#: unrelated things appearing.
IDLE_WIDTH: Final = 34.0
IDLE_HEIGHT: Final = 10.0

#: A light hairline around the pill. The fill is dark and translucent, which on
#: a white document is a grey smudge with no edge — and an always-present
#: affordance most needs to be legible exactly when the user is writing rather
#: than looking for it. The border reads as an inverse shadow: it separates the
#: pill from the background instead of bleeding into it.
PILL_BORDER_WIDTH: Final = 1.0
_PILL_BORDER_GRAY: Final = 1.0
_PILL_BORDER_ALPHA: Final = 0.28

#: How long the growth takes. Short enough that a dictation started the instant
#: the key goes down is not waiting on a flourish, long enough to be read as
#: motion rather than as a jump. Not a measured number — there is nothing to
#: measure it against — and it is a constant rather than a key because the
#: decision a user actually has is *whether*, which is `[feedback]
#: overlay_animate` and macOS's own Reduce Motion.
TRANSITION_SECONDS: Final = 0.16
#: Half the height, so the ends are fully round rather than rounded-off.
CORNER_RADIUS: Final = _HEIGHT / 2.0
#: Distance from the chosen screen edge.
_MARGIN: Final = 44.0

#: Bars, newest on the right so it reads as motion in one direction.
BAR_COUNT: Final = 7
_BAR_WIDTH: Final = 3.0
_BAR_GAP: Final = 3.0
#: Never zero. A dead-flat pill is indistinguishable from a frozen one, and
#: "is it live or is it broken" is the ambiguity §5.4 exists to remove.
MIN_BAR_HEIGHT: Final = 2.0
MAX_BAR_HEIGHT: Final = 16.0
#: Deflection is calibrated to **this operator's measured speech**, not to a
#: guess. 8,684 blocks across ten of his own takes, 6,461 above the noise
#: floor:
#:
#:     silence  p50  0.0028
#:     speech   p50  0.0152    p90  0.0311    p95  0.0374    p99  0.0524
#:
#: The first version used 0.35 as full scale, which put his ordinary speech at
#: 12% of the pill and looked dead — reported as wanting "more dynamics and
#: amplitude". A second guess of 0.10 still only reached 39%. Sizing from the
#: data instead: full scale is his **p95**, so median speech lands near the
#: middle, the loud end of normal speech reaches the top, and roughly 5% of
#: blocks clip — which is what headroom is for.
#:
#: **Settled at 0.046 on 2026-09-03, deliberately between two measured
#: extremes.** 0.35 put his median speech at 12% of the pill and read as dead;
#: his p95 of 0.0374 put it at 62% and read as "a little aggressive". 0.046
#: lands median speech at 50%, p90 at 80% and p95 at 89% — the loud end of
#: normal speech near the top without ordinary talking pinned there. Recorded
#: as a third point on the same measurement rather than a taste adjustment,
#: because the next person to touch it should see all three.
_FULL_SCALE: Final = 0.046
#: Below this, no deflection at all. Without a gate the sqrt curve lifts his
#: measured silence floor of 0.0028 to a quarter of the pill, so a quiet room
#: would shimmer as though the microphone were hearing something. Set just
#: above that floor and below the quietest speech.
#: Consecutive failed renders before the panel is disabled for good.
#:
#: `_failed` was a **one-way latch** until 2026-09-10: a single exception out of
#: `_render` disabled the overlay for the life of the process, and every later
#: `set_state` and `set_level` returned on it. A daemon that runs for days
#: across sleep cycles meets a transient AppKit failure eventually, and gate
#: finding 1 is what that looks like from outside — dictation working, panel
#: gone, a restart fixing it.
#:
#: A budget rather than unlimited retries, because the original argument was
#: right about the *persistent* case: retrying forever turns a broken panel into
#: a broken panel that also runs code on every audio block. Reset by any
#: successful render, or three failures spread across three days would disable a
#: panel that worked perfectly in between.
OVERLAY_FAILURE_LIMIT: Final = 3

#: Used only when `NSScreen.mainScreen()` is nil at build time. Arbitrary and
#: never seen: `_screen` stays `None`, so the next show re-frames against a real
#: screen the moment one exists.
_FALLBACK_SCREEN: Final = (0.0, 0.0, 1440.0, 900.0)

_NOISE_FLOOR: Final = 0.005
#: Deflection curve. Linear RMS looks dead because loudness is perceived
#: roughly logarithmically — a level at 20% of full scale reads as much louder
#: than a fifth as tall. The square root spends more of the pill on the quiet
#: end, where speech actually lives.
_CURVE: Final = 0.5


class OverlayMode(Enum):
    """What the panel draws. Three, since 2026-09-17; two before it.

    An enum rather than the two booleans it replaces. `visible` and `recording`
    can express a fourth combination — hidden-but-recording — that has no
    picture, and a state space with an unrepresentable member in it is a bug
    waiting for the thread that constructs it.
    """

    HIDDEN = "hidden"
    IDLE = "idle"
    ACTIVE = "active"
    #: Recording, hands-free, with the two controls drawn. Still recording —
    #: everything §5.4 says about the ACTIVE form applies here too, which is
    #: why `is_recording` exists rather than callers testing for ACTIVE.
    LATCHED = "latched"


def mode_for(
    state: DictationState, *, idle_enabled: bool, controls: bool = False
) -> OverlayMode:
    """Which form the panel takes. Pure, and the privacy rule lives here.

    **`ACTIVE` is returned for exactly one state and no setting changes that.**
    That is the whole of §5.4's guarantee reduced to one expression: whatever
    else the panel does, the appearance that says "you are being recorded"
    follows the microphone and nothing else. See the preamble on why
    TRANSCRIBING is excluded rather than included — it was the trap when the
    alternative was hiding, and it is the same trap now that the alternative is
    the idle form.

    `idle_enabled` decides only what the *other* states draw: the narrow pill,
    or nothing at all, which is the behaviour before this existed.
    """
    if state is DictationState.RECORDING:
        return OverlayMode.LATCHED if controls else OverlayMode.ACTIVE
    return OverlayMode.IDLE if idle_enabled else OverlayMode.HIDDEN


def is_recording(mode: OverlayMode) -> bool:
    """Does this mode mean the microphone is open?

    Two modes do, and every rule that used to read `is ACTIVE` must read this
    instead. Adding LATCHED without it would have left the bars hidden and the
    level path dead in exactly the sessions the controls are for — a
    hands-free dictation showing a motionless pill, which is §5.4's failure.
    """
    return mode in (OverlayMode.ACTIVE, OverlayMode.LATCHED)


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
        above = max(0.0, level - _NOISE_FLOOR)
        fraction = min(1.0, above / (_FULL_SCALE - _NOISE_FLOOR)) ** _CURVE
        heights.append(MIN_BAR_HEIGHT + span * fraction)
    return tuple(heights)


def as_rect(
    flat: tuple[float, float, float, float],
) -> tuple[tuple[float, float], tuple[float, float]]:
    """A flat `(x, y, w, h)` as the nested pair PyObjC wants for an `NSRect`.

    This module computes geometry as flat four-tuples — `frame_for` and
    `pill_frame` both do — because that is the shape that is pleasant to write
    tests against. PyObjC depythonifies an `NSRect` as `((x, y), (w, h))`, two
    members, nested, and a flat four raises *"depythonifying struct of 2
    members, got tuple of 4"*.

    The window path converts through `NSMakeRect(*rect)` and so never had the
    problem. The **layer** path has no such call, and on 2026-09-17 the idle
    pill shipped handing `pill_frame`'s flat tuple straight to `setFrame_`.
    That is the second time this exact mistake has reached a running daemon;
    the first is in the preamble, dated 2026-09-02. Both times the suite was
    green, because the fake layer stored whatever it was given.

    So: one named conversion, used everywhere a layer is framed, rather than a
    nested literal written out at each call site. A literal is what the bars
    already do and it worked — and it is also how the pill came to be written
    differently from the bars without anything noticing.
    """
    x, y, width, height = flat
    return ((x, y), (width, height))


def pill_frame(mode: OverlayMode) -> tuple[float, float, float, float]:
    """The visible pill's rect *inside* the window, which never changes size.

    Centred, so the two forms share a centre and the transition is an inflation
    rather than a slide. The recording form fills the window exactly: smaller
    would leave a transparent margin for the shadow to fall on, larger would
    clip.

    `HIDDEN` has no rect of its own — the window is ordered out rather than
    drawn empty — and returns the idle one so a panel coming back does not have
    to animate from nowhere.
    """
    if mode is OverlayMode.LATCHED:
        width, height = LATCHED_WIDTH, PANEL_HEIGHT
    elif mode is OverlayMode.ACTIVE:
        width, height = ACTIVE_WIDTH, ACTIVE_HEIGHT
    else:
        width, height = IDLE_WIDTH, IDLE_HEIGHT
    return (
        (PANEL_WIDTH - width) / 2.0,
        (PANEL_HEIGHT - height) / 2.0,
        width,
        height,
    )


def control_frame(which: str) -> tuple[float, float, float, float]:
    """Where ✕ and ✓ sit, in the container's coordinate space.

    Fixed. They are children of the container rather than of the pill, so they
    do not move when the pill changes width — and `mouseDown_` hit-tests
    against exactly these rects, so a control that drifted from its own
    hit-target would look right and click wrong.
    """
    centre = PANEL_WIDTH / 2.0
    offset = -_CONTROL_OFFSET if which == "cancel" else _CONTROL_OFFSET
    return (
        centre + offset - CONTROL_SIZE / 2.0,
        (PANEL_HEIGHT - CONTROL_SIZE) / 2.0,
        CONTROL_SIZE,
        CONTROL_SIZE,
    )


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
    # The window is always the recording form's size. It is the pill layer
    # inside it that shrinks, which is what keeps `setFrame:display:animate:`
    # — a call that blocks the main queue — off this module's critical path.
    width = min(PANEL_WIDTH, screen_width)
    height = min(PANEL_HEIGHT, screen_height)
    margin = min(_MARGIN, max(0.0, (screen_height - height) / 2))

    x = screen_x + (screen_width - width) / 2
    if position == "top":
        y = screen_y + screen_height - height - margin
    else:
        # Anything else is a caller bug — config validation rejects it — and a
        # daemon holding the microphone should not die of one.
        y = screen_y + margin
    return (x, y, width, height)


#: Built on first use, never at import — `manu --help` does not load the
#: Objective-C runtime, and defining the class twice would register two
#: Objective-C classes with one name, which PyObjC refuses. Exactly
#: `tray.py:_menu_target_class`'s arrangement and for the same two reasons.
_CONTROL_VIEW_CLASS: Any | None = None


def _control_view_class() -> Any:
    """An `NSView` that routes a click to whichever control it landed in.

    **`acceptsFirstMouse_` returns True**, and that is the whole reason this is
    a subclass rather than a plain view. The panel never becomes key (§5.4: it
    must not steal the keystrokes the transcript is about to join), and a
    non-key window's first click is normally spent activating it. Without this
    the user's first press on ✕ would do nothing and the second would work,
    which reads as a button that misses.
    """
    global _CONTROL_VIEW_CLASS
    if _CONTROL_VIEW_CLASS is None:
        from AppKit import NSView

        class _AmanuensisControlView(NSView):  # type: ignore[misc]
            def acceptsFirstMouse_(self, _event: Any) -> bool:
                return True

            def mouseDown_(self, event: Any) -> None:
                handler = getattr(self, "handler", None)
                if handler is None:  # pragma: no cover — view outlived overlay
                    return
                point = self.convertPoint_fromView_(event.locationInWindow(), None)
                handler(float(point.x), float(point.y))

        _CONTROL_VIEW_CLASS = _AmanuensisControlView
    return _CONTROL_VIEW_CLASS


def control_hit(x: float, y: float) -> str | None:
    """Which control a point lands in, or None. Pure, and the hit-test.

    Separated from the view so the rule is testable without an event, a window
    or a run loop. A click outside both is **None and does nothing** — not a
    nearest-match — because ✕ is irreversible and unguarded, and a generous
    hit-target on a destructive control is a way to lose a dictation to a
    misplaced click (objection O3).
    """
    for which in ("cancel", "finish"):
        left, bottom, width, height = control_frame(which)
        if left <= x <= left + width and bottom <= y <= bottom + height:
            return which
    return None


class RecordingOverlay:
    """A borderless panel, shown while the microphone is open."""

    def __init__(
        self,
        config: FeedbackConfig | None = None,
        *,
        on_error: Callable[[str], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        on_finish: Callable[[], None] | None = None,
    ) -> None:
        self._config = config if config is not None else FeedbackConfig()
        #: Set once the panel has failed. A panel that raised once will raise
        #: every time, and retrying it on every state change turns one defect
        #: into a failure on every dictation.
        self._failed = False
        #: Consecutive failures, reset by any success. See OVERLAY_FAILURE_LIMIT.
        self._failures = 0
        #: The screen rect the panel's frame was derived from. Gate finding 1's
        #: second mechanism is this going stale: the panel is positioned once,
        #: the display changes under it, and `orderFrontRegardless()` keeps
        #: succeeding while the panel sits somewhere nobody can see. Nothing
        #: raises, so nothing is reported — which is why the operator saw no
        #: error and why the two mechanisms could not be told apart.
        self._screen: tuple[float, float, float, float] | None = None
        self._on_error = on_error
        #: §5.2's two verbs. The overlay calls them and knows nothing else
        #: about them — it does not know what a session is, which is §6.2's
        #: rule and the reason `set_controls` takes a bool rather than a latch.
        self._on_cancel = on_cancel
        self._on_finish = on_finish
        #: Whether the controls should be drawn. Set by `set_controls`, and
        #: cleared by the overlay itself whenever the microphone closes — a
        #: flag that outlived its session would put a live ✓ on an idle pill.
        self._controls = False
        #: Recent audio levels, newest last. Bounded, and read on the main
        #: queue while the PortAudio thread appends — a deque with a maxlen is
        #: atomic enough for both under the GIL, and the alternative is a lock
        #: on the capture thread's hot path.
        self._levels: deque[float] = deque([0.0] * BAR_COUNT, maxlen=BAR_COUNT)
        self._bars: list[Any] = []
        #: The visible pill. Resized between the three forms; the window is not.
        self._pill: Any | None = None
        #: The ✕ and ✓ layers, by name. Built with the bars, shown by mode.
        self._controls_layers: dict[str, Any] = {}
        self._panel: Any | None = None
        self._mode = OverlayMode.HIDDEN
        #: Guards `_panel` and `_visible`. Set from the event tap and the
        #: worker, drawn on the main queue — the indicator's shape exactly.
        self._lock = threading.Lock()

    @property
    def visible(self) -> bool:
        return self._mode is not OverlayMode.HIDDEN

    @property
    def mode(self) -> OverlayMode:
        return self._mode

    def start(self) -> None:
        """Draw the idle pill, before any dictation has happened.

        Separate from `set_state` because the daemon emits no state until its
        first session, and the period before that is exactly when a user is
        wondering whether the thing is running. `cli.py` calls this once the
        daemon is up.

        A no-op when `[feedback] overlay_idle` is off — that setting's whole
        content is that nothing appears until RECORDING.
        """
        self._apply(mode_for(DictationState.IDLE, idle_enabled=self._idle_enabled))

    @property
    def _idle_enabled(self) -> bool:
        return self._config.overlay_idle

    def set_state(self, state: DictationState) -> None:
        """Safe from any thread, and safe before anything is shown."""
        wanted = mode_for(
            state, idle_enabled=self._idle_enabled, controls=self._controls
        )
        if not is_recording(wanted):
            # Cleared here rather than by the caller. A latch ends several ways
            # — the ending tap, Escape, an abort, an error — and requiring each
            # to remember is how one of them forgets and leaves a ✓ on a pill
            # whose microphone is shut.
            self._controls = False
        self._apply(wanted)

    def set_controls(self, showing: bool) -> None:
        """Draw the ✕ and ✓, or stop drawing them.

        **A bool, not a latch.** §6.2 makes this a renderer: it is told what to
        draw and never learns what a latch is, which is the question the spec
        left open (slice S5). `cli.py` owns the translation, because `cli.py`
        is already where the listener's callbacks meet the controller.
        """
        if not self._config.overlay_controls:
            return
        with self._lock:
            if showing == self._controls:
                return
            self._controls = showing
            current = self._mode
        if not is_recording(current):
            # Nothing to redraw: the controls only exist on the recording form,
            # and the next `set_state` will pick the flag up.
            return
        self._apply(OverlayMode.LATCHED if showing else OverlayMode.ACTIVE)

    def _apply(self, wanted: OverlayMode) -> None:
        """Move the panel to a mode, off the main thread.

        The early return on an unchanged mode is what makes `vad_auto` free:
        it can flip states repeatedly with no user action, and the panel is
        created once and re-ordered rather than rebuilt per transition — which
        would leave a pile of them on screen.
        """
        if not self._config.overlay or self._failed:
            return
        with self._lock:
            if wanted is self._mode:
                return
            self._mode = wanted
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
            # `not is_recording`, not `is HIDDEN`. An idle pill that honours a
            # level twitches, and a twitching idle pill reads as recording —
            # see the preamble. The level is still appended, so the deque is
            # warm if a dictation starts, but nothing is drawn. **LATCHED is a
            # recording mode**: reading this as `is not ACTIVE` would freeze
            # the bars for exactly the hands-free sessions the controls are for.
            if not is_recording(self._mode) or self._panel is None:
                return
        from amanuensis.ui.indicator import _main_queue

        _main_queue().addOperationWithBlock_(lambda: self._guarded(self._draw_bars))

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
            layer.setFrame_(
                as_rect((x, (PANEL_HEIGHT - height) / 2.0, width, height))
            )

    def hide(self) -> None:
        """Off the screen entirely, whatever `overlay_idle` says.

        Teardown, not a state transition: this is what the daemon calls on its
        way out, and a pill left on a dead daemon's screen is the inverse of
        the defect the idle form was added to fix.
        """
        with self._lock:
            self._mode = OverlayMode.HIDDEN
        from amanuensis.ui.indicator import _main_queue

        _main_queue().addOperationWithBlock_(lambda: self._render(OverlayMode.HIDDEN))

    def _render(self, wanted: OverlayMode) -> None:
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
        self._guarded(lambda: self._render_unguarded(wanted))

    def _guarded(self, action: Callable[[], None]) -> None:
        """Run `action` on the main queue's behalf, absorbing anything it raises.

        **Both dispatch paths go through here, and until 2026-09-10 only one
        did.** `set_level` dispatched `_draw_bars` raw, so an exception out of a
        `CALayer` call crossed the PyObjC bridge inside an `NSBlockOperation`
        and terminated the process — on the path that runs about thirty times a
        second while the microphone is open, against layers a display change can
        invalidate. Found by a stress pass, not by the change that added the
        guard: the guard was extended to the state path and the level path was
        never asked about.

        They share the failure budget deliberately. A draw that keeps raising is
        a broken panel by the same definition as a show that keeps raising, and
        a budget covering one path while the other retries forever is not a
        budget.
        """
        try:
            action()
        except Exception as exc:
            self._failures += 1
            # The panel is rebuilt from scratch on the next attempt: a half-built
            # one is what a mid-`_build` failure leaves behind, and reusing it is
            # how a transient failure becomes a permanent one.
            self._panel = None
            self._screen = None
            if self._failures >= OVERLAY_FAILURE_LIMIT:
                self._failed = True
                if self._on_error is not None:
                    self._on_error(
                        f"the recording overlay failed {self._failures} times "
                        f"and is off: {exc}"
                    )
            elif self._on_error is not None:
                self._on_error(f"the recording overlay failed and will retry: {exc}")
        else:
            self._failures = 0

    def _render_unguarded(self, wanted: OverlayMode) -> None:
        panel = self._panel if self._panel is not None else self._build()
        if panel is None:  # pragma: no cover — AppKit returned nil
            return
        if wanted is OverlayMode.HIDDEN:
            panel.orderOut_(None)
            return

        self._reframe(panel)
        if wanted is OverlayMode.ACTIVE:
            # Reset before showing. A pill that opens holding the previous
            # dictation's levels looks frozen for the first thirty milliseconds,
            # which is exactly the "is it live or is it stuck" ambiguity.
            self._levels.clear()
            self._levels.extend([0.0] * BAR_COUNT)
            self._draw_bars()
        self._apply_form(wanted)
        # **The click-through this panel now costs, and the whole mitigation.**
        # Taking mouse events means the window's transparent margins swallow
        # clicks aimed at whatever is behind them, and the window is 114 wide in
        # every state while the pill is 34 in most of them. So it takes them
        # only while the controls are on screen — a latched dictation — and
        # gives them back for the rest of the day.
        panel.setIgnoresMouseEvents_(wanted is not OverlayMode.LATCHED)
        panel.orderFrontRegardless()

    def _apply_form(self, wanted: OverlayMode) -> None:
        """Grow or shrink the pill, and show or hide the bars. Main thread only.

        Hidden rather than removed: the layers are built once and toggled,
        because this runs on every transition and `vad_auto` can produce a lot
        of them. Rebuilding seven layers per transition is the same mistake
        `_draw_bars` already refuses to make thirty times a second.

        The whole change goes inside one `CATransaction` so the pill and the
        bars move together. Two transactions would let the bars appear before
        the pill has grown to hold them, which is a frame of bars hanging in
        space — briefly, and visibly.
        """
        recording = is_recording(wanted)
        latched = wanted is OverlayMode.LATCHED
        # `CATransaction` is a class with class methods, not a module of free
        # functions. Written as `CATransactionBegin()` first, which does not
        # exist and raises `AttributeError` on the first transition — caught by
        # `_render`'s guard, so it would have surfaced as a panel that failed
        # and retried rather than as anything naming the real problem.
        transaction = self._quartz().CATransaction
        transaction.begin()
        try:
            if self._animates():
                transaction.setAnimationDuration_(TRANSITION_SECONDS)
            else:
                # Not a zero duration: implicit animation is on by default for
                # a standalone layer, so zero still runs an animation of zero
                # length. `setDisableActions_` is what removes it.
                transaction.setDisableActions_(True)
            if self._pill is not None:
                rect = pill_frame(wanted)
                self._pill.setFrame_(as_rect(rect))
                self._pill.setCornerRadius_(rect[3] / 2.0)
            for bar in self._bars:
                bar.setHidden_(not recording)
            for layer in self._controls_layers.values():
                layer.setHidden_(not latched)
        finally:
            # In a `finally` because an exception between begin and commit
            # leaves the transaction open, and every later implicit animation
            # in the process then joins it — a leak that shows up as the whole
            # UI animating at the wrong duration, nowhere near this module.
            transaction.commit()

    def _animates(self) -> bool:
        """Config, unless macOS has been told to reduce motion.

        Read at transition time rather than cached: the switch can be thrown
        while a daemon that starts at login is running, and a daemon that has
        been up for a week would otherwise be the one process ignoring it.
        """
        if not self._config.overlay_animate:
            return False
        from amanuensis.ui.indicator import _appkit

        workspace = _appkit().NSWorkspace.sharedWorkspace()
        return not bool(workspace.accessibilityDisplayShouldReduceMotion())

    def _reframe(self, panel: Any) -> None:
        """Re-position and re-size the panel for the mode it is entering.

        **Revised 2026-09-17.** This used to run only when the screen had
        changed, and the condition was the test — re-framing on every show
        would nudge a panel the user is looking at. The width now depends on
        the mode, so the frame must be recomputed whenever the mode changes as
        well, and `_mode` having already moved is what keeps this from firing
        on every level update.

        No animation. `setFrame:display:animate:` blocks the main queue for the
        duration, and this panel's failures have terminated the daemon once
        already (2026-09-02); a blocking call on the thread that draws it is
        not a trade worth making for a 200 ms flourish. The growth is a hard
        cut, and whether that is enough is lane 2's question, not this
        module's.


        Checked on show rather than driven by
        `NSApplicationDidChangeScreenParameters`, because the notification is
        one more thing to register, unregister and get wrong on a component
        whose failures are silent — and because a panel that is not visible does
        not need to be right. On show is the last moment it matters.

        **Conditional, and the condition is the test.** Re-framing on every show
        would nudge a panel the user is looking at on every dictation, and would
        make a test of this indistinguishable from a test of nothing.
        """
        current = self._screen_rect()
        if current is None:
            # `NSScreen.mainScreen()` gave nil — every display asleep, or a
            # clamshell with nothing attached. A panel that cannot be
            # positioned because there is no screen has nothing to position on;
            # that is not a fault, and charging it to the failure budget spends
            # what exists for faults. Added 2026-09-10 after S1 put this call
            # on every show.
            return
        from amanuensis.ui.indicator import _appkit

        rect = frame_for(self._config.overlay_position, current)
        panel.setFrame_display_(_appkit().NSMakeRect(*rect), True)
        self._screen = current

    @staticmethod
    def _screen_rect() -> tuple[float, float, float, float] | None:
        """The main screen as a flat tuple. `NSRect` unpacks as `((x, y), (w, h))`
        — two elements, nested — and reading that shape wrong crashed a daemon
        on 2026-09-02 while every test passed against a flat fake."""
        from amanuensis.ui.indicator import _appkit

        screen = _appkit().NSScreen.mainScreen()
        if screen is None:
            return None
        (origin_x, origin_y), (width, height) = screen.frame()
        return (float(origin_x), float(origin_y), float(width), float(height))

    def _build(self) -> Any:
        from amanuensis.ui.indicator import _appkit

        appkit = _appkit()
        # `NSScreen.frame()` is an `NSRect`, which PyObjC unpacks as
        # `((x, y), (width, height))` — two elements, nested. `tuple(...)` of
        # it is therefore length 2, not 4, and this line read the framework's
        # shape wrong until a daemon crashed on it.
        # A nil screen at build time is the same non-fault as at re-frame
        # time; fall back to a rect that is at least on-screen if one ever
        # appears, and leave `_screen` unset so the next show re-frames.
        self._screen = self._screen_rect()
        rect = frame_for(
            self._config.overlay_position, self._screen or _FALLBACK_SCREEN
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

        container = (
            self._control_view()
            .alloc()
            .initWithFrame_(appkit.NSMakeRect(0.0, 0.0, PANEL_WIDTH, PANEL_HEIGHT))
        )
        container.handler = self._on_click
        container.setWantsLayer_(True)
        layer = container.layer()
        panel.setContentView_(container)

        # The pill is a sublayer rather than the view's own layer, and that is
        # what makes the transition animatable. A view-backed layer has implicit
        # animation switched off; a standalone `CALayer` animates its frame on
        # the render server, which costs the main queue nothing. The window
        # itself is never resized — see `pill_frame`.
        self._pill = self._build_pill(layer)
        # Bars and controls are children of the **container**, not of the pill.
        # The pill changes width between three forms; its sublayers would move
        # with it, and a hit-target that drifts from the glyph it belongs to
        # looks right and clicks wrong.
        self._bars = self._build_bars(appkit, layer)
        self._controls_layers = self._build_controls(layer)
        self._panel = panel
        return panel

    def _build_controls(self, parent: Any) -> dict[str, Any]:
        """✕ and ✓ as text layers, hidden until a session latches."""
        quartz = self._quartz()
        white = quartz.CGColorCreateGenericGray(1.0, 0.92)
        layers: dict[str, Any] = {}
        for which, glyph in (("cancel", "\u2715"), ("finish", "\u2713")):
            layer = self._catextlayer().layer()
            layer.setString_(glyph)
            layer.setFontSize_(_CONTROL_FONT_SIZE)
            layer.setAlignmentMode_("center")
            layer.setForegroundColor_(white)
            # Without this the glyph is drawn at 1x and is visibly soft on a
            # Retina display, on a control small enough that softness reads as
            # a rendering fault rather than as a style.
            layer.setContentsScale_(_RETINA_SCALE)
            layer.setFrame_(as_rect(control_frame(which)))
            layer.setHidden_(True)
            parent.addSublayer_(layer)
            layers[which] = layer
        return layers

    def _on_click(self, x: float, y: float) -> None:
        """A click landed on the panel. Main thread, inside AppKit's dispatch.

        Guarded for `_render`'s reason: an exception here crosses the PyObjC
        bridge as an `NSException` and **terminates a process holding the
        microphone**. A ✕ that fails to cancel is a bad afternoon; a ✕ that
        kills the daemon mid-dictation loses the words.
        """
        if self._mode is not OverlayMode.LATCHED:
            # Belt and braces against a press arriving between the mode
            # changing and the window giving mouse events back.
            return
        which = control_hit(x, y)
        if which is None:
            return
        callback = self._on_cancel if which == "cancel" else self._on_finish
        if callback is None:
            return
        # Through the same guard as every other main-thread entry point. It
        # charges the failure budget and rebuilds the panel, which is the right
        # response to a callback that raises: the click was real, the panel is
        # suspect, and the process must survive either way.
        self._guarded(callback)

    @staticmethod
    def _control_view() -> Any:
        """The click-taking `NSView` subclass, behind a seam like `_calayer`.

        A seam and not a direct call because the subclass reaches the real
        Objective-C runtime the moment it is defined, so a test that did not
        replace it would build a real view against a fake `NSMakeRect` — which
        is how this arrived: a flat rect into a real `initWithFrame_`.
        """
        return _control_view_class()

    @classmethod
    def _catextlayer(cls) -> Any:
        """`CATextLayer`, off the same seam as `_calayer` and for its reason:
        tests replace one attribute rather than the framework."""
        return cls._quartz().CATextLayer

    def _build_pill(self, parent: Any) -> Any:
        """The visible pill: dark translucent fill, light hairline border."""
        quartz = self._quartz()
        pill = self._calayer().layer()
        pill.setFrame_(as_rect(pill_frame(OverlayMode.IDLE)))
        pill.setCornerRadius_(IDLE_HEIGHT / 2.0)
        pill.setBackgroundColor_(quartz.CGColorCreateGenericGray(0.0, 0.62))
        pill.setBorderWidth_(PILL_BORDER_WIDTH)
        pill.setBorderColor_(
            quartz.CGColorCreateGenericGray(_PILL_BORDER_GRAY, _PILL_BORDER_ALPHA)
        )
        parent.addSublayer_(pill)
        return pill

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
        left = (PANEL_WIDTH - span) / 2.0
        bars: list[Any] = []
        for index in range(BAR_COUNT):
            bar = calayer.layer()
            x = left + index * (_BAR_WIDTH + _BAR_GAP)
            bar.setFrame_(
                as_rect(
                    (
                        x,
                        (PANEL_HEIGHT - MIN_BAR_HEIGHT) / 2.0,
                        _BAR_WIDTH,
                        MIN_BAR_HEIGHT,
                    )
                )
            )
            bar.setCornerRadius_(_BAR_WIDTH / 2.0)
            bar.setBackgroundColor_(white)
            parent.addSublayer_(bar)
            bars.append(bar)
        return bars
