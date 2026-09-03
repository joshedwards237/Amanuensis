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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from amanuensis.controllers.dictation_controller import DictationState
from amanuensis.models.results import ClipboardExposure
from amanuensis.ui.indicator import _TOOLTIPS, GLYPHS, RecordingIndicator

__all__ = [
    "HOTKEY_ACTION_PREFIX",
    "MODE_ACTION_PREFIX",
    "MenuItem",
    "TrayApp",
]

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
    #: Rows nested under this one. A flat list of nine hotkeys would bury the
    #: two things the menu is actually for — reading the state and quitting.
    submenu: tuple[MenuItem, ...] = ()
    #: Drawn with a tick. Says which binding is live without opening anything.
    checked: bool = False


#: Built on first use, never at import. Subclassing `NSObject` requires
#: Foundation, and this module's whole import discipline is that `manu --help`
#: does not load the Objective-C runtime.
_TARGET_CLASS: Any | None = None


def _menu_target_class() -> Any:
    """An `NSObject` subclass exposing one selector for menu items to call.

    Defined in a function and cached, because defining it twice would register
    two Objective-C classes with the same name and PyObjC raises on that.
    """
    global _TARGET_CLASS
    if _TARGET_CLASS is None:
        from Foundation import NSObject

        class _AmanuensisMenuTarget(NSObject):  # type: ignore[misc]
            def amanuensisMenuAction_(self, sender: Any) -> None:
                handler = getattr(self, "handler", None)
                if handler is None:  # pragma: no cover — target outlived tray
                    return
                verb = sender.representedObject()
                handler(None if verb is None else str(verb))

        _TARGET_CLASS = _AmanuensisMenuTarget
    return _TARGET_CLASS


#: Prefix distinguishing a hotkey row from every other verb. The binding name
#: travels after it, so `activate` stays the one place a verb is interpreted.
HOTKEY_ACTION_PREFIX: Final = "hotkey:"


def _pretty_binding(name: str) -> str:
    """`right_option` -> `Right Option`. The config's spelling is snake_case
    because §5.3 says config keys are; a menu is not a config file."""
    return name.replace("_", " ").title() if name else "not set"


#: Prefix distinguishing a capture-mode row. Same scheme as the hotkey rows.
MODE_ACTION_PREFIX: Final = "mode:"

#: §5.2's one-line description of each mode. The names are config spellings and
#: mean nothing on their own — "vad_auto" in a menu is a puzzle, not a choice.
_MODE_LABELS: Final[dict[str, str]] = {
    "push_to_talk": "Hold to talk",
    "toggle": "Press to start, press to stop",
    "vad_auto": "Press to start, silence ends it",
}


def _pretty_mode(name: str) -> str:
    return _MODE_LABELS.get(name, name.replace("_", " ").title() or "not set")


def _mode_label(name: str) -> str:
    """A mode's menu title, with §5.2's warning attached where it applies."""
    label = _pretty_mode(name)
    if name == "vad_auto":
        # §5.2: "the mode most likely to misfire". A user picking it from a
        # menu deserves the same sentence the spec gives an implementer.
        return f"{label}  ⚠ may cut you off"
    return label


def _binding_label(name: str) -> str:
    """A binding's menu title, with its cost attached.

    A modifier used inside ordinary shortcuts makes a dictation hotkey fire on
    every shortcut that uses it — bind Right Command and ⌘C starts and ends a
    dictation. Offering nine bindings as equals is how a user picks a worse one
    than the default, which happened.
    """
    from amanuensis.hotkey.macos import COLLIDING_BINDINGS

    pretty = _pretty_binding(name)
    return f"{pretty}  ⚠ used in shortcuts" if name in COLLIDING_BINDINGS else pretty


def _one_line(text: str) -> str:
    """Flatten and bound arbitrary text to something a menu can render.

    Control characters are removed rather than escaped. `str.split()` handles
    whitespace and leaves NUL, BEL and escape sequences intact — they reached
    the menu unaltered until the stress pass looked, and a NUL inside an
    `NSString` is not a cosmetic problem. Everything here can arrive from an
    exception message or from another application's name, so none of it is
    trusted.
    """
    stripped = "".join(
        " " if ch.isspace() else ch
        for ch in text
        if ch.isprintable() or ch.isspace()
    )
    flattened = " ".join(stripped.split())
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
        on_hotkey: Callable[[str], None] | None = None,
        on_mode: Callable[[str], None] | None = None,
    ) -> None:
        self._indicator = indicator if indicator is not None else RecordingIndicator()
        self._on_quit = on_quit
        self._on_hotkey = on_hotkey
        self._hotkeys: tuple[str, ...] = ()
        self._hotkey_current = ""
        self._on_mode = on_mode
        self._modes: tuple[str, ...] = ()
        self._mode_current = ""
        self._state = DictationState.IDLE
        self._error: str | None = None
        self._exposure: ClipboardExposure | None = None
        #: Guards the menu model only. Rebuilt on the main queue, mutated from
        #: the worker and the event tap — the same shape as the indicator's.
        self._lock = threading.Lock()
        self._menu: Any | None = None
        #: The Objective-C action target, built lazily and kept alive here.
        self._target: Any | None = None

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
        # Whitespace-only is not an error either: `_one_line` would reduce it
        # to nothing and render a blank row the user cannot tell from a
        # rendering fault.
        self._error = message if message and message.strip() else None
        self._refresh()

    def set_hotkey_options(
        self, available: Sequence[str], current: str
    ) -> None:
        """Offer the bindings the listener recognises, and mark the live one.

        The tray does not know what changing a hotkey involves — stopping an
        event tap, writing a config file, starting a new tap — and §6.2 says it
        must not. It renders a list and hands a name to `on_hotkey`, exactly as
        `Quit` hands nothing to `on_quit`.

        This exists because right-option double-tap fires another
        application's shortcut on the operator's machine, which is not
        something a config file the daemon reads once at startup can fix
        comfortably.
        """
        self._hotkeys = tuple(available)
        self._hotkey_current = current
        self._refresh()

    def set_mode_options(self, available: Sequence[str], current: str) -> None:
        """Offer §5.2's capture modes and mark the live one.

        Same shape as the hotkey picker and for the same reason: hold-to-talk
        versus press-to-start is something a user tries rather than decides,
        and §5.2 already calls all three config-selectable.
        """
        self._modes = tuple(available)
        self._mode_current = current
        self._refresh()

    def set_on_mode(self, on_mode: Callable[[str], None]) -> None:
        self._on_mode = on_mode

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
            # The name is read from the running application (§7.3), so it is
            # another process's string and gets the same treatment as an
            # exception message.
            manager = _one_line(exposure.manager or "") or "A clipboard manager"
            items.append(
                MenuItem(
                    f"{manager} is running — transcripts transit the clipboard"
                )
            )

        if self._hotkeys:
            items.append(
                MenuItem(
                    f"Hotkey: {_pretty_binding(self._hotkey_current)}",
                    enabled=True,
                    submenu=tuple(
                        MenuItem(
                            _binding_label(name),
                            action=f"{HOTKEY_ACTION_PREFIX}{name}",
                            enabled=True,
                            checked=name == self._hotkey_current,
                        )
                        for name in self._hotkeys
                    ),
                )
            )

        if self._modes:
            items.append(
                MenuItem(
                    f"Mode: {_pretty_mode(self._mode_current)}",
                    enabled=True,
                    submenu=tuple(
                        MenuItem(
                            _mode_label(name),
                            action=f"{MODE_ACTION_PREFIX}{name}",
                            enabled=True,
                            checked=name == self._mode_current,
                        )
                        for name in self._modes
                    ),
                )
            )

        items.append(MenuItem("Quit Amanuensis", action="quit", enabled=True))
        return tuple(items)

    def set_on_hotkey(self, on_hotkey: Callable[[str], None]) -> None:
        """Supply the binding-change handler after construction, as `on_quit`
        is supplied — the daemon builds the tray before it can rebind an event
        tap."""
        self._on_hotkey = on_hotkey

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
            return
        if action and action.startswith(MODE_ACTION_PREFIX):
            name = action[len(MODE_ACTION_PREFIX) :]
            if self._on_mode is not None and name in self._modes:
                self._on_mode(name)
            return
        if action and action.startswith(HOTKEY_ACTION_PREFIX):
            name = action[len(HOTKEY_ACTION_PREFIX) :]
            if self._on_hotkey is not None and name in self._hotkeys:
                self._on_hotkey(name)

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
        """Rebuild the rendered menu if there is one. Safe from any thread.

        **The build itself goes to the main queue.** `set_menu` already
        dispatches the *attach*, which is what made this look correct — but
        `NSMenu.alloc()` and every `NSMenuItem` were being constructed on
        whichever thread reported the state change, which is the worker or the
        OS event tap. AppKit object creation is main-thread work, and this is
        the hazard `indicator.py`'s preamble names as the single most likely
        thing to be quietly removed. Found by the stress pass, not by a unit
        test: the fake main queue runs blocks inline, so every existing test
        passed with the construction on the wrong thread.
        """
        with self._lock:
            if self._menu is None:
                return
        from amanuensis.ui.indicator import _main_queue

        _main_queue().addOperationWithBlock_(
            lambda: self._indicator.set_menu(self._build_menu())
        )

    def _build_menu(self) -> Any:
        """Data to `NSMenuItem`s, **including the target and action**.

        Setting only title and enabled renders a menu whose items do nothing,
        which is what this did until 2026-09-03. It passed a test that called
        `activate()` directly — the method AppKit was never wired to reach —
        so the test confirmed the author's model of the framework rather than
        the framework.

        It is not a cosmetic gap. Once the daemon is launched from a desktop
        shortcut there is no terminal to Ctrl-C, and an inert quit item is
        §5.4's recorded failure ("the daemon could not be stopped") with the
        escape hatch removed a second time.
        """
        from amanuensis.ui.indicator import _appkit

        appkit = _appkit()
        target = self._action_target()
        menu = appkit.NSMenu.alloc().init()
        for item in self.menu_items():
            row = appkit.NSMenuItem.alloc().init()
            row.setTitle_(item.title)
            row.setEnabled_(item.enabled)
            if item.checked:
                row.setState_(1)  # NSControlStateValueOn
            if item.submenu:
                child = appkit.NSMenu.alloc().init()
                for sub in item.submenu:
                    sub_row = appkit.NSMenuItem.alloc().init()
                    sub_row.setTitle_(sub.title)
                    sub_row.setEnabled_(sub.enabled)
                    if sub.checked:
                        sub_row.setState_(1)
                    if sub.action is not None:
                        sub_row.setRepresentedObject_(sub.action)
                        sub_row.setTarget_(target)
                        sub_row.setAction_("amanuensisMenuAction:")
                    child.addItem_(sub_row)
                row.setSubmenu_(child)
            if item.action is not None:
                # The verb travels on the item, so one target serves every row
                # and `activate` stays the single place that decides what a
                # verb means.
                row.setRepresentedObject_(item.action)
                row.setTarget_(target)
                row.setAction_("amanuensisMenuAction:")
            menu.addItem_(row)
        with self._lock:
            self._menu = menu
        return menu

    def _action_target(self) -> Any:
        """The Objective-C object AppKit sends the action to.

        Held on `self` because PyObjC does not retain it for us: a target that
        is garbage collected leaves a menu item pointing at freed memory, which
        is a crash rather than a dead click.
        """
        if self._target is None:
            self._target = _menu_target_class().alloc().init()
            self._target.handler = self.activate
        return self._target
