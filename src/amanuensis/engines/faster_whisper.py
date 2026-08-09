"""faster-whisper (CTranslate2) — the default transcription engine.

Everything in this file that looks like a magic number is a PRD citation, and
several of them are citations to a measurement that contradicted the PRD's
first guess. Worth reading before changing one.

Where the weights come from
---------------------------
Goal G3 is "no network at runtime", verified by packet capture. PRD §7.6 gives
the mechanism: weights download **once at install**, from a pinned revision,
and are resolved from a **local path** thereafter — never a repository ID.

That distinction is the whole of the guarantee, and it is easy to lose. Passing
`"tiny.en"` straight to `WhisperModel` works beautifully on any machine whose
Hugging Face cache is warm — which is every machine a developer tests on — and
silently fetches on every machine whose cache is not. So `load()` resolves a
path with `local_files_only=True` first, and a cold cache raises an error
naming `manu install` rather than reaching for the network. The packet capture
at the Phase 1 gate observes one run; this makes the property structural.

Why the engine's own VAD flag is off
------------------------------------
faster-whisper has `vad_filter=True`, and PRD §7.4's trimming could have been
that flag. It is not, and `transcribe()` passes `vad_filter=False` explicitly
so nobody re-enables it by upgrading the library. Trimming lives in
`audio/vad.py` because PRD §9 requires Moonshine be benchmarked against this
engine and Moonshine has no equivalent flag — a comparison where one engine
silently trims and the other does not measures the trimmer. See that module's
preamble for the rest.

`cpu_threads`, which was never specified and was worth 1.8×
-----------------------------------------------------------
CTranslate2 defaults to **four threads** regardless of core count. On a
14-core M3 Max that default measured 4,413 ms against 2,412 ms at the
performance-core count, and **the first run of the pre-Phase-0 probe returned
NO-GO on it** — the project's top risk nearly fired on a library default rather
than on physics (§7.2). `config.resolve_cpu_threads` owns the resolution; this
module's only job is never to leave the parameter unset.

`device`, and the accelerator that does not exist
-------------------------------------------------
CTranslate2 has **no Metal backend**. "Apple Silicon" and "CPU only" are one
execution path with different core counts, which is why §7.2's tier table was
rewritten around what a machine *measures* rather than what chip it contains,
and why `device = "mps"` was removed from §5.3's options — it was never a
reachable value. `resolve_device` rejects it with the reason rather than
falling back silently, because a silent fallback is how "Apple Silicon" ended
up in a table as though it were an accelerator tier.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import numpy as np
from numpy.typing import NDArray

from amanuensis.config import resolve_cpu_threads
from amanuensis.engines.base import TranscriptionEngine
from amanuensis.models.results import Transcription

if TYPE_CHECKING:  # pragma: no cover — import-time cost, not behaviour
    from amanuensis.config import EngineConfig

__all__ = [
    "COMPUTE_TYPE",
    "PINNED_REVISIONS",
    "FasterWhisperEngine",
    "ModelNotAvailableError",
    "resolve_device",
    "resolve_model_name",
    "resolve_model_path",
]

#: §7.2's table specifies int8 for every CPU row.
COMPUTE_TYPE: Final = "int8"

#: `beam_size = 1`. The probe ran greedy throughout and §7.2's measured
#: 328/420 ms figures are greedy figures; raising it here would invalidate the
#: number the tier check compares against. Sweeping it is a named open item.
BEAM_SIZE: Final = 1

#: §7.2's `model = "auto"` table, reduced to the rows that have a v1 user.
#: macOS is the only v1 platform (§3) and CTranslate2 has no CUDA there, so the
#: two CUDA rows — both labelled "estimate, **unmeasured**" in the PRD — are
#: collapsed to one entry that is honest about never having been timed.
#: The CUDA rows also key on VRAM, which §7.2 specifies no way to measure; that
#: gap is recorded in docs/gates/phase-1.md rather than papered over here.
_MODEL_BY_DEVICE: Final[dict[str, str]] = {
    "cpu": "tiny.en",
    "cuda": "large-v3-turbo",
}

#: §7.6: "from a pinned revision". A floating `main` means the bytes a user
#: installs today differ from the bytes this project measured, which makes
#: every number in §7.2 and ADR 0001 a claim about something else. Only models
#: this project has actually resolved a revision for are listed; anything else
#: downloads at its default revision and says so.
PINNED_REVISIONS: Final[dict[str, str]] = {
    "tiny.en": "0d3d19a32d3338f10357c0889762bd8d64bbdeba",
    "base.en": "3d3d5dee26484f91867d81cb899cfcf72b96be6c",
    "small.en": "d1d751a5f8271d482d14ca55d9e2deeebbae577f",
}

#: Warm-up audio: one second of quiet, deterministic noise. Silence would be
#: the obvious choice and is the wrong one — Whisper's decoder repetition-loops
#: on silence (541 ms → 6,039 ms on the same model and sample, §7.2), so a
#: silent warm-up would pay this product's documented worst case on every
#: daemon start. Noise gives the encoder real work and the decoder nothing to
#: latch onto. Seeded, so warm-up cost does not vary run to run.
_WARMUP_SECONDS: Final = 1.0


class ModelNotAvailableError(Exception):
    """Weights are not on disk, and this process will not go and get them."""


def _cuda_device_count() -> int:
    import ctranslate2

    count: int = ctranslate2.get_cuda_device_count()
    return count


def _whisper_model_class() -> type:
    """Import CTranslate2 at the point of use, never at module import.

    `manu --help` and a config error have no business paying a multi-second
    import for a model runtime they will not use (`engines/registry.py` makes
    the same argument, for the same reason).
    """
    from faster_whisper import WhisperModel

    model_class: type = WhisperModel
    return model_class


def resolve_device(device: str) -> str:
    """Turn `[engine] device` into a CTranslate2 device string."""
    if device == "mps":
        raise ValueError(
            "engine.device: 'mps' is not a device — CTranslate2 has no Metal "
            "backend, so on a Mac 'cpu' is the only execution path (§7.2). "
            "It was removed from §5.3's options for this reason."
        )
    if device == "auto":
        return "cuda" if _cuda_device_count() > 0 else "cpu"
    if device in ("cpu", "cuda"):
        return device
    raise ValueError(f"engine.device: expected auto, cpu or cuda; got {device!r}")


def resolve_model_name(model: str, device: str) -> str:
    """Apply §7.2's `model = "auto"` table, or pass an explicit choice through."""
    if model != "auto":
        return model
    try:
        return _MODEL_BY_DEVICE[device]
    except KeyError:  # pragma: no cover — resolve_device has already narrowed
        raise ValueError(f"no 'auto' model for device {device!r}") from None


def resolve_model_path(model: str, cache_dir: Path | None = None) -> Path:
    """Locate weights already on disk. Never downloads.

    Accepts a directory directly, because packagers and offline installs point
    `[engine] model` at one — §7.6's "resolved from a local path" has to cover
    the plain case as well as the cached one.
    """
    candidate = Path(model).expanduser()
    if candidate.is_dir():
        return candidate

    from faster_whisper.utils import download_model

    try:
        located = download_model(
            model,
            local_files_only=True,
            cache_dir=str(cache_dir) if cache_dir is not None else None,
            revision=PINNED_REVISIONS.get(model),
        )
    except Exception as exc:  # hub raises several unrelated types
        raise ModelNotAvailableError(
            f"the {model!r} weights are not on this machine, and Amanuensis "
            f"does not download at runtime (goal G3, §7.6).\n"
            f"Run `manu install` once to fetch them, then try again.\n"
            f"Underlying cause: {type(exc).__name__}: {exc}"
        ) from exc
    return Path(located)


def download_weights(model: str, cache_dir: Path | None = None) -> Path:
    """Fetch weights. The **only** function in this package that may use the
    network, called from `manu install` and from nothing else.

    Kept in this module rather than in the CLI so that the pinned revision and
    the resolution rule live beside each other; a download that used a
    different revision from the one `resolve_model_path` asks for would produce
    a cache the runtime cannot see.
    """
    from faster_whisper.utils import download_model

    return Path(
        download_model(
            model,
            local_files_only=False,
            cache_dir=str(cache_dir) if cache_dir is not None else None,
            revision=PINNED_REVISIONS.get(model),
        )
    )


class FasterWhisperEngine(TranscriptionEngine):
    """CTranslate2-backed Whisper. One instance, resident for the process."""

    def __init__(self, config: EngineConfig) -> None:
        self._config = config
        self._model: Any | None = None
        self._device = resolve_device(config.device)
        self._model_name = resolve_model_name(config.model, self._device)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def model_name(self) -> str:
        """What `auto` resolved to. Reported by the tier check and the ADR —
        a latency figure with no model attached is not a measurement."""
        return self._model_name

    @property
    def cpu_threads(self) -> int:
        return resolve_cpu_threads(self._config.cpu_threads)

    def load(self) -> None:
        """Blocking, idempotent, and never over the network."""
        if self._model is not None:
            return

        path = resolve_model_path(self._model_name)
        self._model = _whisper_model_class()(
            str(path),
            device=self._device,
            compute_type=COMPUTE_TYPE,
            cpu_threads=self.cpu_threads,
        )

    def warm_up(self) -> None:
        """One throwaway inference, so the first real utterance is not the slow one.

        A user's first dictation of the session is exactly when they are
        deciding whether this is fast (§6.3).
        """
        model = self._require_model("warm_up")
        rng = np.random.default_rng(seed=0)
        noise = (
            rng.standard_normal(int(_WARMUP_SECONDS * 16_000)).astype(np.float32) * 0.01
        )
        self._decode(model, noise)

    def transcribe(
        self,
        audio: NDArray[np.float32],
        sample_rate: int,
        *,
        biased: bool = True,
        boost: Sequence[str] = (),
    ) -> Transcription:
        """One utterance in, raw transcript out.

        `sample_rate` is accepted to satisfy the ABC and validated rather than
        used: Whisper's feature extractor is built for 16 kHz and there is no
        resampling here, so a mismatched rate would silently produce a
        transcript of audio played at the wrong speed.

        `biased=False` drops `initial_prompt`, which is §5.7's retry. Nothing
        else changes: a retry that also moved the beam size or the VAD flag
        would be measuring a different pipeline than the one that failed.
        """
        from amanuensis.config import SUPPORTED_SAMPLE_RATE

        if sample_rate != SUPPORTED_SAMPLE_RATE:
            raise ValueError(
                f"audio must be {SUPPORTED_SAMPLE_RATE} Hz; got {sample_rate}"
            )
        model = self._require_model("transcribe")
        return self._decode(model, audio, biased=biased, boost=boost)

    def _decode(
        self,
        model: Any,
        audio: NDArray[np.float32],
        *,
        biased: bool = True,
        boost: Sequence[str] = (),
    ) -> Transcription:
        """The one place decoding parameters are set.

        `transcribe()` returns a generator and the work happens on iteration —
        a timer stopped before the generator is drained measures almost
        nothing. The join is therefore part of the call, not a caller's
        responsibility, so no measurement in this project can get it wrong.

        Draining is also what makes `decoded_seconds` available at all. Each
        segment carries `start` and `end`; this method used to join the texts
        and drop everything else, which meant §5.7's signal was crossing the
        boundary and being discarded on the floor.
        """
        segments, _info = model.transcribe(
            audio,
            language=self._config.language or None,
            beam_size=BEAM_SIZE,
            initial_prompt=self._prompt(boost) if biased else None,
            # Trimming is `audio/vad.py`'s job, for every engine. Explicit
            # rather than defaulted, so a library default flip cannot quietly
            # start double-trimming.
            vad_filter=False,
        )
        text: list[str] = []
        decoded_seconds = 0.0
        for segment in segments:
            text.append(segment.text)
            # `max` rather than "the last one": segment order is the decoder's
            # and nothing in the API promises it is monotonic in `end`.
            decoded_seconds = max(decoded_seconds, float(segment.end))
        return Transcription("".join(text), decoded_seconds)

    def _prompt(self, boost: Sequence[str]) -> str | None:
        """`[engine] initial_prompt`, then `[boost]`'s terms. Prose first.

        §5.6's O7: two config keys for one behaviour, resolved by making
        `[boost]` authoritative and documenting `initial_prompt` as prose
        framing only. Concatenating in that order is what "framing" means —
        the prose sets register, the terms are the vocabulary.

        **The generated segment is shaped so it cannot collapse a transcript.**
        §5.7's measured trigger is a prompt with the form of a complete short
        utterance the decoder can plausibly emit as the whole transcript —
        `"And how much is this?"` produces exactly that string from a 25-second
        clip, deterministically. A comma-separated term list with no
        sentence-final punctuation is structurally not that shape. This is a
        constraint on a string this method writes, not a heuristic over the
        user's prose: a prose *detector* over `initial_prompt` was rejected,
        because it has a false-positive population and §5.7's guard catches the
        failure directly.

        `None` rather than `""` when there is nothing: faster-whisper treats the
        empty string as a prompt and the absence as no prompt at all.
        """
        parts = [
            part for part in (self._config.initial_prompt, ", ".join(boost)) if part
        ]
        return " ".join(parts) or None

    def _require_model(self, verb: str) -> Any:
        if self._model is None:
            raise RuntimeError(
                f"{verb}() was called before load(); the daemon loads the model "
                "once at start (§6.1)"
            )
        return self._model
