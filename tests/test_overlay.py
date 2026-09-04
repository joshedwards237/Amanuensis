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

import pytest

from amanuensis.config import FeedbackConfig
from amanuensis.controllers.dictation_controller import DictationState
from amanuensis.ui import indicator as indicator_module
from amanuensis.ui.overlay import (
    BAR_COUNT,
    CORNER_RADIUS,
    MAX_BAR_HEIGHT,
    MIN_BAR_HEIGHT,
    RecordingOverlay,
    bar_heights,
    frame_for,
    should_show,
)
from test_indicator import _FakeAppKit, _FakeFoundation, _FakeMainQueue

# ---------------------------------------------------------------------------
# When it shows — a privacy affordance that lies is worse than none
# ---------------------------------------------------------------------------


def test_it_shows_while_recording() -> None:
    assert should_show(DictationState.RECORDING) is True


@pytest.mark.parametrize(
    "state",
    [s for s in DictationState if s is not DictationState.RECORDING],
)
def test_it_hides_whenever_the_microphone_is_closed(state: DictationState) -> None:
    """The panel answers exactly one question — *is the microphone live?* —
    and the microphone is live in exactly one state.

    TRANSCRIBING is the trap. It is the longest-running state, it looks busy,
    and showing the panel through it would be the natural thing to do. It is
    also the state in which the microphone has already been released, so a
    panel that stayed up would tell the user they were being recorded when they
    were not. For a privacy affordance that is not a cosmetic error.
    """
    assert should_show(state) is False


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
        panel.collection_behavior
        & appkit.NSWindowCollectionBehaviorFullScreenAuxiliary
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


def test_it_is_removed_when_recording_stops(appkit: _FakeAppKit) -> None:
    overlay = RecordingOverlay(FeedbackConfig())
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

    reported.clear()
    overlay.set_state(DictationState.IDLE)
    overlay.set_state(DictationState.RECORDING)
    assert reported == [], "a failed overlay must not retry on every dictation"


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
    assert span / _WIDTH >= 0.5, (
        f"the bars occupy {span / _WIDTH:.0%} of the pill; the rest is padding"
    )


def test_ordinary_speech_uses_most_of_the_range() -> None:
    """"A little more dynamics and amplitude."

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
        assert max(heights) <= MIN_BAR_HEIGHT + 0.01, (
            f"ambient {ambient} deflects to {max(heights)}"
        )
