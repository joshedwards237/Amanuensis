"""Does the *engine* cause the punctuation edits, or the chain? (§7.2, S6)

The Phase 3 gate found the dominant error class is punctuation — 58 missing
sentence marks and 41 stray capitals, 99 of 171 edits — and that **no
faster-whisper model size fixes it**, because Whisper capitalises the first
token of every segment it emits at every size. §7.2 therefore marked the engine
question open and carried it here, with wording this script exists to satisfy:
"Moonshine and Parakeet have never been benchmarked **for punctuation**."

ADR 0001 already declined Moonshine, on deletions — 12–14 words against
faster-whisper's 2–7 — and that decision is not reopened here. What was never
measured is whether it *punctuates* better, which is the axis G2 is missed on.

**§7.2 freezes the Phase 4 default before this runs.** The result cannot move
the shipped engine inside this phase, which is what stops the measurement from
selecting its own consequence — this project has that failure on record.

Method, and the parts that matter:

* **The same corrections, the same classifier.** `classify_edits` from
  `gate_phase3.py` is imported rather than reimplemented: a second
  implementation's disagreements read as findings about the product, and two
  of three "findings" in one sprint were exactly that.
* **The same chain.** Both engines' raw output goes through the shipped
  post-processing chain and the frozen dictionary. A comparison where one side
  is post-processed measures the chain.
* **Deletions counted separately**, because `decoder_words` merges
  substitution with deletion and ADR 0001 decided on deletion alone. Two
  engines with identical edit rates and opposite failure modes score
  identically in that bucket (objection O1). A deleted word is invisible in
  text the user has not read, which is what §8 exists to refuse.
* **faster-whisper's side is not re-decoded.** The corrections file's
  `injected` is what the product actually put on screen for that take, under
  the config recorded at the time. Re-decoding it would measure today's config
  against yesterday's corrections.

    python scripts/bench_punctuation.py --corrections corrections-2026-09-01.json
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gate_phase3 import _bare, _words, classify_edits

from amanuensis.config import EngineConfig, load_config
from amanuensis.postprocess.registry import build_chain

PUNCTUATION_CLASSES = ("decoder_segmentation", "decoder_capital")


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return audio, rate


def _deletions(injected: str, corrected: str) -> int:
    """Words the user had to put back. ADR 0001's deciding axis.

    Uses the classifier's own tokeniser so the alignment is the one the rest of
    this project reasons about, and counts only the direction `decoder_words`
    cannot separate.
    """
    before = [_bare(w) for w in _words(injected)]
    after = [_bare(w) for w in _words(corrected)]
    matcher = difflib.SequenceMatcher(a=before, b=after, autojunk=False)
    return sum(
        j2 - j1
        for tag, _i1, _i2, j1, j2 in matcher.get_opcodes()
        if tag == "insert"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corrections", type=Path, required=True)
    parser.add_argument("--audio-dir", type=Path, default=None)
    parser.add_argument("--models", default="moonshine/tiny,moonshine/base")
    args = parser.parse_args(argv)

    config = load_config()
    corrections: dict[str, dict[str, Any]] = json.loads(
        args.corrections.read_text()
    )
    audio_dir = args.audio_dir or (
        Path.home() / "Library/Application Support/amanuensis/audio"
    )

    takes = [
        (key, value, audio_dir / f"{key}.wav")
        for key, value in corrections.items()
        if (audio_dir / f"{key}.wav").is_file()
    ]
    missing = len(corrections) - len(takes)
    note = f", {missing} without" if missing else ""
    print(f"{len(takes)} takes with stored audio{note}")
    if not takes:
        print("no stored audio for any correction", file=sys.stderr)
        return 1

    # The frozen dictionary, loaded the way the gate loads it. A chain built
    # without it would run `vocabulary` as a no-op and score every proper noun
    # as a decoder miss — which is the gate's own "a frozen empty dictionary
    # satisfies a digest and measures nothing".
    from amanuensis.postprocess.vocabulary import (
        VocabularyLoader,
        default_vocabulary_path,
        load_vocabulary,
    )

    vocabulary_path = default_vocabulary_path()
    vocabulary = load_vocabulary(vocabulary_path)
    if vocabulary.entry_count == 0:
        print(
            f"vocabulary.toml at {vocabulary_path} has no [replace] entries — "
            "every covered term would score as a decoder miss",
            file=sys.stderr,
        )
        return 1
    chain = build_chain(config.postprocess, VocabularyLoader(vocabulary_path))
    vocab_terms = {key.lower() for key in vocabulary.replacements}
    print(f"frozen dictionary: {vocabulary.entry_count} entries")

    rows: list[dict[str, Any]] = []

    # faster-whisper's side is what shipped, not a re-decode.
    fw_edits = fw_words = fw_dels = 0
    fw_classes: dict[str, int] = {}
    for _key, take, _wav in takes:
        result = classify_edits(
            take["injected"], take["corrected"], vocab_terms,
            terminal_punctuation=config.postprocess.terminal_punctuation,
        )
        fw_edits += result.edits
        fw_words += result.reference_words
        fw_dels += _deletions(take["injected"], take["corrected"])
        for name, count in result.classes.items():
            fw_classes[name] = fw_classes.get(name, 0) + count
    rows.append({
        "engine": f"faster_whisper:{config.engine.model} (as shipped)",
        "edits": fw_edits, "words": fw_words, "deletions": fw_dels,
        "classes": fw_classes, "p50": None, "p95": None,
    })

    from amanuensis.engines.moonshine import MoonshineEngine

    for model in args.models.split(","):
        engine = MoonshineEngine(EngineConfig(model=model.strip()))
        engine.load()
        engine.warm_up()
        edits = words = dels = 0
        classes: dict[str, int] = {}
        timings: list[float] = []
        for _key, take, wav in takes:
            audio, rate = _read_wav(wav)
            started = time.perf_counter()
            raw = engine.transcribe(audio, rate).text
            timings.append((time.perf_counter() - started) * 1000.0)
            text = raw
            for processor in chain:
                text = processor.process(text, None)  # type: ignore[arg-type]
            result = classify_edits(
                text, take["corrected"], vocab_terms,
                terminal_punctuation=config.postprocess.terminal_punctuation,
            )
            edits += result.edits
            words += result.reference_words
            dels += _deletions(text, take["corrected"])
            for name, count in result.classes.items():
                classes[name] = classes.get(name, 0) + count
        ordered = sorted(timings)
        rows.append({
            "engine": f"moonshine:{model.strip()}",
            "edits": edits, "words": words, "deletions": dels, "classes": classes,
            "p50": ordered[(len(ordered) - 1) // 2],
            "p95": ordered[max(0, -(-95 * len(ordered) // 100) - 1)],
        })

    print()
    header = (
        f"{'engine':34} {'edit rate':>10} {'missing marks':>14} "
        f"{'stray caps':>11} {'deletions':>10} {'p50':>8} {'p95':>8}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        rate = row["edits"] / row["words"] if row["words"] else 0.0
        p50 = f"{row['p50']:.0f} ms" if row["p50"] else "  shipped"
        p95 = f"{row['p95']:.0f} ms" if row["p95"] else "  shipped"
        print(
            f"{row['engine']:34} {rate * 100:9.2f}% "
            f"{row['classes'].get('decoder_segmentation', 0):14d} "
            f"{row['classes'].get('decoder_capital', 0):11d} "
            f"{row['deletions']:10d} {p50:>8} {p95:>8}"
        )
    print()
    print("Deletions are ADR 0001's deciding axis and are counted separately")
    print("because decoder_words merges substitution with deletion (objection O1).")
    print("§7.2 freezes the Phase 4 default; this table cannot move it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
