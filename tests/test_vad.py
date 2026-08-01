"""Silence trimming — the dominant latency lever, so it gets the most tests.

PRD §7.4 moved trimming from Phase 3 into Phase 1 because it changes what the
Phase 1 gate measures. The reason is worth restating, because it is not
obvious: Whisper's encoder always processes a padded 30-second window and only
the decoder scales with output length, so a 2-second utterance costs nearly
what a 25-second one does. Every second of leading and trailing dead air is
paid in full on every single utterance.

That makes trimming a *probabilistic step in the critical path* — a neural
detector deciding which samples reach the engine. The project's standing lesson
about those is that they get wrapped in deterministic checks written before the
step is tested, derived from the step's own invariant. The invariant here is
that **trimming is deletion-only and must never cost the user their words**, so
two guards are asserted below ahead of anything about latency:

1. Audio with no detected speech passes through **untouched**, never empty.
2. The output is never longer than the input.

Without the first, a quiet microphone turns into silent data loss that looks
exactly like the ASR failing. Without the second, a bug in chunk assembly could
duplicate audio and nothing downstream would notice.
"""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from amanuensis.audio.vad import VoiceActivityDetector
from amanuensis.config import VadConfig
from conftest import pad_with_silence, requires_corpus


def _detector(**overrides: object) -> VoiceActivityDetector:
    return VoiceActivityDetector(VadConfig(**overrides))  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# The guards — asserted first, because they are what makes the rest safe
# --------------------------------------------------------------------------


def test_audio_with_no_speech_passes_through_untouched(
    silence: NDArray[np.float32],
) -> None:
    """Guard 1. A quiet mic must degrade to "slow", never to "silently empty"."""
    result = _detector().trim(silence, 16_000)

    assert result.fell_back is True
    assert len(result.audio) == len(silence)


def test_trimming_never_returns_more_audio_than_it_was_given(
    silence: NDArray[np.float32],
) -> None:
    """Guard 2. Trimming is deletion-only; that is a checkable property."""
    result = _detector().trim(silence, 16_000)

    assert len(result.audio) <= len(silence)


@requires_corpus
def test_trimming_real_speech_is_still_deletion_only(
    speech: tuple[NDArray[np.float32], int],
) -> None:
    audio, rate = speech

    result = _detector().trim(audio, rate)

    assert len(result.audio) <= len(audio)


# --------------------------------------------------------------------------
# What it is for
# --------------------------------------------------------------------------


@requires_corpus
def test_dead_air_around_an_utterance_is_removed(
    speech: tuple[NDArray[np.float32], int],
) -> None:
    """The Phase 1 case: press, pause, speak, pause, release."""
    audio, rate = speech
    padded = pad_with_silence(audio, rate, seconds=5.0)

    result = _detector().trim(padded, rate)

    assert result.fell_back is False
    assert result.speech_segments >= 1
    # Ten seconds of added silence; a detector that removed none of it is not
    # doing the job §7.4 moved into this phase.
    assert result.retained_seconds < result.original_seconds - 5.0


@requires_corpus
def test_the_result_reports_what_fraction_survived(
    speech: tuple[NDArray[np.float32], int],
) -> None:
    """Visible, not inferred. A trim that ate most of an utterance is a fact
    the CLI has to be able to print — §5.4's rule that a user must be able to
    see what the tool did to their audio."""
    audio, rate = speech
    padded = pad_with_silence(audio, rate, seconds=5.0)

    result = _detector().trim(padded, rate)

    assert 0.0 < result.retained_fraction < 1.0


def test_an_empty_buffer_is_not_an_error() -> None:
    """A hotkey tapped and released instantly. Downstream decides what to do
    with nothing; the detector does not raise about it."""
    result = _detector().trim(np.zeros(0, dtype=np.float32), 16_000)

    assert len(result.audio) == 0
    assert result.original_seconds == 0.0


# --------------------------------------------------------------------------
# Contract edges
# --------------------------------------------------------------------------


def test_an_unsupported_sample_rate_names_the_rates_that_work(
    silence: NDArray[np.float32],
) -> None:
    with pytest.raises(ValueError) as exc:
        _detector().trim(silence, 44_100)

    message = str(exc.value)
    assert "44100" in message
    assert "16000" in message


@requires_corpus
def test_one_detector_serves_many_utterances(
    speech: tuple[NDArray[np.float32], int],
) -> None:
    """The daemon holds one detector for the process lifetime (§6.1). A model
    that accumulated state between calls would make the second dictation of a
    session behave differently from the first."""
    audio, rate = speech
    detector = _detector()

    first = detector.trim(audio, rate)
    second = detector.trim(audio, rate)

    assert first.retained_seconds == second.retained_seconds
    assert np.array_equal(first.audio, second.audio)


def test_the_detector_loads_no_weights_over_the_network() -> None:
    """G3, structurally. The Silero ONNX asset ships inside the faster-whisper
    wheel, so the model path resolves to a file already on disk. A detector that
    downloaded on first use would fire the exact cache-miss fetch this phase's
    packet capture exists to rule out."""
    assert _detector().model_path.exists()
