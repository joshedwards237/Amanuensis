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

    def focus_identity(self) -> str | None:
        """Who would receive text right now? `None` when it cannot be told.

        Added in Phase 2b, for the hazard §6.3's async handoff creates rather
        than for anything injection needs: `end_session()` does not block, so
        session N's text can land in whatever window has focus when the worker
        reaches it. The controller compares this value across the gap and
        declines to type when it changed.

        It lives on the injector because the injector is the component that
        knows where text goes — the controller must not learn what a bundle
        identifier is (§6.2). The value is opaque and comparable; nothing may
        parse it.

        Concrete and `None` by default, on `warm_up`'s argument. `None` means
        **cannot tell**, which is deliberately not the same as *changed*: an
        implementation with no way to answer must still inject, because the
        check exists to catch a change and unknown is not one.
        """
        return None

    def warm_up(self) -> None:  # noqa: B027 — deliberately concrete, see below
        """Pay the one-time cost now, so the first dictation does not.

        Added in Phase 2a from measurement, not symmetry: the first
        `inject()` on macOS cost **165.8 ms** and every subsequent one under
        2 ms, because loading the pyobjc bridges happens on first use. That is
        165 ms against a 400 ms budget, landing on the user's first dictation.

        `TranscriptionEngine.warm_up` exists on the identical argument — "the
        first real call must not pay compile cost" (§6.3) — and this boundary
        had the same problem and no method for it. Phase 2a's CLI avoided it
        only by accident, because checking permissions and detecting clipboard
        managers happen to touch both bridges before the microphone opens.

        Concrete rather than abstract, and a no-op by default: an injector
        with nothing to warm should not be forced to write an empty method,
        and this is not a boundary where forgetting to implement it is
        silently wrong — it is slow once, which the timings show.

        Must be idempotent, and must have no effect a user could observe. The
        engine can afford a throwaway inference; an injector cannot type a
        throwaway character into whatever window has focus.
        """
