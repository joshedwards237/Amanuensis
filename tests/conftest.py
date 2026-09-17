"""Shared fixtures for the Phase 1 suite.

Two things are shared, and both exist because Phase 1 is the first phase whose
tests touch artefacts that are deliberately not in the repository.

**The desk-mic corpus is gitignored** (`tests/fixtures/asr/*.wav`) — a voice
recording in a public repository cannot be unpublished. So any test that needs
real speech skips rather than fails on a fresh clone, and says why. A test that
errored on a missing corpus would make a clean checkout look broken.

**Model weights are a download**, and Phase 1's whole G3 claim is that the
runtime never fetches them. Tests that need a real model therefore skip when
the local cache is cold, rather than warming it — a test suite that silently
downloads 75 MB is exactly the behaviour this project is trying to prove it
does not have.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

CORPUS_DIR = Path(__file__).parent / "fixtures" / "asr"


def corpus_wavs() -> list[Path]:
    return sorted(CORPUS_DIR.glob("*.wav"))


def read_wav(path: Path) -> tuple[NDArray[np.float32], int]:
    """Read a 16-bit PCM WAV as the float32 mono array the pipeline uses.

    The pipeline never reads files — `AudioCapture` hands over an array
    already. This exists so tests can feed real speech through the same shape
    the microphone produces.
    """
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
        channels = handle.getnchannels()
    # 32767, matching what every writer in this project uses
    # (storage/history.py, record_phase3_corpus.py, record_spontaneous.py).
    # Reading back at 32768 applied a systematic 3.05e-5 gain error to every
    # sample — half a least-significant bit, and small, but it meant no
    # round-trip through stored audio was exact even in principle.
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return np.ascontiguousarray(samples, dtype=np.float32), rate


requires_corpus = pytest.mark.skipif(
    not corpus_wavs(),
    reason=(
        "no desk-mic corpus — tests/fixtures/asr/*.wav is gitignored by design "
        "(a voice recording in a public repo cannot be unpublished). Re-record "
        "per the instructions in .gitignore."
    ),
)


@pytest.fixture
def speech() -> tuple[NDArray[np.float32], int]:
    """One real utterance from the corpus. Skips when there is no corpus."""
    wavs = corpus_wavs()
    if not wavs:
        pytest.skip("no desk-mic corpus; see .gitignore")
    return read_wav(wavs[0])


@pytest.fixture
def speech_reference() -> str:
    """The verbatim transcript of whatever `speech` returned.

    Paired with `speech` through the same sort order rather than through a
    hardcoded filename: the corpus is re-recorded per machine (`.gitignore`),
    and a test pinned to `01-natural` would compare one machine's audio against
    another machine's reference the moment someone renamed a sample.
    """
    wavs = corpus_wavs()
    if not wavs:
        pytest.skip("no desk-mic corpus; see .gitignore")
    return wavs[0].with_suffix(".txt").read_text(encoding="utf-8").strip()


@pytest.fixture
def silence() -> NDArray[np.float32]:
    """Three seconds of digital silence at 16 kHz."""
    return np.zeros(48_000, dtype=np.float32)


def pad_with_silence(
    audio: NDArray[np.float32], sample_rate: int, seconds: float
) -> NDArray[np.float32]:
    """Bracket an utterance with silence, the way a real hotkey press does.

    A user presses, pauses, speaks, pauses, releases. PRD §7.4: Whisper's
    encoder pads to a 30-second window regardless, so that leading and trailing
    dead air costs nearly a full utterance's worth of decode time if it is not
    trimmed off first.
    """
    pad = np.zeros(int(sample_rate * seconds), dtype=np.float32)
    return np.concatenate([pad, audio, pad]).astype(np.float32)


@pytest.fixture(autouse=True)
def _isolate_user_data(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point every test at a throwaway config and data directory.

    **Added 2026-08-08 after the suite printed the operator's real
    transcripts.** `manu history` began working in Phase 3, and a pre-existing
    test that called `main(["history"])` to assert the verb refused now listed
    live rows out of `~/Library/Application Support/amanuensis/history.db`.

    The read was the visible half. The unacceptable half is that the same phase
    ships `manu history --purge`, so a test one flag away from that one would
    have deleted the operator's transcripts — the artefact §8 exists to
    preserve — with no test asserting anything about it.

    `autouse` rather than opt-in, deliberately. A fixture each test must
    remember is a fixture one test forgets, and the failure is silent until it
    is catastrophic. The two environment variables are the documented override
    (§5.3, §7.3's portability floor), so this uses the product's own mechanism
    rather than patching a path resolver.
    """
    base = tmp_path_factory.mktemp("amanuensis-isolated")
    monkeypatch.setenv("AMANUENSIS_CONFIG_DIR", str(base / "config"))
    monkeypatch.setenv("AMANUENSIS_DATA_DIR", str(base / "data"))
    return base


class MicrophoneOpenedInTestError(RuntimeError):
    """A test reached the real audio device. See `_no_real_microphone`."""


@pytest.fixture(autouse=True)
def _no_real_microphone(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test opens the operator's microphone. Ever.

    **This exists because one did, on 2026-09-02, twice, for thirteen minutes.**
    `test_the_daemon_refuses_a_mode_it_does_not_implement` passed
    `mode="toggle"` and asserted the daemon refused it as unbuilt. Phase 4 built
    `toggle`. The refusal the test depended on went away and the test did not
    fail — `_daemon` ran on, loaded the model, opened the microphone and blocked
    in the AppKit run loop inside pytest, leaving a second status item in the
    operator's menu bar. He noticed it; the suite did not.

    This is the same species as the 2026-08-08 failure that produced
    `_isolate_user_data` above — a test reaching a real resource because nothing
    structurally stopped it — and the same answer: `autouse`, not opt-in. A
    guard each test must remember is a guard one test forgets, and the forgetting
    is silent until it is not.

    The seam is `AudioCapture._sounddevice`, the same one the capture tests
    already replace. A test that genuinely wants a fake device replaces it
    itself and this fixture never fires; a test that reaches for the real one
    gets an error naming the reason rather than a live microphone.
    """
    from amanuensis.audio import capture as capture_module

    def _refuse() -> object:
        raise MicrophoneOpenedInTestError(
            "a test reached the real audio device. Replace "
            "`amanuensis.audio.capture._sounddevice` with a fake, or use the "
            "`capture` fixtures. See tests/conftest.py::_no_real_microphone — "
            "this guard exists because a test once held the operator's "
            "microphone open for thirteen minutes."
        )

    monkeypatch.setattr(capture_module, "_sounddevice", _refuse)


class RealAccessibilityBridgeReached(RuntimeError):
    """A test reached the real Accessibility bridge. See `_no_real_ax_prompt`."""


@pytest.fixture(autouse=True)
def _no_real_ax_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test raises a macOS permission dialog. Ever.

    `AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})` is the
    call that puts this process in the Accessibility pane, and the way it does
    that is by presenting a **modal system dialog**. On a machine that has
    already granted the permission — which is every machine this has been
    developed on — the call returns True and shows nothing, so the hazard is
    invisible exactly where the suite is usually run. On a fresh contributor's
    machine the same test puts a dialog on their screen, and a modal dialog
    does not fail the run, it **blocks** it.

    Same species and same answer as `_no_real_microphone` above: autouse, not
    opt-in. A test that wants the bridge replaces this seam with its own fake,
    which is what `tests/test_injection.py` and the CLI permission test do.
    """
    from amanuensis.injection import macos as macos_injection

    def _refuse() -> object:
        raise RealAccessibilityBridgeReached(
            "a test reached the real HIServices bridge. Patch "
            "`amanuensis.injection.macos._hiservices` — see "
            "tests/conftest.py::_no_real_ax_prompt. Left unpatched this raises "
            "a modal permission dialog on any machine without the grant."
        )

    monkeypatch.setattr(macos_injection, "_hiservices", _refuse)


class RealIOKitBridgeReached(RuntimeError):
    """A test reached the real IOKit bridge. See `_no_real_hid_prompt`."""


@pytest.fixture(autouse=True)
def _no_real_hid_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Input Monitoring half of `_no_real_ax_prompt`, added 2026-09-17.

    `IOHIDRequestAccess` replaced `CGRequestListenEventAccess` on that date and
    inherits the hazard the fixture above exists for: it presents a modal system
    dialog on a machine that has not granted Input Monitoring, and returns
    quietly on one that has. Every machine this is developed on has.

    It was **not** added at the same time as its sibling, and the gap was not
    theoretical — the first full run after the replacement called the real
    symbol through `tests/test_cli.py`'s permission test, which had patched the
    Quartz seam and could not know about a seam that did not exist when it was
    written. Guarding one bridge and not the other is the shape this repository
    keeps producing: the fix closed the path the review named and left its
    sibling open.
    """
    from amanuensis.hotkey import macos as macos_hotkey

    def _refuse() -> object:
        raise RealIOKitBridgeReached(
            "a test reached the real IOKit bridge. Patch "
            "`amanuensis.hotkey.macos._iokit_request_access` — see "
            "tests/conftest.py::_no_real_hid_prompt. Left unpatched this raises "
            "a modal permission dialog on any machine without the grant."
        )

    monkeypatch.setattr(macos_hotkey, "_iokit_request_access", _refuse)
