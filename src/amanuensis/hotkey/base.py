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

__all__ = ["HotkeyCallback", "HotkeyListener"]

#: Invoked on the OS event-tap thread. Must return promptly and must not
#: block; anything slow belongs on the worker thread.
HotkeyCallback = Callable[[], None]


class HotkeyListener(ABC):
    """Emits press and release events for the configured binding."""

    @abstractmethod
    def start(self, on_press: HotkeyCallback, on_release: HotkeyCallback) -> None:
        """Begin listening. Returns once the tap is installed, not when it stops.

        Raises if the OS refuses the tap — on macOS that means Input
        Monitoring has not been granted, which is a startup-time condition the
        tray must surface rather than a silent no-op.
        """

    @abstractmethod
    def stop(self) -> None:
        """Stop listening and release the tap. Must be idempotent."""

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """True between a successful `start` and a `stop`."""
