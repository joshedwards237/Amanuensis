#!/usr/bin/env python3
"""Measure G1 through the product's own classes, over the real corpus.

Why this exists and `bench_engines.py` does not replace it
----------------------------------------------------------
`scripts/bench_engines.py` compares *engines*: it constructs `WhisperModel`
directly, sets its own parameters, and says so in its preamble — "Phase 1
tooling, not product code... nothing here is an implementation of
`TranscriptionEngine`". That is the right shape for choosing between engines
and the wrong shape for defending G1, because every parameter it sets is a
parameter the product might set differently. The 328/420 ms figures in PRD §7.2
came from a script of that kind, and PRD §9's Phase 1 gate is explicit that
they are a **floor** until re-measured through the real path.

This script is the real path: `VoiceActivityDetector` and
`FasterWhisperEngine`, constructed from an `AppConfig`, recording into
`LatencyBreakdown`. If the product's defaults are wrong, this measures them
wrong, which is the entire point.

What it does not measure
------------------------
`AudioCapture`. Capture reads a microphone and cannot read a file, so the
corpus cannot flow through it. That gap is closed by `manu transcribe`, which
runs the whole path including capture but produces n=1 per invocation. Both
numbers are reported at the gate; neither substitutes for the other.

`postprocess` and `inject` do not exist yet (Phases 2a and 3). So `g1_ms` here
equals `asr_ms`, and every G1 figure this script prints is a **floor** that
will grow. It says so in the output rather than trusting the reader to
remember.

On "Tier B's number"
--------------------
PRD §9 asks for Tier B to be measured and reported as well — "not gated" is not
"unmeasured". Tier B is a machine that misses 350/700, and this machine does
not miss it, so the honest thing is not to fabricate one. `--tier-b` instead
re-runs the identical measurement at `cpu_threads=4` — CTranslate2's default,
the value whose 1.8× penalty returned NO-GO on the probe's first run, and the
closest approximation of a small-core machine available here. It is a
**simulation of a constraint, not a measurement of a machine**, and it is
labelled that way everywhere it is printed. §7.2's demand that the thread sweep
cover at least one non-10P topology is not satisfied by it and is not claimed
to be.

Usage
-----
    .venv/bin/python scripts/measure_g1.py
    .venv/bin/python scripts/measure_g1.py --runs 9 --tier-b
    .venv/bin/python scripts/measure_g1.py --sweep-threads 4,6,8,10,14
"""

from __future__ import annotations

import argparse
import dataclasses
import math
import platform
import statistics
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from amanuensis.audio.vad import VoiceActivityDetector  # noqa: E402
from amanuensis.config import AppConfig, resolve_cpu_threads  # noqa: E402
from amanuensis.engines.faster_whisper import FasterWhisperEngine  # noqa: E402
from amanuensis.models.session import LatencyBreakdown  # noqa: E402

CORPUS = REPO_ROOT / "tests" / "fixtures" / "asr"

# PRD §2, G1. The gated budget.
G1_P50_MS = 400.0
G1_P95_MS = 800.0
# PRD §7.2. The ASR share, which is what Phase 1 can actually fill.
TIER_A_P50_MS = 350.0
TIER_A_P95_MS = 700.0
# PRD §2, G1-CPU. What a Tier B machine publishes.
G1_CPU_P50_MS = 2000.0

DEFAULT_RUNS = 9
SAMPLE_RATE = 16000


@dataclass
class SampleRun:
    name: str
    duration_s: float
    timings: list[LatencyBreakdown] = field(default_factory=list)
    retained_s: float = 0.0
    fell_back: bool = False
    speech_segments: int = 0
    transcript: str = ""

    @property
    def asr_values(self) -> list[float]:
        return [t.asr_ms for t in self.timings]


@dataclass
class Measurement:
    label: str
    cpu_threads: int
    model: str
    samples: list[SampleRun] = field(default_factory=list)

    def pooled(self, attribute: str) -> list[float]:
        return [
            getattr(timing, attribute)
            for sample in self.samples
            for timing in sample.timings
        ]

    @property
    def observations(self) -> int:
        return len(self.pooled("asr_ms"))


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank, matching `amanuensis.tier.percentile`.

    Deliberately the same function as the product uses: a gate that measured
    percentiles differently from the install check would report a tier the user
    never sees.
    """
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = math.ceil(q / 100.0 * len(ordered))
    return ordered[min(max(rank, 1), len(ordered)) - 1]


def load_corpus() -> list[tuple[str, NDArray[np.float32], float]]:
    from faster_whisper.audio import decode_audio

    wavs = sorted(CORPUS.glob("*.wav"))
    if not wavs:
        raise SystemExit(
            f"no corpus at {CORPUS}. The .wav files are gitignored by design "
            "(a voice recording in a public repo cannot be unpublished); "
            "re-record per the instructions in .gitignore."
        )
    loaded = []
    for wav in wavs:
        audio = np.asarray(
            decode_audio(str(wav), sampling_rate=SAMPLE_RATE), dtype=np.float32
        )
        loaded.append((wav.stem, audio, len(audio) / SAMPLE_RATE))
    return loaded


def measure(
    corpus: Sequence[tuple[str, NDArray[np.float32], float]],
    *,
    label: str,
    cpu_threads: int | str,
    runs: int,
    verbose: bool,
) -> Measurement:
    """Run the product path over every sample, `runs` times each."""
    config = dataclasses.replace(
        AppConfig(),
        engine=dataclasses.replace(AppConfig().engine, cpu_threads=cpu_threads),
    )
    detector = VoiceActivityDetector(config.vad)
    engine = FasterWhisperEngine(config.engine)
    detector.load()
    engine.load()
    engine.warm_up()

    result = Measurement(
        label=label, cpu_threads=engine.cpu_threads, model=engine.model_name
    )

    for name, audio, duration in corpus:
        run = SampleRun(name=name, duration_s=duration)
        # One discarded pass per sample: the first trim of a new buffer length
        # pays an allocation the rest do not.
        _one_pass(detector, engine, audio)
        for _ in range(runs):
            timings, trimmed, text = _one_pass(detector, engine, audio)
            run.timings.append(timings)
            run.retained_s = trimmed.retained_seconds
            run.fell_back = trimmed.fell_back
            run.speech_segments = trimmed.speech_segments
            run.transcript = text.strip()
        result.samples.append(run)
        if verbose:
            print(
                f"    {name:<18} {duration:5.1f}s -> {run.retained_s:5.1f}s  "
                f"asr p50 {percentile(run.asr_values, 50):7.1f} ms  "
                f"p95 {percentile(run.asr_values, 95):7.1f} ms",
                flush=True,
            )
    return result


def _one_pass(
    detector: VoiceActivityDetector,
    engine: FasterWhisperEngine,
    audio: NDArray[np.float32],
) -> tuple[LatencyBreakdown, object, str]:
    """One utterance through the product path, timed stage by stage.

    G1's clock starts at hotkey release, so it starts here — `capture_ms` is
    left at zero because there is no capture in this harness and a fabricated
    value would flow straight into `total_ms`.
    """
    timings = LatencyBreakdown()

    start = time.perf_counter()
    trimmed = detector.trim(audio, SAMPLE_RATE)
    timings.vad_ms = (time.perf_counter() - start) * 1000.0

    start = time.perf_counter()
    text = engine.transcribe(trimmed.audio, SAMPLE_RATE).text
    timings.transcribe_ms = (time.perf_counter() - start) * 1000.0

    return timings, trimmed, text


def report(measurement: Measurement, *, simulated: bool = False) -> None:
    asr = measurement.pooled("asr_ms")
    vad = measurement.pooled("vad_ms")
    transcribe = measurement.pooled("transcribe_ms")

    p50, p95 = percentile(asr, 50), percentile(asr, 95)
    print()
    print(f"{measurement.label}")
    if simulated:
        print(
            "  SIMULATED CONSTRAINT, NOT A MEASURED MACHINE. cpu_threads is "
            "pinned; core\n  count, memory bandwidth and thermal envelope are "
            "this machine's."
        )
    print(
        f"  model {measurement.model}, cpu_threads {measurement.cpu_threads}, "
        f"{measurement.observations} observations"
    )
    print()
    print(f"  {'stage':<14} {'p50':>10} {'p95':>10} {'min':>10} {'max':>10}")
    print("  " + "-" * 58)
    for name, values in (
        ("vad_ms", vad),
        ("transcribe_ms", transcribe),
        ("asr_ms", asr),
    ):
        print(
            f"  {name:<14} {percentile(values, 50):9.1f}m {percentile(values, 95):9.1f}m "
            f"{min(values):9.1f}m {max(values):9.1f}m"
        )
    print()
    print(
        f"  vs Tier A thresholds ({TIER_A_P50_MS:.0f} / {TIER_A_P95_MS:.0f} ms): "
        f"{'PASS' if p50 <= TIER_A_P50_MS and p95 <= TIER_A_P95_MS else 'MISS'}"
    )
    print(
        f"  vs G1 ({G1_P50_MS:.0f} / {G1_P95_MS:.0f} ms), as a FLOOR: "
        f"{'PASS' if p50 <= G1_P50_MS and p95 <= G1_P95_MS else 'MISS'}"
    )
    print(
        f"  vs G1-CPU ({G1_CPU_P50_MS:.0f} ms p50): "
        f"{'PASS' if p50 <= G1_CPU_P50_MS else 'MISS'}"
    )
    print(
        f"  headroom left for postprocess + inject at p50: "
        f"{G1_P50_MS - p50:+.0f} ms"
    )

    trimmed_total = sum(s.duration_s - s.retained_s for s in measurement.samples)
    original_total = sum(s.duration_s for s in measurement.samples)
    print()
    print(
        f"  trimming removed {trimmed_total:.1f}s of {original_total:.1f}s "
        f"({trimmed_total / original_total * 100:.0f}%)"
    )
    fell_back = [s.name for s in measurement.samples if s.fell_back]
    if fell_back:
        print(
            f"  ⚠️  no speech detected in: {', '.join(fell_back)} "
            f"(passed through whole — guard 1)"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="measure_g1.py",
        description=(
            "Measure G1 through the product's own VoiceActivityDetector and "
            "FasterWhisperEngine over the committed desk-mic corpus. Every "
            "figure is a floor: postprocess and inject are not built yet."
        ),
    )
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument(
        "--tier-b",
        action="store_true",
        help="also run at cpu_threads=4 as a simulated constraint (see preamble)",
    )
    parser.add_argument(
        "--sweep-threads",
        default=None,
        metavar="LIST",
        help="comma-separated thread counts to sweep, e.g. 4,6,8,10,14",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    verbose = not args.quiet
    corpus = load_corpus()

    print("=" * 70)
    print("PHASE 1 — G1 THROUGH THE PRODUCT PATH")
    print("=" * 70)
    print(
        f"  {platform.system()} {platform.release()} {platform.machine()}, "
        f"Python {platform.python_version()}"
    )
    print(
        f"  corpus: {len(corpus)} samples, "
        f"{sum(d for _, _, d in corpus):.1f}s, {args.runs} runs each"
    )
    print(f"  cpu_threads 'auto' resolves to {resolve_cpu_threads('auto')}")
    print()
    print("  NOT MEASURED HERE: AudioCapture (needs a microphone; `manu")
    print("  transcribe` covers it), postprocess and inject (Phases 2a, 3).")
    print("  Every G1 figure below is therefore a FLOOR.")

    if verbose:
        print()
        print("  per sample (auto threads)")
    primary = measure(
        corpus,
        label="cpu_threads = auto",
        cpu_threads="auto",
        runs=args.runs,
        verbose=verbose,
    )
    report(primary)

    if args.tier_b:
        if verbose:
            print()
            print("  per sample (4 threads — CTranslate2's default)")
        tier_b = measure(
            corpus,
            label="cpu_threads = 4 (CTranslate2 default)",
            cpu_threads=4,
            runs=args.runs,
            verbose=verbose,
        )
        report(tier_b, simulated=True)

    if args.sweep_threads:
        values = sorted({int(v) for v in args.sweep_threads.replace(",", " ").split()})
        print()
        print("cpu_threads sweep")
        print(f"  {'threads':>8} {'asr p50':>10} {'asr p95':>10} {'vs auto':>10}")
        print("  " + "-" * 42)
        baseline = percentile(primary.pooled("asr_ms"), 50)
        for value in values:
            swept = measure(
                corpus,
                label=f"threads={value}",
                cpu_threads=value,
                runs=args.runs,
                verbose=False,
            )
            p50 = percentile(swept.pooled("asr_ms"), 50)
            p95 = percentile(swept.pooled("asr_ms"), 95)
            marker = " *" if value == primary.cpu_threads else "  "
            print(
                f"  {value:>6}{marker} {p50:9.1f}m {p95:9.1f}m "
                f"{p50 / baseline:9.2f}x"
            )
        print()
        print("  * = what 'auto' resolved to on this machine.")
        print("  This sweep varies ONE parameter on ONE machine. PRD §7.2 asks")
        print("  for at least one non-10P topology before the performance-core")
        print("  rule stops being n=1; this does not provide one.")

    print()
    print(
        "mean sample duration: "
        f"{statistics.fmean(d for _, _, d in corpus):.1f}s "
        f"(G1 is defined against 10s — PRD §2)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
