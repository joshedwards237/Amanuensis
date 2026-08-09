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

from amanuensis.models.results import GuardVerdict

__all__ = ["DictationSession", "LatencyBreakdown"]


@dataclass(slots=True)
class LatencyBreakdown:
    """Per-stage timings in milliseconds. Every stage records into this."""

    #: Excluded from G1 — G1's clock starts at hotkey release, and capture is
    #: the user talking. Retained because it is needed to relate a measured
    #: latency to the utterance length it came from.
    capture_ms: float = 0.0
    #: Silence trimming (§7.4). Added in Phase 1, and *inside* G1: the clock
    #: starts at release and trimming happens after it. Kept as its own field
    #: rather than folded into `transcribe_ms` because §7.4 calls trimming the
    #: dominant latency lever — burying the dominant lever inside the stage it
    #: exists to shrink would make this breakdown useless for the one argument
    #: it was built to support.
    vad_ms: float = 0.0
    #: Re-reading `vocabulary.toml` when its mtime changed, and recompiling the
    #: replacement alternation. Inside G1 and inside `g1_ms`: the read happens at
    #: the top of the worker, before trimming, so it is time between hotkey
    #: release and text at the cursor. §6.3's standing rule is that a stage
    #: inside that window needs a field — this is the FIFTH phase running in
    #: which that rule was broken by a new stage.
    #:
    #: Deliberately not excluded as "the user's own cost". §2's two exclusions
    #: (`capture_ms`, `restore_ms`) are both justified by falling *outside* the
    #: release-to-text window, never by whose fault the time is, and admitting
    #: the second justification would let any future stage escape the same way.
    vocab_ms: float = 0.0
    transcribe_ms: float = 0.0
    postprocess_ms: float = 0.0
    #: The §8 pre-injection write. Added in Phase 2a, and *inside* G1 for the
    #: same reason `vad_ms` is: the clock starts at hotkey release and the
    #: write happens after it. Kept separate from `inject_ms` because the two
    #: have different remedies — a slow write is a storage problem, a slow
    #: injection is a target-application problem, and a combined figure would
    #: send a reader to the wrong one.
    #: §5.7's check and any retry it triggered. Inside `g1_ms` — the retry is
    #: a second decode on the path between hotkey release and text at the
    #: cursor. Added 2026-08-05, the fourth phase running in which a stage
    #: inside G1's window had nowhere to be recorded.
    guard_ms: float = 0.0
    persist_ms: float = 0.0
    inject_ms: float = 0.0
    #: Putting the user's clipboard back after a paste (§7.3). Recorded, and
    #: deliberately **outside** `g1_ms`: §2 ends G1 when the text is *fully
    #: present in the focused application*, and the restore runs strictly
    #: after that, while the user is already reading their words. Phase 2a
    #: measured a real dictation at 180.3 ms of `inject_ms`, roughly 150 of
    #: which was `restore_delay_ms` sleeping — enough to report a 272 ms
    #: delivery as a 422 ms G1 miss.
    restore_ms: float = 0.0

    @property
    def asr_ms(self) -> float:
        """vad + transcribe. What §7.2's tier check compares against 350/700.

        The tier thresholds are the transcribe *share* of G1 measured with VAD
        on ("a check run in a configuration the product does not use measures
        nothing"), so the quantity they bound is trimming plus decoding, not
        decoding alone.
        """
        return self.vad_ms + self.transcribe_ms

    @property
    def g1_ms(self) -> float:
        """Every stage after hotkey release. The number G1 is gated on.

        vad + transcribe + postprocess + persist + inject. `persist_ms` is in
        here and deliberately *not* in `asr_ms`: §7.2's tier thresholds bound
        trimming plus decoding, and letting a storage hiccup move a machine's
        recorded tier would make the tier mean something other than what it
        was measured to mean.
        """
        return (
            self.asr_ms
            + self.vocab_ms
            + self.guard_ms
            + self.postprocess_ms
            + self.persist_ms
            + self.inject_ms
        )

    @property
    def total_ms(self) -> float:
        """Every stage including capture. Diagnostics — never assert G1 here.

        `restore_ms` is in here and not in `g1_ms`. It is real time the
        process spends and a restore that never completes is a clipboard the
        user does not get back — but it is not time the user waits for their
        text, which is the only thing G1 is about.
        """
        return self.capture_ms + self.g1_ms + self.restore_ms


@dataclass(slots=True)
class DictationSession:
    """A single dictation, from hotkey press to text at the cursor."""

    id: str
    started_at: datetime
    audio: NDArray[np.float32] | None
    sample_rate: int
    raw_transcript: str | None = None
    final_text: str | None = None
    #: Which engine produced `raw_transcript`, as `backend:model` — §5.5 lists
    #: it among what history stores. A transcript whose engine is unknown
    #: cannot be re-judged when the engine changes, and ADR 0001 is explicitly
    #: revisitable if G1 headroom becomes binding.
    engine: str = ""
    timings: LatencyBreakdown = field(default_factory=LatencyBreakdown)
    #: §5.7's verdict. `None` means the worker never reached the check — which
    #: is different from the check declining to judge, and that difference is
    #: why `GuardOutcome.SKIPPED` exists rather than being spelled `None`.
    guard: GuardVerdict | None = None
    #: Which post-processing rules and dictionary entries actually acted on this
    #: transcript. Written by the chain runner from `process_traced`'s return
    #: value, never by a processor — `process` is pure with respect to the
    #: session and the trace is deliberately not an exception to that
    #: (objection O8). Empty when no processor offered the capability, which is
    #: a different statement from "nothing fired" and is why the gate reports
    #: the chain alongside it.
    fired_entries: tuple[str, ...] = ()
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

        Two of the timings are structurally zero here and that is not a bug:
        the row is written *before* injection, so `inject_ms` has not happened
        and `persist_ms` is the duration of the write producing this very row.
        `HistoryStore.mark_injected` completes them afterwards.
        """
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat(),
            "transcript": self.final_text or self.raw_transcript,
            # The decoder's own words, always — not "when they differ". A
            # column populated only sometimes cannot answer "did the processors
            # change what I said?", which is the question it exists for. Before
            # Phase 3 this shared the slot above, so the raw output was lost the
            # moment any processor ran: §7.5's first Phase 5 constraint is "raw
            # transcript persisted", and the schema could not express it
            # (dictionary objection O1).
            "raw_transcript": self.raw_transcript,
            "duration_seconds": self.duration_seconds(),
            "engine": self.engine,
            "error": self.error,
            # Flattened rather than nested because the row is a SQL row. Only
            # the three quantities §5.7's gate has to report are stored: the
            # outcome, the coverage that produced it, and the denominator that
            # makes a *non*-firing guard diagnosable (objection O10).
            "guard_outcome": str(self.guard.outcome) if self.guard else None,
            "guard_coverage": self.guard.coverage if self.guard else None,
            "guard_retained_seconds": (
                self.guard.retained_seconds if self.guard else None
            ),
            # Comma-joined rather than JSON: the only consumer is a person
            # reading a history row or a gate record, and `rules, vocabulary`
            # is legible where `["rules", "vocabulary"]` is a format to decode.
            # NULL when nothing fired, so "no rule acted" and "the empty list
            # was stored" are not the same value.
            "fired_entries": ", ".join(self.fired_entries) or None,
            **asdict(self.timings),
        }
