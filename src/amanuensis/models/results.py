"""What an injector reports back.

Both types are frozen: they are answers, and an answer that a caller can edit
is a bug waiting for a reader to miss it.

`InjectionResult` names the strategy that ran rather than just succeeding or
failing, because the two strategies fail differently and the tray has to say
which one the user is looking at. Clipboard paste can be defeated by a
clipboard manager racing the restore (a documented, unavoidable cost of that
strategy — PRD §7.3); keystroke injection cannot, and is slower.

`PermissionStatus` lists what is *missing* rather than exposing a bag of
booleans, because the only useful thing to do with it is tell the user which
system settings pane to open. It carries the remediation text with it rather
than leaving each caller to compose one: PRD §9 asks for remediation that can
be copy-pasted, and a message assembled at three call sites is a message that
is right at one of them.

`ClipboardExposure` exists because §7.3's clipboard-manager capture is a
privacy surface rather than a hygiene annoyance (objection O12), and §5.4
requires it be visible without opening a menu. It is a value rather than a
boolean so the warning can name the application — "a clipboard manager is
running" is not something a user can act on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "ClipboardExposure",
    "GuardOutcome",
    "GuardVerdict",
    "InjectionResult",
    "PermissionStatus",
    "Transcription",
]


@dataclass(frozen=True, slots=True)
class Transcription:
    """What one decode produced, and how far through the audio it got.

    `decoded_seconds` is where the decoder stopped, in the timebase of the
    audio handed in — trimmed audio, so it compares directly against
    `TrimResult.retained_seconds`. `None` from an engine that cannot say.

    This exists for the same reason `InjectionResult` carries `restore_ms`: a
    caller needs a quantity only the implementation can compute, and there is
    no way to get it from outside because the call returns once. The engine was
    already receiving this information from faster-whisper and throwing it
    away — segments carry `start`, `end`, `avg_logprob`, `no_speech_prob` and
    `compression_ratio`, and `_decode` joined the texts and dropped the rest.

    `None` and `0.0` are opposite claims and callers must not conflate them.
    `None` is "this engine cannot tell you"; `0.0` is "the decoder produced
    nothing", which is a catastrophe.
    """

    text: str
    decoded_seconds: float | None = None


class GuardOutcome(StrEnum):
    """§5.7's verdict on a transcript.

    A `StrEnum` because it is persisted in `history.db` and read back by
    humans; an integer code would need a lookup table living somewhere else.
    """

    #: Judged and acceptable.
    PASSED = "passed"
    #: Judged, found wanting, and an unbiased re-decode did better.
    RECOVERED = "recovered"
    #: Judged, found wanting, and nothing recovered it. Not injected.
    FAILED = "failed"
    #: Not judged. The reason is always recorded — see `GuardVerdict.reason`.
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class GuardVerdict:
    """§5.7's answer about one transcript, and the evidence behind it.

    Every quantity is carried even when the guard did not run. Objection O10's
    failure is a guard that *silently* never fires — an over-trimming VAD
    shrinks the denominator and nothing about that is visible from the outcome
    alone — so the denominator travels with the verdict on every path,
    including the ones where no judgement was made.
    """

    outcome: GuardOutcome
    #: Seconds of speech the VAD retained. Always populated.
    retained_seconds: float
    #: Decoded span over retained speech. `None` when the engine could not
    #: report a span and the fallback floor was used instead.
    coverage: float | None = None
    #: The fallback instrument, and only ever that. `None` on the coverage path.
    words_per_second: float | None = None
    #: Why the guard skipped, why a retry did not run, or what failed. Prose,
    #: because its only consumer is a person reading an error.
    reason: str | None = None
    #: Was an unbiased second decode actually performed.
    retried: bool = False
    #: Should the caller run one. Set on the first judgement, never on a final
    #: verdict from `resolve`.
    retry_advised: bool = False
    #: Did `resolve` pick the retry's transcript over the original.
    chose_retry: bool = False


@dataclass(frozen=True, slots=True)
class InjectionResult:
    succeeded: bool
    #: "clipboard" or "keystroke" — which path actually ran, which is not
    #: always the configured one if a fallback fired.
    strategy: str
    error: str | None = None
    #: How long the clipboard restore took, in milliseconds. Reported here
    #: because a caller timing `inject()` from outside cannot separate it:
    #: the call returns once, after both the paste and the cleanup that
    #: follows it. §2 ends G1 when the text is fully present, so the two have
    #: to be told apart or G1 is charged for work done after the user already
    #: had their words. Zero for the keystroke strategy, which restores
    #: nothing.
    restore_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class PermissionStatus:
    """A non-destructive answer to "can this app type into other apps?".

    macOS needs Accessibility and Input Monitoring, granted separately, and a
    user who has granted one usually believes they granted both.
    """

    granted: bool
    #: Human-readable names of the permissions still to grant, in the order
    #: the user should grant them. Empty when `granted` is True.
    missing: tuple[str, ...] = field(default_factory=tuple)
    #: What to print at a user who is stuck, verbatim. Empty when `granted`.
    remediation: str = ""


@dataclass(frozen=True, slots=True)
class ClipboardExposure:
    """Whether a known clipboard manager is running (§7.3, objection O12).

    `detected is False` means **no known manager was found**, never "no
    manager is present". The list this is derived from is incomplete by nature
    and cannot be completed; presenting its silence as an all-clear is the
    failure the objection was raised about.
    """

    detected: bool
    #: The application's own name, when one was found. Read from the running
    #: application rather than from the detection table so that a rename shows
    #: the user what they can actually see in their menu bar.
    manager: str | None = None
