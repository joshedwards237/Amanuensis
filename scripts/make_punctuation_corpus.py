"""Decode the ten long takes and emit transcripts for the operator to correct.

**Why this exists, and why it is not simply re-running the Phase 3 gate.** That
gate found the dominant error class is punctuation — 58 missing sentence marks
and 41 stray capitals, 99 of 171 edits — and **its audio was not kept**.
`corrections-2026-09-01.json` is keyed by `history.db` session ids and the
recordings are gone, so no engine-side change can ever be scored against the
9.59% / 31% figures. `bench_punctuation.py` works around exactly that by never
re-decoding, and says so in its own docstring.

`tests/fixtures/phase3/L*.wav` is what does exist: ten long takes, the same ten
prompts, the same speaker, **different takes**, with no operator corrections.
This script decodes them through the product and writes one editable `.txt` per
take. The operator fixes punctuation and case; nothing else. That produces the
corpus the two untried candidates both need.

Three things it records that a later measurement cannot recover:

* **The segment and word timings**, captured at decode time. The pause
  hypothesis is about the gaps between them, and re-decoding later to get them
  back would measure whatever the config had become — the Phase 3 corpus was
  recorded twice for exactly that reason, and the first one measured a dead
  `initial_prompt`.
* **The config that produced it**, for the same reason, in the same file.
* **What the product would actually have typed**, which is the raw transcript
  *after* the shipping post-processing chain. Correcting the raw decoder output
  would measure a product nobody runs.

The output lives in `tests/fixtures/phase3/`, which `.gitignore` covers whole —
these are the verbatim words of spontaneous dictation, which that rule was
written for and which the "reference transcripts ARE committed" exemption
explicitly does not reach.

    python scripts/make_punctuation_corpus.py
    # ... edit tests/fixtures/phase3/corpus/*.txt ...
    python scripts/measure_pause_punctuation.py
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from amanuensis.audio.vad import VoiceActivityDetector  # noqa: E402
from amanuensis.config import SUPPORTED_SAMPLE_RATE, AppConfig  # noqa: E402
from amanuensis.engines.faster_whisper import (  # noqa: E402
    BEAM_SIZE,
    FasterWhisperEngine,
)
from amanuensis.models.session import DictationSession  # noqa: E402
from amanuensis.postprocess.registry import build_chain  # noqa: E402
from amanuensis.postprocess.vocabulary import VocabularyLoader  # noqa: E402

#: The corpus is gitignored, so it exists only in the checkout it was recorded
#: in — a worktree has none, and a measurement run there would have nothing to
#: measure. `--corpus` is how a worktree reaches the lobby's copy.
DEFAULT_CORPUS = REPO / "tests/fixtures/phase3"


def load_wav(path: Path) -> NDArray[np.float32]:
    with wave.open(str(path), "rb") as handle:
        if handle.getframerate() != SUPPORTED_SAMPLE_RATE:
            raise SystemExit(f"{path.name}: {handle.getframerate()} Hz, need 16000")
        if handle.getnchannels() != 1:
            raise SystemExit(f"{path.name}: not mono")
        raw = handle.readframes(handle.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def decode(
    engine: FasterWhisperEngine, audio: NDArray[np.float32]
) -> tuple[str, list[dict[str, Any]]]:
    """The product's decode, with the boundaries kept.

    `_decode` joins the segment texts and discards everything else, which is
    the whole subject of this measurement — so the model is driven directly
    here, with the **same kwargs**, asserted against the engine's own constants
    rather than retyped.
    """
    model = engine._require_model("corpus")
    segments, _info = model.transcribe(
        audio,
        language=engine._config.language or None,
        beam_size=BEAM_SIZE,
        initial_prompt=engine._prompt(()),
        vad_filter=False,
        word_timestamps=True,
    )
    captured: list[dict[str, Any]] = []
    text: list[str] = []
    for segment in segments:
        text.append(segment.text)
        captured.append(
            {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": segment.text,
                "words": [
                    {
                        "word": word.word,
                        "start": float(word.start),
                        "end": float(word.end),
                    }
                    for word in (segment.words or [])
                ],
            }
        )
    return "".join(text), captured


#: The one-file editing form. Ten files is ten context switches on a task that
#: is already forty minutes of reading; a single document is one.
COMBINED_NAME = "EDIT-ME.md"
_HEADER = "## "
_COMBINED_PREAMBLE = """\
# Punctuation corpus — correct this file, then run the measurement

**Correct punctuation and case ONLY.**

* Add the sentence marks that belong. This is the whole point: the decoder
  emits almost none, which is why every take reads as one long run-on.
* Fix stray capitals — Whisper capitalises the first word of every segment it
  emits, and those are not sentence starts.
* Commas are welcome but are **not** what this measures.

**Do not fix misheard words.** A wrong word is the decoder's problem and is not
what this measures; changing one makes the alignment treat it as an edit and
tells us nothing about pauses. If a sentence is gibberish, punctuate the
gibberish.

Leave the `## ` headings exactly as they are — they are how this file is split
back into per-take transcripts.

When you are done:

    python scripts/punctuation_corpus_split.py
    python scripts/measure_pause_punctuation.py

"""


def write_combined(out: Path, slugs: list[str]) -> Path:
    """One document, from the per-take transcripts."""
    parts = [_COMBINED_PREAMBLE]
    for slug in slugs:
        body = (out / f"{slug}.txt").read_text().strip()
        parts.append(f"{_HEADER}{slug}\n\n{body}\n")
    path = out / COMBINED_NAME
    path.write_text("\n".join(parts))
    return path


def split_combined(out: Path) -> list[str]:
    """The per-take transcripts, back from the one document.

    Refuses rather than guesses when a heading is missing or unknown: a split
    that silently dropped a take would produce a corpus short by ~190 words and
    a precision figure computed over nine tenths of it.
    """
    path = out / COMBINED_NAME
    if not path.exists():
        raise SystemExit(f"no {path} — run with --combine first")

    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in path.read_text().splitlines():
        if line.startswith(_HEADER):
            current = line[len(_HEADER) :].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    expected = {p.stem for p in out.glob("L*.txt")}
    unknown = set(sections) - expected
    missing = expected - set(sections)
    if unknown:
        raise SystemExit(f"unknown heading(s) in {COMBINED_NAME}: {sorted(unknown)}")
    if missing:
        raise SystemExit(f"{COMBINED_NAME} is missing: {sorted(missing)}")

    written: list[str] = []
    for slug, lines in sections.items():
        text = "\n".join(lines).strip()
        if not text:
            raise SystemExit(f"{slug} is empty in {COMBINED_NAME}")
        (out / f"{slug}.txt").write_text(text + "\n")
        written.append(slug)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS,
        help="directory holding the L*.wav takes (default: this checkout's)",
    )
    parser.add_argument(
        "--combine",
        action="store_true",
        help=f"write {COMBINED_NAME} from the per-take transcripts and stop",
    )
    parser.add_argument(
        "--split",
        action="store_true",
        help=f"write the per-take transcripts back from {COMBINED_NAME} and stop",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite transcripts you have already edited",
    )
    args = parser.parse_args(argv)

    corpus = args.corpus.expanduser().resolve()
    out = corpus / "corpus"

    if args.split:
        written = split_combined(out)
        print(f"wrote {len(written)} transcripts back to {out}")
        return 0
    if args.combine:
        slugs = sorted(p.stem for p in out.glob("L*.txt"))
        if not slugs:
            raise SystemExit(f"no transcripts in {out} — run without --combine first")
        print(f"edit: {write_combined(out, slugs)}")
        return 0

    takes = sorted(corpus.glob("L*.wav"))
    if not takes:
        raise SystemExit(f"no L*.wav in {corpus}")

    out.mkdir(parents=True, exist_ok=True)
    edited = [p for p in out.glob("*.txt") if p.stat().st_size > 0]
    if edited and not args.force:
        raise SystemExit(
            f"{len(edited)} transcript(s) already in {out}.\n"
            "Re-running would overwrite corrections. Pass --force if that is "
            "what you want."
        )

    config = AppConfig()
    engine = FasterWhisperEngine(config.engine)
    engine.load()
    detector = VoiceActivityDetector(config.vad)
    detector.load()
    chain = build_chain(config.postprocess, VocabularyLoader())

    record: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        # Recorded beside the data, not in a commit message. The Phase 3 corpus
        # was decoded under an `initial_prompt` removed from `config.toml` the
        # same afternoon, and nothing in the result said so.
        "config": {
            "backend": config.engine.backend,
            "model": engine.model_name,
            "language": config.engine.language,
            "beam_size": BEAM_SIZE,
            "initial_prompt": config.engine.initial_prompt,
            "cpu_threads": engine.cpu_threads,
            "vad": {
                "threshold": config.vad.threshold,
                "min_silence_duration_ms": config.vad.min_silence_duration_ms,
                "speech_pad_ms": config.vad.speech_pad_ms,
            },
            "postprocess_chain": list(config.postprocess.chain),
            "terminal_punctuation": config.postprocess.terminal_punctuation,
        },
        "takes": {},
    }

    for wav in takes:
        audio = load_wav(wav)
        trimmed = detector.trim(audio, SUPPORTED_SAMPLE_RATE)
        raw, segments = decode(engine, trimmed.audio)

        # The shipping chain, so the operator corrects what the product would
        # have typed rather than what the decoder emitted.
        session = DictationSession(
            id=wav.stem,
            started_at=datetime.now(UTC),
            audio=None,
            sample_rate=SUPPORTED_SAMPLE_RATE,
            raw_transcript=raw,
        )
        injected = raw
        for processor in chain:
            injected = processor.process(injected, session)

        (out / f"{wav.stem}.txt").write_text(injected.strip() + "\n")
        record["takes"][wav.stem] = {
            "raw": raw,
            "injected": injected,
            "retained_fraction": trimmed.retained_fraction,
            "segments": segments,
        }
        boundaries = max(0, len(segments) - 1)
        print(f"  {wav.stem}: {len(segments)} segments, {boundaries} boundaries")

    (out / "decode.json").write_text(json.dumps(record, indent=1))

    print(f"edit: {write_combined(out, [w.stem for w in takes])}")
    print(f"\nWrote {len(takes)} transcripts to {out}")
    print("\nCorrect PUNCTUATION AND CASE ONLY. Do not fix misheard words —")
    print("a wrong word is the decoder's problem and is not what this measures.")
    print("\nThen: python scripts/measure_pause_punctuation.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
