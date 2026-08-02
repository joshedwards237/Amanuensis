"""The install-time tier check (PRD §7.2).

What a tier is
--------------
A **recorded fact about a machine**, not a gate condition. Nothing in §9
rejects on it.

> **Tier A** — the check measures p50 ≤ 350 ms and p95 ≤ 700 ms for the ASR
> stage. G1 binds and is published as a guarantee.
>
> **Tier B** — it does not. G1-CPU applies: the number is measured, published,
> and told to the user at install. It does not halt the project.

The reasoning that produced this shape is worth keeping close to the code,
because both halves of it were mistakes the project actually made.

**The thresholds are absolute, not a restatement of G1.** Tier A once meant
"transcribes inside G1's budget on this machine", which made §9's Phase 1 gate
— *rejects if G1 is missed on a Tier A machine* — unreachable: a machine cannot
be both inside the budget by definition and miss it. The project's top risk had
a mitigation with no failing state (objection A1). The 350/700 figures are the
ASR **share** of G1's 400/800, leaving ~50 ms for post-processing and
injection. That residual is thin and known to be thin. Checking against the
full `g1_ms` budget instead would classify a machine measuring 380 ms as Tier A
and then ship it a gated promise it misses in normal operation — and the bias
would run consistently toward the tier that carries the guarantee.

**Both halves bind.** A p50 inside budget with a p95 outside it is Tier B. This
project has been burned twice by a bare median: a p50 from one clean sample
said GO, and the p95 over six real samples was fourteen times worse. Nine runs
rather than one median, because a single warmed median cannot see a
repetition-looping excursion — and that excursion, 541 ms to 6,039 ms on the
same model and sample, is this product's documented failure mode.

Decided once
------------
The tier is measured at install and written to disk. It is **not** re-derived
per session: a machine that is momentarily busy must not flip tiers, and a
machine near the boundary must not oscillate. Re-running the check is how a
tier changes.

What the check runs, and why each parameter is named
----------------------------------------------------
§7.2 specifies six parameters and each one moves the boundary, which is why
they are constants here rather than arguments with defaults:

* **A bundled reference clip**, not the user's voice — the check must be
  reproducible and must not require a microphone permission before first use.
* **VAD on**, matching runtime. Without it no candidate model passes p95 at
  all; a check run in a configuration the product does not use measures
  nothing.
* **One throwaway warm-up**, discarded. Steady state, not compile cost.
* **Nine runs**, reporting p50 and p95.
* **The `model = "auto"` selection**, already resolved.
* **Compared against the ASR-share thresholds**, not `g1_ms`.

Model download is deliberately *not* part of the timed check. It is a one-time
install cost and timing it would measure the network.
"""

from __future__ import annotations

import json
import math
import platform
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import numpy as np
from numpy.typing import NDArray

from amanuensis.audio.vad import VoiceActivityDetector
from amanuensis.config import default_data_dir
from amanuensis.engines.faster_whisper import FasterWhisperEngine

if TYPE_CHECKING:  # pragma: no cover
    from amanuensis.config import AppConfig

__all__ = [
    "TIER_A_P50_MS",
    "TIER_A_P95_MS",
    "TIER_CHECK_RUNS",
    "ReferenceClipMissingError",
    "TierResult",
    "classify",
    "default_clip_path",
    "read_tier",
    "record_tier",
    "run_tier_check",
    "tier_path",
]

#: The ASR share of G1's 400/800 ms, leaving ~50 ms p50 for post-processing and
#: injection. NOT G1 itself — see the module preamble.
TIER_A_P50_MS: Final = 350.0
TIER_A_P95_MS: Final = 700.0

#: §7.2. Nine, because a warmed median cannot see the excursion that is this
#: product's documented failure mode. Note that with nine observations the
#: nearest-rank p95 is the slowest run — that is a weak percentile and the
#: record says so rather than implying more precision than it has.
TIER_CHECK_RUNS: Final = 9

#: G1 is defined against a ten-second utterance (§2), so the clip is one.
EXPECTED_CLIP_SECONDS: Final = 10.0


class ReferenceClipMissingError(Exception):
    """The bundled reference clip is not on disk. See docs/gates/phase-1.md —
    §7.2 specifies a bundled clip and its provenance is not yet settled, so the
    repository does not ship one."""


@dataclass(frozen=True, slots=True)
class TierResult:
    """A tier plus everything needed to reproduce it or to distrust it.

    A tier with no model, thread count or date attached is a number with no
    claim behind it — §7.2 names six parameters for this check and all six move
    the boundary, so all six travel with the answer.
    """

    tier: str
    p50_ms: float
    p95_ms: float
    model: str
    cpu_threads: int
    runs: int
    clip_seconds: float
    measured_at: str
    machine: str

    @property
    def g1_binds(self) -> bool:
        """Tier A publishes G1 as a guarantee; Tier B publishes G1-CPU (§2)."""
        return self.tier == "A"


def classify(p50_ms: float, p95_ms: float) -> str:
    """Tier A or Tier B. Both halves bind; the boundary is inclusive."""
    inside = p50_ms <= TIER_A_P50_MS and p95_ms <= TIER_A_P95_MS
    return "A" if inside else "B"


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile.

    Nearest-rank rather than interpolated, deliberately: an interpolated p95
    over nine observations invents a value that was never measured, and the
    whole point of this check is not inventing values.
    """
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = math.ceil(q / 100.0 * len(ordered))
    return ordered[min(max(rank, 1), len(ordered)) - 1]


# ---------------------------------------------------------------------------
# Persistence — beside history.db, resolved through platformdirs
# ---------------------------------------------------------------------------


def tier_path() -> Path:
    """Where the recorded tier lives. Honours `$AMANUENSIS_DATA_DIR`."""
    return default_data_dir() / "tier.json"


def record_tier(result: TierResult) -> Path:
    """Write the tier, replacing any previous one.

    Replace rather than append: re-running the install check is how a tier
    changes (§7.2), and a history of tiers would invite someone to average
    them.
    """
    path = tier_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
    return path


def read_tier() -> TierResult | None:
    """The recorded tier, or None if this machine has never run the check.

    None is a third state, distinct from Tier B, and callers must not collapse
    it — "not measured" and "measured and slow" carry opposite obligations
    toward the user.

    A corrupt or partial file also reads as None. Losing a recorded tier costs
    one re-run of the install check; refusing to start the daemon over it would
    cost the user their dictation.
    """
    path = tier_path()
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return TierResult(**raw)
    except (OSError, ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# The measurement
# ---------------------------------------------------------------------------


def default_clip_path() -> Path:
    """The bundled reference clip, shipped inside the package."""
    return Path(__file__).parent / "assets" / "tier_check.wav"


def load_clip(path: Path | None = None) -> tuple[NDArray[np.float32], float]:
    """Decode the reference clip to 16 kHz mono float32.

    Decoding happens outside the timed region: the product transcribes samples
    already in memory from `AudioCapture`, so timing a file decode would
    measure disk I/O the product never pays.
    """
    from amanuensis.config import SUPPORTED_SAMPLE_RATE

    clip = path if path is not None else default_clip_path()
    if not clip.exists():
        raise ReferenceClipMissingError(
            f"the reference clip is not at {clip}.\n"
            "§7.2 specifies a bundled ten-second clip for this check; the "
            "repository does not ship one yet (its provenance is an open item "
            "— see docs/gates/phase-1.md).\n"
            "Generate one with `scripts/make_tier_clip.sh`, or point the check "
            "at your own recording with `manu install --clip PATH`."
        )

    from faster_whisper.audio import decode_audio

    audio = np.asarray(
        decode_audio(str(clip), sampling_rate=SUPPORTED_SAMPLE_RATE), dtype=np.float32
    )
    return audio, len(audio) / SUPPORTED_SAMPLE_RATE


def run_tier_check(
    config: AppConfig,
    clip_path: Path | None = None,
    runs: int = TIER_CHECK_RUNS,
) -> TierResult:
    """Measure this machine's ASR stage and classify it.

    Measures **trim + transcribe**, which is what the 350/700 thresholds bound.
    Both models are loaded and warmed first, so what is timed is steady state
    rather than one machine's ONNX initialisation averaged into nine decodes.
    """
    from amanuensis.config import SUPPORTED_SAMPLE_RATE

    audio, clip_seconds = load_clip(clip_path)

    detector = VoiceActivityDetector(config.vad)
    engine = FasterWhisperEngine(config.engine)
    detector.load()
    engine.load()
    engine.warm_up()

    # One throwaway pass through the real path, discarded. The engine's own
    # warm-up covers the decoder; this covers everything else the first call
    # touches, including the trim.
    _measure_once(detector, engine, audio, SUPPORTED_SAMPLE_RATE)

    latencies = [
        _measure_once(detector, engine, audio, SUPPORTED_SAMPLE_RATE)
        for _ in range(runs)
    ]

    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    return TierResult(
        tier=classify(p50, p95),
        p50_ms=round(p50, 1),
        p95_ms=round(p95, 1),
        model=engine.model_name,
        cpu_threads=engine.cpu_threads,
        runs=runs,
        clip_seconds=round(clip_seconds, 2),
        measured_at=datetime.now(UTC).isoformat(),
        machine=f"{platform.system()} {platform.release()} {platform.machine()}",
    )


def _measure_once(
    detector: VoiceActivityDetector,
    engine: FasterWhisperEngine,
    audio: NDArray[np.float32],
    sample_rate: int,
) -> float:
    """One ASR stage, in milliseconds: trim then transcribe."""
    start = time.perf_counter()
    trimmed = detector.trim(audio, sample_rate)
    engine.transcribe(trimmed.audio, sample_rate)
    return (time.perf_counter() - start) * 1000.0
