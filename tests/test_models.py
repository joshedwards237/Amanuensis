"""Session and timing models.

`LatencyBreakdown` carries the one distinction most likely to be flattened by
a later reader: `g1_ms` is the gated number and `total_ms` is diagnostics.
Asserting G1 against `total_ms` compares a ~10,400 ms figure to a 400 ms
budget and fails unconditionally (PRD §6.3), so the difference gets a test
rather than a comment.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

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


def test_permission_status_is_not_granted_until_every_permission_is() -> None:
    granted = PermissionStatus(granted=True, missing=())
    partial = PermissionStatus(granted=False, missing=("Accessibility",))

    assert granted.granted
    assert not partial.granted
    assert "Accessibility" in partial.missing
