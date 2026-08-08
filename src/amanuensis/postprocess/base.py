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

from amanuensis.models.session import DictationSession

__all__ = ["TextPostProcessor"]


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
