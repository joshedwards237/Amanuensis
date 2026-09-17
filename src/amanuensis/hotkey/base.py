"""Listening for the hotkey. The other platform-selection boundary (§6.3).

This ABC is the one the "is there a real chance we replace the
implementation?" test was never applied to — §6.4 declared `hotkey/base.py`
while §6.2 and §6.3 never contracted it. Portability floor item 4 (PRD §7.3)
closes that: a hotkey listener is at least as platform-shaped as an injector,
and the cost of giving it the same treatment is near zero now and real after
Phase 2b.

The threading contract is the load-bearing part. The listener runs on an OS
event tap, and the callbacks it invokes **must not block it** — a blocked
event tap on macOS is a system-wide input stall, not a slow app. So the
callbacks take no arguments and return nothing: there is nothing useful a
callback could return to a thread that must not wait for it. `on_press` hands
work to the controller, which hands it to the worker, which is where anything
slow happens (§6.3).

`start` and `stop` rather than a context manager: the listener's lifetime is
the daemon's, and a `with` block implies a scope the daemon does not have.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from amanuensis.models.results import PermissionStatus

__all__ = ["HotkeyCallback", "HotkeyListener"]

#: Invoked on the OS event-tap thread. Must return promptly and must not
#: block; anything slow belongs on the worker thread.
HotkeyCallback = Callable[[], None]


class HotkeyListener(ABC):
    """Emits press and release events for the configured binding."""

    @abstractmethod
    def start(
        self,
        on_press: HotkeyCallback,
        on_release: HotkeyCallback,
        on_cancel: HotkeyCallback | None = None,
        on_latch: HotkeyCallback | None = None,
    ) -> None:
        """Begin listening. Returns once the tap is installed, not when it stops.

        `on_latch` fires once when a double-tap latches — a **notification**,
        not an operation. Nothing about the session changes: the capture opened
        on the first press and keeps running (§5.2, as amended). It exists so
        surfaces that must look different hands-free can learn that they should,
        without any of them learning what a latch is.

        Raises if the OS refuses the tap — on macOS that means Input
        Monitoring has not been granted, which is a startup-time condition the
        tray must surface rather than a silent no-op.
        """

    def clear_latch(self) -> None:  # noqa: B027
        """Forget that a hands-free session is in progress.

        Called when a session ends by any route that is **not** the key —
        Escape, the overlay's ✕, `manu toggle`, a VAD auto-end. A listener that
        tracks latch state cannot see those, and one that keeps thinking it is
        latched swallows the next press.

        Concrete rather than abstract, and a no-op by default: a listener with
        no latch has nothing to clear, and making every implementation write an
        empty method to say so is how the method stops being read.

        `B027` flags exactly this — an empty non-abstract method on an ABC,
        which subclasses inherit silently. That is the intent here and the
        silence is the point, so the rule is waived rather than satisfied by
        making every implementation carry a stub it does not need.
        """

    @abstractmethod
    def stop(self) -> None:
        """Stop listening and release the tap. Must be idempotent."""

    @abstractmethod
    def check_permissions(self) -> PermissionStatus:
        """Non-destructive check. Called at startup, surfaced in the tray.

        Added in Phase 2b, on `TextInjector`'s argument rather than for
        symmetry: every plausible platform has some version of "this app may
        not watch your keyboard", and the moment of the user's first dictation
        is the worst time to discover it. `start` raising is not a substitute
        — the daemon needs to report the state *before* it takes the microphone,
        and it needs to report which of the two macOS grants is missing.

        Must not prompt. A daemon that starts at login and raises a system
        dialog every time teaches the user to dismiss whatever it shows them.
        """

    def request_permissions(self) -> None:  # noqa: B027 — concrete, see below
        """Ask the OS to register this process as an applicant. May prompt.

        Added 2026-09-14, from lane 6, and the twin of `TextInjector`'s. Input
        Monitoring behaves as Accessibility does: a process that has only
        preflighted is not listed in its pane, so the remediation this ABC's
        `check_permissions` hands back names a row that does not exist yet.

        Called only after a failed check, only from the CLI. Concrete and
        defaulting to nothing, for the reason given on `TextInjector`.
        """

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """True between a successful `start` and a `stop`."""
