"""One press-speak-release cycle, and everything that happened to it.

`DictationSession` is mutable on purpose, and that is the one thing worth
knowing before reading it. §6.3's concurrency model has `end_session()` hand
the buffer to a worker thread and return immediately — it must not block the
OS event tap. So the session object is what callers observe completion
through; the call returning tells them nothing. Freezing it would force
either a blocking call or a second object to carry the result.

**Completion is signalled, never polled.** The session carries a
`threading.Event`, and the ordering rule is the entire synchronisation story:
the worker writes every field *first* and sets the event *last*, so any thread
that observes the event set is guaranteed a fully written session. Nothing else
guards the fields, and nothing else needs to.

An earlier revision of PRD §6.3 said "callers observe completion through the
session" while the session had no flag, no event and no lock — which left
spinning on a mutable dataclass across a thread boundary as the only available
reading, and that is precisely what Half-Sync/Half-Async is chosen to avoid.
The gap was found by adversarial review (objection A6) after this file had
already been written to the contract as stated.

`LatencyBreakdown` exists because G1 cannot be defended without per-stage
timings. It is a product requirement, not a debugging nicety (PRD §5.5), and
it carries two summary properties that a later reader will be tempted to
collapse into one. Resist that: `g1_ms` is gated, `total_ms` is diagnostics.
Asserting G1 on `total_ms` compares a ~10,400 ms figure against a 400 ms
budget and fails unconditionally, because capture time is the length of the
utterance.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
from numpy.typing import NDArray

__all__ = ["DictationSession", "LatencyBreakdown"]


@dataclass(slots=True)
class LatencyBreakdown:
    """Per-stage timings in milliseconds. Every stage records into this."""

    #: Excluded from G1 — G1's clock starts at hotkey release, and capture is
    #: the user talking. Retained because it is needed to relate a measured
    #: latency to the utterance length it came from.
    capture_ms: float = 0.0
    transcribe_ms: float = 0.0
    postprocess_ms: float = 0.0
    inject_ms: float = 0.0

    @property
    def g1_ms(self) -> float:
        """transcribe + postprocess + inject. The number G1 is gated on."""
        return self.transcribe_ms + self.postprocess_ms + self.inject_ms

    @property
    def total_ms(self) -> float:
        """Every stage including capture. Diagnostics — never assert G1 here."""
        return self.capture_ms + self.g1_ms


@dataclass(slots=True)
class DictationSession:
    """A single dictation, from hotkey press to text at the cursor."""

    id: str
    started_at: datetime
    audio: NDArray[np.float32] | None
    sample_rate: int
    raw_transcript: str | None = None
    final_text: str | None = None
    timings: LatencyBreakdown = field(default_factory=LatencyBreakdown)
    error: str | None = None
    #: Set by the worker, *last*, after every field above is written. A thread
    #: that sees this set is guaranteed a fully populated session; that ordering
    #: is the only synchronisation rule in the model (§6.3).
    completed: threading.Event = field(default_factory=threading.Event)

    def wait(self, timeout: float | None = None) -> bool:
        """Block until the worker finishes this session.

        Returns True if it completed, False on timeout — the same contract as
        `threading.Event.wait`, deliberately, so a caller who already knows that
        API has nothing new to learn.

        Never call this from the event-tap thread. Blocking that thread on macOS
        stalls input system-wide, which is the reason `end_session()` is
        non-blocking in the first place.
        """
        return self.completed.wait(timeout)

    def duration_seconds(self) -> float:
        """How long the user spoke. Zero when nothing was captured."""
        if self.audio is None or self.sample_rate <= 0:
            return 0.0
        return len(self.audio) / self.sample_rate

    def to_history_row(self) -> dict[str, Any]:
        """The row `HistoryStore` persists *before* injection is attempted.

        Falls back to `raw_transcript` because §8's ordering puts the write
        ahead of post-processing having produced anything: a crash between
        transcription and injection must not cost the user their words.

        Audio never rides along. It is the sensitive artefact and is stored
        only behind `[history] store_audio`, by a different path (§5.5).
        """
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat(),
            "transcript": self.final_text or self.raw_transcript,
            "duration_seconds": self.duration_seconds(),
            "error": self.error,
            **asdict(self.timings),
        }
