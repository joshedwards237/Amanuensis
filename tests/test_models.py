"""Session and timing models.

`LatencyBreakdown` carries the one distinction most likely to be flattened by
a later reader: `g1_ms` is the gated number and `total_ms` is diagnostics.
Asserting G1 against `total_ms` compares a ~10,400 ms figure to a 400 ms
budget and fails unconditionally (PRD §6.3), so the difference gets a test
rather than a comment.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

import numpy as np
import pytest

from amanuensis.models.results import InjectionResult, PermissionStatus
from amanuensis.models.session import DictationSession, LatencyBreakdown


def _session(**overrides: object) -> DictationSession:
    defaults: dict[str, object] = {
        "id": "s-1",
        "started_at": datetime(2026, 7, 31, 12, 0, tzinfo=UTC),
        "audio": None,
        "sample_rate": 16000,
    }
    defaults.update(overrides)
    return DictationSession(**defaults)  # type: ignore[arg-type]


def test_g1_excludes_capture_and_total_includes_it() -> None:
    timings = LatencyBreakdown(
        capture_ms=10_000.0,
        transcribe_ms=328.0,
        postprocess_ms=12.0,
        inject_ms=40.0,
    )

    assert timings.g1_ms == 380.0
    assert timings.total_ms == 10_380.0


def test_a_fresh_breakdown_is_all_zero() -> None:
    assert LatencyBreakdown().g1_ms == 0.0
    assert LatencyBreakdown().total_ms == 0.0


def test_duration_is_derived_from_the_audio_and_the_sample_rate() -> None:
    audio = np.zeros(32_000, dtype=np.float32)

    assert _session(audio=audio).duration_seconds() == 2.0


def test_duration_of_a_session_that_captured_nothing_is_zero() -> None:
    assert _session(audio=None).duration_seconds() == 0.0


def test_history_row_carries_the_timings_g1_is_defended_with() -> None:
    session = _session(
        raw_transcript="hello world",
        final_text="Hello world.",
        timings=LatencyBreakdown(transcribe_ms=300.0, inject_ms=40.0),
    )

    row = session.to_history_row()

    assert row["id"] == "s-1"
    assert row["transcript"] == "Hello world."
    assert row["transcribe_ms"] == 300.0
    assert row["inject_ms"] == 40.0
    # Audio is the sensitive artefact and never rides along in the row (§5.5).
    assert "audio" not in row


def test_history_row_falls_back_to_the_raw_transcript() -> None:
    """Persist-before-inject (§8) writes before post-processing has a result."""
    session = _session(raw_transcript="hello world", final_text=None)

    assert session.to_history_row()["transcript"] == "hello world"


def test_injection_result_reports_failure_with_a_reason() -> None:
    ok = InjectionResult(succeeded=True, strategy="clipboard")
    bad = InjectionResult(
        succeeded=False, strategy="clipboard", error="clipboard was locked"
    )

    assert ok.succeeded and ok.error is None
    assert not bad.succeeded and bad.error == "clipboard was locked"


def test_a_fresh_session_is_not_complete() -> None:
    assert not _session().completed.is_set()


def test_wait_returns_false_on_timeout_and_true_once_signalled() -> None:
    """§6.3, objection A6: completion is signalled, never polled.

    Before this existed, "callers observe completion through the session"
    described an interface that was not there — the only available reading was
    spinning on a mutable dataclass across a thread boundary, which is the thing
    Half-Sync/Half-Async is chosen to avoid.
    """
    session = _session()

    assert session.wait(timeout=0.01) is False

    session.completed.set()

    assert session.wait(timeout=0.01) is True


def test_the_worker_thread_writes_before_it_signals() -> None:
    """The ordering rule: fields first, event last.

    Nothing else guards the fields, so a thread that sees the event set must be
    guaranteed a fully written session. Asserted against a real thread rather
    than by inspection, because this is the one invariant the whole model rests
    on.
    """
    session = _session()

    def worker() -> None:
        session.raw_transcript = "hello world"
        session.timings.transcribe_ms = 328.0
        session.completed.set()

    thread = threading.Thread(target=worker)
    thread.start()

    assert session.wait(timeout=2.0) is True
    assert session.raw_transcript == "hello world"
    assert session.timings.transcribe_ms == 328.0
    thread.join()


def test_two_sessions_do_not_share_a_completion_event() -> None:
    """A default_factory bug here would make every session complete at once."""
    first, second = _session(), _session()

    first.completed.set()

    assert not second.completed.is_set()


def test_permission_status_is_not_granted_until_every_permission_is() -> None:
    granted = PermissionStatus(granted=True, missing=())
    partial = PermissionStatus(granted=False, missing=("Accessibility",))

    assert granted.granted
    assert not partial.granted
    assert "Accessibility" in partial.missing


# --------------------------------------------------------------------------
# vad_ms — added in Phase 1
# --------------------------------------------------------------------------


def test_vad_trimming_is_inside_the_gated_number() -> None:
    """G1's clock starts at hotkey release (§2), and trimming happens after
    release and before transcription. Folding it into `transcribe_ms` would
    have hidden the *dominant* latency lever (§7.4) inside the stage it exists
    to shrink, in the very breakdown G1 is defended with.
    """
    timings = LatencyBreakdown(
        capture_ms=10_000.0,
        vad_ms=18.0,
        transcribe_ms=328.0,
        postprocess_ms=12.0,
        inject_ms=40.0,
    )

    assert timings.g1_ms == 398.0
    assert timings.total_ms == 10_398.0


def test_the_asr_stage_is_what_the_tier_check_compares(tmp_path: object) -> None:
    """§7.2's 350/700 thresholds cover the ASR stage with VAD on — "a check run
    in a configuration the product does not use measures nothing"."""
    timings = LatencyBreakdown(vad_ms=18.0, transcribe_ms=328.0, inject_ms=40.0)

    assert timings.asr_ms == 346.0


def test_history_row_carries_the_trim_cost() -> None:
    session = _session(timings=LatencyBreakdown(vad_ms=18.0, transcribe_ms=300.0))

    assert session.to_history_row()["vad_ms"] == 18.0


# --------------------------------------------------------------------------
# persist_ms and engine — added in Phase 2a
# --------------------------------------------------------------------------


def test_the_pre_injection_write_is_inside_the_gated_number() -> None:
    """Same argument as `vad_ms`, one phase later. §8 puts the history write
    between transcription and injection, and G1's clock is already running —
    it starts at hotkey release (§2). A stage inside the gated number with no
    field to record into is a stage that cannot be defended when G1 is missed.

    It is its own field rather than folded into `inject_ms` because the two
    have different remedies: a slow write is a storage problem, a slow inject
    is a target-application problem.
    """
    timings = LatencyBreakdown(
        capture_ms=10_000.0,
        vad_ms=18.0,
        transcribe_ms=328.0,
        postprocess_ms=12.0,
        persist_ms=2.0,
        inject_ms=40.0,
    )

    assert timings.g1_ms == 400.0
    assert timings.total_ms == 10_400.0


def test_the_write_cost_is_not_counted_against_the_tier_thresholds() -> None:
    """§7.2's 350/700 bound trimming plus decoding. Persisting is neither, and
    folding it in would move a machine's recorded tier for a reason that has
    nothing to do with its ASR speed."""
    timings = LatencyBreakdown(vad_ms=18.0, transcribe_ms=328.0, persist_ms=2.0)

    assert timings.asr_ms == 346.0


def test_history_row_names_the_engine_that_produced_the_transcript() -> None:
    """§5.5 lists engine among what history stores. Without it a transcript
    cannot be re-judged when the engine changes, which is the whole reason
    ADR 0001 is revisitable."""
    session = _session(engine="faster_whisper:tiny.en")

    assert session.to_history_row()["engine"] == "faster_whisper:tiny.en"


def test_restoring_the_clipboard_is_outside_the_gated_number() -> None:
    """§2 defines G1 as ending when the text is **fully present** in the
    focused application. The clipboard restore happens strictly after that —
    the user has their words and is reading them while it runs — so counting
    it against G1 measures the product as slower than the experience it
    delivers.

    Measured at the Phase 2a gate: a real dictation reported `inject_ms` of
    180.3 ms, of which roughly 150 ms was `restore_delay_ms` sleeping. That
    pushed a 272 ms delivery over G1's 400 ms p50 on paper.

    It is still recorded, and still in `total_ms`, because a restore that
    never completes is a clipboard the user does not get back.
    """
    timings = LatencyBreakdown(
        vad_ms=25.6,
        transcribe_ms=213.2,
        persist_ms=2.8,
        inject_ms=30.3,
        restore_ms=150.0,
    )

    assert timings.g1_ms == pytest.approx(271.9)
    assert timings.total_ms == pytest.approx(421.9)


def test_the_restore_is_not_charged_to_the_asr_stage_either() -> None:
    timings = LatencyBreakdown(vad_ms=18.0, transcribe_ms=328.0, restore_ms=150.0)

    assert timings.asr_ms == 346.0
