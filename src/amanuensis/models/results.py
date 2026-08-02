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

__all__ = ["ClipboardExposure", "InjectionResult", "PermissionStatus"]


@dataclass(frozen=True, slots=True)
class InjectionResult:
    succeeded: bool
    #: "clipboard" or "keystroke" — which path actually ran, which is not
    #: always the configured one if a fallback fired.
    strategy: str
    error: str | None = None


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
