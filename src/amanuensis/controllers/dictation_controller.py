"""The loop: press, capture, release, transcribe, persist, inject.

This is where §6.3's concurrency model stops being a table. Three threads meet
here and the rules between them are the whole design:

| Concern | Thread |
|---|---|
| the status indicator's run loop | main |
| `start_session` / `end_session` | the OS event tap |
| transcribe, post-process, persist, inject | one worker, serial |

**`end_session()` must not block.** It is called from the event tap, and a
blocked event tap on macOS is not a slow application — it is a machine whose
keyboard has stopped responding. So it stops the microphone, builds a session,
puts it on a queue and returns. The `-> DictationSession` in §6.3's contract is
the session object, populated asynchronously; the return tells the caller
nothing about whether the work is done.

**Completion is signalled, never polled.** The worker writes every field and
sets `session.completed` *last*. Any thread that observes the event set is
guaranteed a fully written session, and nothing else guards the fields. That
one ordering is the entire synchronisation story — it is also the rule most
likely to be broken by a well-meaning edit that moves a `set()` earlier "so
the tray updates sooner".

**The worker is serial, and the focus is checked at injection time.** Because
`end_session()` does not block, sessions can overlap: dictate twice quickly and
session N's text can land in whatever window has focus when the worker reaches
it. §6.3's v1 resolution is not to re-target — raising another application on
the user's behalf is a larger intrusion than declining to type — so a session
whose focused application changed is **written to history and not injected**.
The words survive; they just do not go somewhere the user did not ask for.

What this class does *not* do, and the boundary is worth restating because it
is the one that erodes first (§6.2): it does not know how injection works on
macOS, does not know which model is loaded, does not format text, and does not
draw anything. It holds the state §5.4 requires be visible and hands it to a
callback; what renders it is not its business.

§8's persist-before-inject ordering lives in `deliver` below. It was written in
`cli.py` in Phase 2a and moved here unchanged — the guarantee changed address,
not content, and `cli.py` now imports it so there is exactly one copy.
"""

from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

from amanuensis import guard
from amanuensis.models.results import GuardOutcome, InjectionResult, Transcription
from amanuensis.models.session import DictationSession
from amanuensis.postprocess.base import TracedPostProcessor
from amanuensis.postprocess.vocabulary import VocabularyLoader

if TYPE_CHECKING:  # pragma: no cover — import-time cost, not behaviour
    from collections.abc import Callable, Sequence

    from amanuensis.config import AppConfig
    from amanuensis.injection.base import TextInjector

__all__ = [
    "DictationController",
    "DictationState",
    "TranscriptStore",
    "deliver",
]

#: How long `shutdown()` waits for the worker to finish the session it is on.
#: Generous: the worst case is a transcription already in flight, and killing
#: that would lose the injection §8 exists to protect.
_SHUTDOWN_TIMEOUT_S = 30.0

#: §2's measured decode model — `transcribe_ms ≈ 48.8 + 13.69 × seconds`, taken
#: across 0.7–43.4 s of speech at the Phase 2b gate. Used to *predict* the cost
#: of §5.7's retry before paying it, which is the only useful moment: a ceiling
#: checked after the fact is a report, not a budget.
#:
#: These are Tier A figures on one machine. A slower machine under-predicts and
#: retries where it should not, which costs latency on an already-degraded path
#: and never costs a transcript. That is the right direction for the error.
_DECODE_INTERCEPT_MS = 48.8
_DECODE_MS_PER_SECOND = 13.69

#: How long between retention sweeps on the worker thread.
#:
#: `retain_days` used to be enforced only at daemon start, while the whole
#: argument for re-reading `vocabulary.toml` on mtime is that this daemon is
#: **long-lived** (objection O11). Both cannot be true: a daemon running for a
#: fortnight would never have expired a row. This is a clock comparison on a
#: thread that already exists rather than a second timer thread.
_SWEEP_INTERVAL_S = 24 * 60 * 60.0


class DictationState(StrEnum):
    """What the user must be able to see without opening a menu (§5.4).

    Exactly §5.4's values, and no more. A state the indicator cannot render is
    a state the user cannot read, and §5.4 makes ambiguity about the microphone
    a privacy problem rather than a polish one.

    A `StrEnum` so it can be logged and compared against a literal without a
    conversion that a future reader would have to check.
    """

    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    #: §5.7's retry produced the text at the cursor, which means it was decoded
    #: *without* the vocabulary bias the user configured. Distinct from IDLE
    #: because the transcript was substituted, and distinct from ERROR because
    #: they did get their words (§5.4, 2026-08-05).
    RECOVERED = "recovered"
    ERROR = "error"


class TranscriptStore(Protocol):
    """The two operations `deliver` needs from a history store.

    Narrower than `HistoryStore` on purpose: the ordering below is the §8
    guarantee, and a protocol that admitted `purge` would invite a future
    version of this function to do something other than persist and mark.
    """

    def write_pending(self, session: DictationSession) -> bool: ...

    def mark_injected(self, session: DictationSession) -> None: ...


def deliver(
    session: DictationSession,
    history: TranscriptStore,
    injector: TextInjector,
    focus_at_capture: str | None = None,
) -> InjectionResult:
    """Persist, then inject, then mark. In that order, always.

    PRD §8: *never lose a transcript — write to history before injection*.
    Everything else in this function is subordinate to those three calls being
    in that sequence, and the sequence is what the test asserts.

    Four deliberate choices, three of them Phase 2a's and unchanged:

    **`mark_injected` runs only on success.** Failure is the absence of a
    call, not a branch — the case the guarantee protects needs no code, which
    means it cannot be broken by editing the code that handles success.

    **An injector that raises is caught.** The ABC says `inject` reports
    rather than raises, and a pyobjc bridge is exactly the sort of thing that
    violates a contract like that at the worst moment. The words are already
    safe by then; catching is what turns a traceback into a sentence and stops
    `mark_injected` running on a path that did not succeed.

    **Both stages are timed into `LatencyBreakdown`.** G1's clock starts at
    hotkey release and both of these happen after it (§2). A stage with no
    field to record into is a stage that cannot be defended when G1 is missed.

    **The focus check sits between the write and the injection** (new in Phase
    2b). `focus_at_capture` is the identity of the frontmost application when
    the user released the hotkey; when it is known and no longer current, the
    words are kept and nothing is typed (§6.3, objection A6). `None` on either
    side means *cannot tell*, which is not the same as *changed* — an injector
    with no way to answer must still inject.
    """
    started = time.perf_counter()
    persisted = history.write_pending(session)
    session.timings.persist_ms = (time.perf_counter() - started) * 1000.0

    if not persisted:
        # choice-story #7: a session that never reaches injection leaves
        # nothing behind. Pasting an empty string would still clobber the
        # clipboard, which is a real cost for no benefit whatsoever.
        return InjectionResult(
            succeeded=False, strategy="none", error="nothing was transcribed"
        )

    # Only asked when there is something to compare against. A caller with no
    # async gap — `manu transcribe --inject` is one — passes nothing, and the
    # injector is not troubled for an answer that would be discarded.
    if focus_at_capture is not None:
        focus_now = injector.focus_identity()
        if focus_now is not None and focus_now != focus_at_capture:
            return InjectionResult(
                succeeded=False,
                strategy="none",
                error=(
                    "the focused application changed between capture and "
                    f"injection ({focus_at_capture} -> {focus_now}); the "
                    "transcript was kept and not typed"
                ),
            )

    text = session.final_text or session.raw_transcript or ""

    started = time.perf_counter()
    try:
        result = injector.inject(text)
    except Exception as exc:  # the ABC forbids this; the bridge may not comply
        result = InjectionResult(
            succeeded=False,
            strategy="unknown",
            error=f"the injector raised: {exc!r}",
        )
    # The restore is subtracted rather than left in. `inject()` returns after
    # both, and §2 ends G1 when the text is fully present — charging the
    # clipboard cleanup to the number the user experiences would report a
    # 272 ms delivery as a 422 ms miss, which is exactly what the first real
    # dictation did before this split existed.
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    session.timings.restore_ms = result.restore_ms
    session.timings.inject_ms = max(0.0, elapsed_ms - result.restore_ms)

    if result.succeeded:
        history.mark_injected(session)
    return result


class DictationController:
    """Owns the loop. Knows nothing about macOS, models, or text formatting."""

    def __init__(
        self,
        config: AppConfig,
        engine: Any,
        injector: TextInjector,
        processors: Sequence[Any],
        history: TranscriptStore,
        capture: Any,
        detector: Any,
        on_state_change: Callable[[DictationState], None] | None = None,
        vocabulary: VocabularyLoader | None = None,
    ) -> None:
        self.config = config
        self.engine = engine
        self.injector = injector
        self.processors = list(processors)
        self.history = history
        self.capture = capture
        self.detector = detector
        # Optional so every existing caller and test keeps working. `None` means
        # no dictionary at all — not an empty one — and the difference shows up
        # in `_why_no_retry`, where "no bias was applied" is a reason and "the
        # bias was empty" is the same thing said differently.
        self.vocabulary = vocabulary
        self._on_state_change = on_state_change

        self._queue: queue.Queue[DictationSession | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._state = DictationState.IDLE
        #: The session currently being captured. Written on the event-tap
        #: thread only, which is the one thread that starts and ends captures.
        self._recording: dict[str, Any] | None = None
        #: Focused-application identity per queued session. Written on the
        #: event-tap thread and read on the worker's; the two touch different
        #: keys, and a lock held for one assignment would buy nothing and read
        #: as though something subtler were happening. Kept beside the queue
        #: rather than on the session because it is a fact about the delivery,
        #: not about the dictation — `to_history_row` should not grow a column
        #: for it.
        self._focus_by_session: dict[str, str | None] = {}
        #: Monotonic stamp of the last retention sweep. `None` until the daemon
        #: does the start-up one, so the first worker sweep is a full interval
        #: after start rather than on the first dictation.
        self._last_sweep_at: float | None = None

    # -- state -------------------------------------------------------------

    @property
    def state(self) -> DictationState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _set_state(self, state: DictationState) -> None:
        """Record the state and tell whoever is drawing it.

        The callback is the UI's, and a UI that raises must not stop dictation
        — §6.2 makes the tray a status surface with no business logic, and that
        has to hold in the failure direction too.
        """
        self._state = state
        if self._on_state_change is None:
            return
        try:
            self._on_state_change(state)
        except Exception:
            pass

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Load the model, warm the injector, and start the worker.

        Both costs are paid here rather than on the user's first dictation:
        `TranscriptionEngine.load()` is documented blocking and takes seconds,
        and the first `inject()` cost 165.8 ms before `warm_up` existed
        (Phase 2a, finding 2).
        """
        if self.is_running:
            return

        self.detector.load()
        self.engine.load()
        self.engine.warm_up()
        self.injector.warm_up()

        worker = threading.Thread(
            target=self._drain, name="amanuensis-worker", daemon=True
        )
        self._worker = worker
        worker.start()
        self._set_state(DictationState.IDLE)

    def shutdown(self) -> None:
        """Stop the worker and release the microphone. Idempotent.

        The microphone is released first and unconditionally. A daemon that
        exits still holding it is §5.4's failure in its purest form — the
        indicator is gone and the microphone may not be.
        """
        if self._recording is not None:
            self.abort_session()

        worker = self._worker
        if worker is None:
            return

        self._queue.put(None)
        worker.join(_SHUTDOWN_TIMEOUT_S)
        self._worker = None

    # -- the event-tap thread ----------------------------------------------

    def start_session(self) -> None:
        """The hotkey went down. Open the microphone and return.

        A second press while recording is a no-op rather than an error: this
        runs on the event tap, where raising is not a diagnostic anyone reads,
        and the listener's own transition guard already makes it unreachable.
        """
        if self._recording is not None:
            return

        self.capture.start()
        self._recording = {"started_at": datetime.now(UTC), "at": time.perf_counter()}
        self._set_state(DictationState.RECORDING)

    def end_session(self) -> DictationSession:
        """The hotkey came up. Hand the audio to the worker and return.

        **Does not wait for transcription.** The returned session is populated
        asynchronously; callers observe completion through `session.wait()`,
        never by polling its fields.

        Raises when no session is open. That is unreachable through
        `HotkeyListener`, which only emits transitions — and it is a raise
        rather than a fabricated empty session because a session with no audio
        in it would be indistinguishable from a real dictation of silence.
        """
        recording = self._recording
        if recording is None:
            raise RuntimeError("no session is being recorded; call start_session first")

        audio = self.capture.stop()
        self._recording = None

        timings_capture_ms = (time.perf_counter() - recording["at"]) * 1000.0
        session = DictationSession(
            id=uuid.uuid4().hex,
            started_at=recording["started_at"],
            audio=audio,
            sample_rate=self.config.audio.sample_rate,
        )
        session.timings.capture_ms = timings_capture_ms

        # Read on this thread, not the worker's: this is the application the
        # user was looking at when they released the key, and by the time the
        # worker reaches the session it may not be (§6.3, objection A6).
        focus = self.injector.focus_identity()

        # Stashed alongside rather than on the session: it is a fact about the
        # delivery, not about the dictation, and `to_history_row` should not
        # grow a column for it.
        #
        # **Before the queue put, and the order is the point** (Phase 3,
        # objection O2). Queueing first makes the session visible to the worker
        # while its focus is not yet recorded, and `deliver` skips the focus
        # check entirely on a `None` — so losing that race does not degrade the
        # check, it *disables* it, and §6.3's protection against injecting into
        # an application the user has switched away from silently stops
        # applying. A safety check turned off by timing rather than by
        # configuration is the kind nobody notices.
        self._focus_by_session[session.id] = focus

        self._set_state(DictationState.TRANSCRIBING)
        self._queue.put(session)
        return session

    def abort_session(self) -> None:
        """Throw the capture away. Nothing is persisted (choice-story #7).

        §8's guarantee protects words the user committed to. An aborted
        session has no such claim, and §5.5 is explicit that every misfired
        session used to be written to disk before the user had seen it.
        """
        if self._recording is None:
            return
        self._recording = None
        try:
            self.capture.stop()
        finally:
            self._set_state(DictationState.IDLE)

    # -- the worker thread -------------------------------------------------

    def _maybe_sweep(self) -> None:
        """Expire old transcripts, at most once a day, on the worker.

        Runs *after* a session rather than before: the sweep takes a write lock
        and the one call that must not wait on it is the §8 pre-injection write.
        Failures are swallowed — a retention sweep that cannot run is a disk
        that fills, and raising here would take the microphone down with it.
        """
        sweep = getattr(self.history, "sweep", None)
        if sweep is None:
            return
        now = time.monotonic()
        if (
            self._last_sweep_at is not None
            and now - self._last_sweep_at < _SWEEP_INTERVAL_S
        ):
            return
        self._last_sweep_at = now
        try:
            sweep()
        except Exception:
            pass

    def _drain(self) -> None:
        while True:
            session = self._queue.get()
            if session is None:
                return
            try:
                self._process(session)
            finally:
                # Last, always, and after every field is written. A thread
                # that sees this set is guaranteed a fully populated session.
                session.completed.set()

    def _judge(
        self,
        session: DictationSession,
        decoded: Transcription,
        trimmed: Any,
        *,
        boost: tuple[str, ...] = (),
    ) -> Transcription:
        """Run §5.7's guard, and the retry if one is both advised and payable.

        Deciding *whether* to spend a second decode is scheduling, which is why
        it lives here rather than in `guard.py`: it needs the engine, the clock
        and the config. Choosing between the two decodes once both exist is a
        judgement about transcripts and stays in `guard.resolve`.
        """
        first = guard.evaluate(
            decoded.text,
            decoded_seconds=decoded.decoded_seconds,
            retained_seconds=trimmed.retained_seconds,
            padding_seconds=trimmed.padding_seconds,
            fell_back=trimmed.fell_back,
            config=self.config.guard,
        )
        if not first.retry_advised:
            session.guard = guard.resolve(first, None)
            return decoded

        # "Was anything biasing this decode?" rather than "is one config key
        # non-empty" (objection O3). `[boost]` supplies bias while
        # `initial_prompt` is empty, which is the configuration §5.6 recommends —
        # and the old check answered "nothing to drop" there, making the guard's
        # whole recovery path unreachable exactly where the new bias lives.
        biased = bool(self.config.engine.initial_prompt) or bool(boost)
        refusal = self._why_no_retry(trimmed.retained_seconds, biased=biased)
        if refusal is not None:
            session.guard = replace(guard.resolve(first, None), reason=refusal)
            return decoded

        # `biased=False` drops `initial_prompt`; passing no boost drops the
        # other half. The retry has to shed all of it or it is the same decode.
        retried = self.engine.transcribe(
            trimmed.audio, session.sample_rate, biased=False
        )
        second = guard.evaluate(
            retried.text,
            decoded_seconds=retried.decoded_seconds,
            retained_seconds=trimmed.retained_seconds,
            padding_seconds=trimmed.padding_seconds,
            fell_back=trimmed.fell_back,
            config=self.config.guard,
        )
        verdict = guard.resolve(first, second)
        session.guard = verdict
        return retried if verdict.chose_retry else decoded

    def _why_no_retry(self, retained_seconds: float, *, biased: bool) -> str | None:
        """`None` when a retry is worth running, otherwise why it is not.

        Two refusals, and both would otherwise be silent. Re-decoding with no
        bias configured is mechanically the same call — `beam_size = 1` is
        greedy, so identical inputs return identical words — and reporting it
        as a recovery attempt would be an instrument describing work it did not
        do. And the cost is predicted from §2's measured model rather than
        discovered afterwards, because the point is to decline it.
        """
        settings = self.config.guard
        if settings.retry_below_coverage <= 0.0:
            return "the retry is disabled (retry_below_coverage = 0)"
        if not biased:
            return (
                "nothing biased this decode, so an unbiased retry would be "
                "the same decode — nothing to drop"
            )
        predicted_ms = _DECODE_INTERCEPT_MS + _DECODE_MS_PER_SECOND * retained_seconds
        if predicted_ms > settings.retry_max_latency_ms:
            return (
                f"an unbiased retry would cost about {predicted_ms:.0f} ms, over "
                f"retry_max_latency_ms ({settings.retry_max_latency_ms}) — skipped"
            )
        return None

    def _process(self, session: DictationSession) -> None:
        """Transcribe, post-process, persist, inject. On the worker thread.

        Every failure is caught and recorded on the session rather than
        raised: this is the bottom of a thread, so an exception here vanishes
        into a stack nobody reads and leaves the indicator claiming the
        microphone is live.
        """
        focus = self._focus_by_session.pop(session.id, None)
        try:
            # ONE read point for `vocabulary.toml`, here, before the decode.
            # `[boost]` needs the terms before transcription and `[replace]`
            # does not care, so the earlier point serves both halves of §5.6
            # from one snapshot (objection O10).
            boost: tuple[str, ...] = ()
            vocabulary_error: str | None = None
            if self.vocabulary is not None:
                started = time.perf_counter()
                loaded = self.vocabulary.refresh()
                boost = loaded.terms_for(focus)
                vocabulary_error = self.vocabulary.error
                session.timings.vocab_ms = (time.perf_counter() - started) * 1000.0

            started = time.perf_counter()
            trimmed = self.detector.trim(session.audio, session.sample_rate)
            session.timings.vad_ms = (time.perf_counter() - started) * 1000.0

            started = time.perf_counter()
            decoded = self.engine.transcribe(
                trimmed.audio, session.sample_rate, boost=boost
            )
            session.timings.transcribe_ms = (time.perf_counter() - started) * 1000.0
            session.engine = f"{self.config.engine.backend}:{self.engine.model_name}"

            started = time.perf_counter()
            decoded = self._judge(session, decoded, trimmed, boost=boost)
            session.timings.guard_ms = (time.perf_counter() - started) * 1000.0
            session.raw_transcript = decoded.text
            verdict = session.guard
            if verdict is not None and verdict.outcome is GuardOutcome.FAILED:
                # §5.7. The words are written by `deliver` below and reachable
                # with `manu history --last`; what does not happen is putting a
                # transcript known to be destroyed at the user's cursor, where
                # noticing and undoing it is their problem.
                started = time.perf_counter()
                self.history.write_pending(session)
                session.timings.persist_ms = (time.perf_counter() - started) * 1000.0
                session.error = verdict.reason
                self._set_state(DictationState.ERROR)
                return

            started = time.perf_counter()
            text = session.raw_transcript
            fired: list[str] = []
            for processor in self.processors:
                try:
                    # Feature detection, not a required method (§6.3's
                    # `TracedPostProcessor`). A processor that can say which of
                    # its rules acted returns that alongside the text, and the
                    # controller writes it to the session — `process` stays pure
                    # with respect to the session and there is no shared slot to
                    # go stale across the early returns above (objection O8).
                    if isinstance(processor, TracedPostProcessor):
                        text, acted = processor.process_traced(text, session)
                        fired.extend(acted)
                    else:
                        text = processor.process(text, session)
                except Exception as exc:
                    # §6.3 and `postprocess/base.py` both promise this, and
                    # neither was true until Phase 3 (objection O1): the chain
                    # runs *before* the §8 write, and the outer handler below
                    # returns before `deliver` — which is the only caller of
                    # `write_pending` on this path. So a raising processor used
                    # to persist nothing and inject nothing.
                    #
                    # Abandon the chain, keep the last good text, name the
                    # processor, and fall through to `deliver` so the words are
                    # written and delivered anyway. The error is recorded rather
                    # than swallowed, because a chain that silently stops is a
                    # transcript the user cannot explain.
                    name = getattr(processor, "name", type(processor).__name__)
                    session.error = (
                        f"the {name!r} post-processor raised "
                        f"({type(exc).__name__}: {exc}); the chain was "
                        "abandoned and the text before it was used"
                    )
                    break
            session.timings.postprocess_ms = (time.perf_counter() - started) * 1000.0
            session.fired_entries = tuple(fired)
            if self.processors:
                session.final_text = text

            if vocabulary_error is not None and session.error is None:
                # The dictation succeeded; their file did not parse. Recorded on
                # the session so it reaches history.db and the indicator, because
                # a reload that fails silently is C3's original complaint one
                # layer down — the user edits the file, nothing changes, and
                # nothing says why (choice-story #5).
                session.error = f"vocabulary.toml was not reloaded: {vocabulary_error}"

            result = deliver(session, self.history, self.injector, focus)
            if not result.succeeded and result.error is not None:
                # Not necessarily a failure the user loses anything to — §8's
                # write already ran — but the tray has to be able to say so.
                session.error = result.error
        except Exception as exc:
            session.error = f"{type(exc).__name__}: {exc}"
            self._set_state(DictationState.ERROR)
            return

        self._maybe_sweep()

        if session.error:
            self._set_state(DictationState.ERROR)
        elif session.guard is not None and session.guard.chose_retry:
            self._set_state(DictationState.RECOVERED)
        else:
            self._set_state(DictationState.IDLE)
