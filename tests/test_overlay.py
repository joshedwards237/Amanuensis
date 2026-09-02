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
from amanuensis.ui.overlay import RecordingOverlay, frame_for, should_show
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
