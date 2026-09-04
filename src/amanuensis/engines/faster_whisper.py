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

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
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
    "PINNED_DIGESTS",
    "PINNED_REVISIONS",
    "FasterWhisperEngine",
    "ModelNotAvailableError",
    "WeightsDigestError",
    "WeightsVerification",
    "resolve_device",
    "resolve_model_name",
    "resolve_model_path",
    "verify_weights",
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

#: SHA-256 per file of each pinned revision, §7.6. Recorded **by this project**
#: from snapshots it holds, which is the entire point: Hugging Face already
#: content-addresses its LFS blobs, so checking a download against the hub's own
#: metadata verifies the hub against itself and catches nothing a compromised or
#: re-pointed hub would do. A digest written down here catches it.
#:
#: For three phases §7.6 claimed "checksum verification" and `download_weights`
#: verified nothing (objection O8) — the sixth instance in this project of a
#: stated constraint the code did not honour. Regenerate with
#: `scripts/record_weight_digests.py` after changing a pin; the two tables are
#: hand-maintained and `test_every_pinned_revision_has_a_recorded_digest`
#: is what notices when they drift apart.
PINNED_DIGESTS: Final[dict[str, dict[str, str]]] = {
    "tiny.en": {
        "config.json":
            "14b1b421a90349bc551b881461426b561a874049cb9e4c4864f2ca384f6a7cc5",
        "model.bin":
            "1a5afae06a4db91c975c9a9d78be5cc110ee4ea022ad57d55492e4550e936b2a",
        "tokenizer.json":
            "929c5252409436dce1b38a75d1abbcb5e132d170d8e324e4e04ed915fa2d22df",
        "vocabulary.txt":
            "ff77588746d3a2595d32ab5b69ffd7b95ce2441ac57533cb66fc3eb575a115cf",
    },
    "base.en": {
        "config.json":
            "f3bc3821e9fc76a27bae538e11ae5b677dcdd352b4600429ce7951d398569aeb",
        "model.bin":
            "2a166925539a16005f14ff328359f9b9adb9dc4fb631bb3b227526862e93e2ef",
        "tokenizer.json":
            "929c5252409436dce1b38a75d1abbcb5e132d170d8e324e4e04ed915fa2d22df",
        "vocabulary.txt":
            "ff77588746d3a2595d32ab5b69ffd7b95ce2441ac57533cb66fc3eb575a115cf",
    },
    "small.en": {
        "config.json":
            "666a9605530ac1f61fa8177f3702b4dacec9966749e42610839fcc32661d5fae",
        "model.bin":
            "62b2a45b05ee59acb4a5341b33ee35e041395d378d418a18acfe4c9e768ee37a",
        "tokenizer.json":
            "929c5252409436dce1b38a75d1abbcb5e132d170d8e324e4e04ed915fa2d22df",
        "vocabulary.txt":
            "ff77588746d3a2595d32ab5b69ffd7b95ce2441ac57533cb66fc3eb575a115cf",
    },
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


class WeightsDigestError(Exception):
    """Downloaded bytes are not the bytes this project recorded (§7.6).

    Raised rather than warned. A digest mismatch on model weights is either a
    corrupted download or a repository serving something other than the pinned
    revision, and there is no version of "carry on with these" that is correct
    for a product whose headline claim is that nothing leaves the machine.
    """


@dataclass(frozen=True)
class WeightsVerification:
    """What `verify_weights` actually checked, so a caller can say so.

    `verified is False` with `files_checked == 0` is the honest report for a
    model this project has no digests for — Moonshine and Parakeet arrive in
    Phase 4 in exactly that state (§7.2). Returning a bare `True` there would be
    a check that cannot fail, which is the shape §7.6 was amended to close.
    """

    model: str
    verified: bool
    files_checked: int


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

    path = Path(
        download_model(
            model,
            local_files_only=False,
            cache_dir=str(cache_dir) if cache_dir is not None else None,
            revision=PINNED_REVISIONS.get(model),
        )
    )
    # Fail closed, here rather than in the caller. A verification the CLI has to
    # remember to call is a verification one code path forgets, and this one
    # guards the only bytes that enter this machine from outside it.
    verify_weights(path, model)
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_weights(path: Path, model: str) -> WeightsVerification:
    """Re-hash a snapshot against `PINNED_DIGESTS` (§7.6, objection O8).

    Raises `WeightsDigestError` naming **every** file that is wrong, not the
    first — a mismatch on one file and a mismatch on all four are different
    events and the message should say which happened.
    """
    expected = PINNED_DIGESTS.get(model)
    if expected is None:
        return WeightsVerification(model=model, verified=False, files_checked=0)

    problems: list[str] = []
    for name, digest in sorted(expected.items()):
        candidate = path / name
        if not candidate.is_file():
            problems.append(f"{name}: missing")
            continue
        try:
            actual = _sha256(candidate)
        except OSError as exc:
            # A file that cannot be read has not been verified, and that is a
            # verification failure rather than an internal error. Without this
            # a `chmod 000` weights file raised PermissionError straight past
            # every caller — found by the stress pass, not by the unit tests.
            problems.append(f"{name}: unreadable ({exc.strerror})")
            continue
        if actual != digest:
            problems.append(f"{name}: expected {digest[:12]}…, got {actual[:12]}…")

    # Files nobody recorded are not inert just because nothing loads them today.
    # `record_weight_digests.py` records every file in a snapshot, so the record
    # is complete by construction and anything extra is an anomaly worth
    # refusing. Dotfiles are exempt: macOS writes `.DS_Store` into any directory
    # the user opens in Finder, and a verification that fails because someone
    # looked at a folder is a verification people learn to bypass.
    if path.is_dir():
        try:
            unexpected = sorted(
                entry.name
                for entry in path.iterdir()
                if entry.name not in expected and not entry.name.startswith(".")
            )
        except OSError as exc:
            problems.append(f"{path}: cannot be listed ({exc.strerror})")
        else:
            problems.extend(
                f"{name}: not in the recorded snapshot" for name in unexpected
            )

    if problems:
        raise WeightsDigestError(
            f"{model} at {path} does not match the digests recorded for its "
            f"pinned revision (§7.6):\n  " + "\n  ".join(problems)
        )
    return WeightsVerification(model=model, verified=True, files_checked=len(expected))


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
