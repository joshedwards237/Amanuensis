#!/usr/bin/env python3
"""Record a corpus of spontaneous, unscripted speech — with the silence left in.

Two gaps, one session
---------------------
The existing corpus (`tests/fixtures/asr/`) was **read from a script and
tightly cropped**, and both of those turn out to matter.

**It contains no disfluencies.** PRD §9's Phase 5 is `UNRESOLVED,
corpus-blocked` for exactly this reason: four post-processing approaches were
measured against it and none improved WER, which is inconclusive rather than
negative, because a corpus with nothing to clean up cannot show a cleaner
working. The blocking question is stated in the PRD as a question — **do
disfluencies survive the decoder at all?** — and nothing on disk can answer it.

**It contains no dead air.** It was cut with `ffmpeg -t`, so there is nothing
for the trimmer to remove: over the whole corpus, trimming removed 9% and cost
30 ms p50, close to net-negative (Phase 1 gate, finding 9). §7.4 calls trimming
the dominant latency lever and that claim is currently unmeasurable on the data
this project has. A real hotkey press is *press, pause, speak, pause, release*,
and `manu transcribe` trimmed one 9.9 s capture to 2.0 s — an order of
magnitude away from what the corpus shows.

So every take here is padded with real silence at both ends, on purpose. The
padded file measures trimming; the same file measures disfluency. Nothing is
cropped, because cropping is the thing that destroyed the last corpus's ability
to answer this.

**No reference transcripts are needed.** Neither question is a WER question.
Disfluency is measured by presence — does "um" reach the transcript — and
trimming by latency. That is why this script does not ask you to write down
what you said, and why you must not try to say anything in particular.

It also fixes a third thing quietly: four short takes, because PRD §2 defines
G1 against a **ten-second** utterance and the existing corpus averages 18.6 s.

Recording through the product
-----------------------------
Capture goes through `amanuensis.audio.capture.AudioCapture`, not `ffmpeg`. The
corpus is then recorded by the same code path that will record real dictation —
same device resolution, same 16 kHz mono float32 — so a corpus artefact caused
by the capture layer shows up here rather than being introduced later and
blamed on the engine.

Privacy
-------
`.wav` files are gitignored and are never committed. This is a public
repository and a voice recording cannot be unpublished.

Usage
-----
    .venv/bin/python scripts/record_spontaneous.py           # all takes
    .venv/bin/python scripts/record_spontaneous.py --take 5  # redo just take 5
    .venv/bin/python scripts/record_spontaneous.py --list    # read the prompts first
"""

from __future__ import annotations

import argparse
import sys
import time
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

DEFAULT_OUT = REPO_ROOT / "tests" / "fixtures" / "spontaneous"

#: Seconds of deliberate silence before and after every take. Not padding added
#: in software — real room tone, recorded. Software silence is digitally zero
#: and Silero treats it differently from a quiet room.
LEAD_SILENCE_S = 3.0
TAIL_SILENCE_S = 3.0

#: A take is kept only if the speech window is clearly louder than the silence
#: windows. Deterministic, and checked before the take is written rather than
#: after the whole session — the invariant is "you spoke, and you were quiet at
#: the ends", and both halves are checkable.
MIN_SPEECH_TO_SILENCE_RATIO = 4.0
CLIPPING_PEAK = 0.99


@dataclass(frozen=True)
class Take:
    slug: str
    speak_seconds: float
    prompt: str
    why: str


#: The prompts are the whole design. A prompt you can prepare an answer to
#: produces fluent speech, which is precisely the corpus that already exists and
#: cannot answer the question. Every one of these requires thinking *during* the
#: sentence — recalling, deciding, or arguing a position you do not hold — which
#: is where restarts, filled pauses and self-corrections actually come from.
TAKES: tuple[Take, ...] = (
    Take(
        "01-worst-thing",
        10,
        "What is the single worst thing about this codebase right now? "
        "Start talking before you have decided what it is.",
        "forces the decision to happen mid-sentence",
    ),
    Take(
        "02-room",
        10,
        "Describe the room you are in. Close your eyes first and do it from "
        "memory.",
        "recall from a visual memory, which stalls in a different way",
    ),
    Take(
        "03-dinner",
        10,
        "What did you eat last night, and was it any good? Include how it was "
        "cooked.",
        "low stakes, no technical vocabulary, nothing to prepare",
    ),
    Take(
        "04-explain-gate",
        10,
        "Explain what a phase gate is to someone who has never written "
        "software.",
        "translating a known idea for an unknown audience, live",
    ),
    Take(
        "05-vad-guard",
        25,
        "From memory and without looking at anything: how does the VAD "
        "fallback guard work, and why is it there?",
        "technical recall under a no-notes constraint",
    ),
    Take(
        "06-undecided",
        25,
        "Talk through a decision you have NOT made yet — work or otherwise. "
        "Reason it out loud. Do not summarise a conclusion you already hold.",
        "the reasoning is genuinely happening, so the speech is genuinely unplanned",
    ),
    Take(
        "07-last-session",
        25,
        "Recall your last work session in order. What did you do first, then "
        "what, then what.",
        "sequential recall produces backtracking and repair",
    ),
    Take(
        "08-steel-man",
        25,
        "Argue AGAINST a decision in this project that you actually agree "
        "with. Build the other side live.",
        "constructing an argument you do not believe is maximally disfluent",
    ),
    Take(
        "09-bug",
        25,
        "Describe a bug that took you far too long, and what it actually "
        "turned out to be.",
        "narrative recall with a punchline you have to reach for",
    ),
    Take(
        "10-hardest-part",
        25,
        "What is the hardest unsolved part of this project? Do not prepare "
        "the answer.",
        "open-ended and unanswerable in one clean sentence",
    ),
)

RULES = """\
FIVE RULES. The corpus is worthless if these are broken.

  1. DO NOT PREPARE. Start speaking before you know how the sentence ends.
     A prepared answer is fluent, and fluent speech is the corpus that
     already exists and cannot answer the question.

  2. DO NOT REDO A TAKE BECAUSE YOU STUMBLED. The stumble is the data.
     "um", "uh", false starts, "I mean", "sorry, actually" — every one of
     those is the thing being measured. A clean take is a failed take.

  3. DO NOT READ ANYTHING. Not the prompt, not notes, not the screen.
     Read the prompt, look away, then start.

  4. STAY IN THE TAKE IF YOU GO QUIET. A three-second pause mid-thought is
     signal, not a mistake. Do not fill it deliberately either — just let
     it happen.

  5. BE QUIET DURING THE SILENCE WINDOWS. Three seconds before and after,
     no typing, no chair, no throat-clearing. That silence is what the
     trimming measurement is made of, and it is the half the existing
     corpus does not have.

None of this needs to be interesting, correct, or well-argued.
Nobody will read a transcript. The .wav files are gitignored and are
never committed.
"""


def rms(audio: NDArray[np.float32]) -> float:
    if len(audio) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))


@dataclass
class Verdict:
    ok: bool
    problems: list[str]
    speech_rms: float
    silence_rms: float
    peak: float


def inspect_take(
    audio: NDArray[np.float32], sample_rate: int, speak_seconds: float
) -> Verdict:
    """Check the take before it is written, against what the take is for.

    Two things can go wrong and neither is visible by listening once: you were
    not actually quiet at the ends (which makes the trimming measurement
    meaningless) or the mic was too hot (which changes what the detector sees).
    Both are arithmetic, so both are checked here rather than discovered during
    analysis.
    """
    lead = int(LEAD_SILENCE_S * sample_rate)
    tail = int(TAIL_SILENCE_S * sample_rate)
    padded = len(audio) > lead + tail
    silence = np.concatenate([audio[:lead], audio[-tail:]]) if padded else audio
    speech = audio[lead:-tail] if padded else audio

    speech_rms, silence_rms = rms(speech), rms(silence)
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0

    problems: list[str] = []
    if speech_rms < 1e-4:
        problems.append("no speech detected at all — was the right mic selected?")
    elif silence_rms > 0 and speech_rms / silence_rms < MIN_SPEECH_TO_SILENCE_RATIO:
        problems.append(
            f"the silence windows are not quiet enough "
            f"(speech is only {speech_rms / silence_rms:.1f}x the room tone; "
            f"needs {MIN_SPEECH_TO_SILENCE_RATIO:.0f}x). Background noise or "
            f"you started early / ran over."
        )
    if peak >= CLIPPING_PEAK:
        problems.append(f"clipping (peak {peak:.3f}) — move back or lower input gain")

    expected = LEAD_SILENCE_S + speak_seconds + TAIL_SILENCE_S
    actual = len(audio) / sample_rate
    if abs(actual - expected) > 1.5:
        problems.append(f"length {actual:.1f}s, expected about {expected:.1f}s")

    return Verdict(not problems, problems, speech_rms, silence_rms, peak)


def write_wav(path: Path, audio: NDArray[np.float32], sample_rate: int) -> None:
    """16 kHz mono 16-bit PCM — the format the rest of the pipeline reads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(audio, -1.0, 1.0)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes((clipped * 32767.0).astype("<i2").tobytes())


def countdown(label: str, seconds: float) -> None:
    """A visible clock, because the timing is the user's job to hit."""
    end = time.monotonic() + seconds
    while True:
        remaining = end - time.monotonic()
        if remaining <= 0:
            break
        print(f"\r  {label}  {remaining:4.1f}s ", end="", flush=True)
        time.sleep(min(0.1, remaining))
    print(f"\r  {label}  done      ", flush=True)


def record_take(take: Take, capture: object, sample_rate: int) -> NDArray[np.float32]:
    """Record one take, narrating the silence-speak-silence structure live."""
    print()
    print(f"  PROMPT: {take.prompt}")
    print(f"  ({take.why})")
    print()
    input("  Read it, look away, then press Enter. Recording starts immediately. ")

    capture.start()  # type: ignore[attr-defined]
    try:
        countdown("SILENCE — say nothing ", LEAD_SILENCE_S)
        print()
        print("  >>> SPEAK NOW <<<")
        countdown("speaking             ", take.speak_seconds)
        print()
        print("  >>> STOP — go quiet, do not move <<<")
        countdown("SILENCE — say nothing ", TAIL_SILENCE_S)
    finally:
        audio = capture.stop()  # type: ignore[attr-defined]
    return audio


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="record_spontaneous.py",
        description=(
            "Record spontaneous unscripted speech with the silence left in, to "
            "unblock PRD §9's Phase 5 and to make §7.4's trimming claim "
            "measurable. No reference transcripts needed."
        ),
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--take", type=int, action="append", default=None, metavar="N",
        help="record only take N (1-based). Repeatable. Use to redo one.",
    )
    parser.add_argument(
        "--list", action="store_true", help="print the prompts and exit"
    )
    parser.add_argument("--device", default=None, help="microphone name substring")
    args = parser.parse_args(argv)

    if args.list:
        print(RULES)
        for index, take in enumerate(TAKES, start=1):
            print(f"{index:2d}. [{take.speak_seconds:.0f}s] {take.prompt}")
        return 0

    import dataclasses

    from amanuensis.audio.capture import AudioCapture, DeviceNotFoundError
    from amanuensis.config import load_config

    config = load_config()
    audio_config = config.audio
    if args.device:
        audio_config = dataclasses.replace(audio_config, device=args.device)

    capture = AudioCapture(audio_config)
    try:
        device = capture.resolve_device()
    except DeviceNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    selected = TAKES if not args.take else [TAKES[n - 1] for n in args.take]
    speaking = sum(t.speak_seconds for t in selected)
    overhead = len(selected) * (LEAD_SILENCE_S + TAIL_SILENCE_S)

    print("=" * 70)
    print("SPONTANEOUS SPEECH CORPUS")
    print("=" * 70)
    print()
    print(RULES)
    print(f"  {len(selected)} takes — {speaking:.0f}s of speaking, "
          f"{overhead:.0f}s of silence, plus however long you take between them.")
    print(f"  Microphone: {'system default' if device is None else f'index {device}'}"
          f"   Writing to: {args.out}")
    print()
    input("  Press Enter when the room is quiet and you are ready. ")

    kept: list[str] = []
    for index, take in enumerate(selected, start=1):
        while True:
            print()
            print("-" * 70)
            print(f"TAKE {index}/{len(selected)} — {take.slug}")
            audio = record_take(take, capture, audio_config.sample_rate)
            verdict = inspect_take(audio, audio_config.sample_rate, take.speak_seconds)

            print()
            print(f"  {len(audio) / audio_config.sample_rate:.1f}s   "
                  f"speech RMS {verdict.speech_rms:.4f}   "
                  f"silence RMS {verdict.silence_rms:.4f}   "
                  f"peak {verdict.peak:.3f}")
            for problem in verdict.problems:
                print(f"  ⚠️  {problem}")

            if verdict.ok:
                print("  Looks good.")
            choice = input(
                "  [Enter] keep   [r] redo   [s] skip this take: "
            ).strip().lower()
            if choice == "r":
                continue
            if choice == "s":
                break

            path = args.out / f"{take.slug}.wav"
            write_wav(path, audio, audio_config.sample_rate)
            kept.append(path.name)
            print(f"  wrote {path}")
            break

    print()
    print("=" * 70)
    print(f"{len(kept)} takes written to {args.out}")
    for name in kept:
        print(f"  {name}")
    print()
    print("These are gitignored and will not be committed.")
    print("Next: the analysis reads them from that directory — nothing to do")
    print("but say they exist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
