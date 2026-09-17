"""The §5.4 recording affordance — a panel, and the rules about when it shows.

The confidence test written into §5.4 fixes the condition this module exists
for: a full-screen application with the menu bar auto-hidden, where the Phase 2b
glyph is not merely small but **absent**. Everything below is either that
condition or the two ways a panel can betray it — by lying about the microphone,
or by stealing focus from the application being dictated into.

Visibility policy and geometry are pure functions, so they are tested as
functions. The AppKit half is tested through the same fake seam as the
indicator.
"""

from __future__ import annotations

from typing import Any

import pytest

from amanuensis.config import FeedbackConfig
from amanuensis.controllers.dictation_controller import DictationState
from amanuensis.ui import indicator as indicator_module
from amanuensis.ui.overlay import (
    ACTIVE_WIDTH,
    BAR_COUNT,
    CORNER_RADIUS,
    IDLE_WIDTH,
    MAX_BAR_HEIGHT,
    MIN_BAR_HEIGHT,
    OVERLAY_FAILURE_LIMIT,
    OverlayMode,
    RecordingOverlay,
    bar_heights,
    frame_for,
    mode_for,
)
from test_indicator import _FakeAppKit, _FakeFoundation, _FakeMainQueue

# ---------------------------------------------------------------------------
# When it shows — a privacy affordance that lies is worse than none
# ---------------------------------------------------------------------------


def test_it_is_active_while_recording() -> None:
    assert mode_for(DictationState.RECORDING, idle_enabled=True) is OverlayMode.ACTIVE
    assert mode_for(DictationState.RECORDING, idle_enabled=False) is OverlayMode.ACTIVE


@pytest.mark.parametrize("idle_enabled", [True, False])
@pytest.mark.parametrize(
    "state",
    [s for s in DictationState if s is not DictationState.RECORDING],
)
def test_nothing_but_recording_draws_the_active_form(
    state: DictationState, idle_enabled: bool
) -> None:
    """The panel answers exactly one question — *is the microphone live?* —
    and the microphone is live in exactly one state.

    TRANSCRIBING is the trap. It is the longest-running state, it looks busy,
    and showing the active form through it would be the natural thing to do. It
    is also the state in which the microphone has already been released, so a
    panel that kept the wide, moving form would tell the user they were being
    recorded when they were not. For a privacy affordance that is not a
    cosmetic error.

    **Unchanged in substance by the 2026-09-17 persistent idle pill**, and that
    is the point of asserting it across both settings. The panel is now on
    screen in those states; what it must never do is *look like recording* in
    them. Widening the affordance's presence must not widen what it claims.
    """
    assert (
        mode_for(state, idle_enabled=idle_enabled) is not OverlayMode.ACTIVE
    ), "a state with a closed microphone drew the recording form"


@pytest.mark.parametrize(
    "state",
    [s for s in DictationState if s is not DictationState.RECORDING],
)
def test_the_pill_stays_on_screen_when_the_microphone_closes(
    state: DictationState,
) -> None:
    """§5.4, 2026-09-17. Idle is a *state of the panel*, not its absence.

    Gate finding 1 is the argument: a panel that had stopped drawing looked
    exactly like a panel with no reason to draw, and the two were
    indistinguishable for days. They are now different pictures.
    """
    assert mode_for(state, idle_enabled=True) is OverlayMode.IDLE


@pytest.mark.parametrize(
    "state",
    [s for s in DictationState if s is not DictationState.RECORDING],
)
def test_the_idle_pill_can_be_declined(state: DictationState) -> None:
    """`[feedback] overlay_idle = false` restores the pre-2026-09-17 behaviour
    exactly — nothing on screen until RECORDING — rather than approximating it.

    A permanent pill is a taste, and §5.3 requires a decision that could
    reasonably go either way to be a key. The recording indicator is kept
    either way: declining the idle form must not cost the affordance.
    """
    assert mode_for(state, idle_enabled=False) is OverlayMode.HIDDEN


def test_idle_and_active_differ_in_width_as_well_as_motion() -> None:
    """§5.4's first binding consequence: **two independent cues**.

    Motion alone is rejected. A frozen render is indistinguishable from a
    resting one, so a user looking at a stopped panel would read it as idle and
    a user looking at an idle panel could not rule out that it was stopped —
    which is finding 1 with a new costume. The same reasoning already forbids
    `MIN_BAR_HEIGHT = 0`.

    Width is the cue that survives a frozen render, so it must actually differ.
    """
    assert IDLE_WIDTH < ACTIVE_WIDTH


def test_the_idle_pill_is_framed_at_its_own_width() -> None:
    """The geometry has to know about both, or the pill is drawn wide and empty.

    Same screen, same edge, same centring — only the width differs, so the two
    forms share a centre and the transition reads as a growth rather than a
    jump across the screen.
    """
    screen = (0.0, 0.0, 1440.0, 900.0)
    idle_x, idle_y, idle_w, idle_h = frame_for("bottom", screen, width=IDLE_WIDTH)
    active_x, active_y, active_w, active_h = frame_for(
        "bottom", screen, width=ACTIVE_WIDTH
    )

    assert idle_w == IDLE_WIDTH
    assert active_w == ACTIVE_WIDTH
    assert idle_y == active_y and idle_h == active_h
    assert idle_x + idle_w / 2 == pytest.approx(active_x + active_w / 2)


def test_disabling_the_overlay_means_it_never_shows() -> None:
    overlay = RecordingOverlay(FeedbackConfig(overlay=False))
    overlay.set_state(DictationState.RECORDING)
    assert overlay.visible is False


# ---------------------------------------------------------------------------
# Where it sits — it must not cover the caret
# ---------------------------------------------------------------------------


def test_bottom_and_top_are_on_opposite_edges() -> None:
    screen = (0.0, 0.0, 1440.0, 900.0)
    bottom = frame_for("bottom", screen)
    top = frame_for("top", screen)
    assert bottom[1] < top[1], "bottom must sit below top"


def test_the_panel_is_horizontally_centred() -> None:
    screen = (0.0, 0.0, 1440.0, 900.0)
    x, _y, width, _height = frame_for("bottom", screen)
    assert abs((x + width / 2) - 720.0) < 1.0


def test_it_stays_on_screen_on_a_small_display() -> None:
    """A panel wider than the screen is a panel with its text off the edge."""
    screen = (0.0, 0.0, 320.0, 240.0)
    x, y, width, height = frame_for("bottom", screen)
    assert x >= 0.0 and y >= 0.0
    assert x + width <= 320.0
    assert y + height <= 240.0


def test_it_honours_a_screen_origin_that_is_not_zero() -> None:
    """A second display sits at a non-zero origin in the global coordinate
    space, and a panel that ignores that lands on the wrong monitor."""
    screen = (1440.0, 200.0, 1920.0, 1080.0)
    x, y, _w, _h = frame_for("bottom", screen)
    assert x >= 1440.0
    assert y >= 200.0


def test_an_unknown_position_falls_back_rather_than_raising() -> None:
    """Config validation already rejects these, so reaching here means a caller
    bug — and a daemon holding the microphone should not die of one."""
    assert frame_for("sideways", (0.0, 0.0, 1440.0, 900.0)) == frame_for(
        "bottom", (0.0, 0.0, 1440.0, 900.0)
    )


# ---------------------------------------------------------------------------
# The AppKit half — visible in full screen, and never stealing focus
# ---------------------------------------------------------------------------


@pytest.fixture
def appkit(monkeypatch: pytest.MonkeyPatch) -> _FakeAppKit:
    fake = _FakeAppKit()
    _install_panel_fakes(fake)
    foundation = _FakeFoundation(_FakeMainQueue())
    monkeypatch.setattr(indicator_module, "_appkit", lambda: fake)
    monkeypatch.setattr(indicator_module, "_foundation", lambda: foundation)
    # The bars are CALayers and Quartz is behind its own seam.
    monkeypatch.setattr(
        RecordingOverlay, "_calayer", staticmethod(lambda: fake.CALayer)
    )
    monkeypatch.setattr(RecordingOverlay, "_quartz", staticmethod(lambda: fake.Quartz))
    return fake


def _install_panel_fakes(fake: _FakeAppKit) -> None:
    from test_overlay_fakes import install

    install(fake)


def test_the_panel_joins_all_spaces_and_full_screen(appkit: _FakeAppKit) -> None:
    """This is the confidence test's condition, in one assertion.

    Without `FullScreenAuxiliary` the panel is invisible in exactly the case
    §5.4's criterion names — a full-screen app — which is the case the Phase 2b
    glyph already failed. An overlay that repeats the failure it was built to
    fix would pass a criterion written afterwards and fail this one.
    """
    overlay = RecordingOverlay(FeedbackConfig())
    overlay.set_state(DictationState.RECORDING)
    panel = appkit.panels[-1]
    assert panel.collection_behavior & appkit.NSWindowCollectionBehaviorCanJoinAllSpaces
    assert (
        panel.collection_behavior & appkit.NSWindowCollectionBehaviorFullScreenAuxiliary
    )


def test_the_panel_never_takes_focus(appkit: _FakeAppKit) -> None:
    """It appears over the application the user is dictating into. Taking key
    focus would send the keystrokes somewhere else — from, specifically, the
    window about to receive the transcript."""
    overlay = RecordingOverlay(FeedbackConfig())
    overlay.set_state(DictationState.RECORDING)
    panel = appkit.panels[-1]
    assert panel.ordered_front_regardless is True
    assert panel.made_key is False
    assert panel.ignores_mouse is True


def test_the_active_form_is_dropped_when_recording_stops(
    appkit: _FakeAppKit,
) -> None:
    """**Rewritten 2026-09-17.** This used to assert the panel was ordered out.

    It is not, any more — it drops to the idle form and stays on screen. What
    the original test was really protecting is unchanged and is asserted here
    instead: when the microphone closes, the *recording appearance* goes away.
    Which of the two the panel drops to is the new behaviour; that it drops is
    the old requirement.
    """
    overlay = RecordingOverlay(FeedbackConfig())
    overlay.set_state(DictationState.RECORDING)
    assert overlay.mode is OverlayMode.ACTIVE

    overlay.set_state(DictationState.TRANSCRIBING)

    assert overlay.mode is OverlayMode.IDLE
    assert appkit.panels[-1].ordered_out is False
    assert all(bar.hidden for bar in overlay._bars), "the bars outlived the microphone"
    assert overlay._dot is not None and not overlay._dot.hidden


def test_it_is_removed_when_recording_stops_and_the_idle_pill_is_off(
    appkit: _FakeAppKit,
) -> None:
    """The original assertion, kept where it still holds.

    `overlay_idle = false` promises the pre-2026-09-17 behaviour *exactly*, and
    the cheapest way for that promise to rot is for nothing to check it once
    the new path is the interesting one.
    """
    overlay = RecordingOverlay(FeedbackConfig(overlay_idle=False))
    overlay.set_state(DictationState.RECORDING)
    assert overlay.visible is True

    overlay.set_state(DictationState.TRANSCRIBING)

    assert overlay.visible is False
    assert appkit.panels[-1].ordered_out is True


def test_rapid_state_changes_do_not_stack_panels(appkit: _FakeAppKit) -> None:
    """`vad_auto` can start and stop dictation repeatedly with no user action.
    A panel per transition would leave a pile of them on screen."""
    overlay = RecordingOverlay(FeedbackConfig())
    for _ in range(20):
        overlay.set_state(DictationState.RECORDING)
        overlay.set_state(DictationState.IDLE)
    assert len(appkit.panels) == 1


def test_the_real_nsrect_shape_is_what_the_fake_returns() -> None:
    """The fake lied and a daemon paid for it.

    `NSScreen.frame()` is an `NSRect`, which PyObjC unpacks as
    `((x, y), (w, h))` — two elements. `test_overlay_fakes` returned a flat
    4-tuple, so every overlay test passed while the product crashed on the
    first state change with "not enough values to unpack (expected 4, got 2)",
    inside an NSBlockOperation, taking the process with it.

    Asserted against the fake here and against the framework in the daemon:
    a fake whose shape nobody checked is a fake that can only confirm.
    """
    from test_overlay_fakes import install

    class _Bare:
        pass

    fake = _Bare()
    install(fake)
    frame = fake.NSScreen.mainScreen().frame()  # type: ignore[attr-defined]
    assert len(tuple(frame)) == 2, "NSRect is nested, not flat"
    (x, y), (w, h) = frame
    assert (x, y, w, h) == (0.0, 0.0, 1440.0, 900.0)


def test_a_failing_panel_disables_the_overlay_and_reports_it(
    appkit: _FakeAppKit,
) -> None:
    """§5.4 calls the overlay a confidence feature — macOS's own microphone
    indicator carries correctness regardless. So a panel that raises costs the
    panel, not the daemon holding the microphone, and it says so in words
    through the surface this phase built for saying things in words."""
    reported: list[str] = []

    def explode() -> None:
        raise RuntimeError("AppKit said no")

    appkit.NSPanel = type("NSPanel", (), {"alloc": staticmethod(explode)})
    overlay = RecordingOverlay(FeedbackConfig(), on_error=reported.append)

    overlay.set_state(DictationState.RECORDING)

    assert reported, "the failure was swallowed silently"
    assert "overlay" in reported[0].lower()

    # **This assertion changed on 2026-09-10 and the change is the point.**
    # It used to read `assert reported == []` — one failure, off forever, never
    # heard from again. That contract is what gate finding 1 reports from the
    # other side: a transient AppKit failure on a daemon running for days killed
    # the panel until a restart, and the microphone stayed live.
    #
    # The half that was right survives: it must not retry on *every* dictation
    # forever. So the budget is bounded and the reporting is bounded with it.
    reported.clear()
    for _ in range(OVERLAY_FAILURE_LIMIT + 3):
        overlay.set_state(DictationState.IDLE)
        overlay.set_state(DictationState.RECORDING)
    assert (
        len(reported) < OVERLAY_FAILURE_LIMIT
    ), "a permanently failing overlay is still reporting on every dictation"


# ---------------------------------------------------------------------------
# The waveform — a pill with bars, no text (operator request 2026-09-03)
# ---------------------------------------------------------------------------


def test_silence_still_shows_a_resting_line() -> None:
    """A dead-flat pill is indistinguishable from a frozen one.

    The panel's whole job is telling you the microphone is live. If silence
    renders as nothing, a crashed overlay and a quiet room look identical —
    which is the ambiguity §5.4 exists to remove, reintroduced as a visual.
    """
    heights = bar_heights([0.0] * BAR_COUNT)
    assert len(heights) == BAR_COUNT
    assert all(h > 0 for h in heights), "silence renders as nothing"
    assert max(heights) < MAX_BAR_HEIGHT * 0.3, "silence looks like speech"


def test_speech_is_visibly_taller_than_silence() -> None:
    quiet = max(bar_heights([0.0] * BAR_COUNT))
    loud = max(bar_heights([0.35] * BAR_COUNT))
    assert loud > quiet * 2.5, f"speech {loud} is not clearly taller than {quiet}"


def test_bars_are_clamped_to_the_pill() -> None:
    """A bar taller than the panel draws outside it."""
    for level in (1.0, 5.0, 1e9, float("inf")):
        assert all(h <= MAX_BAR_HEIGHT for h in bar_heights([level] * BAR_COUNT))


def test_non_finite_and_negative_levels_do_not_break_it() -> None:
    """`_on_block` hands over whatever the device produced."""
    for level in (float("nan"), float("-inf"), -1.0):
        heights = bar_heights([level] * BAR_COUNT)
        assert all(h > 0 and h <= MAX_BAR_HEIGHT for h in heights), level


def test_the_newest_level_is_on_the_right() -> None:
    """It should read as motion, which means a consistent direction."""
    heights = bar_heights([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.4])
    assert heights[-1] == max(heights)


def test_a_short_history_still_fills_the_pill() -> None:
    """The first few blocks after the key goes down are all there is."""
    heights = bar_heights([0.3])
    assert len(heights) == BAR_COUNT
    assert all(h > 0 for h in heights)


def test_set_level_is_safe_before_anything_is_shown() -> None:
    """Audio blocks arrive on the PortAudio thread from the moment capture
    starts, which is before the panel exists."""
    overlay = RecordingOverlay(FeedbackConfig())
    for _ in range(50):
        overlay.set_level(0.2)


def test_the_pill_is_smaller_than_the_labelled_panel_was() -> None:
    """The operator's words: too square, too big, and no text.

    Asserted rather than left to taste so a later change cannot quietly grow
    it back — the numbers are the request.
    """
    _x, _y, width, height = frame_for("bottom", (0.0, 0.0, 1440.0, 900.0))
    assert width <= 130, f"{width} wide is not a pill"
    assert height <= 30, f"{height} tall is not a pill"
    assert width / height >= 3.0, "a pill is much wider than it is tall"
    assert CORNER_RADIUS >= height / 2 - 0.51, "the ends must be fully round"


def test_the_pill_is_mostly_waveform_not_padding() -> None:
    """Its user's second note: "cut down the padding outside the waveform".

    Asserted as a ratio rather than a pixel count so a later change to the bar
    geometry cannot quietly reintroduce the empty margins.
    """
    from amanuensis.ui.overlay import _BAR_GAP, _BAR_WIDTH, _WIDTH

    span = BAR_COUNT * _BAR_WIDTH + (BAR_COUNT - 1) * _BAR_GAP
    assert (
        span / _WIDTH >= 0.5
    ), f"the bars occupy {span / _WIDTH:.0%} of the pill; the rest is padding"


def test_ordinary_speech_uses_most_of_the_range() -> None:
    """ "A little more dynamics and amplitude."

    0.0152 is the operator's **measured** median speech level over 6,461
    blocks, not a plausible-looking number. At the original full scale of 0.35
    it reached 12% of the pill; a second guess of 0.10 reached 39%. The levels
    here are his, so a future retune that flatters the curve while losing his
    voice fails this.
    """
    # Both bounds, because this has been wrong in both directions: 12% read as
    # dead, 62% read as aggressive. The band is the settled middle.
    median_speech = max(bar_heights([0.0152] * BAR_COUNT)) / MAX_BAR_HEIGHT
    assert 0.40 <= median_speech <= 0.60, f"median speech at {median_speech:.0%}"
    loud_speech = max(bar_heights([0.0311] * BAR_COUNT)) / MAX_BAR_HEIGHT
    assert 0.70 <= loud_speech <= 0.92, f"p90 speech at {loud_speech:.0%}"


def test_quiet_and_loud_are_still_distinguishable() -> None:
    """A curve steep enough to make speech big can flatten everything into
    'full'. Three levels must remain ordered and separated."""
    # His measured quartiles, all inside the range rather than clipped.
    quiet = max(bar_heights([0.008] * BAR_COUNT))
    normal = max(bar_heights([0.0152] * BAR_COUNT))
    loud = max(bar_heights([0.0311] * BAR_COUNT))
    assert quiet < normal < loud
    assert normal - quiet >= 2.0, "quiet and normal are visually the same"


def test_a_quiet_room_does_not_shimmer() -> None:
    """The operator's measured silence floor is 0.0028 RMS, and the sqrt curve
    lifts that to a quarter of the pill without a noise gate — a still room
    would look like the microphone was hearing something."""
    for ambient in (0.0, 0.001, 0.0028, 0.004):
        heights = bar_heights([ambient] * BAR_COUNT)
        assert (
            max(heights) <= MIN_BAR_HEIGHT + 0.01
        ), f"ambient {ambient} deflects to {max(heights)}"


# ---------------------------------------------------------------------------
# Gate finding 1 — the panel died in place and the microphone did not
# ---------------------------------------------------------------------------


def _flaky_panel(fake: _FakeAppKit, failures: int) -> None:
    """Make `NSPanel.alloc` raise `failures` times, then behave."""
    from test_overlay_fakes import _FakePanel

    remaining = {"n": failures}

    class NSPanel:
        @staticmethod
        def alloc() -> _FakePanel:
            if remaining["n"] > 0:
                remaining["n"] -= 1
                raise RuntimeError("AppKit said no")
            panel = _FakePanel()
            fake.panels.append(panel)
            return panel

    fake.NSPanel = NSPanel


def test_a_transient_render_failure_does_not_disable_the_panel_forever(
    appkit: _FakeAppKit,
) -> None:
    """`_failed` was a one-way latch with no recovery: one exception out of
    `_render` disabled the panel for the life of the process, and every later
    `set_state` and `set_level` returned on it.

    A daemon that runs for days across sleep cycles will meet a transient
    AppKit failure eventually, and the operator's 2026-09-10 report is what
    that looks like from outside — dictation working, panel gone, a restart
    fixing it. One of gate finding 1's two open mechanisms.
    """
    _flaky_panel(appkit, failures=1)
    overlay = RecordingOverlay(FeedbackConfig(), on_error=lambda _m: None)

    overlay.set_state(DictationState.RECORDING)  # raises
    overlay.set_state(DictationState.IDLE)
    overlay.set_state(DictationState.RECORDING)  # must recover

    assert appkit.panels, "one transient failure disabled the panel permanently"
    assert appkit.panels[-1].ordered_front_regardless


def test_a_persistently_failing_render_still_gives_up(appkit: _FakeAppKit) -> None:
    """The negative control, and it is not optional.

    Retrying forever turns a broken panel into a broken panel that also runs
    code on every state change and every audio block, on the main queue.
    `_failed`'s original argument -- disable rather than retry -- was right
    about the persistent case and wrong about the transient one, and the fix
    has to keep the half that was right.
    """
    reported: list[str] = []
    _flaky_panel(appkit, failures=10_000)
    overlay = RecordingOverlay(FeedbackConfig(), on_error=reported.append)

    for _ in range(OVERLAY_FAILURE_LIMIT + 3):
        overlay.set_state(DictationState.RECORDING)
        overlay.set_state(DictationState.IDLE)

    assert (
        len(reported) <= OVERLAY_FAILURE_LIMIT
    ), f"it reported {len(reported)} times -- it is retrying forever"


def test_a_success_resets_the_failure_budget(appkit: _FakeAppKit) -> None:
    """Otherwise the budget is a slow one-way latch: failures spread across
    days would disable a panel that worked perfectly between them.

    **Four earlier versions of this test could not fail**, each for a different
    reason, and my own sabotage pass found all four rather than review. Worth
    recording, because each is a distinct way an assertion goes hollow:

    1. Alternating states against a fake that raised once — a hide is a render
       too, so every failure was followed by a success that reset the budget.
    2. `burst` armed failures across `2 × burst` renders — a success still
       landed inside every burst.
    3. Asserting `ordered_front_regardless`, which is **sticky** on the fake: it
       records that a show once happened and nothing clears it, so it passed on
       a panel shown before the failures began.
    4. Injecting failures at `NSPanel.alloc`, which is only reached when no
       panel exists. The overlay builds once, so the second burst injected
       nothing at all.

    What makes this one discriminate: failures are injected at the **render**
    (`render_failures`, consumed by show and hide alike, which happen every
    time), and the assertion counts a **new** panel rather than reading a sticky
    flag.
    """
    import itertools

    overlay = RecordingOverlay(FeedbackConfig(), on_error=lambda _m: None)
    burst = OVERLAY_FAILURE_LIMIT - 1
    assert burst >= 1 and 2 * burst >= OVERLAY_FAILURE_LIMIT, (
        "the arithmetic no longer discriminates — a non-resetting budget would "
        "survive this test"
    )
    flip = itertools.cycle([DictationState.RECORDING, DictationState.IDLE])

    for _ in range(2):
        appkit.render_failures = burst
        for _ in range(burst):
            overlay.set_state(next(flip))
        overlay.set_state(next(flip))  # a clean render resets the budget

    overlay.set_state(DictationState.IDLE)
    built = len(appkit.panels)
    overlay.set_state(DictationState.RECORDING)

    assert (
        len(appkit.panels) > built or appkit.panels[-1].ordered_front_regardless
    ), "no render happened — the budget did not reset and the overlay is off"
    assert not overlay._failed, "the overlay latched off despite the resets"


def test_a_failed_render_discards_the_panel_it_failed_on(
    appkit: _FakeAppKit,
) -> None:
    """Recovery has to be a *fresh* panel, not another go at the broken one.

    A render can fail with a panel already built — the show call itself raising
    is the case, and it is the one a display change produces. Keeping that panel
    means the next attempt retries the object that just failed, which turns the
    bounded budget into three attempts at the same broken thing rather than
    three chances to recover. Found by sabotage: removing the discard failed
    nothing, so it was untested defensive code until this existed.
    """
    overlay = RecordingOverlay(FeedbackConfig(), on_error=lambda _m: None)
    overlay.set_state(DictationState.RECORDING)
    first = appkit.panels[-1]

    overlay.set_state(DictationState.IDLE)
    appkit.render_failures = 1
    overlay.set_state(DictationState.RECORDING)  # raises with a panel in hand
    overlay.set_state(DictationState.IDLE)
    overlay.set_state(DictationState.RECORDING)  # must recover

    assert appkit.panels[-1] is not first, "it retried the panel that had just failed"
    assert appkit.panels[-1].ordered_front_regardless


def test_the_panel_is_reframed_when_the_screen_moves(appkit: _FakeAppKit) -> None:
    """Gate finding 1's second mechanism, and the silent one.

    The panel is built once against `NSScreen.mainScreen()` and there is no
    handler for any display-change or wake notification -- so a lid close moves
    the screen out from under it while `orderFrontRegardless()` still succeeds
    and raises nothing. Nothing reports it because nothing failed, which is why
    the operator saw no error and why the two mechanisms could not be told
    apart.
    """
    overlay = RecordingOverlay(FeedbackConfig(), on_error=lambda _m: None)
    overlay.set_state(DictationState.RECORDING)
    panel = appkit.panels[-1]
    built = panel.frame

    overlay.set_state(DictationState.IDLE)
    appkit.screen_frame = ((0.0, 0.0), (1280.0, 800.0))
    overlay.set_state(DictationState.RECORDING)

    assert (
        panel.frame != built
    ), "the panel kept a frame derived from a screen that is no longer there"


def test_an_unchanged_screen_does_not_move_the_panel(appkit: _FakeAppKit) -> None:
    """The positive control on the check above.

    **Rewritten 2026-09-17, and the invariant is narrower than it was.** The
    frame is now re-set on every mode change, because the two forms are
    different widths — so "it did not call setFrame" is no longer available and
    no longer means anything. What the original was protecting is the panel not
    wandering under a user who is looking at it, and that survives intact: with
    the screen unchanged, the *position* must be identical across a full
    recording cycle, and only the width may differ.

    Asserted on the geometry rather than on a call count for that reason. A
    count could be satisfied by re-framing to the wrong place exactly once.
    """
    overlay = RecordingOverlay(FeedbackConfig(), on_error=lambda _m: None)
    overlay.set_state(DictationState.RECORDING)
    panel = appkit.panels[-1]
    recording_frame = panel.frame

    overlay.set_state(DictationState.IDLE)
    idle_frame = panel.frame
    overlay.set_state(DictationState.RECORDING)

    assert panel.frame == recording_frame, "the panel moved on an unchanged screen"
    assert idle_frame[1] == recording_frame[1], "the pill changed edge"
    assert idle_frame[3] == recording_frame[3], "the pill changed height"
    assert idle_frame[2] == IDLE_WIDTH and recording_frame[2] == ACTIVE_WIDTH


def test_a_raising_layer_on_the_level_path_does_not_escape(
    appkit: _FakeAppKit,
) -> None:
    """The hottest path in the module was the unguarded one.

    `set_level` dispatched `_draw_bars` **raw** — not through `_render`'s
    wrapper — so an exception out of a `CALayer` call crossed the PyObjC bridge
    inside an `NSBlockOperation` and terminated the process. That is verbatim
    the 2026-09-02 failure the wrapper was written for, on the path that runs
    about thirty times a second while the microphone is open, against layers
    that a display change can invalidate.

    Found by a stress pass over S1, not by the work that added the wrapper: the
    guard was extended to the state path and the level path was never asked
    about.
    """
    reported: list[str] = []
    overlay = RecordingOverlay(FeedbackConfig(), on_error=reported.append)
    overlay.set_state(DictationState.RECORDING)

    def explode() -> Any:
        raise RuntimeError("CALayer said no")

    for layer in overlay._bars:
        layer.frame = explode

    overlay.set_level(0.02)  # must not raise

    assert reported, "the failure was swallowed with no report at all"


def test_a_draw_failure_discards_the_panel_rather_than_redrawing_it(
    appkit: _FakeAppKit,
) -> None:
    """One failure per panel, not thirty a second.

    A draw runs ~30×/s while recording, so "report and carry on" would mean a
    broken panel reporting thirty times a second. The failure discards the
    panel, and `set_level` returns early once there is none — so a broken draw
    costs one report and stops until the next show rebuilds.
    """
    reported: list[str] = []
    overlay = RecordingOverlay(FeedbackConfig(), on_error=reported.append)
    overlay.set_state(DictationState.RECORDING)

    def explode() -> Any:
        raise RuntimeError("CALayer said no")

    for layer in overlay._bars:
        layer.frame = explode
    for _ in range(30):
        overlay.set_level(0.02)

    assert len(reported) == 1, (
        f"a broken draw reported {len(reported)} times — it is redrawing a "
        "panel it already knows is broken"
    )


def test_a_draw_that_fails_every_show_reports_every_show(
    appkit: _FakeAppKit,
) -> None:
    """A broken draw is loud once per dictation, and that is the design.

    **This test first asserted that repeated draw failures spend the budget and
    disable the panel. They do not, and the code is right.** Each show ends with
    a successful *hide*, and any success resets the budget — which is the same
    transient-failure rule that makes the budget worth having. Alternating
    failure and success never escalates, by construction.

    So the property that matters is not escalation, it is **visibility**: a
    draw that fails on every dictation raises the fault mark on every dictation.
    Since 2026-09-10 that mark is in the menu-bar title, so a user watching the
    bar sees it without opening anything. Silent degradation is what gate
    finding 1 was; this is the opposite and it is what should be asserted.
    """
    reported: list[str] = []
    overlay = RecordingOverlay(FeedbackConfig(), on_error=reported.append)

    def explode() -> Any:
        raise RuntimeError("CALayer said no")

    shows = OVERLAY_FAILURE_LIMIT + 2
    for _ in range(shows):
        overlay.set_state(DictationState.RECORDING)
        for layer in overlay._bars:
            layer.frame = explode
        overlay.set_level(0.02)
        overlay.set_state(DictationState.IDLE)

    assert len(reported) == shows, (
        f"{len(reported)} reports across {shows} broken dictations — a draw "
        "that fails every time must say so every time"
    )
    assert (
        not overlay._failed
    ), "it disabled the panel on transient failures separated by successes"


def test_a_nil_main_screen_is_not_a_render_failure(appkit: _FakeAppKit) -> None:
    """`NSScreen.mainScreen()` returns nil when no display is active, which is
    a real state — every display asleep, or a clamshell with nothing attached.

    S1 introduced a call to it on **every show**, so a nil there cost a render
    failure, and three in a row disabled the panel. A panel that cannot be
    positioned because there is no screen has nothing to position on; that is
    not a fault, and treating it as one spends the budget that exists for
    faults.
    """
    overlay = RecordingOverlay(FeedbackConfig(), on_error=lambda _m: None)
    overlay.set_state(DictationState.RECORDING)
    overlay.set_state(DictationState.IDLE)

    class _NoScreen:
        @staticmethod
        def mainScreen() -> None:
            return None

    appkit.NSScreen = _NoScreen
    overlay.set_state(DictationState.RECORDING)

    assert overlay._failures == 0, "a nil screen was charged to the failure budget"
    assert not overlay._failed


# ---------------------------------------------------------------------------
# The persistent idle pill, end to end (§5.4, 2026-09-17)
# ---------------------------------------------------------------------------


def test_the_pill_is_on_screen_before_any_dictation(appkit: _FakeAppKit) -> None:
    """`start()` is what makes the affordance persistent.

    Without it the panel appears at the first state change, which is the first
    dictation — so the liveness signal is absent during exactly the period a
    user is wondering whether the daemon is running. `cli.py` calls this once
    the daemon is up.
    """
    overlay = RecordingOverlay(FeedbackConfig())

    overlay.start()

    panel = appkit.panels[-1]
    assert panel.ordered_front_regardless
    assert not panel.ordered_out


def test_sound_does_not_move_an_idle_pill(appkit: _FakeAppKit) -> None:
    """§5.4's second binding consequence: **ignored, not merely unfed**.

    The capture thread and the state thread are different threads, so a level
    published microseconds after the microphone closed can still arrive while
    the panel is idle. If the draw path honours it, the idle pill twitches —
    and a twitching idle pill is a pill that looks like it is recording, which
    is the failure §5.4 exists to name.

    Asserted against the bar layers' geometry rather than against a call
    count: the question is whether the picture moved, and a guard that returns
    early after drawing would satisfy any assertion about calls.
    """
    overlay = RecordingOverlay(FeedbackConfig())
    overlay.start()
    before = [layer.frame() for layer in overlay._bars]

    overlay.set_level(0.5)

    assert [layer.frame() for layer in overlay._bars] == before


def test_sound_moves_the_pill_while_recording(appkit: _FakeAppKit) -> None:
    """The positive control for the test above.

    Without it, a `set_level` that did nothing at all in every state would pass
    — and a recording indicator that never moves is the defect the whole
    module exists to avoid.
    """
    overlay = RecordingOverlay(FeedbackConfig())
    overlay.start()
    overlay.set_state(DictationState.RECORDING)
    before = [layer.frame() for layer in overlay._bars]

    overlay.set_level(0.5)

    assert [layer.frame() for layer in overlay._bars] != before


def test_the_panel_widens_when_recording_starts(appkit: _FakeAppKit) -> None:
    """The width cue, at the panel rather than in the geometry function.

    `frame_for` being right is necessary and not sufficient: the panel has to
    actually be re-framed on the transition, and a panel that computes the
    right rect and never applies it looks identical to one that has no idle
    form at all.
    """
    overlay = RecordingOverlay(FeedbackConfig())
    overlay.start()
    idle_width = appkit.panels[-1].frame[2]

    overlay.set_state(DictationState.RECORDING)

    assert appkit.panels[-1].frame[2] == ACTIVE_WIDTH
    assert idle_width == IDLE_WIDTH


def test_the_panel_narrows_again_when_the_microphone_closes(
    appkit: _FakeAppKit,
) -> None:
    """And back. A pill left wide after a dictation reports a live microphone
    for as long as the daemon runs, which is the over-report the module
    preamble refuses.
    """
    overlay = RecordingOverlay(FeedbackConfig())
    overlay.start()
    overlay.set_state(DictationState.RECORDING)

    overlay.set_state(DictationState.TRANSCRIBING)

    assert appkit.panels[-1].frame[2] == IDLE_WIDTH


def test_declining_the_idle_pill_leaves_nothing_on_screen(
    appkit: _FakeAppKit,
) -> None:
    """`overlay_idle = false` end to end, not merely in `mode_for`.

    The config key has to reach the render path. A key that is honoured by the
    pure function and ignored by the panel is worse than no key: the user turns
    it off, the pill stays, and the setting is a lie.
    """
    overlay = RecordingOverlay(FeedbackConfig(overlay_idle=False))

    overlay.start()

    assert not appkit.panels or not appkit.panels[-1].ordered_front_regardless
