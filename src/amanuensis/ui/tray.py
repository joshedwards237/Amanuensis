"""`TrayApp` — the same five states, with room for words.

`RecordingIndicator` (Phase 2b) already renders every `DictationState` as a
glyph in the menu bar, so a tray that "shows the state" would add nothing. What
this adds is the thing a glyph structurally cannot do: **say what happened**.
"Accessibility permission was revoked" is not expressible in one character, and
until now it went to stderr — a terminal the user is not looking at, in a
product whose whole shape is that you do not look at it.

Three design decisions worth the reader's time.

**It composes the indicator rather than replacing it.** `indicator.py`'s own
preamble said Phase 4's tray "renders the same states with a menu attached",
and that module is where the threading was gotten right — `set_state` from any
thread, drawing on the main queue, the `NSTimer` that lets Ctrl-C work at all.
Reimplementing it here would fork the one piece of this daemon that was found
by running it rather than by reasoning. So there is exactly **one**
`NSStatusItem` in this process, and it belongs to the indicator.

**The menu is a pure model.** `menu_items()` returns data; the AppKit code
turns data into `NSMenuItem`s. Almost every test of this module therefore needs
no fake framework, which matters because the interesting content — the error
text, the persistent clipboard row — is exactly the part a fake would let you
render wrongly and still pass.

**No business logic** (§6.2). `on_quit` is a callback the daemon supplies. This
class does not know what stopping means, which is the boundary CLAUDE.md names
first among the ones that get violated.

What it deliberately does not do: preferences (§11.2 puts a settings UI
post-v1), history browsing (`manu history` owns that), and mode switching.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from amanuensis.controllers.dictation_controller import DictationState
from amanuensis.models.results import ClipboardExposure
from amanuensis.ui.indicator import _TOOLTIPS, GLYPHS, RecordingIndicator

__all__ = ["MenuItem", "TrayApp"]

#: A menu row is one line. Errors in this project are multi-line by habit — the
#: clipboard warning is five — and a traceback pasted into a menu makes an
#: unusable menu. Dropping it instead would hide the failure, so the only
#: answer that does neither is truncation, at a width a menu can carry.
_MAX_ERROR_CHARS: Final = 160


@dataclass(frozen=True, slots=True)
class MenuItem:
    """One row. `action is None` means informational — shown, not clickable."""

    title: str
    action: str | None = None
    enabled: bool = False


def _one_line(text: str) -> str:
    """Flatten and bound an arbitrary message to something a menu can render."""
    flattened = " ".join(text.split())
    if len(flattened) <= _MAX_ERROR_CHARS:
        return flattened
    return flattened[: _MAX_ERROR_CHARS - 1] + "…"


class TrayApp:
    """A status surface. One status item, one menu, no decisions."""

    def __init__(
        self,
        indicator: RecordingIndicator | None = None,
        *,
        on_quit: Callable[[], None] | None = None,
    ) -> None:
        self._indicator = indicator if indicator is not None else RecordingIndicator()
        self._on_quit = on_quit
        self._state = DictationState.IDLE
        self._error: str | None = None
        self._exposure: ClipboardExposure | None = None
        #: Guards the menu model only. Rebuilt on the main queue, mutated from
        #: the worker and the event tap — the same shape as the indicator's.
        self._lock = threading.Lock()
        self._menu: Any | None = None

    # -- state -------------------------------------------------------------

    @property
    def state(self) -> DictationState:
        return self._state

    @property
    def title(self) -> str:
        """The glyph. §5.4 requires the state be readable without opening the
        menu, so it lives in the title and the menu merely elaborates."""
        return GLYPHS[self._state]

    def set_state(self, state: DictationState) -> None:
        """Safe from any thread, and safe before `show()` — the controller
        starts before the run loop does."""
        self._state = state
        self._indicator.set_state(state)
        self._refresh()

    def set_error(self, message: str | None) -> None:
        """Put words on screen, or take them away.

        An empty string is treated as no error: a blank menu row is worse than
        none, because the user cannot tell it from a rendering fault.
        """
        self._error = message if message else None
        self._refresh()

    def set_clipboard_exposure(self, exposure: ClipboardExposure | None) -> None:
        """§5.4 and §7.3 both assign this row to Phase 4.

        Persistent, and only ever positive. `detected is False` means *no
        known manager was found* — the detection list is incomplete by nature
        (objection O12), so there is no all-clear to render and this method
        renders none.
        """
        self._exposure = exposure
        self._refresh()

    # -- the menu, as data -------------------------------------------------

    def menu_items(self) -> tuple[MenuItem, ...]:
        """The whole menu, in order. Pure — no AppKit, no side effects."""
        items = [MenuItem(_TOOLTIPS[self._state])]

        if self._error is not None:
            items.append(MenuItem(_one_line(self._error)))

        exposure = self._exposure
        if exposure is not None and exposure.detected:
            manager = exposure.manager or "a clipboard manager"
            items.append(
                MenuItem(
                    f"{manager} is running — transcripts transit the clipboard"
                )
            )

        items.append(MenuItem("Quit Amanuensis", action="quit", enabled=True))
        return tuple(items)

    def set_on_quit(self, on_quit: Callable[[], None]) -> None:
        """Supply the quit handler after construction.

        The daemon builds the tray before it can say what stopping means —
        `stop()` is the tray's own, and the controller and listener teardown
        that follows it lives in `manu daemon`'s `finally`. Still a callback:
        §6.2's boundary is that this class does not decide, not that it is
        wired at `__init__`.
        """
        self._on_quit = on_quit

    def activate(self, action: str | None) -> None:
        """Run a menu action. Unknown actions are ignored deliberately: AppKit
        hands back whatever tag it was given, and an unrecognised one is a bug
        in this file rather than a reason to kill a daemon holding the mic."""
        if action == "quit" and self._on_quit is not None:
            self._on_quit()

    # -- AppKit ------------------------------------------------------------

    def show(self) -> None:
        """Create the status item and attach the menu. Main thread only."""
        self._indicator.show()
        self._indicator.set_menu(self._build_menu())

    def run(self) -> None:
        """Blocks. Main thread only — see `indicator.run`."""
        self._indicator.run()

    def stop(self) -> None:
        self._indicator.stop()

    def _refresh(self) -> None:
        """Rebuild the rendered menu if there is one. Safe from any thread."""
        with self._lock:
            if self._menu is None:
                return
        self._indicator.set_menu(self._build_menu())

    def _build_menu(self) -> Any:
        from amanuensis.ui.indicator import _appkit

        appkit = _appkit()
        menu = appkit.NSMenu.alloc().init()
        for item in self.menu_items():
            row = appkit.NSMenuItem.alloc().init()
            row.setTitle_(item.title)
            row.setEnabled_(item.enabled)
            menu.addItem_(row)
        with self._lock:
            self._menu = menu
        return menu
