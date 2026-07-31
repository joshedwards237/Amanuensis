"""The transcription swap point.

This is a **replacement** boundary in PRD §6.3's three-way classification:
one implementation is live at a time, selected by a config string through
`registry.py`. It earns its ABC on the stated test — there is a real chance
the implementation gets replaced. Moonshine is a genuine alternative to
faster-whisper on CPU, and CTranslate2 having no Metal backend means the
default is not obviously the endpoint (§7.2).

Three of the four members are about *lifecycle*, not transcription, and that
is the interesting part of the contract. The daemon exists so the model stays
resident; a per-invocation load costs 3–8 seconds and there is no version of
that which is acceptable (§6.1). So `load` and `warm_up` are separate calls:
loading gets weights into memory, warming runs a throwaway inference so the
first real utterance does not pay a compile cost. `is_loaded` exists so the
tray can distinguish *transcribing* from *not ready* — two states that look
identical to a user and mean opposite things.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
from numpy.typing import NDArray

__all__ = ["TranscriptionEngine"]


class TranscriptionEngine(ABC):
    """Audio in, text out. Everything else about the model is its own business."""

    @abstractmethod
    def load(self) -> None:
        """Called once at daemon start. Blocking. Must be idempotent.

        Runs on the worker thread (§6.3), never on the event tap.
        """

    @abstractmethod
    def transcribe(self, audio: NDArray[np.float32], sample_rate: int) -> str:
        """Transcribe one utterance. Returns the raw transcript, unprocessed.

        Formatting, filler removal and vocabulary correction belong to the
        post-processing chain. An engine that tidies its own output makes the
        chain's behaviour depend on which engine ran.
        """

    @abstractmethod
    def warm_up(self) -> None:
        """Run one throwaway inference. The first real call must not pay the
        compile cost — a user's first dictation of the session is exactly when
        they are deciding whether this is fast."""

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """True once `load` has completed and `transcribe` may be called."""
