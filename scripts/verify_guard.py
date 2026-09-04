"""§9's verification for the collapse guard, on real audio. Both directions.

    python scripts/verify_guard.py

Needs the desk-mic corpus (`tests/fixtures/asr/*.wav`), which is gitignored —
a voice recording in a public repository cannot be unpublished. Skips with a
message rather than failing on a fresh clone.

**Two controls, and the negative one is the one that can actually fail.**

*Positive* — the guard must fire on a real collapse. `initial_prompt = "And how
much is this?"` reduces `03-proper-nouns` to a transcript that is the prompt
echoed back, deterministically. This is what the 2026-08-03 record described as
a "prose prompt" collapse; the reproduction shows the mechanism is narrower and
more interesting than that. The decoder **echoes the prompt and terminates** —
early termination, not domain drift, which is the open question dictionary
objection O3 posed and could not answer from a rate floor.

*Negative* — the guard must not fire on genuine speech, at any length. This is
the half that matters, because a false refusal costs the user words they said.
Six samples from one speaker cannot prove it; §9 labels the false-positive
direction untested for that reason and this script is not what changes it.

The first run of this verification used an invented prompt, fired nothing, and
would have been reported as a pass. A positive control that cannot fail is the
same instrument failure this repository has recorded three times.
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

from amanuensis.audio.vad import VoiceActivityDetector
from amanuensis.config import EngineConfig, GuardConfig, VadConfig
from amanuensis.engines.faster_whisper import FasterWhisperEngine
from amanuensis.guard import evaluate

CORPUS = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "asr"

#: Measured 2026-08-07 to collapse `03-proper-nouns` to 8.3% coverage. The
#: transcript it produces is this string, verbatim — the decoder emits the
#: prompt and stops.
COLLAPSING_PROMPT = "And how much is this?"

_EXIT_OK = 0
_EXIT_FAILED = 1
_EXIT_SKIPPED = 2


def read_wav(path: Path) -> tuple[np.ndarray, int]:
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


def sweep(prompt: str, label: str) -> list[tuple[str, float, str, str]]:
    engine = FasterWhisperEngine(EngineConfig(initial_prompt=prompt))
    engine.load()
    detector = VoiceActivityDetector(VadConfig())
    detector.load()
    settings = GuardConfig()

    rows: list[tuple[str, float, str, str]] = []
    for wav in sorted(CORPUS.glob("*.wav")):
        audio, rate = read_wav(wav)
        trimmed = detector.trim(audio, rate)
        decoded = engine.transcribe(trimmed.audio, rate)
        verdict = evaluate(
            decoded.text,
            decoded_seconds=decoded.decoded_seconds,
            retained_seconds=trimmed.retained_seconds,
            padding_seconds=trimmed.padding_seconds,
            fell_back=trimmed.fell_back,
            config=settings,
        )
        rows.append(
            (
                wav.stem,
                verdict.coverage if verdict.coverage is not None else float("nan"),
                str(verdict.outcome),
                decoded.text.strip()[:44],
            )
        )

    print(f"\n=== {label} ===")
    print(f"{'sample':<18}{'coverage':>10}  {'outcome':<9} transcript")
    for name, coverage, outcome, text in rows:
        mark = "  <-- FIRED" if outcome == "failed" else ""
        print(f"{name:<18}{coverage:>9.1%}  {outcome:<9} {text!r}{mark}")
    return rows


def main() -> int:
    if not CORPUS.is_dir() or not any(CORPUS.glob("*.wav")):
        print(f"the desk-mic corpus is not present at {CORPUS} — nothing to verify.")
        print("it is gitignored by design; see tests/conftest.py.")
        return _EXIT_SKIPPED

    genuine = sweep("", "NEGATIVE CONTROL — no prompt, genuine speech")
    collapsed = sweep(COLLAPSING_PROMPT, f"POSITIVE CONTROL — {COLLAPSING_PROMPT!r}")

    false_positives = [row for row in genuine if row[2] == "failed"]
    caught = [row for row in collapsed if row[2] == "failed"]
    floor = min(row[1] for row in genuine)

    print("\n=== VERDICT ===")
    print(f"genuine speech, lowest coverage seen : {floor:.1%}")
    refused = f"{len(false_positives)} of {len(genuine)}"
    print(f"genuine speech falsely refused       : {refused}")
    print(f"collapses caught                     : {len(caught)}")

    if false_positives:
        print("\nFAIL — the guard refused genuine speech:")
        for name, coverage, _outcome, text in false_positives:
            print(f"  {name}: {coverage:.1%}  {text!r}")
        return _EXIT_FAILED
    if not caught:
        # A positive control that catches nothing has not shown the guard
        # works; it has shown the control does not reproduce the failure.
        print("\nFAIL — the positive control did not reproduce a collapse.")
        print("the guard is unverified in the direction it exists for.")
        return _EXIT_FAILED

    print("\nPASS — fires on the collapse, silent on all genuine samples.")
    print("the false-positive direction remains one speaker; §9 says so.")
    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
