#!/usr/bin/env python3
"""Record the Phase 3 duration corpus — ten long takes and ten short ones.

Why this exists, and what it is not
-----------------------------------
**It is not the Phase 3 gate.** §9's gate is ten *real dictations* through the
daemon, judged on edit rate, with `postprocess_ms` populated and the dictionary
frozen. None of that is possible before the phase ships. This script records
**audio**, and audio answers three questions that do not need the feature and
should not wait for it.

**1. §2's latency model has never met a long utterance.** The measured
relationship is `transcribe_ms ≈ 48.8 + 13.69 × seconds`, fitted across
0.7–43.4 s. It predicts ~909 ms at sixty seconds — over G1's 800 ms p95 — and
the Phase 3 gate will run straight into that prediction. Every sample in
`tests/fixtures/asr/` is under twenty seconds, so the extrapolation has never
been checked against a real recording. A model used to *predict* the cost of
§5.7's retry (`dictation_controller._why_no_retry`) ought to have been.

**2. The collapse guard has no coverage distribution.** Its thresholds come
from six samples: `min_decoded_coverage = 0.5` and `retry_below_coverage = 0.7`,
the latter recorded as "calibrated against ONE short sample". The follow-up gate
record states plainly that the guard's false-positive direction is untested, and
objection O5 established that ten sixty-second dictations *cannot* test it —
the blind spot is at the short end, where the genuine floor of 82.8% came from a
3.2-second clip. So this corpus is deliberately **bimodal**: ten takes well past
sixty seconds and ten well under five. The middle is already covered.

**3. Recording before the dictionary exists is the freeze, for free.**
Dictionary objection O6: the Phase 3 gate measures edit rate, the dictionary
moves edit rate by construction, and entries written against the test set
measure nothing. Audio recorded before `vocabulary.toml` has any entries in it
cannot have been targeted. The timestamps are the evidence, and they are on the
files.

What is deliberately reused
---------------------------
The structure is `record_spontaneous.py`'s and the reasoning behind it is not
repeated here: capture goes through `AudioCapture` rather than `ffmpeg` so a
capture-layer artefact shows up here instead of being blamed on the engine;
every take is padded with **real recorded silence** at both ends rather than
digital zeros, because Silero treats the two differently; and a take is checked
against a speech-to-silence ratio before it is written, so "you spoke, and you
were quiet at the ends" is verified per take rather than discovered at the end
of a session.

The one thing that is not reused is the prompt design. Sustaining unprepared
speech for seventy-five seconds is a different task from filling twenty, and a
prompt that runs dry at forty produces a take with thirty-five seconds of
silence in the middle — which measures the trimmer, not the decoder.

Privacy
-------
`.wav` files are gitignored and never committed. This is a public repository
and a voice recording cannot be unpublished.

Usage
-----
    .venv/bin/python scripts/record_phase3_corpus.py --list
    .venv/bin/python scripts/record_phase3_corpus.py --set long
    .venv/bin/python scripts/record_phase3_corpus.py --set short
    .venv/bin/python scripts/record_phase3_corpus.py --take 3   # redo one
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

#: Printed for any third-party import this script needs and cannot find.
#:
#: The failure mode this exists for is specific and was hit on the first real
#: run. `sys.path.insert` below makes `amanuensis` importable from a source
#: checkout with nothing installed, which is convenient and *also* means the
#: script gets a long way into a session on an interpreter that cannot finish
#: it — the operator read a prompt, pressed Enter twice, and met
#: `ModuleNotFoundError: sounddevice` inside take 1 of 10.
_WRONG_INTERPRETER = """\
error: {missing!r} is not installed for this interpreter.
  You are running: {executable}
  This script puts src/ on sys.path, so `amanuensis` imports even outside the
  virtualenv — which is why it got this far. Run it as:
      .venv/bin/python scripts/record_phase3_corpus.py"""

try:
    import numpy as np
    from numpy.typing import NDArray
except ModuleNotFoundError as exc:  # pragma: no cover — an environment problem
    raise SystemExit(
        _WRONG_INTERPRETER.format(missing=exc.name, executable=sys.executable)
    ) from exc

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

DEFAULT_OUT = REPO_ROOT / "tests" / "fixtures" / "phase3"

#: Real room tone at both ends, not software silence. Longer than the
#: spontaneous corpus's three seconds on the long takes only: a seventy-five
#: second take is one the speaker has to settle into, and a rushed start puts
#: breath in the lead window and fails the ratio check for the wrong reason.
LEAD_SILENCE_S = 3.0
TAIL_SILENCE_S = 3.0

#: Speech RMS over silence RMS. 2.0 is the measured floor from the spontaneous
#: corpus session — room tone alone sits at 0.98x and correctly falls back, and
#: two genuine takes passed at 2.57x. Not re-derived here; if a take between
#: 2.0x and 2.57x ever fails to trim, that record is the one to move.
MIN_SPEECH_TO_SILENCE_RATIO = 2.0
CLIPPING_PEAK = 0.99

#: Seventy-five, not sixty. §9 asks for dictations of >= 60 seconds and the VAD
#: removes internal pauses before anything measures them — a seventy-five second
#: take with normal thinking pauses lands near sixty of retained speech. Aiming
#: at exactly sixty would produce a corpus that mostly misses the threshold it
#: was recorded for.
LONG_SPEAK_S = 75.0

#: Three, not five. §5.7's blind spot is "short utterances are this product's
#: ordinary case", and the genuine floor it was calibrated against was a
#: 3.2-second clip. Recording at the threshold measures the threshold; recording
#: below it measures the population.
SHORT_SPEAK_S = 3.0


@dataclass(frozen=True)
class Take:
    slug: str
    speak_seconds: float
    prompt: str
    why: str


RULES = """\
  THREE RULES, and they are the measurement rather than etiquette.

  1. DO NOT PREPARE. Read the prompt, look away, start. A rehearsed answer is
     fluent in a way real dictation is not, and fluency is the variable.
  2. DO NOT REDO a take because you disliked it. A stumble is data. Redo only
     if the recording itself failed — wrong device, an interruption, a cough
     into the microphone.
  3. KEEP TALKING to the end of the timer. Running dry at forty seconds
     produces thirty-five seconds of silence in the middle, which measures the
     trimmer and not the decoder. If you run out of things to say, say why you
     ran out. That is still speech.
"""

#: Ten prompts built to sustain seventy-five seconds without preparation. Each
#: one has a built-in continuation — a "then what", a comparison, or a list —
#: because the failure mode of a long prompt is not silence at the start, it is
#: a complete answer at second thirty.
LONG_TAKES: tuple[Take, ...] = (
    Take(
        "L01-project-walkthrough",
        LONG_SPEAK_S,
        "Walk someone through what this project does, from pressing the key to "
        "the text appearing. Then tell them which part you are least sure of.",
        "domain vocabulary and proper nouns, at length — the [boost] case",
    ),
    Take(
        "L02-yesterday",
        LONG_SPEAK_S,
        "Describe what you actually did yesterday, hour by hour, in order. "
        "Then say which hour was the most useful and why.",
        "ordinary narrative with real recall pauses",
    ),
    Take(
        "L03-explain-disagreement",
        LONG_SPEAK_S,
        "Describe a technical disagreement you have had. Give their side "
        "first and properly, then yours, then say who you now think was right.",
        "structured argument — the shape that produces self-correction",
    ),
    Take(
        "L04-how-to",
        LONG_SPEAK_S,
        "Explain to a competent stranger how to set up a development "
        "environment for something you work on. Include the step people skip.",
        "instructions, tool names, acronyms",
    ),
    Take(
        "L05-room",
        LONG_SPEAK_S,
        "Describe the room you are in, in detail, as if to someone who has to "
        "reproduce it. Then describe what you would change about it.",
        "concrete nouns, no jargon — the control against L01 and L04",
    ),
    Take(
        "L06-worst-bug",
        LONG_SPEAK_S,
        "Tell the story of the worst bug you have chased: what it looked like, "
        "what you thought it was, what it turned out to be.",
        "narrative under recall load — where filled pauses appear if they do",
    ),
    Take(
        "L07-teach-something",
        LONG_SPEAK_S,
        "Teach something you know well and the listener does not. Start from "
        "why it matters, not from the definition.",
        "sustained exposition, few proper nouns",
    ),
    Take(
        "L08-plan-the-week",
        LONG_SPEAK_S,
        "Plan your week out loud. What is fixed, what is negotiable, what you "
        "will drop first if it goes wrong.",
        "dates, days, numbers — the classes rules touch",
    ),
    Take(
        "L09-read-back",
        LONG_SPEAK_S,
        "Describe the last thing you read that changed your mind, and say what "
        "you believed before it.",
        "abstract vocabulary, long clauses",
    ),
    Take(
        "L10-freeform",
        LONG_SPEAK_S,
        "Anything. Talk for the full time about whatever you like. Do not plan " "it.",
        "the least constrained take, deliberately last",
    ),
)

#: Ten short takes. Under five seconds is the population §5.7 says it cannot
#: judge, and one-word and two-word utterances are included on purpose: the
#: retired words-per-second floor could not distinguish a genuine "Yes." from a
#: collapsed transcript, and coverage is supposed to. This is where that claim
#: is checked.
SHORT_TAKES: tuple[Take, ...] = (
    Take(
        "S01-yes",
        1.5,
        'Say just: "Yes."',
        "one word — the case the rate floor could not judge",
    ),
    Take(
        "S02-no-thanks", 1.5, 'Say just: "No, thank you."', "three words, with a comma"
    ),
    Take(
        "S03-name",
        2.0,
        "Say your own full name and nothing else.",
        "proper nouns, minimum duration",
    ),
    Take(
        "S04-command",
        SHORT_SPEAK_S,
        "Say a shell command you ran recently, out loud.",
        "identifiers and symbols",
    ),
    Take(
        "S05-question",
        SHORT_SPEAK_S,
        "Ask a short question you would actually ask a colleague.",
        "question intonation, terminal punctuation",
    ),
    Take(
        "S06-address",
        SHORT_SPEAK_S,
        "Say a street address.",
        "digits and proper nouns together",
    ),
    Take(
        "S07-time",
        2.0,
        "Say what time it is and what you are doing next.",
        "numbers, short",
    ),
    Take(
        "S08-agree",
        1.5,
        'Say just: "That works for me."',
        "the ordinary short dictation",
    ),
    Take(
        "S09-acronyms",
        SHORT_SPEAK_S,
        "Say three acronyms you use at work.",
        "the class [boost] exists for, at short duration",
    ),
    Take(
        "S10-fragment",
        2.0,
        "Say an incomplete sentence and stop mid-thought.",
        "no terminal punctuation available — the R1 case",
    ),
)


def preflight(capture: object, sample_rate: int) -> str | None:
    """Actually open the microphone. Returns a problem to print, or None.

    **This exists because the check it replaces could not fail.** The first
    version reported the resolved device and moved on — but `resolve_device()`
    returns `None` immediately when `[audio] device = "default"`, without
    touching PortAudio, so in the default configuration it verified nothing.
    The real failure surfaced on take 1, after the operator had read a prompt
    and pressed Enter twice: `ModuleNotFoundError: No module named
    'sounddevice'`.

    That is the sixth instance in this repository of a check that passes by
    checking nothing, and the first one written after the pattern was named.

    So this opens a real stream, keeps it open briefly, and confirms frames
    arrived. It exercises the import, the macOS microphone permission, the
    device, and the callback — the four things that can be wrong — and it does
    it *before* the session starts rather than inside the first take.
    """
    try:
        import sounddevice  # noqa: F401
    except ModuleNotFoundError as exc:
        return _WRONG_INTERPRETER.format(
            missing=exc.name, executable=sys.executable
        ).removeprefix("error: ")

    try:
        capture.start()  # type: ignore[attr-defined]
    except Exception as exc:  # PortAudio raises its own hierarchy
        return (
            f"the microphone could not be opened: {type(exc).__name__}: {exc}\n"
            "  On macOS this is usually the Microphone permission — grant it in\n"
            "  System Settings > Privacy & Security > Microphone."
        )
    try:
        time.sleep(0.25)
        probe = capture.stop()  # type: ignore[attr-defined]
    except Exception as exc:
        return f"the microphone could not be closed: {type(exc).__name__}: {exc}"

    if probe is None or len(probe) == 0:
        return (
            "the microphone opened but delivered no audio.\n"
            "  Check that the input device in Sound preferences is the one you "
            "expect."
        )
    return None


def countdown(label: str, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        print(f"\r  {label}  {remaining:5.1f}s ", end="", flush=True)
        time.sleep(min(0.1, remaining))
    print(f"\r  {label}  done       ", flush=True)


def record_take(take: Take, capture: object, sample_rate: int) -> NDArray[np.float32]:
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


def _rms(samples: NDArray[np.float32]) -> float:
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))


@dataclass(frozen=True)
class Check:
    """Whether a take is usable, decided before it is written rather than after.

    `ratio` is the whole check. A take where the speech window is not clearly
    louder than both silence windows is one where something went wrong that the
    speaker cannot hear — wrong input device, a muted microphone, or a speaker
    who started talking during the lead silence.
    """

    ok: bool
    ratio: float
    peak: float
    reason: str = ""


def check_take(audio: NDArray[np.float32], take: Take, sample_rate: int) -> Check:
    lead = int(LEAD_SILENCE_S * sample_rate)
    tail = int(TAIL_SILENCE_S * sample_rate)
    if len(audio) < lead + tail + sample_rate:
        return Check(
            False, 0.0, 0.0, "the recording is shorter than its own silence windows"
        )

    silence = np.concatenate([audio[:lead], audio[-tail:]])
    speech = audio[lead:-tail]
    silence_rms = _rms(silence)
    speech_rms = _rms(speech)
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0

    # A zero silence floor means digital silence, which is a device fault
    # rather than a quiet room — report it rather than dividing by it.
    if silence_rms <= 0.0:
        return Check(
            False,
            0.0,
            peak,
            "the silence windows are digitally zero — check the input device",
        )

    ratio = speech_rms / silence_rms
    if peak >= CLIPPING_PEAK:
        return Check(
            False, ratio, peak, f"clipped at {peak:.3f} — move back from the microphone"
        )
    if ratio < MIN_SPEECH_TO_SILENCE_RATIO:
        return Check(
            False,
            ratio,
            peak,
            f"speech/silence {ratio:.2f}x is below {MIN_SPEECH_TO_SILENCE_RATIO}x",
        )
    return Check(True, ratio, peak)


def write_wav(path: Path, audio: NDArray[np.float32], sample_rate: int) -> None:
    """16-bit PCM, the format `tests/conftest.read_wav` and every tool expects.

    Clipped rather than rescaled, matching `HistoryStore._write_audio`: a sample
    above 1.0 is already distorted, and rescaling the clip to accommodate it
    would quietly change every other sample too.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = np.clip(audio, -1.0, 1.0)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes((samples * 32767.0).astype("<i2").tobytes())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="record_phase3_corpus.py",
        description=(
            "Record the Phase 3 duration corpus: ten takes past sixty seconds "
            "and ten under five. NOT the Phase 3 gate — see the module "
            "docstring."
        ),
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--set",
        choices=("long", "short", "all"),
        default="all",
        help="which half to record (default: all)",
    )
    parser.add_argument(
        "--take",
        action="append",
        default=None,
        metavar="SLUG",
        help="record only this slug (e.g. L03-explain-disagreement). Repeatable.",
    )
    parser.add_argument(
        "--list", action="store_true", help="print the prompts and exit"
    )
    parser.add_argument("--device", default=None, help="microphone name substring")
    args = parser.parse_args(argv)

    everything = LONG_TAKES + SHORT_TAKES
    if args.list:
        print(RULES)
        for take in everything:
            print(f"  {take.slug:28s} [{take.speak_seconds:5.1f}s] {take.prompt}")
        return 0

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

    if args.take:
        by_slug = {take.slug: take for take in everything}
        unknown = [slug for slug in args.take if slug not in by_slug]
        if unknown:
            print(f"error: unknown take(s): {', '.join(unknown)}", file=sys.stderr)
            return 2
        selected = [by_slug[slug] for slug in args.take]
    elif args.set == "long":
        selected = list(LONG_TAKES)
    elif args.set == "short":
        selected = list(SHORT_TAKES)
    else:
        selected = list(everything)

    # Already-recorded takes are skipped rather than overwritten. A session
    # this long will be interrupted, and re-recording take 1 on every resume is
    # how a corpus ends up with one speaker's morning voice and their evening
    # one in the same set.
    pending = [t for t in selected if not (args.out / f"{t.slug}.wav").exists()]
    skipped = len(selected) - len(pending)

    speaking = sum(t.speak_seconds for t in pending)
    overhead = len(pending) * (LEAD_SILENCE_S + TAIL_SILENCE_S)

    print("=" * 72)
    print("PHASE 3 DURATION CORPUS")
    print("=" * 72)
    print()
    print(RULES)
    print(f"  {len(pending)} takes to record ({skipped} already on disk).")
    print(
        f"  {speaking:.0f}s of speaking + {overhead:.0f}s of silence, plus your own pauses."
    )
    print(f"  Microphone: {'system default' if device is None else f'index {device}'}")
    print(f"  Writing to: {args.out}")
    print()
    if not pending:
        print("  Nothing to do.")
        return 0

    # Before the operator commits to anything. A seventy-five second take is a
    # bad place to discover the audio stack is not there.
    problem = preflight(capture, audio_config.sample_rate)
    if problem is not None:
        print(f"error: {problem}", file=sys.stderr)
        return 2
    print("  microphone: OK (opened, delivered audio, closed)")
    print()
    input("  Press Enter to begin. ")

    sample_rate = audio_config.sample_rate
    written: list[dict[str, object]] = []
    failed: list[str] = []

    for index, take in enumerate(pending, start=1):
        print()
        print("-" * 72)
        print(f"  TAKE {index}/{len(pending)} — {take.slug}")
        audio = record_take(take, capture, sample_rate)
        check = check_take(audio, take, sample_rate)
        if not check.ok:
            print(f"  REJECTED: {check.reason}")
            print(f"  Not written. Re-run with --take {take.slug} to redo it.")
            failed.append(take.slug)
            continue
        path = args.out / f"{take.slug}.wav"
        write_wav(path, audio, sample_rate)
        seconds = len(audio) / sample_rate
        print(
            f"  kept — {seconds:.1f}s total, speech/silence {check.ratio:.2f}x, peak {check.peak:.3f}"
        )
        written.append(
            {
                "slug": take.slug,
                "seconds": round(seconds, 3),
                "speak_seconds": take.speak_seconds,
                "speech_to_silence": round(check.ratio, 3),
                "peak": round(check.peak, 4),
                "prompt": take.prompt,
            }
        )

    # The manifest is what makes the corpus reusable by anything other than a
    # human reading filenames, and it is the only part that gets committed —
    # the audio never can be.
    if written:
        manifest = args.out / "manifest.json"
        existing: list[dict[str, object]] = []
        if manifest.exists():
            try:
                existing = json.loads(manifest.read_text())
            except (OSError, ValueError):
                existing = []
        by_slug_manifest = {str(row.get("slug")): row for row in existing}
        for row in written:
            by_slug_manifest[str(row["slug"])] = row
        manifest.write_text(
            json.dumps(
                sorted(by_slug_manifest.values(), key=lambda r: str(r["slug"])),
                indent=2,
            )
            + "\n"
        )
        print()
        print(f"  manifest: {manifest}")

    print()
    print("=" * 72)
    print(f"  {len(written)} written, {len(failed)} rejected.")
    if failed:
        print(f"  Redo: --take {' --take '.join(failed)}")
    # Non-zero when nothing was captured at all, so a session that silently
    # recorded nothing does not look like a session that recorded everything.
    return 1 if not written and pending else 0


if __name__ == "__main__":
    raise SystemExit(main())
