"""Transforming the transcript. A **composition** boundary (PRD §6.3).

This is the one ABC of the three kinds where several instances are live at
once, ordered, each transforming the same value. It was originally given the
same two-member contract as the others on the assumption it was the same kind
of thing. It is not, and three properties follow that the other two do not
need:

**Order is significant.** `chain` is ordered (§5.3) and reordering changes the
output. That makes the chain a value with meaning, not a set.

**`process` is pure with respect to the session.** It returns transformed text
and does not mutate `DictationSession`. Two things depend on that: a chain
stays replayable against a stored transcript, and a processor cannot reach the
audio. The session is passed in — not withheld — because a processor
legitimately needs context like the engine used or the utterance duration; it
just may not write to it.

**A raising processor must not cost the transcript.** If `process` raises
mid-chain, the chain is abandoned and the *last good text* proceeds to the §8
write and then to injection; the error is surfaced in the tray and recorded,
never swallowed. This is also why `process` returns a string rather than a
result object — a processor's failure is the chain runner's problem, not a
value the next processor has to unwrap.

**Corrected 2026-08-08 (Phase 3, objection O1), and the correction is the
interesting part.** This paragraph previously read "§8's persist-before-inject
ordering has already run, so the words survive regardless." It has not: the
chain runs *before* the write, and `DictationController._process` had no
per-processor guard, so its outer handler returned before `deliver` — the only
caller of `write_pending` on that path. A raising processor persisted nothing
and injected nothing, on the constraint this project lists first.

It was unreachable for three phases because `cli.py` passed `processors=[]`,
which is why a paragraph asserting a guarantee sat above code that could not
honour it. **Fourth instance in this repository of the specification stating a
constraint the tooling cannot meet**, after `restore_ms` having no column,
`store_audio` doing nothing for three phases, and `raw_transcript` sharing a
column with the final text. The ordering above is now what the controller does,
rather than what it was documented to do.

This contract was frozen before the Phase 5 experiments returned, and that was
safe precisely because every candidate approach — constrained decoding, a
fine-tuned seq2seq model, token-level keep/delete classification, and
rules-only — satisfies this same signature.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from amanuensis.models.session import DictationSession

__all__ = ["TextPostProcessor", "TracedPostProcessor"]


class TextPostProcessor(ABC):
    """One step in the ordered post-processing chain."""

    @abstractmethod
    def process(self, text: str, session: DictationSession) -> str:
        """Return transformed text. Must not mutate `session`."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The `chain` entry that selects this processor, e.g. `"rules"`.

        Also what the tray and the history record name when a processor
        raises, which is the only time a user learns the chain has parts.
        """


@runtime_checkable
class TracedPostProcessor(Protocol):
    """An optional second capability: say which rules actually changed anything.

    **Why this is a Protocol beside the ABC rather than a method on it.**
    PRD §5.6's `[replace]` map has a failure mode where a rule fires on a
    homonym, and the user then sees wrong text with no signal that the
    dictionary touched it — the transcript looks like an ASR error, which is
    the one explanation that sends them to the wrong fix (dictionary objection
    O5). So the session has to record what fired. Three ways to get that, and
    the two obvious ones are both wrong here:

    - **A `fired` attribute read after the call.** Rejected (objection O8). It
      is a single unkeyed slot on a shared instance, and `_process` has two
      early returns — so a session that fails between the chain and the read
      leaves its entries to be read as the *next* session's. The safety
      argument would also be a property of the caller rather than of the class,
      which no test on this class can express.
    - **Adding the method to `TextPostProcessor`.** `tests/test_contracts.py`
      asserts the ABC declares exactly `{process, name}`, deliberately, so that
      the boundary does not drift under Phase 5's experiments.

    A Protocol makes the trace a **return value**. There is no slot to go
    stale, no cross-thread invariant to state, and the chain runner writes it to
    the session — which is where session writes already live.

    The pattern is **Extension Interface** (POSA vol. 2), structurally the same
    as Go's optional-interface upgrade idiom (`http.Flusher` beside
    `http.ResponseWriter`). Its cost is stated rather than hidden:
    `runtime_checkable` verifies **method presence only**, so a class declaring
    `process_traced(self, text)` satisfies `isinstance` and then fails at the
    call. `tests/test_contracts.py` carries the signature check the ABC already
    has, because a second contract with no guard is how the first one drifted.

    A further cost, accepted: `[postprocess] chain` names processors, not
    capabilities, so a user reading their config cannot tell whether the trace
    column will be populated. Surfacing capabilities in config would be a worse
    trade than a documented asymmetry.
    """

    def process_traced(
        self, text: str, session: DictationSession
    ) -> tuple[str, tuple[str, ...]]:
        """Return the transformed text and the names of the rules that acted.

        The names are for a human reading a gate record or a history row, so
        they are the rule identifiers rather than a structured diff. A rule that
        *would* have fired but is disabled reports itself with a `:candidate`
        suffix — see `RuleBasedPostProcessor` for why a disabled rule still has
        to be counted.

        Must agree with `process` on the text. A trace describing a different
        pass from the one the user ran is a firing rate for code that never ran.
        """
        ...
