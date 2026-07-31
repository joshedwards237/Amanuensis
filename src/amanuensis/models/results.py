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
system settings pane to open.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["InjectionResult", "PermissionStatus"]


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
