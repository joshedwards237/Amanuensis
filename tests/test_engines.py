"""The faster-whisper engine: lifecycle, model resolution, and G3.

Three groups of tests, in the order they matter.

**G3 first.** Goal G3 says no network at runtime, and PRD §7.6 is specific
about the mechanism: weights download once at install and are resolved from a
local path thereafter — never a repository ID. The Phase 1 gate verifies this
by packet capture, but a packet capture is an *observation* of one run. These
tests are the structural half: the engine asks for weights with
`local_files_only`, so a cold cache raises an actionable error instead of
quietly reaching for the network. An engine that fetched on a cache miss would
pass a packet capture on every machine where the cache happened to be warm.

**Lifecycle second.** `load` / `warm_up` / `is_loaded` exist because the daemon
holds the model resident (§6.1) — a per-invocation load costs 3–8 seconds and
there is no version of that which is acceptable. `is_loaded` in particular is
what lets the tray tell *transcribing* apart from *not ready*, two states that
look identical to a user and mean opposite things.

**Model selection third**, and only the parts §7.2 actually measured. The
`auto` row for macOS is `tiny.en`; the CUDA rows are labelled unmeasured
estimates in the PRD and are treated here as what they are.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pytest
from numpy.typing import NDArray

from amanuensis.config import EngineConfig
from amanuensis.engines.base import TranscriptionEngine
from amanuensis.engines.faster_whisper import (
    PINNED_DIGESTS,
    PINNED_REVISIONS,
    FasterWhisperEngine,
    ModelNotAvailableError,
    WeightsDigestError,
    resolve_device,
    resolve_model_name,
    resolve_model_path,
    verify_weights,
)
from conftest import requires_corpus


class _FakeSegment:
    #: Where the fake decoder claims to have stopped. Named so §5.7's test can
    #: assert against it without restating the number.
    END = 0.9

    def __init__(self, text: str, start: float = 0.0, end: float | None = None) -> None:
        self.text = text
        self.start = start
        self.end = _FakeSegment.END if end is None else end


class _FakeWhisperModel:
    """Records how it was constructed, so the tests can assert on §7.2's params."""

    instances: ClassVar[list[_FakeWhisperModel]] = []

    def __init__(self, model_path: str, **kwargs: Any) -> None:
        self.model_path = model_path
        self.kwargs = kwargs
        self.transcribe_calls: list[dict[str, Any]] = []
        _FakeWhisperModel.instances.append(self)

    #: Overridable per test, so the empty-decode case does not need its own fake.
    segments: ClassVar[list[_FakeSegment] | None] = None

    def transcribe(self, audio: object, **kwargs: Any) -> tuple[object, object]:
        self.transcribe_calls.append(kwargs)
        produced = _FakeWhisperModel.segments
        if produced is None:
            produced = [_FakeSegment(" hello world")]
        return iter(produced), object()


@pytest.fixture
def fake_whisper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> type:
    _FakeWhisperModel.instances = []
    _FakeWhisperModel.segments = None
    monkeypatch.setattr(
        "amanuensis.engines.faster_whisper._whisper_model_class",
        lambda: _FakeWhisperModel,
    )
    monkeypatch.setattr(
        "amanuensis.engines.faster_whisper.resolve_model_path",
        lambda model, cache_dir=None: tmp_path / "weights",
    )
    return _FakeWhisperModel


def _engine(**overrides: object) -> FasterWhisperEngine:
    return FasterWhisperEngine(EngineConfig(**overrides))  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# G3 — weights come from disk, or the call fails loudly
# --------------------------------------------------------------------------


def test_a_cold_cache_raises_instead_of_downloading(tmp_path: Path) -> None:
    """The structural half of G3.

    `local_files_only` is the whole mechanism: with a cold cache the resolver
    has no way to succeed, so there is no code path in which the runtime
    fetches. The alternative — resolve lazily and let faster-whisper download —
    would look identical on any machine whose cache was already warm, which is
    every machine a developer tests on.
    """
    with pytest.raises(ModelNotAvailableError) as exc:
        resolve_model_path("tiny.en", cache_dir=tmp_path)

    message = str(exc.value)
    assert "tiny.en" in message
    assert "manu install" in message


def test_a_model_given_as_a_directory_is_used_as_is(tmp_path: Path) -> None:
    """Packagers and offline installs point `[engine] model` at a directory.
    §7.6's "resolved from a local path" has to accept the plain case."""
    weights = tmp_path / "my-model"
    weights.mkdir()

    assert resolve_model_path(str(weights)) == weights


def test_load_hands_the_engine_a_path_not_a_repository_id(
    fake_whisper: type, tmp_path: Path
) -> None:
    engine = _engine()

    engine.load()

    constructed = _FakeWhisperModel.instances[0]
    assert constructed.model_path == str(tmp_path / "weights")
    assert "/" not in Path(constructed.model_path).name  # not "Systran/..."


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------


def test_an_engine_is_not_loaded_before_load_is_called() -> None:
    assert _engine().is_loaded is False


def test_transcribing_before_load_is_a_programming_error(
    silence: NDArray[np.float32],
) -> None:
    """Not a silent empty string. A caller that skipped `load` has a bug, and
    returning "" would present it as the user having said nothing."""
    with pytest.raises(RuntimeError) as exc:
        _engine().transcribe(silence, 16_000)

    assert "load" in str(exc.value)


def test_load_is_idempotent(fake_whisper: type) -> None:
    """§6.3 says so explicitly. The daemon may re-enter start-up after an error
    and must not end up holding two copies of the weights in memory."""
    engine = _engine()

    engine.load()
    engine.load()

    assert len(_FakeWhisperModel.instances) == 1
    assert engine.is_loaded is True


def test_warm_up_runs_an_inference_and_discards_it(fake_whisper: type) -> None:
    engine = _engine()
    engine.load()

    engine.warm_up()

    assert len(_FakeWhisperModel.instances[0].transcribe_calls) == 1


def test_warm_up_before_load_is_a_programming_error() -> None:
    with pytest.raises(RuntimeError):
        _engine().warm_up()


def test_the_engine_satisfies_the_abc() -> None:
    assert issubclass(FasterWhisperEngine, TranscriptionEngine)


# --------------------------------------------------------------------------
# Decoding parameters — each one is a PRD citation, not a preference
# --------------------------------------------------------------------------


def test_the_engine_does_not_run_its_own_vad(
    fake_whisper: type, silence: NDArray[np.float32]
) -> None:
    """Trimming lives in `audio/vad.py`, once, for every engine.

    faster-whisper has a `vad_filter` of its own and using it would be the
    shorter path. It is not taken, because PRD §9 requires Moonshine be
    benchmarked against this engine and Moonshine has no such flag — a
    comparison where one engine silently trims and the other does not measures
    the trimmer, not the engines.
    """
    engine = _engine()
    engine.load()

    engine.transcribe(silence, 16_000)

    assert _FakeWhisperModel.instances[0].transcribe_calls[0].get("vad_filter") is False


def test_the_configured_language_reaches_the_decoder(fake_whisper: type) -> None:
    engine = _engine(language="en")
    engine.load()

    engine.transcribe(np.zeros(16_000, dtype=np.float32), 16_000)

    assert _FakeWhisperModel.instances[0].transcribe_calls[0]["language"] == "en"


def test_cpu_threads_auto_is_resolved_and_never_left_at_the_library_default(
    fake_whisper: type,
) -> None:
    """PRD §7.2: CTranslate2 defaults to 4 threads and that default measured
    1.8× slower. The first run of the pre-Phase-0 probe returned NO-GO on it."""
    engine = _engine(cpu_threads="auto")

    engine.load()

    threads = _FakeWhisperModel.instances[0].kwargs["cpu_threads"]
    assert isinstance(threads, int)
    assert threads >= 1


def test_an_explicit_thread_count_is_passed_through(fake_whisper: type) -> None:
    engine = _engine(cpu_threads=6)

    engine.load()

    assert _FakeWhisperModel.instances[0].kwargs["cpu_threads"] == 6


def test_int8_is_the_compute_type_for_every_cpu_row(fake_whisper: type) -> None:
    engine = _engine()

    engine.load()

    assert _FakeWhisperModel.instances[0].kwargs["compute_type"] == "int8"


# --------------------------------------------------------------------------
# Model and device selection
# --------------------------------------------------------------------------


def test_auto_on_cpu_resolves_to_the_model_7_2_measured() -> None:
    """`tiny.en`, replacing `base.en` on 2026-07-31 (objection A3). It is the
    only candidate meeting both halves of G1 with VAD on."""
    assert resolve_model_name("auto", device="cpu") == "tiny.en"


def test_an_explicit_model_wins_over_the_auto_table() -> None:
    assert resolve_model_name("small.en", device="cpu") == "small.en"


def test_mps_is_not_a_device_because_ctranslate2_has_no_metal_backend() -> None:
    """§7.2. "Apple Silicon" and "CPU only" are the same execution path with
    different core counts, which is why the tier table was rewritten around
    what a machine measures rather than what chip it contains."""
    with pytest.raises(ValueError) as exc:
        resolve_device("mps")

    assert "Metal" in str(exc.value)


def test_device_auto_on_a_machine_without_cuda_is_cpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "amanuensis.engines.faster_whisper._cuda_device_count", lambda: 0
    )

    assert resolve_device("auto") == "cpu"


# --------------------------------------------------------------------------
# The real thing — skipped unless the weights are already on disk
# --------------------------------------------------------------------------


def _weights_are_cached() -> bool:
    try:
        resolve_model_path("tiny.en")
    except ModelNotAvailableError:
        return False
    return True


requires_weights = pytest.mark.skipif(
    not _weights_are_cached(),
    reason="tiny.en is not in the local cache; run `manu install` (downloads once)",
)


@requires_weights
@requires_corpus
def test_a_real_utterance_comes_back_as_text(
    speech: tuple[NDArray[np.float32], int], speech_reference: str
) -> None:
    audio, rate = speech
    engine = _engine()
    engine.load()
    engine.warm_up()

    text = engine.transcribe(audio, rate).text

    assert text.strip()
    # A loose overlap check, deliberately. WER belongs to the benchmark and
    # ADR 0001; what this asserts is that the wiring produces *this* utterance
    # rather than plausible text from a mis-fed buffer.
    reference = set(speech_reference.lower().split())
    heard = set(text.lower().split())
    assert len(reference & heard) >= len(reference) // 3, f"heard {text!r}"


@requires_weights
def test_warm_up_on_the_real_model_does_not_hang_on_silence() -> None:
    """The documented failure mode, guarded.

    Whisper's decoder repetition-loops on silence — 541 ms to 6,039 ms on the
    same model and sample (PRD §7.2). A warm-up that fed it a silent buffer
    would pay that on every daemon start, so this asserts the warm-up is bounded
    rather than trusting that it is.
    """
    import time

    engine = _engine()
    engine.load()

    start = time.perf_counter()
    engine.warm_up()
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert elapsed_ms < 3_000.0, f"warm-up took {elapsed_ms:.0f} ms"


# --------------------------------------------------------------------------
# §5.7 — an unbiased decode, and where the decoder stopped
# --------------------------------------------------------------------------


def test_the_configured_prompt_reaches_the_decoder_by_default(
    fake_whisper: type,
) -> None:
    engine = _engine(initial_prompt="spreadsheets, XLSX, Airtable")
    engine.load()

    engine.transcribe(np.zeros(16_000, dtype=np.float32), 16_000)

    call = _FakeWhisperModel.instances[0].transcribe_calls[0]
    assert call["initial_prompt"] == "spreadsheets, XLSX, Airtable"


def test_an_unbiased_decode_suppresses_the_prompt(fake_whisper: type) -> None:
    """§5.7's retry. `beam_size = 1` is greedy, so a retry that left the prompt
    in place would return the same words and recover nothing."""
    engine = _engine(initial_prompt="spreadsheets, XLSX, Airtable")
    engine.load()

    engine.transcribe(np.zeros(16_000, dtype=np.float32), 16_000, biased=False)

    call = _FakeWhisperModel.instances[0].transcribe_calls[0]
    assert call["initial_prompt"] is None


def test_an_unbiased_decode_changes_nothing_else(fake_whisper: type) -> None:
    """Only the bias is dropped. A retry that also changed beam size or the
    VAD flag would be measuring a different pipeline than the one that failed."""
    engine = _engine(initial_prompt="anything", language="en")
    engine.load()

    engine.transcribe(np.zeros(16_000, dtype=np.float32), 16_000)
    engine.transcribe(np.zeros(16_000, dtype=np.float32), 16_000, biased=False)

    biased, unbiased = _FakeWhisperModel.instances[0].transcribe_calls
    assert {k: v for k, v in biased.items() if k != "initial_prompt"} == {
        k: v for k, v in unbiased.items() if k != "initial_prompt"
    }


def test_the_decoded_span_is_reported(fake_whisper: type) -> None:
    """§5.7's primary instrument. The segments were already crossing this
    boundary and being discarded — `_decode` joined the texts and dropped
    `start`, `end`, `avg_logprob`, `no_speech_prob` and `compression_ratio`."""
    engine = _engine()
    engine.load()

    result = engine.transcribe(np.zeros(16_000, dtype=np.float32), 16_000)

    assert result.text == " hello world"
    assert result.decoded_seconds == pytest.approx(_FakeSegment.END)


def test_a_decode_with_no_segments_reports_a_zero_span(fake_whisper: type) -> None:
    """Zero, not `None`. `None` means the engine cannot say; zero means it said
    the decoder produced nothing — and §5.7 treats those oppositely."""
    engine = _engine()
    engine.load()
    _FakeWhisperModel.segments = []

    result = engine.transcribe(np.zeros(16_000, dtype=np.float32), 16_000)

    assert result.text == ""
    assert result.decoded_seconds == 0.0


def test_the_boost_segment_cannot_take_the_shape_that_collapses_a_transcript() -> None:
    """The collapse guard's deferred O6, answered on the half this code owns.

    §5.7's measured trigger is a prompt with **the form of a complete short
    utterance the decoder can plausibly emit as the whole transcript** —
    `initial_prompt = "And how much is this?"` produces exactly that string from
    a 25-second clip, deterministically. A comma-separated term list carries no
    sentence-final punctuation and is structurally not that shape.

    Not a heuristic: a prose *detector* over user-authored `initial_prompt` was
    rejected, because it false-positives on legitimate prompts and §5.7's guard
    catches the failure directly. This constrains a string the engine writes.
    """
    from amanuensis.config import EngineConfig
    from amanuensis.engines.faster_whisper import FasterWhisperEngine

    engine = FasterWhisperEngine(EngineConfig(initial_prompt=""))
    segment = engine._prompt(("Airtable", "Firestore", "XLSX"))

    assert segment == "Airtable, Firestore, XLSX"
    assert not segment.endswith((".", "?", "!"))


def test_prose_framing_comes_before_the_terms() -> None:
    """§5.6's O7: `[boost]` is authoritative and `initial_prompt` is prose
    framing only. Concatenating in that order is what "framing" means."""
    from amanuensis.config import EngineConfig
    from amanuensis.engines.faster_whisper import FasterWhisperEngine

    engine = FasterWhisperEngine(EngineConfig(initial_prompt="Technical dictation."))
    assert engine._prompt(("XLSX",)) == "Technical dictation. XLSX"


def test_no_prompt_and_no_terms_is_none_rather_than_empty() -> None:
    """faster-whisper treats `""` as a prompt and `None` as no prompt at all."""
    from amanuensis.config import EngineConfig
    from amanuensis.engines.faster_whisper import FasterWhisperEngine

    assert FasterWhisperEngine(EngineConfig(initial_prompt=""))._prompt(()) is None


# ---------------------------------------------------------------------------
# Checksum verification — §7.6, objection O8
# ---------------------------------------------------------------------------


def _snapshot(tmp_path: Path, model: str) -> Path:
    """A snapshot with every file present and every file wrong.

    Right shape, wrong bytes — so a verifier that only checks for presence
    passes it and a verifier that hashes does not.
    """
    directory = tmp_path / model
    directory.mkdir()
    for name in PINNED_DIGESTS[model]:
        (directory / name).write_bytes(b"not the real weights")
    return directory


def test_every_pinned_revision_has_a_recorded_digest() -> None:
    """A pin with no digest is a revision nobody verifies (§7.6).

    The two tables are maintained by hand and drift apart silently — this is
    the assertion that notices.
    """
    assert set(PINNED_DIGESTS) == set(PINNED_REVISIONS)
    for model, files in PINNED_DIGESTS.items():
        assert files, f"{model} has an empty digest record"
        assert "model.bin" in files, f"{model} records no digest for the weights"
        for name, digest in files.items():
            assert len(digest) == 64, f"{model}/{name} is not a sha256"
            int(digest, 16)  # raises if it is not hex


def test_tampered_weights_are_refused(tmp_path: Path) -> None:
    """The negative control. Bytes that are not the recorded bytes must fail.

    This is the objection O8 case: for three phases `download_weights` pinned a
    revision and verified nothing, so this test could not have passed and no
    test asked it to.
    """
    directory = _snapshot(tmp_path, "tiny.en")
    with pytest.raises(WeightsDigestError) as exc:
        verify_weights(directory, "tiny.en")
    assert "model.bin" in str(exc.value)


def test_a_missing_file_is_refused_not_skipped(tmp_path: Path) -> None:
    """A digest record that silently ignores an absent file verifies nothing."""
    directory = _snapshot(tmp_path, "tiny.en")
    (directory / "model.bin").unlink()
    with pytest.raises(WeightsDigestError) as exc:
        verify_weights(directory, "tiny.en")
    assert "model.bin" in str(exc.value)


def test_a_model_with_no_recorded_digest_reports_unverified(tmp_path: Path) -> None:
    """The other half of the shape §7.6 is amended to close.

    Moonshine and Parakeet arrive in Phase 4 with no pin and no digest. A check
    that passes for a model it has no record of is a check that cannot fail, so
    the absence is reported rather than treated as success.
    """
    directory = tmp_path / "unpinned"
    directory.mkdir()
    (directory / "model.bin").write_bytes(b"anything at all")
    result = verify_weights(directory, "moonshine/tiny")
    assert result.verified is False
    assert result.files_checked == 0


def test_the_real_cached_weights_verify() -> None:
    """The positive control, against bytes this project actually shipped on.

    Without it the negative control above is passed by a function that refuses
    everything. Skips rather than fails where the cache is cold — the digests
    are the artefact under test, not the download.
    """
    try:
        directory = resolve_model_path("tiny.en")
    except ModelNotAvailableError:
        pytest.skip("no local tiny.en snapshot — run `manu install`")
    result = verify_weights(directory, "tiny.en")
    assert result.verified is True
    assert result.files_checked == len(PINNED_DIGESTS["tiny.en"])
