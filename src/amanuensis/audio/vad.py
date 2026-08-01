"""Silence trimming — the dominant latency lever, and the only probabilistic
step Phase 1 puts in the path between a user's voice and their transcript.

Why this is worth a module
--------------------------
Whisper's encoder always processes a padded 30-second window; only the decoder
scales with output length. Measured (PRD §7.4): `base.en` takes 352 ms for a
10-second utterance and 517 ms for a 26-second one — 1.5×, not 2.6×. The
consequence runs the other way and is the whole point: **a 2-second utterance
costs nearly what a 25-second one does.** Most real dictation is short, so
without trimming the common case pays close to the worst case, every single
time. That is why §7.4 moved trimming out of Phase 3 and into the phase that
measures latency — Phase 1 without trimming would have measured a padded window
rather than the product.

Why it is not `vad_filter=True`
-------------------------------
faster-whisper has a VAD flag of its own and using it would have been three
characters of work. It is not used, for two reasons that both outlive this
phase:

1. **PRD §9 requires Moonshine be benchmarked against faster-whisper**, and
   Moonshine has no such flag. A comparison in which one engine silently trims
   and the other does not measures the trimmer, not the engines.
2. **`hotkey.mode = "vad_auto"` (§5.3) needs a detector with no engine
   attached** — it decides when to *start and stop recording*, which happens
   before any engine is involved.

So the detector lives in the audio layer, applies to every engine, and the
engine's own flag is explicitly turned off (see `engines/faster_whisper.py`).

Where the weights come from, and why that is a G3 matter
--------------------------------------------------------
The Silero ONNX model ships **inside the faster-whisper wheel**
(`faster_whisper/assets/silero_vad_v6.onnx`). Loading it touches the filesystem
and nothing else. That is not a convenience — goal G3 is verified by packet
capture, and a VAD that downloaded its own weights on first use would fire
exactly the cache-miss fetch this project spent a phase gate ruling out. The
import of `faster_whisper.vad` from the audio layer is therefore deliberate:
depending on that package for an asset already vendored beats vendoring a
second copy or fetching one.

The guards, and why they were written before the first measurement
------------------------------------------------------------------
This is a neural detector deciding which samples reach the engine. The
invariant is that **trimming is deletion-only and must never cost the user
their words**, and it is checkable, which is what makes the failures catchable
at all:

* **No speech detected → the input passes through untouched.** Never empty. A
  quiet microphone must degrade to "slow", never to silent data loss that
  presents as the ASR having failed.
* **The output is never longer than the input.** A bug in chunk assembly could
  otherwise duplicate audio and nothing downstream would notice.

`TrimResult` reports what survived rather than only returning the audio,
because a trim that ate most of an utterance is a fact the user needs to be
able to see (§5.4's principle: what the tool did to your audio is not allowed
to be invisible).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:  # pragma: no cover — import-time cost, not behaviour
    from amanuensis.config import VadConfig

__all__ = ["SUPPORTED_SAMPLE_RATES", "TrimResult", "VoiceActivityDetector"]

#: 16 kHz only. Silero itself ships an 8 kHz head, but faster-whisper's wrapper
#: hardcodes a 512-sample window, which is the 16 kHz frame size — feeding it
#: 8 kHz audio would run the detector on frames twice the intended duration and
#: return timestamps that are quietly wrong rather than obviously wrong.
#: `config.py` pins `[audio] sample_rate` to the same value for Whisper's sake.
SUPPORTED_SAMPLE_RATES: tuple[int, ...] = (16000,)


@dataclass(frozen=True, slots=True)
class TrimResult:
    """Trimmed audio plus enough context to tell whether to trust it."""

    audio: NDArray[np.float32]
    original_seconds: float
    retained_seconds: float
    speech_segments: int
    #: True when no speech was detected and the input was passed through whole.
    #: Distinct from `speech_segments == 0` for a caller that wants to say
    #: "I heard nothing, so I trimmed nothing" rather than guessing.
    fell_back: bool

    @property
    def retained_fraction(self) -> float:
        """How much of the buffer survived. 1.0 when nothing was removed."""
        if self.original_seconds <= 0.0:
            return 1.0
        return self.retained_seconds / self.original_seconds

    @property
    def removed_seconds(self) -> float:
        return self.original_seconds - self.retained_seconds


class VoiceActivityDetector:
    """Silero VAD, used here only to drop silence before transcription.

    One instance serves the process lifetime (§6.1). The ONNX session is built
    on first use and reused; building it per utterance would add tens of
    milliseconds to the stage that exists to remove hundreds.
    """

    def __init__(self, config: VadConfig) -> None:
        self._config = config

    @cached_property
    def model_path(self) -> Path:
        """The bundled Silero asset. Exists on disk before any call is made."""
        from faster_whisper.vad import get_assets_path

        return Path(get_assets_path()) / "silero_vad_v6.onnx"

    def load(self) -> None:
        """Build the ONNX session now, so no utterance pays for it.

        Idempotent — `get_vad_model` is `lru_cache`d upstream, so this is a
        cheap call after the first. It exists for the same reason
        `TranscriptionEngine.warm_up` does: without it the session build lands
        inside the first measured trim, in the stage whose whole purpose is
        being small. The daemon calls this at start; the tier check calls it
        before its warm-up run, or the reported p50 is one machine's ONNX
        initialisation averaged into nine decodes.
        """
        from faster_whisper.vad import get_vad_model

        get_vad_model()

    def trim(self, audio: NDArray[np.float32], sample_rate: int) -> TrimResult:
        """Remove silence, or explain why nothing was removed.

        Never raises on unusual audio — an empty buffer and a silent buffer are
        both ordinary things for a user to produce and neither is an error. The
        one rejection is a sample rate the detector cannot honestly process,
        which is a configuration mistake rather than a user action.
        """
        if sample_rate not in SUPPORTED_SAMPLE_RATES:
            supported = ", ".join(str(rate) for rate in SUPPORTED_SAMPLE_RATES)
            raise ValueError(
                f"sample rate {sample_rate} is not supported by Silero VAD; "
                f"supported rates: {supported}"
            )

        original_seconds = len(audio) / sample_rate
        if len(audio) == 0:
            return TrimResult(
                audio=audio,
                original_seconds=0.0,
                retained_seconds=0.0,
                speech_segments=0,
                fell_back=True,
            )

        segments = self._speech_segments(audio, sample_rate)
        if not segments:
            # Guard 1. Passing the buffer through whole means a missed
            # detection costs latency; returning nothing would cost the words.
            return TrimResult(
                audio=audio,
                original_seconds=original_seconds,
                retained_seconds=original_seconds,
                speech_segments=0,
                fell_back=True,
            )

        from faster_whisper.vad import collect_chunks

        chunks, _metadata = collect_chunks(audio, segments, sampling_rate=sample_rate)
        trimmed = np.concatenate(chunks).astype(np.float32, copy=False)

        # Guard 2. Deletion-only is a checkable property, so it is checked
        # rather than assumed. If chunk assembly ever grows audio, the original
        # is what the user gets and the anomaly is visible in `fell_back`.
        if len(trimmed) > len(audio):
            return TrimResult(
                audio=audio,
                original_seconds=original_seconds,
                retained_seconds=original_seconds,
                speech_segments=len(segments),
                fell_back=True,
            )

        return TrimResult(
            audio=trimmed,
            original_seconds=original_seconds,
            retained_seconds=len(trimmed) / sample_rate,
            speech_segments=len(segments),
            fell_back=False,
        )

    def _speech_segments(
        self, audio: NDArray[np.float32], sample_rate: int
    ) -> list[dict[str, int]]:
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        options = VadOptions(
            threshold=self._config.threshold,
            min_silence_duration_ms=self._config.min_silence_duration_ms,
            speech_pad_ms=self._config.speech_pad_ms,
        )
        segments: list[dict[str, int]] = get_speech_timestamps(
            audio, options, sampling_rate=sample_rate
        )
        return segments
