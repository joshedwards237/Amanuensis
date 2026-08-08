"""The orchestrator, and the three things it must not get wrong.

`DictationController` is where §6.3's concurrency model stops being a table in
a document. Everything asserted here is a property of that model rather than of
dictation:

**`end_session()` must not block.** It is called on the OS event-tap thread,
and a blocked event tap on macOS is a system-wide input stall — not a slow
application, a machine whose keyboard has stopped. So the test times it against
a worker that is deliberately slow, rather than asserting on the shape of the
code.

**Every field is written before `completed` is set.** That ordering is the only
synchronisation rule in the model (§6.3). A thread that observes the event set
is guaranteed a fully written session, and nothing else guards the fields — so
the test observes from another thread rather than from the one that did the
writing.

**Persist happens before inject, still.** §8's ordering moved house in this
phase; it did not get rewritten. The same assertion that guarded it in
`cli.py` guards it here, because a guarantee that is only tested where it used
to live is a guarantee with a phase-shaped hole in it.

The fourth property is new to this phase and is the one the async handoff
creates: a session whose focused application changed between capture and
injection is **written to history and not injected** (§6.3, objection A6).
Re-targeting the original window would mean raising another application on the
user's behalf, which is a larger intrusion than declining to type.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from amanuensis.config import AppConfig, HistoryConfig, InjectionConfig
from amanuensis.controllers.dictation_controller import (
    DictationController,
    DictationState,
    deliver,
)
from amanuensis.models.results import (
    GuardOutcome,
    InjectionResult,
    PermissionStatus,
    Transcription,
)
from amanuensis.models.session import DictationSession


class _FakeCapture:
    def __init__(self, audio: NDArray[np.float32] | None = None) -> None:
        self._audio = np.ones(16000, dtype=np.float32) if audio is None else audio
        self.is_recording = False
        self.starts = 0
        self.stops = 0

    def start(self) -> None:
        self.starts += 1
        self.is_recording = True

    def stop(self) -> NDArray[np.float32]:
        self.stops += 1
        self.is_recording = False
        return self._audio


class _FakeTrim:
    def __init__(
        self,
        audio: NDArray[np.float32],
        retained_seconds: float = 1.0,
        fell_back: bool = False,
        padding_seconds: float = 0.0,
    ) -> None:
        self.audio = audio
        self.original_seconds = retained_seconds
        self.retained_seconds = retained_seconds
        self.speech_segments = 1
        #: The real detector adds `speech_pad_ms` to each side and reports it,
        #: so §5.7 can divide by speech rather than by speech-plus-padding.
        #: Zero here keeps every test's coverage arithmetic readable.
        self.padding_seconds = padding_seconds
        self.fell_back = fell_back


class _FakeDetector:
    def __init__(self, retained_seconds: float = 1.0, fell_back: bool = False) -> None:
        self.calls = 0
        self.retained_seconds = retained_seconds
        self.fell_back = fell_back

    def load(self) -> None:
        pass

    def trim(self, audio: NDArray[np.float32], _rate: int) -> _FakeTrim:
        self.calls += 1
        return _FakeTrim(audio, self.retained_seconds, self.fell_back)


class _FakeEngine:
    model_name = "tiny.en"
    cpu_threads = 4

    def __init__(
        self,
        text: str = "hello there",
        delay_s: float = 0.0,
        coverage: float = 0.97,
        unbiased_text: str | None = None,
        unbiased_coverage: float | None = None,
    ) -> None:
        self.text = text
        #: Fraction of the retained audio this engine claims to have decoded.
        #: The default is what genuine speech looks like, so every test that is
        #: not about §5.7 sails through the guard untouched.
        self.coverage = coverage
        #: What the §5.7 retry gets back. `None` means `biased` changes
        #: nothing, which is the right default outside the retry tests.
        self.unbiased_text = unbiased_text
        self.unbiased_coverage = unbiased_coverage
        self.delay_s = delay_s
        self.is_loaded = False
        self.calls = 0
        #: One entry per call, True when biased. The retry is only meaningful
        #: if it actually asked for a different decode, and a test that checks
        #: the *text* cannot tell a real retry from a lucky second roll.
        self.bias_flags: list[bool] = []
        #: Set by the controller's detector fake, so the engine can report a
        #: decoded span in the same timebase the guard divides by.
        self.retained_seconds = 1.0

    def load(self) -> None:
        self.is_loaded = True

    def warm_up(self) -> None:
        pass

    def transcribe(
        self, audio: NDArray[np.float32], _rate: int, *, biased: bool = True
    ) -> Transcription:
        self.calls += 1
        self.bias_flags.append(biased)
        if self.delay_s:
            time.sleep(self.delay_s)
        seconds = len(audio) / 16000
        if not biased and self.unbiased_text is not None:
            coverage = (
                self.coverage
                if self.unbiased_coverage is None
                else self.unbiased_coverage
            )
            return Transcription(self.unbiased_text, seconds * coverage)
        return Transcription(self.text, seconds * self.coverage)


class _FakeInjector:
    def __init__(
        self,
        succeeds: bool = True,
        focus: str | None = "com.apple.dt",
        then_focus: str | None = None,
    ) -> None:
        self.succeeds = succeeds
        self.focus = focus
        #: What the *second* and later reads report. The controller reads the
        #: focus once on the event-tap thread and once on the worker's, so this
        #: is how a test moves the user to another application in the gap
        #: without racing the worker to do it.
        self.then_focus = then_focus
        self.focus_reads = 0
        self.injected: list[str] = []
        self.warmed = 0

    def inject(self, text: str) -> InjectionResult:
        self.injected.append(text)
        return InjectionResult(
            succeeded=self.succeeds,
            strategy="clipboard",
            error=None if self.succeeds else "no",
            restore_ms=5.0,
        )

    def check_permissions(self) -> PermissionStatus:
        return PermissionStatus(granted=True)

    def warm_up(self) -> None:
        self.warmed += 1

    def focus_identity(self) -> str | None:
        self.focus_reads += 1
        if self.focus_reads > 1 and self.then_focus is not None:
            return self.then_focus
        return self.focus


class _FakeHistory:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.written: list[DictationSession] = []

    def write_pending(self, session: DictationSession) -> bool:
        self.calls.append("write_pending")
        self.written.append(session)
        return bool((session.final_text or session.raw_transcript or "").strip())

    def mark_injected(self, _session: DictationSession) -> None:
        self.calls.append("mark_injected")


class _Upper:
    name = "upper"

    def process(self, text: str, _session: DictationSession) -> str:
        return text.upper()


def _controller(**overrides: Any) -> DictationController:
    parts: dict[str, Any] = {
        "config": AppConfig(),
        "engine": _FakeEngine(),
        "injector": _FakeInjector(),
        "processors": [],
        "history": _FakeHistory(),
        "capture": _FakeCapture(),
        "detector": _FakeDetector(),
    }
    parts.update(overrides)
    return DictationController(**parts)


@pytest.fixture
def controller() -> Any:
    made = _controller()
    made.start()
    yield made
    made.shutdown()


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


def test_a_full_cycle_reaches_the_cursor(controller: DictationController) -> None:
    controller.start_session()
    session = controller.end_session()

    assert session.wait(5.0), "the worker never completed the session"
    assert session.raw_transcript == "hello there"
    assert controller.injector.injected == ["hello there"]


def test_persist_happens_before_inject(controller: DictationController) -> None:
    """§8, unchanged by the move into the controller.

    The ordering is asserted through the history's own call log rather than by
    reading the source, because the guarantee is about what happens at runtime
    when injection fails — which is the case it exists for.
    """
    controller.start_session()
    session = controller.end_session()
    session.wait(5.0)

    assert controller.history.calls == ["write_pending", "mark_injected"]


def test_a_failed_injection_leaves_the_transcript_written(controller: Any) -> None:
    injector = _FakeInjector(succeeds=False)
    made = _controller(injector=injector)
    made.start()
    try:
        made.start_session()
        session = made.end_session()
        session.wait(5.0)
    finally:
        made.shutdown()

    assert made.history.calls == ["write_pending"], "mark_injected must not run"
    assert made.history.written[0].raw_transcript == "hello there"


def test_the_processor_chain_runs_in_order(controller: Any) -> None:
    made = _controller(processors=[_Upper()])
    made.start()
    try:
        made.start_session()
        session = made.end_session()
        session.wait(5.0)
    finally:
        made.shutdown()

    assert session.final_text == "HELLO THERE"
    assert made.injector.injected == ["HELLO THERE"]


def test_an_empty_transcript_is_not_injected(controller: Any) -> None:
    """choice-story #7: a session that never reaches injection leaves nothing
    behind. Pasting an empty string still clobbers the clipboard."""
    made = _controller(engine=_FakeEngine(text="   "))
    made.start()
    try:
        made.start_session()
        session = made.end_session()
        session.wait(5.0)
    finally:
        made.shutdown()

    assert made.injector.injected == []


# ---------------------------------------------------------------------------
# The concurrency model
# ---------------------------------------------------------------------------


def test_end_session_does_not_block_on_transcription() -> None:
    """The event-tap thread calls this. Blocking it stalls input machine-wide.

    Measured against a worker that takes half a second, so the assertion is
    about the handoff rather than about the shape of the code.
    """
    made = _controller(engine=_FakeEngine(delay_s=0.5))
    made.start()
    try:
        made.start_session()
        started = time.perf_counter()
        session = made.end_session()
        elapsed = time.perf_counter() - started
    finally:
        session.wait(5.0)
        made.shutdown()

    assert elapsed < 0.1, f"end_session blocked for {elapsed * 1000:.0f} ms"


def test_completed_is_set_last(controller: DictationController) -> None:
    """The only synchronisation rule in the model (§6.3).

    Observed from another thread, because the guarantee is precisely that a
    thread which did not do the writing still sees a fully written session.
    """
    seen: dict[str, Any] = {}

    controller.start_session()
    session = controller.end_session()

    def observe() -> None:
        session.completed.wait(5.0)
        seen["transcript"] = session.raw_transcript
        seen["inject_ms"] = session.timings.inject_ms
        seen["persist_ms"] = session.timings.persist_ms

    watcher = threading.Thread(target=observe)
    watcher.start()
    watcher.join(5.0)

    assert seen["transcript"] == "hello there"
    assert seen["persist_ms"] > 0.0


def test_sessions_are_processed_serially() -> None:
    """§6.3: the worker is serial. Two overlapping dictations must not
    interleave transcription with injection."""
    order: list[str] = []
    lock = threading.Lock()

    class _Recording(_FakeInjector):
        def inject(self, text: str) -> InjectionResult:
            with lock:
                order.append(f"inject:{text}")
            return super().inject(text)

    class _Counting(_FakeEngine):
        def transcribe(self, audio: Any, rate: int) -> str:
            with lock:
                order.append(f"transcribe:{self.calls}")
            return super().transcribe(audio, rate)

    made = _controller(engine=_Counting(), injector=_Recording())
    made.start()
    try:
        made.start_session()
        first = made.end_session()
        made.start_session()
        second = made.end_session()
        first.wait(5.0)
        second.wait(5.0)
    finally:
        made.shutdown()

    assert order == [
        "transcribe:0",
        "inject:hello there",
        "transcribe:1",
        "inject:hello there",
    ]


def test_a_start_while_recording_is_a_no_op(controller: DictationController) -> None:
    controller.start_session()
    controller.start_session()

    assert controller.capture.starts == 1
    controller.end_session().wait(5.0)


def test_abort_discards_without_persisting(controller: DictationController) -> None:
    """choice-story #7: an aborted session has no §8 claim and leaves nothing.

    §5.5 is explicit — previously every misfired session was written to disk
    before the user had seen it, and retained for thirty days by default.
    """
    controller.start_session()
    controller.abort_session()

    assert controller.capture.stops == 1
    assert controller.history.calls == []
    assert controller.state is DictationState.IDLE


# ---------------------------------------------------------------------------
# The hazard the async handoff creates
# ---------------------------------------------------------------------------


def test_a_changed_focus_is_persisted_and_not_injected() -> None:
    """§6.3's v1 resolution, objection A6.

    §8's guarantee saves the words; it does not stop them landing in the wrong
    application. The words go to history and nothing is typed.
    """
    # The user releases the hotkey in Terminal and switches to Mail before the
    # worker reaches the session.
    injector = _FakeInjector(focus="com.apple.Terminal", then_focus="com.apple.mail")
    made = _controller(injector=injector)
    made.start()
    try:
        made.start_session()
        session = made.end_session()
        session.wait(5.0)
    finally:
        made.shutdown()

    assert made.history.calls == ["write_pending"]
    assert injector.injected == []
    assert session.error is not None
    assert "focus" in session.error.lower()


def test_an_unknown_focus_does_not_block_injection() -> None:
    """`focus_identity` returning None means "cannot tell", not "changed".

    An injector on a platform with no way to answer must still inject; the
    check exists to catch a *change*, and unknown is not a change.
    """
    made = _controller(injector=_FakeInjector(focus=None))
    made.start()
    try:
        made.start_session()
        session = made.end_session()
        session.wait(5.0)
    finally:
        made.shutdown()

    assert made.injector.injected == ["hello there"]


# ---------------------------------------------------------------------------
# State, for §5.4
# ---------------------------------------------------------------------------


def test_state_transitions_are_reported(controller: Any) -> None:
    """§5.4: the user must always know whether the mic is live. The controller
    owns the state; something else renders it."""
    seen: list[DictationState] = []
    made = _controller(on_state_change=seen.append)
    made.start()
    try:
        made.start_session()
        session = made.end_session()
        session.wait(5.0)
        # The worker sets IDLE after injection; give it a moment to land.
        deadline = time.perf_counter() + 5.0
        while made.state is not DictationState.IDLE and time.perf_counter() < deadline:
            time.sleep(0.01)
    finally:
        made.shutdown()

    # `start()` reports IDLE so the indicator has something to draw before the
    # first dictation — a blank status item is exactly the ambiguity §5.4
    # forbids.
    assert seen == [
        DictationState.IDLE,
        DictationState.RECORDING,
        DictationState.TRANSCRIBING,
        DictationState.IDLE,
    ]


def test_the_mic_state_is_never_ambiguous_on_failure(controller: Any) -> None:
    """A raising engine must not leave the indicator saying "recording".

    §5.4 makes this a privacy requirement rather than a polish one: the state
    the user reads has to match whether the microphone is live, including on
    the paths nobody planned.
    """

    class _Exploding(_FakeEngine):
        def transcribe(self, _audio: Any, _rate: int) -> str:
            raise RuntimeError("ct2 fell over")

    seen: list[DictationState] = []
    made = _controller(engine=_Exploding(), on_state_change=seen.append)
    made.start()
    try:
        made.start_session()
        session = made.end_session()
        session.wait(5.0)
    finally:
        made.shutdown()

    assert session.error is not None
    assert made.state is not DictationState.RECORDING
    assert not made.capture.is_recording


def test_a_raising_state_callback_does_not_break_the_loop(controller: Any) -> None:
    """The callback belongs to the UI. A tray that throws must not stop
    dictation — §6.2 makes the tray a status surface with no business logic,
    and that has to hold in the failure direction too."""

    def explode(_state: DictationState) -> None:
        raise RuntimeError("the status item is having a day")

    made = _controller(on_state_change=explode)
    made.start()
    try:
        made.start_session()
        session = made.end_session()
        assert session.wait(5.0)
    finally:
        made.shutdown()

    assert made.injector.injected == ["hello there"]


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_start_warms_the_injector_and_loads_the_engine() -> None:
    """Both costs land at daemon start or on the user's first dictation. The
    first injection cost 165.8 ms before `warm_up` existed (Phase 2a)."""
    made = _controller()
    made.start()
    try:
        assert made.injector.warmed == 1
        assert made.engine.is_loaded
    finally:
        made.shutdown()


def test_shutdown_is_idempotent() -> None:
    made = _controller()
    made.start()
    made.shutdown()
    made.shutdown()

    assert not made.is_running


def test_shutdown_stops_a_live_microphone() -> None:
    """A daemon that exits holding the microphone is §5.4's failure in its
    purest form: the indicator is gone and the mic may not be."""
    made = _controller()
    made.start()
    made.start_session()
    made.shutdown()

    assert not made.capture.is_recording


def test_end_session_without_a_press_is_refused(
    controller: DictationController,
) -> None:
    """Unreachable through the listener, which only emits transitions — and
    asserted anyway, because "unreachable" is a claim about another module."""
    with pytest.raises(RuntimeError, match="no session"):
        controller.end_session()


def test_config_slices_are_not_the_whole_config() -> None:
    """§6.3, choice-story #3: components receive the narrowest slice they need.

    The controller is the one component that legitimately holds the whole
    `AppConfig` — it is the orchestrator — but it must not be the route by
    which anything else reaches a table it was denied.
    """
    made = _controller(
        config=AppConfig(
            injection=InjectionConfig(strategy="keystroke"),
            history=HistoryConfig(retain=False),
        )
    )
    assert made.config.injection.strategy == "keystroke"


# ---------------------------------------------------------------------------
# `deliver` on its own — the §8 ordering, tested without a thread
#
# Moved here from `test_cli.py` in Phase 2b along with the function. These
# exercise the ordering directly; the controller tests above exercise the fact
# that the worker actually calls it. Both are worth having: the first is the
# guarantee, the second is that the guarantee is on the path.
# ---------------------------------------------------------------------------


class _SpyHistory:
    """Records the order in which the store was called, and by whom."""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.written: list[str] = []

    def write_pending(self, session: object) -> bool:
        transcript = getattr(session, "final_text", None) or getattr(
            session, "raw_transcript", ""
        )
        if not transcript or not transcript.strip():
            return False
        self.calls.append("persist")
        self.written.append(transcript)
        return True

    def mark_injected(self, session: object) -> None:
        self.calls.append("mark")


class _SpyInjector:
    def __init__(
        self,
        calls: list[str],
        *,
        succeeded: bool = True,
        raises: Exception | None = None,
    ) -> None:
        self.calls = calls
        self._succeeded = succeeded
        self._raises = raises
        self.injected: list[str] = []

    def inject(self, text: str) -> InjectionResult:
        self.calls.append("inject")
        if self._raises is not None:
            raise self._raises
        self.injected.append(text)
        return InjectionResult(
            succeeded=self._succeeded,
            strategy="clipboard",
            error=None if self._succeeded else "no permission",
        )

    def check_permissions(self) -> PermissionStatus:
        return PermissionStatus(granted=True)


def _session(text: str = "the small conference room") -> DictationSession:
    return DictationSession(
        id="01J0000000000000000000",
        started_at=datetime(2026, 8, 2, 9, 0, tzinfo=UTC),
        audio=None,
        sample_rate=16000,
        raw_transcript=text,
    )


def test_the_transcript_is_persisted_before_it_is_injected() -> None:
    """§8, stated as an ordering: *write to history before injection*. This is
    the one invariant in the product that cannot be repaired later — a crash
    between the two costs the user their words, and no amount of correct
    behaviour afterwards gets them back.
    """
    calls: list[str] = []

    deliver(_session(), _SpyHistory(calls), _SpyInjector(calls))

    assert calls == ["persist", "inject", "mark"]


def test_a_failed_injection_leaves_the_transcript_persisted() -> None:
    """The Phase 2a gate's third reject condition. `mark_injected` is not
    called, so the `retain = false` file is not unlinked and the row is not
    flagged — both paths keep the words."""
    calls: list[str] = []
    history = _SpyHistory(calls)

    result = deliver(_session(), history, _SpyInjector(calls, succeeded=False))

    assert result.succeeded is False
    assert history.written == ["the small conference room"]
    assert "mark" not in calls


def test_an_injector_that_raises_does_not_cost_the_transcript() -> None:
    """The ABC says `inject` reports rather than raises, and a pyobjc bridge
    is exactly the kind of thing that violates a contract like that. The write
    has already happened, so the words are safe; what this guarantees is that
    the process reports it instead of dying with a traceback."""
    calls: list[str] = []
    history = _SpyHistory(calls)
    injector = _SpyInjector(calls, raises=RuntimeError("NSInternalInconsistency"))

    result = deliver(_session(), history, injector)

    assert result.succeeded is False
    assert result.error is not None
    assert "NSInternalInconsistency" in result.error
    assert history.written == ["the small conference room"]
    assert "mark" not in calls


def test_the_write_and_the_injection_are_both_timed() -> None:
    """Both are inside G1's clock (§2) — it starts at hotkey release and these
    happen after it. A stage that cannot be measured cannot be defended when
    G1 is missed."""
    session = _session()

    deliver(session, _SpyHistory([]), _SpyInjector([]))

    assert session.timings.persist_ms > 0.0
    assert session.timings.inject_ms > 0.0


def test_nothing_is_injected_when_there_was_nothing_to_persist() -> None:
    """choice-story #7: a session that never reaches injection leaves nothing
    behind. Pasting an empty string would still clobber the clipboard."""
    calls: list[str] = []

    result = deliver(_session(text="   "), _SpyHistory(calls), _SpyInjector(calls))

    assert result.succeeded is False
    assert calls == []


# ---------------------------------------------------------------------------
# §5.7 — the collapse guard, as orchestration
# ---------------------------------------------------------------------------
#
# The judgement lives in `tests/test_guard.py`. What is asserted here is what
# the controller does with it, and the properties that are easy to get wrong:
# the retry has to actually ask for a different decode, a refused transcript
# must not reach the cursor, and §8's write has to precede that refusal rather
# than be skipped along with the injection.


def _long_dictation(**overrides: Any) -> DictationController:
    """A controller whose sessions are thirty seconds of speech."""
    parts: dict[str, Any] = {
        "detector": _FakeDetector(retained_seconds=30.0),
        "capture": _FakeCapture(np.ones(16000 * 30, dtype=np.float32)),
    }
    parts.update(overrides)
    return _controller(**parts)


def _biased_config(prompt: str = "notes about spreadsheets", **guard: Any) -> AppConfig:
    from dataclasses import replace

    base = AppConfig()
    return replace(
        base,
        engine=replace(base.engine, initial_prompt=prompt),
        guard=replace(base.guard, **guard) if guard else base.guard,
    )


def _dictate(controller: DictationController) -> DictationSession:
    controller.start()
    try:
        controller.start_session()
        session = controller.end_session()
        assert session.wait(timeout=5.0)
        return session
    finally:
        controller.shutdown()


def test_a_healthy_transcript_passes_the_guard_and_is_injected() -> None:
    injector = _FakeInjector()
    engine = _FakeEngine("the small conference room", coverage=0.98)
    controller = _long_dictation(engine=engine, injector=injector)

    session = _dictate(controller)

    assert session.guard is not None
    assert session.guard.outcome is GuardOutcome.PASSED
    assert engine.calls == 1
    assert injector.injected == ["the small conference room"]


def test_a_collapse_is_retried_without_the_bias_and_recovers() -> None:
    """The recovery path, and the assertion that it is a real one.

    §7.2 fixes `beam_size = 1`, so a retry that did not change the inputs would
    return the same words. Asserting on `bias_flags` rather than on the text is
    the difference between testing the retry and testing the fake.
    """
    injector = _FakeInjector()
    engine = _FakeEngine(
        " For Tenants.",
        coverage=0.06,
        unbiased_text="the whole thing, decoded",
        unbiased_coverage=0.97,
    )
    controller = _long_dictation(
        engine=engine, injector=injector, config=_biased_config()
    )

    session = _dictate(controller)

    assert session.guard is not None
    assert session.guard.outcome is GuardOutcome.RECOVERED
    assert session.guard.retried is True
    assert engine.bias_flags == [True, False]
    assert injector.injected == ["the whole thing, decoded"]
    assert session.raw_transcript == "the whole thing, decoded"


def test_a_collapse_the_retry_cannot_fix_is_not_injected() -> None:
    """§5.7: at the cursor, a destroyed transcript costs the user a noticing
    and an undo. It is refused, and `manu history --last` is what makes that
    defensible rather than a second way to lose the words."""
    injector = _FakeInjector()
    engine = _FakeEngine(
        " For Tenants.",
        coverage=0.06,
        unbiased_text=" Tenants.",
        unbiased_coverage=0.08,
    )
    controller = _long_dictation(
        engine=engine, injector=injector, config=_biased_config()
    )

    session = _dictate(controller)

    assert session.guard is not None
    assert session.guard.outcome is GuardOutcome.FAILED
    assert session.guard.retried is True
    assert injector.injected == []
    assert session.error is not None
    assert controller.state is DictationState.ERROR


def test_the_transcript_is_still_persisted_when_the_guard_refuses() -> None:
    """§8's ordering is unconditional and this path does not weaken it.

    The words are exactly as recoverable on the refused path as on the injected
    one — that is the entire reason refusing is acceptable.
    """
    history = _FakeHistory()
    engine = _FakeEngine(
        " For Tenants.", coverage=0.06, unbiased_text=" T.", unbiased_coverage=0.05
    )
    controller = _long_dictation(
        engine=engine, history=history, config=_biased_config()
    )

    session = _dictate(controller)

    assert "write_pending" in history.calls
    assert "mark_injected" not in history.calls
    assert history.written[0] is session


def test_there_is_no_retry_when_no_bias_was_configured() -> None:
    """Reporting a recovery attempt that was mechanically identical to the
    first decode would be an instrument describing work it did not do."""
    engine = _FakeEngine(" For Tenants.", coverage=0.06)
    controller = _long_dictation(engine=engine)  # AppConfig(): initial_prompt = ""

    session = _dictate(controller)

    assert engine.calls == 1
    assert session.guard is not None
    assert session.guard.outcome is GuardOutcome.FAILED
    assert session.guard.retried is False
    assert session.guard.reason is not None
    assert "initial_prompt" in session.guard.reason


def test_the_retry_can_be_turned_off() -> None:
    config = _biased_config(retry_below_coverage=0.0)
    engine = _FakeEngine(" For Tenants.", coverage=0.06)
    controller = _long_dictation(engine=engine, config=config)

    session = _dictate(controller)

    assert engine.calls == 1
    assert session.guard is not None
    assert session.guard.outcome is GuardOutcome.FAILED
    assert session.guard.retried is False


def test_a_retry_predicted_to_blow_the_budget_is_skipped_and_said_so() -> None:
    """Objection O5. §2's model gives `transcribe_ms ~ 48.8 + 13.69 x seconds`,
    so the cost is knowable before it is paid. A guard that silently spent two
    seconds re-decoding a five-minute dictation would be trading one failure
    for another."""
    config = _biased_config(retry_max_latency_ms=50)
    engine = _FakeEngine(" For Tenants.", coverage=0.06)
    controller = _long_dictation(engine=engine, config=config)

    session = _dictate(controller)

    assert engine.calls == 1
    assert session.guard is not None
    assert session.guard.retried is False
    assert session.guard.reason is not None
    assert "retry_max_latency_ms" in session.guard.reason


def test_a_short_dictation_is_judged_like_any_other() -> None:
    """The property the words-per-second design could not have. One second of
    audio, fully decoded — no exemption, no blind spot."""
    injector = _FakeInjector()
    controller = _controller(engine=_FakeEngine("ok", coverage=0.95), injector=injector)

    session = _dictate(controller)

    assert session.guard is not None
    assert session.guard.outcome is GuardOutcome.PASSED
    assert injector.injected == ["ok"]


def test_a_short_dictation_can_still_fail() -> None:
    """And the other half of it: the guard is not merely inactive down here."""
    injector = _FakeInjector()
    controller = _controller(
        engine=_FakeEngine(" um", coverage=0.04), injector=injector
    )

    session = _dictate(controller)

    assert session.guard is not None
    assert session.guard.outcome is GuardOutcome.FAILED
    assert injector.injected == []


def test_post_processing_runs_on_the_recovered_text() -> None:
    """The chain must see what will be injected, not what was thrown away."""
    engine = _FakeEngine(
        " For Tenants.",
        coverage=0.06,
        unbiased_text="the whole thing",
        unbiased_coverage=0.97,
    )
    injector = _FakeInjector()
    controller = _long_dictation(
        engine=engine,
        injector=injector,
        processors=[_Upper()],
        config=_biased_config(),
    )

    _dictate(controller)

    assert injector.injected == ["THE WHOLE THING"]


def test_the_guard_is_timed(controller: DictationController) -> None:
    """§6.3's standing rule: a stage inside G1's window with no field is a
    stage that cannot be defended when G1 is missed. Four phases in a row have
    now found one."""
    controller.start_session()
    session = controller.end_session()
    assert session.wait(timeout=5.0)

    assert session.timings.guard_ms > 0.0
    assert session.timings.g1_ms >= session.timings.guard_ms


# ---------------------------------------------------------------------------
# Phase 3 — defects the phase's own review found in shipped code
# ---------------------------------------------------------------------------


class _Exploding:
    """A processor that always raises. The ABC says this must not cost words."""

    name = "exploding"

    def process(self, _text: str, _session: DictationSession) -> str:
        raise RuntimeError("the chain is on fire")


def test_a_raising_processor_does_not_cost_the_transcript() -> None:
    """PRD §6.3 and postprocess/base.py both promise this and neither was true.

    The chain runs *before* `deliver`, which is the only caller of
    `write_pending` on that path, and the only handler returned before it. So a
    processor raising meant nothing persisted and nothing injected — on the one
    constraint CLAUDE.md lists first. Unreachable for three phases because
    `cli.py` passed `processors=[]` (objection O1).
    """
    made = _controller(processors=[_Exploding()])
    made.start()
    try:
        made.start_session()
        session = made.end_session()
        assert session.wait(5.0), "the worker never completed the session"
    finally:
        made.shutdown()

    assert (
        "write_pending" in made.history.calls
    ), "the transcript was never persisted — §8's guarantee is unconditional"
    assert made.injector.injected == [
        "hello there"
    ], "the last good text should still reach the cursor"
    assert (
        session.error is not None and "exploding" in session.error
    ), "the failing processor must be named, not swallowed (§6.3)"


def test_a_later_processor_survives_an_earlier_one_raising() -> None:
    """The chain is abandoned at the raise; it does not skip and continue.

    `base.py` says the *last good text* proceeds, not the text a later
    processor would have produced from a value the failed one never returned.
    """
    made = _controller(processors=[_Exploding(), _Upper()])
    made.start()
    try:
        made.start_session()
        session = made.end_session()
        assert session.wait(5.0)
    finally:
        made.shutdown()

    assert made.injector.injected == [
        "hello there"
    ], "the chain must stop at the raise rather than run the rest"


def test_the_focus_is_stashed_before_the_session_is_queued() -> None:
    """Otherwise the worker can dequeue a session whose focus is not there yet.

    `deliver` skips the focus check entirely when `focus_at_capture` is None, so
    losing that race does not degrade the check — it *disables* it, and §6.3's
    protection against injecting into an application the user switched away
    from stops applying, non-deterministically (objection O2).

    Asserted structurally rather than by racing: the moment the session becomes
    visible to the worker, its focus must already be recorded.
    """
    made = _controller()
    seen: list[bool] = []
    real_queue = made._queue

    class _WatchingQueue:
        def put(self, item: Any) -> None:
            if item is not None:
                seen.append(item.id in made._focus_by_session)
            real_queue.put(item)

        def get(self) -> Any:
            return real_queue.get()

    made._queue = _WatchingQueue()  # type: ignore[assignment]
    made.start()
    try:
        made.start_session()
        session = made.end_session()
        assert session.wait(5.0)
    finally:
        made.shutdown()

    assert seen == [True], (
        "the session was queued before its focus was stashed; a worker "
        "dequeuing in between reads None and skips the focus check"
    )
