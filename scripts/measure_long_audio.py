#!/usr/bin/env python3
"""Does §2's decode model survive a real sixty-second utterance?

`transcribe_ms ≈ 48.8 + 13.69 × seconds` was fitted at the Phase 2b gate across
0.7–43.4 s of speech. Two things lean on it and neither has ever seen a long
recording:

- **The Phase 3 gate runs straight into it.** The model predicts ~909 ms at
  sixty seconds, over G1's 800 ms p95. That prediction is recorded in advance so
  it cannot be read as a regression this phase caused — but a prediction nobody
  checks is a prediction, not a measurement.
- **`_why_no_retry` spends it.** §5.7 predicts the cost of the recovery decode
  from this model and *declines* the retry when the prediction exceeds
  `retry_max_latency_ms`. If the model under-predicts at length, the guard pays
  a retry it budgeted against a number that was wrong.

This also produces the first coverage distribution on long audio. §5.7's
thresholds come from six samples of under twenty seconds, and the follow-up gate
record states the guard's false-positive direction is untested. Ten
eighty-second takes do not close that — objection O5 established the blind spot
is at the *short* end — but "coverage on long audio" was equally unmeasured and
is cheap to take while the files are here.

**What this is not.** Not the Phase 3 gate, which is live dictation judged on
edit rate. This reads files and measures the decoder.

    .venv/bin/python scripts/measure_long_audio.py
    .venv/bin/python scripts/measure_long_audio.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import wave
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    import numpy as np
    from numpy.typing import NDArray
except ModuleNotFoundError as exc:  # pragma: no cover — an environment problem
    raise SystemExit(
        f"error: {exc.name!r} is not installed for this interpreter "
        f"({sys.executable}).\n  Run: .venv/bin/python scripts/measure_long_audio.py"
    ) from exc

CORPUS = REPO_ROOT / "tests" / "fixtures" / "phase3"

#: §2's model, as `dictation_controller` uses it. Imported by value rather than
#: from the controller so that a change there shows up here as a disagreement
#: rather than being silently adopted.
_INTERCEPT_MS = 48.8
_MS_PER_SECOND = 13.69


def read_wav(path: Path) -> tuple[NDArray[np.float32], int]:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="measure_long_audio.py")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument(
        "--biased",
        action="store_true",
        help=(
            "decode with config.toml's initial_prompt applied, as the daemon "
            "does. Off by default — see the note at the transcribe call."
        ),
    )
    args = parser.parse_args(argv)

    from amanuensis import guard as guard_module
    from amanuensis.audio.vad import VoiceActivityDetector
    from amanuensis.config import load_config
    from amanuensis.engines.faster_whisper import FasterWhisperEngine
    from amanuensis.tier import percentile

    wavs = sorted(args.corpus.glob("*.wav"))
    if not wavs:
        # Non-zero: a measurement over nothing must not read as a measurement.
        print(f"error: no .wav files in {args.corpus}", file=sys.stderr)
        return 2

    config = load_config()
    engine = FasterWhisperEngine(config.engine)
    detector = VoiceActivityDetector(config.vad)
    detector.load()
    engine.load()
    engine.warm_up()

    rows: list[dict[str, Any]] = []
    for path in wavs:
        audio, rate = read_wav(path)

        started = time.perf_counter()
        trimmed = detector.trim(audio, rate)
        vad_ms = (time.perf_counter() - started) * 1000.0

        started = time.perf_counter()
        # Unbiased by default: the original question here is the decoder against
        # duration, and `initial_prompt` is the one input §5.7 shows can change
        # how far it gets. A biased run would confound the two.
        #
        # `--biased` exists for the *other* question, added at the Phase 3 gate.
        # Objection O5's short set asks whether the guard refuses genuine short
        # speech, and the guard's false positives happen in the daemon — which
        # decodes biased whenever `initial_prompt` or `[boost]` is set, and this
        # machine's config.toml has set one since 2026-08-03. Measuring the
        # false-positive direction with bias off would measure a configuration
        # the operator does not run. Both runs are reported; neither replaces
        # the other.
        decoded = engine.transcribe(trimmed.audio, rate, biased=args.biased)
        transcribe_ms = (time.perf_counter() - started) * 1000.0

        speech = trimmed.retained_seconds - trimmed.padding_seconds
        predicted = _INTERCEPT_MS + _MS_PER_SECOND * trimmed.retained_seconds

        # **The product's own verdict, not a second opinion.** The first version
        # of this script recomputed `decoded_seconds / speech` itself and
        # reported coverages above 100% as a finding — which the product never
        # produces, because `guard._by_coverage` clamps at 1.0 and has done
        # since the guard shipped. A harness that reimplements the quantity it
        # is measuring reports on code the user does not run; `measure_g1.py`
        # already reuses `tier.percentile` for exactly this reason, and this
        # script did not follow it.
        verdict = guard_module.evaluate(
            decoded.text,
            decoded_seconds=decoded.decoded_seconds,
            retained_seconds=trimmed.retained_seconds,
            padding_seconds=trimmed.padding_seconds,
            fell_back=trimmed.fell_back,
            config=config.guard,
        )
        coverage = verdict.coverage
        rows.append(
            {
                "slug": path.stem,
                "original_seconds": round(trimmed.original_seconds, 2),
                "retained_seconds": round(trimmed.retained_seconds, 2),
                "speech_seconds": round(speech, 2),
                # The guard's numerator, reported raw because its own
                # `coverage` is `min(decoded / speech, 1.0)` and a clamped 1.0
                # cannot distinguish "exactly covered" from "five times over".
                # That distinction is the whole of objection O5's question —
                # how much margin a genuine short utterance has before the
                # refusal fires — and the clamp erases it. This is the input
                # to the product's verdict, not a second opinion about it.
                # `float | None` since `engines/moonshine.py` landed
                # (2026-09-02): an engine that cannot report how far it
                # got says so rather than claiming zero, which §5.7
                # would read as "stopped immediately". Carried through
                # as null for the same reason.
                "decoded_seconds": (
                    None
                    if decoded.decoded_seconds is None
                    else round(decoded.decoded_seconds, 2)
                ),
                "vad_ms": round(vad_ms, 1),
                "transcribe_ms": round(transcribe_ms, 1),
                "predicted_ms": round(predicted, 1),
                "error_ms": round(transcribe_ms - predicted, 1),
                "coverage": round(coverage, 4) if coverage is not None else None,
                "outcome": str(verdict.outcome),
                "retry_advised": verdict.retry_advised,
                "words": len(decoded.text.split()),
                "fell_back": trimmed.fell_back,
            }
        )
        if not args.json:
            print(
                f"  {path.stem:28s} {trimmed.retained_seconds:6.1f}s retained  "
                f"transcribe {transcribe_ms:7.1f} ms  "
                f"predicted {predicted:7.1f}  "
                f"delta {transcribe_ms - predicted:+8.1f}  "
                f"coverage {coverage:.1%}"
                if coverage is not None
                else f"  {path.stem:28s} (no decoded span)"
            )

    measured = [row["transcribe_ms"] for row in rows]
    predicted_all = [row["predicted_ms"] for row in rows]
    coverages = [row["coverage"] for row in rows if row["coverage"] is not None]

    summary = {
        "n": len(rows),
        # Recorded rather than implied. Two runs of this script over the same
        # files now differ in a way the numbers alone do not show.
        "biased": args.biased,
        "transcribe_ms_p50": percentile(measured, 50),
        "transcribe_ms_p95": percentile(measured, 95),
        "predicted_ms_p50": percentile(predicted_all, 50),
        "predicted_ms_p95": percentile(predicted_all, 95),
        "coverage_min": min(coverages) if coverages else None,
        "coverage_p50": percentile(coverages, 50) if coverages else None,
        # Counted from the guard's own verdicts rather than by re-applying its
        # thresholds here — the same reason the coverage above is its.
        "guard_would_fire": sum(1 for row in rows if row["outcome"] == "failed"),
        "retry_would_trigger": sum(1 for row in rows if row["retry_advised"]),
    }

    if args.json:
        print(json.dumps({"rows": rows, "summary": summary}, indent=2))
        return 0

    print()
    print(
        f"  n = {summary['n']}   "
        f"initial_prompt {'APPLIED' if args.biased else 'off'}   "
        "(nearest-rank percentiles, never interpolated)"
    )
    print(
        f"  transcribe_ms   p50 {summary['transcribe_ms_p50']:8.1f}   "
        f"p95 {summary['transcribe_ms_p95']:8.1f}"
    )
    print(
        f"  §2 predicted    p50 {summary['predicted_ms_p50']:8.1f}   "
        f"p95 {summary['predicted_ms_p95']:8.1f}"
    )
    print(
        f"  coverage        min {summary['coverage_min']:8.1%}   "
        f"p50 {summary['coverage_p50']:8.1%}"
    )
    print(
        f"  guard would refuse {summary['guard_would_fire']}/{summary['n']}, "
        f"retry on {summary['retry_would_trigger']}/{summary['n']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
