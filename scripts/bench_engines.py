#!/usr/bin/env python3
"""Phase 1 engine-selection benchmark — latency and WER across candidate ASR engines.

Why this exists
---------------
The pre-Phase-0 probe (`docs/gates/probe.md`) measured latency on one clip and
selected `base.en` on that basis alone. PRD §9 is explicit that this is not
enough to pick a model: "The corpus is built BEFORE the engine is chosen."
Objection O7 named the gap — latency is measured, accuracy is not — and PRD §2's
accuracy-measurement note answers it with a small committed corpus under
`tests/fixtures/asr/` plus a per-engine WER figure for the Phase 1 ADR.

This script produces that figure, and the latency figures beside it, so that
`docs/adr/0001-engine-selection.md` records a measurement rather than a guess.

What this is NOT
----------------
This is **Phase 1 tooling, not product code**. Nothing here is an
implementation of `TranscriptionEngine` and nothing under `src/` imports it. It
exists to produce a number for a decision and does not pretend to be
architecture; `FasterWhisperEngine` is not descended from this file, the ADR it
produced is.

Written before Phase 0 existed, and the preamble said so — "there is no `src/`
tree, no `pyproject.toml`, no ABCs". All three now exist, and this script
constructs `WhisperModel` directly anyway. That is deliberate and is the
distinction from `scripts/measure_g1.py`: **this script compares engines and
therefore sets its own parameters; that one measures the product and therefore
sets none.** A benchmark that went through `FasterWhisperEngine` could only
ever measure models `FasterWhisperEngine` already supports, which is the
opposite of what an engine-selection ADR needs. The single exception is
trimming — see `--trim` below.

It also does not measure G1. G1 is `LatencyBreakdown.g1_ms` = transcribe +
postprocess + inject (PRD §2, §6.3). This measures **transcription only**, which
makes every latency number here a *floor*. That is stated in the output rather
than left for the reader to remember.

Key decisions, and why
----------------------
* **`device="cpu"`, always.** CTranslate2 has no Metal backend (PRD §7.2), so
  `mps` was never a reachable value and is not offered. On macOS "Apple Silicon"
  is a CPU path with more cores, not an accelerator.

* **`cpu_threads` defaults to the performance-core count, never the library
  default.** CTranslate2 defaults to 4 threads; on the probe's M3 Max that
  default cost 1.8× and turned a GO into a NO-GO (PRD §7.2, probe finding 1).
  A benchmark that silently inherited the library default would measure the
  wrong machine. `--sweep-threads` exists because the probe's value was chosen
  as "match the performance cores" and was never tuned.

* **Audio is decoded once, outside the timed region.** The product transcribes
  samples already in memory from `AudioCapture`; timing a file decode would
  measure disk I/O that the product never pays. What is timed is transcription
  and the consumption of its segment generator — faster-whisper's `transcribe()`
  returns lazily, so a timer stopped before the generator is drained measures
  almost nothing. That trap is why the loop below looks slightly awkward.

* **Warm up, then take a median.** A resident daemon is always warm (PRD §9,
  Phase 1: "warm-up"), so a cold first run is not the number the user
  experiences. The warm-up run is discarded and is also where the transcript
  used for WER comes from — identical input, greedy decoding, so it matches the
  timed runs.

* **WER is implemented here rather than imported.** It is a Levenshtein distance
  over word sequences and roughly forty lines. `jiwer` would be a dependency
  added to a repository that does not yet have a `pyproject.toml` to declare it
  in, for a script that is deleted or archived after the ADR is written.

* **The WER report states its own limits.** PRD §2 is unambiguous that this
  figure is for *relative* comparison between engines, is not a G2 measurement,
  and cannot validate an absolute threshold. A number in a table does not carry
  that caveat by itself, so the output computes and prints how much of the WER
  gap between two models is a single word, and marks pairs of models this corpus
  cannot tell apart. The markdown block is caveat-fenced so it cannot be pasted
  into the ADR without the caveat coming with it.

* **Moonshine is benchmarked here** (added 2026-07-31, Phase 1). PRD §7.2
  requires it and §9 makes the comparison a gate deliverable. It arrives as the
  `bench` optional dependency (`useful-moonshine-onnx`), deliberately not as a
  runtime one — it pulls librosa, numba, scipy and scikit-learn behind it, and
  a contributor running the test suite should not pay for a second ASR runtime.
  Model names are prefixed `moonshine/`; everything else in the report is
  unchanged, which is the point of having a report shape.

* **Trimming is applied outside the timed region, identically to every engine**
  (`--trim`). This is the one place the script reaches into `src/`, and it is
  load-bearing: faster-whisper has a `vad_filter` flag and Moonshine has
  nothing like it, so a comparison run with each engine's own trimming would
  measure the trimmers. `--vad-filter` survives only to reproduce older
  faster-whisper-only numbers and must not be combined with `--trim`.

What it deliberately does not do
--------------------------------
* No `beam_size` sweep. The probe's "should sweep it" is a real gap, exposed
  here as `--beam-size` rather than automated, because sweeping it multiplies
  the run time of an already long benchmark and belongs in a second pass.
* No cold-start / model-residency measurement. PRD §8's < 15 s NFR is a
  different instrument; this one warms up on purpose.
* No edit rate. That is Phase 3 (PRD §2), and it is the actual product goal.

Note on the network: constructing a model downloads weights from Hugging Face on
first use. That is a *benchmark-time* fetch, not a runtime one — G3 concerns the
shipped daemon (PRD §7.6), which resolves models from a local path. Run once to
populate the cache before trusting any timing.

Usage
-----
    .venv/bin/python scripts/bench_engines.py --dry-run     # validate corpus only
    .venv/bin/python scripts/bench_engines.py
    .venv/bin/python scripts/bench_engines.py --models base.en,tiny.en --runs 9
    .venv/bin/python scripts/bench_engines.py --sweep-threads 4,8,10,14
    .venv/bin/python scripts/bench_engines.py --out docs/adr/0001-engine-selection.md.part
"""

from __future__ import annotations

import argparse
import math
import os
import platform
import statistics
import subprocess
import sys
import time
import unicodedata
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

# --------------------------------------------------------------------------
# Constants — every one of these is a PRD citation, not a preference.
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = REPO_ROOT / "tests" / "fixtures" / "asr"

# PRD §2, G1: p50 <= 400 ms, p95 <= 800 ms, for a 10-second utterance, Tier A.
G1_P50_MS = 400.0
G1_P95_MS = 800.0

# PRD §2, G1-CPU (provisional): p50 <= 2000 ms. A Tier B machine class that
# misses this is dropped in §3 rather than shipped.
G1_CPU_P50_MS = 2000.0

# PRD §2: G1's basis is a 10-second utterance. Samples far from this are still
# measured, but the comparison against the budget means something different.
G1_UTTERANCE_SECONDS = 10.0
G1_UTTERANCE_TOLERANCE = 3.0

# PRD §7.2 candidates plus the probe's measured set. `distil-large-v3` is here
# because it was §7.2's original Apple Silicon selection and the ADR should show
# the row it is rejecting, not just assert it.
DEFAULT_MODELS = [
    "tiny.en",
    "base.en",
    "distil-small.en",
    "small.en",
    "distil-large-v3",
    # PRD §7.2: "Benchmark it in Phase 1 against `base.en` — not `small.en`,
    # which the probe showed is 2.2x over budget."
    "moonshine/tiny",
    "moonshine/base",
]

# PRD §7.2's table specifies int8 for every CPU row.
COMPUTE_TYPE = "int8"

# The probe ran beam_size=1 throughout; keeping the default comparable to
# docs/gates/probe.md is worth more than a marginally better transcript.
DEFAULT_BEAM_SIZE = 1

DEFAULT_RUNS = 5

# PRD §5.3: engine.language.
LANGUAGE = "en"

# The corpus contract, from .gitignore's regeneration instructions and PRD §2.
EXPECTED_SAMPLE_RATE = 16000
EXPECTED_CHANNELS = 1
EXPECTED_SAMPLE_WIDTH = 2  # bytes; 16-bit PCM

# PRD §9 Phase 1: "five to ten samples". Fewer is not an error — it is a caveat
# the report has to carry.
CORPUS_MIN_RECOMMENDED = 5

# 95% two-sided normal quantile, for the Wilson interval below.
Z_95 = 1.959963984540054

# Display labels for the environment block. `.title()` produces "Ctranslate2"
# and "Logical Cpus", which look like a machine wrote them without looking.
ENV_LABELS = {
    "platform": "Platform",
    "machine": "Architecture",
    "python": "Python",
    "logical_cpus": "Logical CPUs",
    "cpu": "CPU",
    "memory": "Memory",
    "faster_whisper": "`faster-whisper`",
    "ctranslate2": "`ctranslate2`",
}


# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------


def resolve_cpu_threads() -> tuple[int, str]:
    """Resolve `cpu_threads = "auto"` per PRD §7.2.

    Performance cores only. Efficiency cores are deliberately excluded because
    scheduling inference across heterogeneous cores on Apple Silicon typically
    costs more than it returns. Returns the value and how it was derived, so the
    report can say which branch it took rather than leaving the reader to guess
    whether the number is meaningful.
    """
    # `physicalcpu`, not `logicalcpu`. §7.2 was amended to the former on
    # 2026-07-31 (objection A8) and `config.resolve_cpu_threads` queries it; on
    # Apple Silicon both return the same number, but a benchmark that asks a
    # different question from the product is a benchmark of something else.
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["sysctl", "-n", "hw.perflevel0.physicalcpu"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            value = int(out.stdout.strip())
            if value > 0:
                return value, "hw.perflevel0.physicalcpu (performance cores)"
        except (subprocess.SubprocessError, ValueError, OSError):
            # Intel Macs have no perflevel keys. Fall through rather than fail —
            # a benchmark that refuses to run on an older Mac is worse than one
            # that runs and says which number it used.
            pass
    fallback = os.cpu_count() or 1
    return fallback, "os.cpu_count() (no performance-core split available)"


def describe_machine() -> dict[str, str]:
    """Everything needed to reproduce a run, or to distrust one."""
    info = {
        "platform": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "python": platform.python_version(),
        "logical_cpus": str(os.cpu_count() or "unknown"),
    }
    if sys.platform == "darwin":
        for label, key in (("cpu", "machdep.cpu.brand_string"), ("memory_bytes", "hw.memsize")):
            try:
                out = subprocess.run(
                    ["sysctl", "-n", key], capture_output=True, text=True, check=True, timeout=5
                )
                info[label] = out.stdout.strip()
            except (subprocess.SubprocessError, OSError):
                pass
    if "memory_bytes" in info:
        try:
            info["memory"] = f"{int(info.pop('memory_bytes')) / 2**30:.0f} GB"
        except ValueError:
            info.pop("memory_bytes", None)
    return info


def library_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    try:
        import faster_whisper

        versions["faster_whisper"] = getattr(faster_whisper, "__version__", "unknown")
    except ImportError:
        versions["faster_whisper"] = "NOT INSTALLED"
    try:
        import ctranslate2

        versions["ctranslate2"] = getattr(ctranslate2, "__version__", "unknown")
    except ImportError:
        versions["ctranslate2"] = "NOT INSTALLED"
    return versions


# --------------------------------------------------------------------------
# Corpus discovery
# --------------------------------------------------------------------------


class CorpusError(Exception):
    """Raised when the corpus is missing, incomplete, or unreadable.

    Always carries a message that names the offending path and says what to do
    about it. A benchmark that fails with `FileNotFoundError` on a corpus that
    is gitignored by design (see `.gitignore`) is a bad experience for the one
    person who will hit it most: whoever clones this on a second machine.
    """


@dataclass
class Sample:
    name: str
    wav: Path
    txt: Path
    reference: str
    duration_s: float
    format_warning: str | None = None

    @property
    def reference_words(self) -> list[str]:
        return normalise(self.reference)


def _wav_duration(path: Path) -> tuple[float, str | None]:
    """Duration in seconds, plus a warning if the file is not the specified format.

    A format mismatch is a warning rather than an error: faster-whisper will
    resample happily, so the run still produces numbers — they are just not
    numbers for the corpus PRD §2 specified. Silently accepting it would let a
    44.1 kHz stereo recording sit in an ADR labelled as desk-mic 16 kHz mono.
    """
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            channels = handle.getnchannels()
            width = handle.getsampwidth()
    except (wave.Error, EOFError, OSError) as exc:
        raise CorpusError(f"{path}: cannot read as WAV ({exc})") from exc

    if rate <= 0:
        raise CorpusError(f"{path}: reports a sample rate of {rate}")

    mismatches = []
    if rate != EXPECTED_SAMPLE_RATE:
        mismatches.append(f"{rate} Hz (expected {EXPECTED_SAMPLE_RATE})")
    if channels != EXPECTED_CHANNELS:
        mismatches.append(f"{channels} channels (expected {EXPECTED_CHANNELS})")
    if width != EXPECTED_SAMPLE_WIDTH:
        mismatches.append(f"{width * 8}-bit (expected {EXPECTED_SAMPLE_WIDTH * 8}-bit)")

    warning = ", ".join(mismatches) if mismatches else None
    return frames / rate, warning


RECORD_HINT = (
    "Record it with the microphone you actually dictate with:\n"
    '    ffmpeg -f avfoundation -list_devices true -i ""      # find your mic index\n'
    '    ffmpeg -f avfoundation -i ":0" -t 10 -ar 16000 -ac 1 \\\n'
    "           -c:a pcm_s16le tests/fixtures/asr/<name>.wav\n"
    "(.wav files are gitignored by design — a voice recording in a public repo\n"
    " cannot be unpublished. The .txt references are committed.)"
)


def discover_corpus(directory: Path) -> list[Sample]:
    """Pair every `<name>.wav` with its `<name>.txt`, or explain what is missing."""
    if not directory.exists():
        raise CorpusError(
            f"corpus directory does not exist: {directory}\n"
            f"PRD §9 Phase 1 requires five to ten desk-mic samples with reference\n"
            f"transcripts before an engine is chosen.\n{RECORD_HINT}"
        )
    if not directory.is_dir():
        raise CorpusError(f"corpus path is not a directory: {directory}")

    wavs = {p.stem: p for p in sorted(directory.glob("*.wav"))}
    txts = {p.stem: p for p in sorted(directory.glob("*.txt"))}

    problems: list[str] = []
    for stem in sorted(set(wavs) - set(txts)):
        problems.append(
            f"  {wavs[stem].name} has no reference transcript.\n"
            f"    Write one at: {directory / (stem + '.txt')}\n"
            f"    It must be what you actually said, verbatim — WER against an\n"
            f"    idealised script measures the script, not the engine."
        )
    for stem in sorted(set(txts) - set(wavs)):
        problems.append(
            f"  {txts[stem].name} has no audio.\n"
            f"    Expected: {directory / (stem + '.wav')}\n"
            f"    .wav files are gitignored, so this is the normal state after a\n"
            f"    fresh clone — the corpus is re-recorded per machine."
        )
    if problems:
        raise CorpusError(
            "corpus is incomplete — every sample needs both halves:\n"
            + "\n".join(problems)
            + f"\n\n{RECORD_HINT}"
        )
    if not wavs:
        raise CorpusError(
            f"no samples found in {directory}\n"
            f"PRD §9 Phase 1 asks for five to ten, varied deliberately: a code-heavy\n"
            f"sentence, one dense with proper nouns, one at a natural rambling pace,\n"
            f"one deliberately fast, one with background noise.\n{RECORD_HINT}"
        )

    samples: list[Sample] = []
    for stem, wav in wavs.items():
        reference = txts[stem].read_text(encoding="utf-8").strip()
        if not normalise(reference):
            raise CorpusError(
                f"{txts[stem]} is empty or contains no words.\n"
                f"WER is undefined without a reference; fix or remove the sample."
            )
        duration, warning = _wav_duration(wav)
        samples.append(
            Sample(
                name=stem,
                wav=wav,
                txt=txts[stem],
                reference=reference,
                duration_s=duration,
                format_warning=warning,
            )
        )
    return samples


# --------------------------------------------------------------------------
# WER
# --------------------------------------------------------------------------

# Apostrophes are deleted rather than replaced with a space: "don't" must
# normalise to one token, not two, or every contraction inflates the reference
# word count and the error count with it. Every other punctuation mark becomes a
# space, so "code-heavy" is two tokens on both sides of the comparison —
# consistent, which is all WER needs, since both sides go through this function.
_APOSTROPHES = "'‘’ʼʻ`"


def normalise(text: str) -> list[str]:
    """Lowercase, strip punctuation, collapse whitespace, return words.

    Deliberately minimal. It does NOT normalise numbers, and that matters: the
    probe found every model renders "four hundred milliseconds" as "400
    milliseconds". If a reference transcript spells the number out, every model
    takes the same hit — comparable between engines, which is the only claim
    this corpus supports, but it does inflate the absolute figure. Write
    references the way the models will: digits as digits.
    """
    text = unicodedata.normalize("NFKC", text).lower()
    out_chars: list[str] = []
    for char in text:
        if char in _APOSTROPHES:
            continue
        if unicodedata.category(char).startswith("P") or unicodedata.category(char) == "Sm":
            out_chars.append(" ")
        else:
            out_chars.append(char)
    return "".join(out_chars).split()


@dataclass
class EditCounts:
    substitutions: int = 0
    deletions: int = 0
    insertions: int = 0
    reference_words: int = 0

    @property
    def errors(self) -> int:
        return self.substitutions + self.deletions + self.insertions

    @property
    def wer(self) -> float:
        if self.reference_words == 0:
            return 0.0
        return self.errors / self.reference_words

    def __add__(self, other: EditCounts) -> EditCounts:
        return EditCounts(
            self.substitutions + other.substitutions,
            self.deletions + other.deletions,
            self.insertions + other.insertions,
            self.reference_words + other.reference_words,
        )


def word_errors(reference: Sequence[str], hypothesis: Sequence[str]) -> EditCounts:
    """Levenshtein over word sequences, with the operation breakdown kept.

    The breakdown is worth the extra bookkeeping: deletions dominating means an
    engine is truncating, insertions dominating means it is hallucinating, and
    substitutions dominating means it is mishearing. Three different problems
    that one WER percentage cannot distinguish, and the ADR is choosing between
    engines partly on which failure it can tolerate.

    Ties are resolved substitution > deletion > insertion. Any consistent order
    gives the same total distance; only the attribution between categories
    shifts, so the breakdown is indicative and the total is exact.
    """
    n, m = len(reference), len(hypothesis)
    # Row of (distance, substitutions, deletions, insertions).
    previous: list[tuple[int, int, int, int]] = [(j, 0, 0, j) for j in range(m + 1)]

    for i in range(1, n + 1):
        current: list[tuple[int, int, int, int]] = [(i, 0, i, 0)]
        for j in range(1, m + 1):
            if reference[i - 1] == hypothesis[j - 1]:
                d, s, dele, ins = previous[j - 1]
                current.append((d, s, dele, ins))
                continue
            sub = previous[j - 1]
            dele = previous[j]
            ins = current[j - 1]
            best = min(sub[0], dele[0], ins[0]) + 1
            if sub[0] + 1 == best:
                current.append((best, sub[1] + 1, sub[2], sub[3]))
            elif dele[0] + 1 == best:
                current.append((best, dele[1], dele[2] + 1, dele[3]))
            else:
                current.append((best, ins[1], ins[2], ins[3] + 1))
        previous = current

    _, subs, dels, inss = previous[m]
    return EditCounts(subs, dels, inss, n)


def wilson_interval(errors: int, trials: int, z: float = Z_95) -> tuple[float, float] | None:
    """95% Wilson score interval for an error rate.

    Present so the report can say "these two models are not distinguishable by
    this corpus" instead of ranking them on a difference of one word.

    The independence assumption is violated — word errors cluster within an
    utterance, and a mangled proper noun takes its neighbours with it — so the
    true interval is WIDER than this. That makes the interval a lower bound on
    uncertainty, which is the safe direction for a figure PRD §2 says is for
    relative comparison only. Returns None when insertions push errors past the
    reference length, where the binomial model stops applying at all.
    """
    if trials <= 0 or errors > trials:
        return None
    p = errors / trials
    denom = 1.0 + (z * z) / trials
    centre = (p + (z * z) / (2 * trials)) / denom
    half = z * math.sqrt(p * (1 - p) / trials + (z * z) / (4 * trials * trials)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


# --------------------------------------------------------------------------
# Measurement
# --------------------------------------------------------------------------


@dataclass
class SampleResult:
    sample: Sample
    latencies_ms: list[float]
    transcript: str
    counts: EditCounts

    @property
    def median_ms(self) -> float:
        return statistics.median(self.latencies_ms)

    @property
    def min_ms(self) -> float:
        return min(self.latencies_ms)

    @property
    def max_ms(self) -> float:
        return max(self.latencies_ms)


@dataclass
class ModelResult:
    model: str
    cpu_threads: int
    samples: list[SampleResult] = field(default_factory=list)
    error: str | None = None

    @property
    def all_latencies(self) -> list[float]:
        return [ms for s in self.samples for ms in s.latencies_ms]

    @property
    def counts(self) -> EditCounts:
        """Pooled edit counts. `counts.wer` is the **micro**-average.

        Kept because the Wilson interval needs errors and trials, and a
        binomial interval over a mean of per-sample rates is not a thing. It is
        not the headline figure — see `macro_wer`.
        """
        total = EditCounts()
        for s in self.samples:
            total = total + s.counts
        return total

    @property
    def macro_wer(self) -> float:
        """The unweighted mean of per-sample WERs. **This is the PRD's figure.**

        PRD §7.2, amended 2026-07-31 under objection A3: "WER in this document
        is macro-average... The 14.8% figure is withdrawn." That 14.8% was the
        micro-average, and this script computed and printed exactly it for
        another two months, because the amendment landed in the PRD and not
        here. The two differ by about a third relative, and the open question
        of whether post-processing compensates for weaker ASR is answered
        differently depending on which is used.

        Macro, because each sample is one dictation event and the product's
        user experiences them one at a time; a word-weighted mean lets one long
        sample dominate six.
        """
        if not self.samples:
            return 0.0
        return statistics.fmean(s.counts.wer for s in self.samples)

    @property
    def wer_spread(self) -> tuple[float, float]:
        """Best and worst per-sample WER. A macro mean hides which sample."""
        if not self.samples:
            return (0.0, 0.0)
        rates = [s.counts.wer for s in self.samples]
        return (min(rates), max(rates))

    @property
    def p50_ms(self) -> float:
        return percentile(self.all_latencies, 50)

    @property
    def p95_ms(self) -> float:
        return percentile(self.all_latencies, 95)


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile.

    Nearest-rank rather than interpolated, deliberately: an interpolated p95 over
    forty observations invents a value that was never measured, and this whole
    exercise is about not inventing values. With N observations the p95 is simply
    the ceil(0.95*N)-th slowest — which is also why the report says how many
    observations went into it.
    """
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = math.ceil(q / 100.0 * len(ordered))
    return ordered[min(max(rank, 1), len(ordered)) - 1]


def load_audio(samples: Iterable[Sample]) -> dict[str, object]:
    """Decode every sample once, up front.

    Outside the timed region on purpose — see the preamble. Also fails fast on a
    corrupt file before a twenty-minute benchmark rather than during it.
    """
    from faster_whisper.audio import decode_audio

    decoded: dict[str, object] = {}
    for sample in samples:
        try:
            decoded[sample.name] = decode_audio(str(sample.wav), sampling_rate=EXPECTED_SAMPLE_RATE)
        except Exception as exc:  # noqa: BLE001 — decode backends raise many types
            raise CorpusError(f"{sample.wav}: could not decode audio ({exc})") from exc
    return decoded


def _whisper_transcriber(
    model_name: str, *, cpu_threads: int, beam_size: int, vad_filter: bool
) -> Any:
    """A timed faster-whisper call.

    `transcribe()` returns a generator; the work happens on iteration. The join
    is inside the timer because that is where the decoding actually occurs — a
    timer stopped before the generator is drained measures almost nothing.
    """
    from faster_whisper import WhisperModel

    model = WhisperModel(
        model_name,
        device="cpu",
        compute_type=COMPUTE_TYPE,
        cpu_threads=cpu_threads,
    )

    def transcribe(data: object) -> tuple[str, float]:
        start = time.perf_counter()
        segments, _info = model.transcribe(
            data,
            language=LANGUAGE,
            beam_size=beam_size,
            vad_filter=vad_filter,
        )
        text = "".join(segment.text for segment in segments)
        return text, (time.perf_counter() - start) * 1000.0

    return transcribe


def _moonshine_transcriber(model_name: str) -> Any:
    """A timed Moonshine call.

    Moonshine has no beam size, no thread control and no VAD flag — it is an
    ONNX encoder/decoder with one knob, which is part of what makes it a
    genuine alternative rather than a variant. `cpu_threads` therefore does not
    apply to these rows and the report says so instead of printing the
    faster-whisper value beside a number it did not affect.

    Tokenisation is inside the timer because it is inside the product's
    equivalent too: what the caller needs is text, and a benchmark that stopped
    at token IDs would flatter whichever engine had the slower tokeniser.
    """
    from moonshine_onnx import MoonshineOnnxModel, load_tokenizer

    model = MoonshineOnnxModel(model_name=model_name)
    tokenizer = load_tokenizer()

    def transcribe(data: object) -> tuple[str, float]:
        import numpy as np

        batched = np.asarray(data, dtype=np.float32)[None, ...]
        start = time.perf_counter()
        tokens = model.generate(batched)
        text = tokenizer.decode_batch(tokens)[0]
        return text, (time.perf_counter() - start) * 1000.0

    return transcribe


MOONSHINE_PREFIX = "moonshine/"


def is_moonshine(model_name: str) -> bool:
    return model_name.startswith(MOONSHINE_PREFIX)


def trim_corpus(
    samples: Sequence[Sample], audio: dict[str, object]
) -> tuple[dict[str, object], list[str]]:
    """Trim every sample once, with the product's detector, before any timing.

    Outside the timed region and applied identically to every engine — see the
    preamble. Returns the trimmed audio and the names of any samples where the
    detector found no speech and the buffer passed through whole (guard 1 in
    `amanuensis.audio.vad`), because a fallback that went unreported would look
    like an engine having got slower on that sample.
    """
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from amanuensis.audio.vad import VoiceActivityDetector
    from amanuensis.config import VadConfig

    detector = VoiceActivityDetector(VadConfig())
    detector.load()

    trimmed: dict[str, object] = {}
    fell_back: list[str] = []
    for sample in samples:
        import numpy as np

        data = np.asarray(audio[sample.name], dtype=np.float32)
        result = detector.trim(data, EXPECTED_SAMPLE_RATE)
        trimmed[sample.name] = result.audio
        if result.fell_back:
            fell_back.append(sample.name)
    return trimmed, fell_back


def run_model(
    model_name: str,
    samples: Sequence[Sample],
    audio: dict[str, object],
    *,
    cpu_threads: int,
    runs: int,
    beam_size: int,
    vad_filter: bool,
    verbose: bool,
) -> ModelResult:
    """Benchmark one model across the whole corpus."""
    result = ModelResult(model=model_name, cpu_threads=cpu_threads)

    try:
        if verbose:
            print(f"  loading {model_name} (cpu, cpu_threads={cpu_threads})...", flush=True)
        transcribe = (
            _moonshine_transcriber(model_name)
            if is_moonshine(model_name)
            else _whisper_transcriber(
                model_name,
                cpu_threads=cpu_threads,
                beam_size=beam_size,
                vad_filter=vad_filter,
            )
        )
    except Exception as exc:  # download and load failures are varied
        # One unavailable model must not cost the whole run. A missing
        # `distil-large-v3` download should still leave `base.en` measured.
        result.error = f"{type(exc).__name__}: {exc}"
        print(f"  !! {model_name} unavailable — {result.error}", file=sys.stderr, flush=True)
        return result

    for sample in samples:
        data = audio[sample.name]
        # Warm-up: discarded for timing, kept for WER. A resident daemon is
        # always warm (PRD §9), so the cold run is not the user's experience.
        transcript, warm_ms = transcribe(data)
        latencies: list[float] = []
        for _ in range(runs):
            _text, elapsed = transcribe(data)
            latencies.append(elapsed)
        counts = word_errors(sample.reference_words, normalise(transcript))
        result.samples.append(
            SampleResult(
                sample=sample,
                latencies_ms=latencies,
                transcript=transcript.strip(),
                counts=counts,
            )
        )
        if verbose:
            print(
                f"    {sample.name}: median {statistics.median(latencies):7.1f} ms "
                f"(warm-up {warm_ms:.0f} ms discarded), WER {counts.wer * 100:5.1f}%",
                flush=True,
            )

    return result


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def tier_for(p50_ms: float) -> str:
    """PRD §7.2's tier definition, applied to one model on this machine.

    Tier A when the selected model transcribes a 10-second utterance inside G1's
    budget; Tier B when it does not. Qualified by `(transcribe only)` everywhere
    it is printed, because this measurement is a floor — the real g1_ms adds
    postprocess and inject on top.
    """
    return "A" if p50_ms <= G1_P50_MS else "B"


def verdict(p50: float, p95: float) -> tuple[str, str]:
    """Pass/fail strings against G1 and G1-CPU."""
    g1 = "PASS" if (p50 <= G1_P50_MS and p95 <= G1_P95_MS) else "MISS"
    g1_cpu = "PASS" if p50 <= G1_CPU_P50_MS else "MISS"
    return g1, g1_cpu


def corpus_caveats(samples: Sequence[Sample], results: Sequence[ModelResult]) -> list[str]:
    """Everything that makes this corpus a weak instrument, computed not asserted.

    PRD §2: the WER figure "is for relative comparison only... it is not a G2
    measurement." A percentage in a table does not carry that on its own, so the
    limits are computed from the actual corpus and printed next to the number.
    """
    lines: list[str] = []
    total_words = sum(len(s.reference_words) for s in samples)
    total_audio = sum(s.duration_s for s in samples)

    lines.append(
        f"**This WER is for relative comparison between engines only.** It is not a "
        f"G2 measurement and cannot validate an absolute threshold (PRD §2, "
        f"accuracy-measurement note). G2 is edit rate, measured in Phase 3."
    )
    lines.append(
        f"Corpus: **{len(samples)} samples**, {total_audio:.1f} s of audio, "
        f"**{total_words} reference words**."
    )
    if total_words:
        resolution = 100.0 / total_words
        lines.append(
            f"Resolution: one misrecognised word moves WER by **{resolution:.2f} "
            f"percentage points**. Any gap between two models smaller than that is "
            f"not a difference."
        )
    if len(samples) < CORPUS_MIN_RECOMMENDED:
        lines.append(
            f"⚠️ Only {len(samples)} samples; PRD §9 Phase 1 asks for five to ten, "
            f"varied deliberately (code-heavy, proper nouns, rambling, fast, noisy)."
        )
    lines.append(
        "Speaker and room diversity are **not measurable from these files** and are "
        "assumed to be one speaker, one microphone, one room — the same n=1 caveat "
        "the pre-Phase-0 probe carried (`docs/gates/probe.md`). A model that wins "
        "here has won on one voice."
    )
    lines.append(
        "Numbers spelled out in a reference transcript count as errors against every "
        "engine (all of them emit digits — probe finding). Consistent between "
        "engines, but it inflates the absolute figure."
    )

    ties = indistinguishable_pairs(results)
    if ties:
        rendered = ", ".join(f"`{a}` / `{b}`" for a, b in ties)
        lines.append(
            f"**Not distinguishable by this corpus** (95% Wilson intervals overlap; "
            f"the true intervals are wider still, since word errors cluster): {rendered}."
        )
    return lines


def indistinguishable_pairs(results: Sequence[ModelResult]) -> list[tuple[str, str]]:
    """Model pairs whose WER confidence intervals overlap.

    Named as such rather than "statistically insignificant" because the claim is
    modest and exact: this corpus cannot tell them apart. It says nothing about
    whether a bigger one could.
    """
    intervals: list[tuple[str, tuple[float, float]]] = []
    for result in results:
        if result.error or not result.samples:
            continue
        counts = result.counts
        interval = wilson_interval(counts.errors, counts.reference_words)
        if interval:
            intervals.append((result.model, interval))

    pairs: list[tuple[str, str]] = []
    for i, (name_a, (lo_a, hi_a)) in enumerate(intervals):
        for name_b, (lo_b, hi_b) in intervals[i + 1 :]:
            if lo_a <= hi_b and lo_b <= hi_a:
                pairs.append((name_a, name_b))
    return pairs


def duration_note(samples: Sequence[Sample]) -> str | None:
    """Warn when the corpus is not measuring G1's stated basis.

    PRD §2 binds G1 to a 10-second utterance, and PRD §7.4 explains why the
    length matters less than one would think — Whisper's encoder always
    processes a padded 30-second window, so a 2-second utterance costs nearly
    what a 25-second one does. That makes a corpus of very short clips
    *optimistic-looking and misleading* rather than simply different.
    """
    if not samples:
        return None
    mean = statistics.fmean(s.duration_s for s in samples)
    if abs(mean - G1_UTTERANCE_SECONDS) <= G1_UTTERANCE_TOLERANCE:
        return None
    return (
        f"Mean sample duration is {mean:.1f} s, not the {G1_UTTERANCE_SECONDS:.0f} s "
        f"G1 is defined against (PRD §2). Whisper's encoder pads to a 30-second "
        f"window regardless (PRD §7.4), so this changes the number less than the "
        f"ratio suggests — but the figures below are not a like-for-like G1 "
        f"comparison until the corpus centres on 10 s."
    )


def print_console_report(
    results: Sequence[ModelResult],
    samples: Sequence[Sample],
    env: dict[str, str],
    threads: int,
    threads_basis: str,
    runs: int,
    beam_size: int,
    vad_filter: bool,
) -> None:
    ok = [r for r in results if not r.error and r.samples]

    print()
    print("=" * 78)
    print("PHASE 1 ENGINE BENCHMARK")
    print("=" * 78)
    print()
    print("Machine")
    for key, value in env.items():
        print(f"  {strip_markdown(ENV_LABELS.get(key, key)):<16} {value}")
    print(f"  {'cpu_threads':<16} {threads}  — {threads_basis}")
    print(f"  {'device':<16} cpu  — CTranslate2 has no Metal backend (PRD §7.2)")
    print(f"  {'compute_type':<16} {COMPUTE_TYPE}")
    print(f"  {'beam_size':<16} {beam_size}")
    print(f"  {'vad_filter':<16} {vad_filter}")
    print(f"  {'runs per sample':<16} {runs} (median reported; one warm-up discarded)")
    print()

    print(f"Corpus ({len(samples)} samples)")
    for sample in samples:
        flag = f"  ⚠️ {sample.format_warning}" if sample.format_warning else ""
        print(
            f"  {sample.name:<24} {sample.duration_s:6.1f} s  "
            f"{len(sample.reference_words):4d} words{flag}"
        )
    note = duration_note(samples)
    if note:
        print()
        print(f"  ⚠️ {note}")
    print()

    print("Latency — TRANSCRIPTION ONLY. This is a floor, not G1.")
    print("  G1 (PRD §2) is g1_ms = transcribe + postprocess + inject. What is left")
    print(f"  of the {G1_P50_MS:.0f} ms p50 budget after transcription is shown as headroom.")
    print()
    header = (
        f"  {'model':<20} {'p50':>10} {'p95':>10} {'min':>10} {'max':>10} "
        f"{'headroom':>10} {'G1':>5} {'G1-CPU':>7} {'tier':>5}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    for result in results:
        if result.error:
            print(f"  {result.model:<20} unavailable — {result.error[:44]}")
            continue
        p50, p95 = result.p50_ms, result.p95_ms
        g1, g1_cpu = verdict(p50, p95)
        cells = [
            f"{p50:.1f}ms",
            f"{p95:.1f}ms",
            f"{min(result.all_latencies):.1f}ms",
            f"{max(result.all_latencies):.1f}ms",
            f"{G1_P50_MS - p50:+.1f}ms",
        ]
        print(
            f"  {result.model:<20} " + " ".join(f"{c:>10}" for c in cells)
            + f" {g1:>5} {g1_cpu:>7} {tier_for(p50):>5}"
        )
    if ok:
        n_obs = len(ok[0].all_latencies)
        print()
        print(f"  p50/p95 pooled over {n_obs} observations per model "
              f"({len(samples)} samples × {runs} runs), nearest-rank.")
        if n_obs < 20:
            print(f"  ⚠️ A p95 from {n_obs} observations is the "
                  f"{math.ceil(0.95 * n_obs)}th value — barely a percentile.")
    print()

    print("Accuracy (WER) — RELATIVE COMPARISON ONLY, NOT A G2 MEASUREMENT")
    print()
    print("  MACRO is the PRD's figure (§7.2, objection A3). The micro column is")
    print("  shown only because the Wilson interval is computed from it; a 2026-07-31")
    print("  amendment withdrew a micro figure that had been in circulation.")
    print()
    print(f"  {'model':<20} {'macro':>8} {'range':>16} {'micro':>8} "
          f"{'95% CI':>16} {'sub':>5} {'del':>5} {'ins':>5}")
    print("  " + "-" * 90)
    for result in results:
        if result.error:
            continue
        counts = result.counts
        interval = wilson_interval(counts.errors, counts.reference_words)
        ci = f"{interval[0] * 100:.1f}–{interval[1] * 100:.1f}%" if interval else "n/a"
        low, high = result.wer_spread
        print(
            f"  {result.model:<20} {result.macro_wer * 100:7.2f}% "
            f"{f'{low * 100:.1f}–{high * 100:.1f}%':>16} "
            f"{counts.wer * 100:7.2f}% {ci:>16} "
            f"{counts.substitutions:5d} {counts.deletions:5d} {counts.insertions:5d}"
        )
    print()
    for line in corpus_caveats(samples, results):
        print(f"  * {strip_markdown(line)}")
    print()

    print("Tier (PRD §7.2)")
    inside = [r for r in ok if r.p50_ms <= G1_P50_MS]
    if inside:
        best = min(inside, key=lambda r: r.p50_ms)
        names = ", ".join(r.model for r in inside)
        print(f"  Tier A (transcribe only). {len(inside)} of {len(ok)} candidates land inside")
        print(f"  the {G1_P50_MS:.0f} ms p50 budget: {names}.")
        print(f"  Fastest is {best.model} at {best.p50_ms:.0f} ms.")
        print()
        print("  A tier is decided by the model the ADR SELECTS, not by the fastest one")
        print("  measured — so this is Tier A only if the selected model is in that list,")
        print(f"  and only if postprocess + inject fit in the "
              f"{G1_P50_MS - best.p50_ms:.0f} ms that remain.")
    elif ok:
        best = min(ok, key=lambda r: r.p50_ms)
        g1_cpu = "inside" if best.p50_ms <= G1_CPU_P50_MS else "OUTSIDE"
        print(f"  Tier B (transcribe only). No candidate lands inside {G1_P50_MS:.0f} ms.")
        print(f"  Fastest is {best.model} at {best.p50_ms:.0f} ms — {g1_cpu} the "
              f"{G1_CPU_P50_MS:.0f} ms G1-CPU floor.")
        print()
        print( "  PRD §9: a Tier B miss does not reject the gate; it is recorded and")
        print( "  published. Missing G1-CPU is a different matter — PRD §2 drops that")
        print( "  machine class in §3 rather than shipping it.")
    else:
        print("  No model completed. Nothing to report.")
    print()


def strip_markdown(text: str) -> str:
    """Console rendering of a caveat written once, in markdown."""
    return text.replace("**", "").replace("`", "")


def build_markdown(
    results: Sequence[ModelResult],
    samples: Sequence[Sample],
    env: dict[str, str],
    threads: int,
    threads_basis: str,
    runs: int,
    beam_size: int,
    vad_filter: bool,
    sweep: Sequence[ModelResult] | None,
) -> str:
    """The block that goes into docs/adr/0001-engine-selection.md.

    Structured so the caveats travel with the numbers. The WER table sits under
    a blockquote it cannot be separated from without deliberate editing — a
    table pasted alone into an ADR becomes an authoritative-looking accuracy
    claim within one revision, and PRD §2 spent a whole note saying it is not one.
    """
    lines: list[str] = []
    add = lines.append

    add("<!-- Generated by scripts/bench_engines.py — Phase 1 tooling, not product code. -->")
    add("")
    add("## Measurement")
    add("")
    add("| | |")
    add("|---|---|")
    add(f"| Date | {time.strftime('%Y-%m-%d')} |")
    for key, value in env.items():
        add(f"| {ENV_LABELS.get(key, key)} | {value} |")
    add(f"| `cpu_threads` | {threads} — {threads_basis} |")
    add("| `device` | `cpu` — CTranslate2 has no Metal backend (PRD §7.2) |")
    add(f"| `compute_type` | `{COMPUTE_TYPE}` |")
    add(f"| `beam_size` | {beam_size} |")
    add(f"| `vad_filter` | `{vad_filter}` |")
    add(f"| Runs | {runs} timed per sample, one warm-up discarded, median reported |")
    add(f"| Corpus | {len(samples)} samples, "
        f"{sum(s.duration_s for s in samples):.1f} s, "
        f"{sum(len(s.reference_words) for s in samples)} reference words |")
    add("")

    add("## Latency")
    add("")
    add("> **Transcription only — this is a floor, not G1.** G1 is "
        "`LatencyBreakdown.g1_ms` = transcribe + postprocess + inject (PRD §2, §6.3). "
        "The headroom column is what remains of the 400 ms p50 budget for the other "
        "two stages.")
    add("")
    note = duration_note(samples)
    if note:
        add(f"> ⚠️ {note}")
        add("")
    add("| Model | p50 | p95 | min | max | Headroom vs G1 p50 | G1 (400/800 ms) | "
        "G1-CPU (2000 ms p50) | Tier |")
    add("|---|---|---|---|---|---|---|---|---|")
    for result in results:
        if result.error:
            add(f"| `{result.model}` | — | — | — | — | — | unavailable | unavailable | — |")
            continue
        p50, p95 = result.p50_ms, result.p95_ms
        g1, g1_cpu = verdict(p50, p95)
        add(
            f"| `{result.model}` | {p50:.0f} ms | {p95:.0f} ms | "
            f"{min(result.all_latencies):.0f} ms | {max(result.all_latencies):.0f} ms | "
            f"{G1_P50_MS - p50:+.0f} ms | **{g1}** | {g1_cpu} | {tier_for(p50)} |"
        )
    add("")

    ok = [r for r in results if not r.error and r.samples]
    if ok:
        n_obs = len(ok[0].all_latencies)
        add(f"Percentiles are nearest-rank over {n_obs} observations per model "
            f"({len(samples)} samples × {runs} runs).")
        if n_obs < 20:
            add(f"⚠️ A p95 drawn from {n_obs} observations is the "
                f"{math.ceil(0.95 * n_obs)}th value; treat it as indicative.")
        add("")

    add("### Per sample")
    add("")
    add("| Sample | Duration | " + " | ".join(f"`{r.model}`" for r in results) + " |")
    add("|---|---|" + "---|" * len(results))
    for i, sample in enumerate(samples):
        cells = []
        for result in results:
            if result.error or i >= len(result.samples):
                cells.append("—")
            else:
                sr = result.samples[i]
                cells.append(f"{sr.median_ms:.0f} ms ({sr.min_ms:.0f}–{sr.max_ms:.0f})")
        add(f"| `{sample.name}` | {sample.duration_s:.1f} s | " + " | ".join(cells) + " |")
    add("")
    add("Cells are median (min–max) in milliseconds.")
    add("")

    add("## Accuracy (WER)")
    add("")
    add("\n>\n".join(f"> {caveat}" for caveat in corpus_caveats(samples, results)))
    add("")
    add("> **The macro column is the PRD's figure** (§7.2, amended 2026-07-31 under "
        "objection A3: \"WER in this document is macro-average... The 14.8% figure is "
        "withdrawn\"). Micro is reported beside it only because the Wilson interval is "
        "a binomial over pooled errors and cannot be computed from a mean of rates. "
        "The two differ by roughly a third relative; do not quote the micro column.")
    add("")
    add("| Model | WER (macro) | Per-sample range | WER (micro) | 95% CI (micro) | "
        "Substitutions | Deletions | Insertions |")
    add("|---|---|---|---|---|---|---|---|")
    for result in results:
        if result.error:
            add(f"| `{result.model}` | — | — | — | — | — | — | — |")
            continue
        counts = result.counts
        interval = wilson_interval(counts.errors, counts.reference_words)
        ci = f"{interval[0] * 100:.1f}–{interval[1] * 100:.1f}%" if interval else "n/a"
        low, high = result.wer_spread
        add(
            f"| `{result.model}` | **{result.macro_wer * 100:.2f}%** | "
            f"{low * 100:.1f}–{high * 100:.1f}% | {counts.wer * 100:.2f}% | {ci} | "
            f"{counts.substitutions} | {counts.deletions} | {counts.insertions} |"
        )
    add("")

    add("### Per sample WER")
    add("")
    add("| Sample | Words | " + " | ".join(f"`{r.model}`" for r in results) + " |")
    add("|---|---|" + "---|" * len(results))
    for i, sample in enumerate(samples):
        cells = []
        for result in results:
            if result.error or i >= len(result.samples):
                cells.append("—")
            else:
                cells.append(f"{result.samples[i].counts.wer * 100:.1f}%")
        add(f"| `{sample.name}` | {len(sample.reference_words)} | " + " | ".join(cells) + " |")
    add("")

    if sweep:
        add("## `cpu_threads` sweep")
        add("")
        add("> PRD §7.2: CTranslate2 defaults to 4 threads; the probe measured a **1.8× "
            "penalty** from that default and the chosen value was never tuned beyond "
            "\"match the performance cores\". This sweep is the tuning.")
        add("")
        add("| `cpu_threads` | Model | p50 | p95 | vs. resolved default |")
        add("|---|---|---|---|---|")
        baseline = next((r for r in sweep if r.cpu_threads == threads and not r.error), None)
        for result in sweep:
            if result.error:
                add(f"| {result.cpu_threads} | `{result.model}` | — | — | unavailable |")
                continue
            if baseline and baseline.p50_ms > 0:
                ratio = f"{result.p50_ms / baseline.p50_ms:.2f}×"
            else:
                ratio = "—"
            marker = " *(resolved default)*" if result.cpu_threads == threads else ""
            add(f"| {result.cpu_threads}{marker} | `{result.model}` | "
                f"{result.p50_ms:.0f} ms | {result.p95_ms:.0f} ms | {ratio} |")
        add("")

    add("## What this does not measure")
    add("")
    add("- Audio capture, model residency / cold start (PRD §8's < 15 s NFR), "
        "post-processing, and text injection. All excluded, all real.")
    add("- Edit rate — the actual G2 product goal (PRD §2). That is Phase 3.")
    add("- Moonshine, which PRD §7.2 requires be benchmarked against `base.en` in "
        "Phase 1. Not installed in this environment; add it before the ADR closes.")
    add("- `beam_size` beyond the single value above. The probe flagged sweeping it "
        "as an open item, since it trades latency against the accuracy this corpus "
        "measures weakly.")
    add("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_thread_list(raw: str, default_threads: int) -> list[int]:
    """Parse --sweep-threads, or derive a sensible sweep.

    The derived set always includes 4 — the CTranslate2 default that cost the
    probe 1.8× — so the sweep reproduces the finding rather than assuming it.
    """
    if raw and raw != "auto":
        try:
            values = sorted({int(v) for v in raw.replace(",", " ").split()})
        except ValueError as exc:
            raise ValueError(f"--sweep-threads: expected integers, got {raw!r}") from exc
        if not values or any(v < 1 for v in values):
            raise ValueError("--sweep-threads: values must be integers >= 1")
        return values
    total = os.cpu_count() or default_threads
    candidates = {4, default_threads, total, max(1, default_threads // 2)}
    return sorted(v for v in candidates if v >= 1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bench_engines.py",
        description=(
            "Phase 1 engine-selection benchmark: latency and WER for candidate ASR "
            "engines over the committed desk-mic corpus. Produces the table for "
            "docs/adr/0001-engine-selection.md. Phase 1 tooling, not product code."
        ),
        epilog=(
            "The WER figure is for RELATIVE comparison between engines only. It is "
            "not a G2 measurement and cannot validate an absolute threshold "
            "(PRD §2, accuracy-measurement note)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS,
        help=f"directory of <name>.wav / <name>.txt pairs (default: {DEFAULT_CORPUS})",
    )
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help=f"comma-separated model names (default: {','.join(DEFAULT_MODELS)})",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        help=f"timed runs per sample, after one discarded warm-up (default: {DEFAULT_RUNS})",
    )
    parser.add_argument(
        "--cpu-threads",
        type=int,
        default=None,
        help="override the resolved performance-core count (PRD §7.2). Never defaults to 4.",
    )
    parser.add_argument(
        "--beam-size",
        type=int,
        default=DEFAULT_BEAM_SIZE,
        help=f"decoder beam size (default: {DEFAULT_BEAM_SIZE}, matching the probe)",
    )
    parser.add_argument(
        "--vad-filter",
        action="store_true",
        help=(
            "enable faster-whisper's Silero VAD. PRD §7.4 moved silence trimming into "
            "Phase 1 because it is the dominant latency lever — the encoder pads to a "
            "30 s window regardless. Off by default so numbers stay comparable with "
            "docs/gates/probe.md; turn it on to see what the product will actually do."
        ),
    )
    parser.add_argument(
        "--trim",
        action="store_true",
        help=(
            "trim silence with the product's VoiceActivityDetector before timing, "
            "identically for every engine. This is what the product does (PRD §7.4) "
            "and the only fair way to compare an engine that has a VAD flag against "
            "one that does not. Mutually exclusive with --vad-filter."
        ),
    )
    parser.add_argument(
        "--sweep-threads",
        nargs="?",
        const="auto",
        default=None,
        metavar="LIST",
        help=(
            "sweep cpu_threads (e.g. 4,8,10,14). With no value, derives a set that "
            "always includes CTranslate2's default of 4. Uses --sweep-model."
        ),
    )
    parser.add_argument(
        "--sweep-model",
        default=None,
        help="model to use for the thread sweep (default: the first --models entry)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write the markdown report here instead of stdout",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and inventory the corpus, then exit without loading any model",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress per-sample progress output",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    verbose = not args.quiet

    try:
        samples = discover_corpus(args.corpus)
    except CorpusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    threads, threads_basis = resolve_cpu_threads()
    if args.cpu_threads is not None:
        if args.cpu_threads < 1:
            print("error: --cpu-threads must be >= 1", file=sys.stderr)
            return 2
        threads, threads_basis = args.cpu_threads, "--cpu-threads override"

    if args.dry_run:
        print(f"corpus: {args.corpus}  ({len(samples)} samples)")
        for sample in samples:
            flag = f"  ⚠️ {sample.format_warning}" if sample.format_warning else ""
            print(
                f"  {sample.name:<24} {sample.duration_s:6.1f} s  "
                f"{len(sample.reference_words):4d} words{flag}"
            )
        note = duration_note(samples)
        if note:
            print(f"\n⚠️ {note}")
        if len(samples) < CORPUS_MIN_RECOMMENDED:
            print(f"\n⚠️ {len(samples)} samples; PRD §9 Phase 1 asks for five to ten.")
        print(f"\ncpu_threads would resolve to {threads} — {threads_basis}")
        return 0

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not models:
        print("error: --models resolved to an empty list", file=sys.stderr)
        return 2
    if args.runs < 1:
        print("error: --runs must be >= 1", file=sys.stderr)
        return 2

    # Validate the sweep arguments BEFORE anything expensive. They are only used
    # at the very end, and a typo discovered after a twenty-minute benchmark has
    # already run is a twenty-minute typo.
    thread_values: list[int] = []
    sweep_model = ""
    if args.sweep_threads is not None:
        try:
            thread_values = parse_thread_list(args.sweep_threads, threads)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        sweep_model = args.sweep_model or models[0]

    env = describe_machine() | library_versions()
    if env.get("faster_whisper") == "NOT INSTALLED":
        print(
            "error: faster-whisper is not importable. Run this with the probe venv:\n"
            "    .venv/bin/python scripts/bench_engines.py",
            file=sys.stderr,
        )
        return 2

    if args.trim and args.vad_filter:
        print(
            "error: --trim and --vad-filter both remove silence, and combining "
            "them would trim twice and attribute the cost to the engine.",
            file=sys.stderr,
        )
        return 2

    try:
        audio = load_audio(samples)
    except CorpusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.trim:
        audio, fell_back = trim_corpus(samples, audio)
        if verbose:
            print("trimmed every sample once with the product's VAD, outside the "
                  "timed region", flush=True)
        if fell_back:
            print(f"  ⚠️  no speech detected in {', '.join(fell_back)} — passed "
                  f"through whole (guard 1)", flush=True)

    if verbose:
        print(f"benchmarking {len(models)} models over {len(samples)} samples, "
              f"{args.runs} timed runs each (cpu_threads={threads})", flush=True)
        print("first use of a model downloads its weights — that is benchmark-time "
              "network traffic, not runtime (G3 concerns the shipped daemon).", flush=True)

    results = [
        run_model(
            model,
            samples,
            audio,
            cpu_threads=threads,
            runs=args.runs,
            beam_size=args.beam_size,
            vad_filter=args.vad_filter,
            verbose=verbose,
        )
        for model in models
    ]

    sweep_results: list[ModelResult] = []
    if thread_values:
        if verbose:
            print(f"\nsweeping cpu_threads {thread_values} on {sweep_model}", flush=True)
        for value in thread_values:
            sweep_results.append(
                run_model(
                    sweep_model,
                    samples,
                    audio,
                    cpu_threads=value,
                    runs=args.runs,
                    beam_size=args.beam_size,
                    vad_filter=args.vad_filter,
                    verbose=verbose,
                )
            )

    print_console_report(
        results, samples, env, threads, threads_basis,
        args.runs, args.beam_size, args.vad_filter,
    )

    markdown = build_markdown(
        results, samples, env, threads, threads_basis,
        args.runs, args.beam_size, args.vad_filter,
        sweep_results or None,
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(markdown, encoding="utf-8")
        print(f"markdown report written to {args.out}")
    else:
        print("--- markdown (paste into docs/adr/0001-engine-selection.md) " + "-" * 16)
        print(markdown)

    # A failed model load is not a failed benchmark, but it must not exit 0 —
    # CI or a wrapper script should be able to tell that a row is missing.
    return 1 if any(r.error for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
