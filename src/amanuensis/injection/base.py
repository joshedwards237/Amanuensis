"""Getting text to the cursor. A platform-selection boundary (PRD §6.3).

One instance per process, chosen by `factory.py` from the running platform —
not by a config string, because the user does not get to pick their OS. The
config key that *does* exist, `[injection] strategy`, selects between
clipboard paste and synthetic keystrokes *within* an implementation; it is not
a second dispatch axis.

`check_permissions` is on the ABC rather than being a macOS detail because
every plausible platform has some version of "this app may not type into
other apps", and discovering that at the moment of the user's first dictation
is the worst time to discover it. It is called at startup and surfaced in the
tray, and it must be non-destructive — a permission check that itself types
something is not a check.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from amanuensis.models.results import InjectionResult, PermissionStatus

__all__ = ["TextInjector"]


class TextInjector(ABC):
    """Put `text` where the user's cursor is, in whatever app has focus."""

    @abstractmethod
    def inject(self, text: str) -> InjectionResult:
        """Inject `text` at the cursor.

        Returns a result rather than raising on failure: §8's persist-before-
        inject ordering means the transcript already survives, so a failed
        injection is a reportable outcome, not an exception the caller must
        handle to avoid data loss.
        """

    @abstractmethod
    def check_permissions(self) -> PermissionStatus:
        """Non-destructive check. Called at startup, surfaced in the tray."""
