"""The global hotkey on macOS. A `CGEventTap`, and everything that costs.

This module installs a tap that sees **every modifier-key event on the
machine**, forever, in a process that also holds the microphone. That is what
a global hotkey is, and it is worth being precise about what follows from it.

**The tap is listen-only, and that is not a preference** (`_TAP_OPTION`). An
active tap may rewrite or discard the events it sees. A dictation tool that
swallows a keystroke it did not mean to swallow has broken another
application's input; a listen-only tap that misses an event has failed to
start a dictation. The second failure is recoverable by pressing the key
again. The first is not recoverable at all, and would be indistinguishable
from a hardware fault to the user experiencing it. Phase 2b takes the failure
mode it can apologise for.

**Input Monitoring, not Accessibility.** Phase 2a's injector needs
`CGPreflightPostEventAccess`; this needs `CGPreflightListenEventAccess`. They
are separate grants, in separate System Settings panes, and a user who granted
one for injection will reasonably believe they granted both — so the
remediation here says which one it is *and* says the other is not it. Both are
the non-prompting halves of documented pairs: the `CGRequest*` twins raise a
system dialog, which a daemon that starts at login must never do at startup.

**Modifier state is read from the per-side device bits, not the generic mask.**
`kCGEventFlagMaskAlternate` is set while *either* option key is down. Release
right-option while left-option is held and the generic bit does not change, so
a listener reading it never sees the release and never stops recording. The
device-dependent bits (`NX_DEVICERALTKEYMASK` and friends, IOKit
`IOLLEvent.h`) answer the question actually being asked — is *this* key down —
and are present in `CGEventFlags` on every `flagsChanged` event. They are
undocumented in the CoreGraphics headers and stable since the NeXT era; the
alternative is tracking key identity by hand across events, which is the same
information with a bug in it.

**The callbacks must not block.** The tap runs on a CFRunLoop on its own
thread, and macOS disables a tap whose callback is slow — permanently, with no
error, at the moment the machine was busiest. `_on_event` therefore does the
smallest amount of work that can distinguish a press from a release, hands off,
and re-enables the tap when the OS reports it disabled. Anything slow belongs
on the worker thread (§6.3).

What this module does *not* do: know what a dictation is, record audio, or
decide what a press means. It converts OS events into two callbacks.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Final

from amanuensis.hotkey.base import HotkeyCallback, HotkeyListener
from amanuensis.models.results import PermissionStatus

if TYPE_CHECKING:  # pragma: no cover — import-time cost, not behaviour
    from amanuensis.config import HotkeyConfig

__all__ = [
    "HotkeyPermissionError",
    "MacOSHotkeyListener",
    "UnsupportedBindingError",
]

#: Binding name -> (virtual key code, the device-dependent flag bit that is
#: set while *that specific key* is held).
#:
#: The device bits come from IOKit's `IOLLEvent.h` (`NX_DEVICE*KEYMASK`). They
#: are not in the CoreGraphics headers, which expose only the side-agnostic
#: `kCGEventFlagMask*` constants — and those cannot distinguish left from
#: right, which is the entire point of binding to one option key rather than
#: both. `fn` has no left/right split and uses the CoreGraphics bit.
_BINDINGS: Final[dict[str, tuple[int, int]]] = {
    "left_control": (59, 0x000001),
    "left_shift": (56, 0x000002),
    "right_shift": (60, 0x000004),
    "left_command": (55, 0x000008),
    "right_command": (54, 0x000010),
    "left_option": (58, 0x000020),
    "right_option": (61, 0x000040),
    "right_control": (62, 0x002000),
    "fn": (63, 0x800000),
}

#: §9 Phase 2b is push-to-talk only. `toggle` and `vad_auto` are Phase 4, and
#: §5.2 calls `vad_auto` the mode most likely to misfire — accepting the key
#: and behaving as push-to-talk would be a configured mode silently doing
#: something else.
_SUPPORTED_MODES: Final[frozenset[str]] = frozenset(
    {"push_to_talk", "toggle", "vad_auto"}
)

#: How long `start()` waits for the tap thread to install the tap. Generous —
#: it covers a pyobjc import on a cold process, and the failure it guards
#: against is a hang, not a slow machine.
_START_TIMEOUT_S: Final = 5.0

#: `stop()` retries the run-loop stop this many times, `_STOP_POLL_S` apart.
#: See `stop` for the race this covers.
_STOP_ATTEMPTS: Final = 20
_STOP_POLL_S: Final = 0.1

_INPUT_MONITORING_PANE: Final = (
    "x-apple.systempreferences:com.apple.preference.security" "?Privacy_ListenEvent"
)

_REMEDIATION: Final = f"""\
Amanuensis cannot see the hotkey until macOS grants Input Monitoring.
Open the pane:

    open "{_INPUT_MONITORING_PANE}"

This is **not** the Accessibility permission. Accessibility lets Amanuensis
type text into other applications; Input Monitoring lets it see the key you
press to start. They are granted separately, in different panes, and granting
one does not grant the other.

macOS grants this per application, and it grants it to whatever launched
`manu` — so look for your terminal in the list (Terminal, iTerm, Ghostty,
VS Code), not for "Amanuensis". Toggle it on, then start the daemon again;
the grant is read at launch, so an already-running process will not notice
it."""


class HotkeyPermissionError(Exception):
    """The OS refused the event tap. Carries the remediation, verbatim."""


class UnsupportedBindingError(Exception):
    """`[hotkey] binding` or `mode` names something this listener cannot do."""


def _quartz() -> Any:
    """Import Quartz at the point of use, never at module import.

    Same argument `injection/macos.py` makes: `manu --help` must not load the
    Objective-C runtime. This is also the seam the tests replace — installing
    a real tap in a test would need Input Monitoring granted to pytest and
    would then be watching the developer's actual keyboard.
    """
    import Quartz

    return Quartz


class MacOSHotkeyListener(HotkeyListener):
    """Turns modifier-key events into press and release callbacks.

    Takes the `[hotkey]` slice of the config, not the whole thing (§6.3): a
    listener that could read `[injection]` is a listener that could grow an
    opinion about injection.
    """

    def __init__(self, config: HotkeyConfig) -> None:
        if config.mode not in _SUPPORTED_MODES:
            known = ", ".join(sorted(_SUPPORTED_MODES))
            raise UnsupportedBindingError(
                f"hotkey.mode: {config.mode!r} is not a capture mode this "
                f"listener implements. Known modes: {known} (PRD §5.2)."
            )
        if config.binding not in _BINDINGS:
            known = ", ".join(sorted(_BINDINGS))
            raise UnsupportedBindingError(
                f"hotkey.binding: {config.binding!r} is not a modifier key "
                f"this listener recognises. Known bindings: {known}. "
                "Non-modifier keys are not supported — a tap that watched "
                "keyDown would see every character the user types, which is a "
                "much larger surface than a dictation hotkey needs."
            )

        self._config = config
        self._keycode, self._flag_bit = _BINDINGS[config.binding]

        #: `toggle` and `vad_auto` both start on a key-down and neither ends
        #: on the matching key-up, so the listener carries whether a session is
        #: open. `push_to_talk` never reads it — its transitions *are* the key
        #: transitions, which is exactly what makes it the predictable default.
        self._session_open = False

        self._on_press: HotkeyCallback | None = None
        self._on_release: HotkeyCallback | None = None
        self._thread: threading.Thread | None = None
        self._loop: Any | None = None
        self._port: Any | None = None
        self._source: Any | None = None
        self._ready = threading.Event()
        #: A one-slot holder rather than an `Exception | None` attribute:
        #: the value is written on the tap thread and read on the caller's,
        #: and a plain attribute reads to a type checker as though nothing
        #: between the two assignments could have changed it.
        self._start_error: list[Exception] = []
        #: Guards against a duplicate down-event starting a second capture over
        #: a running one. Only ever touched on the event-tap thread.
        self._is_down = False

    # -- introspection -----------------------------------------------------

    @property
    def keycode(self) -> int:
        """The virtual key code this listener watches. For diagnostics."""
        return self._keycode

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- the ABC -----------------------------------------------------------

    def check_permissions(self) -> PermissionStatus:
        """Can this process observe input? Asked without prompting.

        `CGPreflightListenEventAccess` is the non-prompting half of a
        documented pair. `CGRequestListenEventAccess` raises the system
        dialog, and a daemon that starts at login and prompts every time
        teaches the user to dismiss whatever it shows them.
        """
        if _quartz().CGPreflightListenEventAccess():
            return PermissionStatus(granted=True)
        return PermissionStatus(
            granted=False,
            missing=("Input Monitoring",),
            remediation=_REMEDIATION,
        )

    def start(self, on_press: HotkeyCallback, on_release: HotkeyCallback) -> None:
        """Install the tap and begin listening. Returns once it is installed.

        The permission is checked *before* the tap is attempted, so the error
        the user sees is the actionable one. `CGEventTapCreate` reports
        failure by returning `None`, which would otherwise surface as a
        `TypeError` several frames later — or, worse, as a listener that
        reports itself running and never fires.
        """
        if self.is_running:
            raise RuntimeError("this listener is already running; call stop() first")

        status = self.check_permissions()
        if not status.granted:
            raise HotkeyPermissionError(status.remediation)

        self._on_press = on_press
        self._on_release = on_release
        self._is_down = False
        self._session_open = False
        self._start_error.clear()
        self._ready.clear()

        thread = threading.Thread(
            target=self._run, name="amanuensis-hotkey", daemon=True
        )
        self._thread = thread
        thread.start()

        # Wait for the tap to be installed, not for the loop to finish. A
        # daemon that reported "listening" before the tap existed would have a
        # window in which the hotkey silently does nothing.
        if not self._ready.wait(_START_TIMEOUT_S):
            self._thread = None
            raise HotkeyPermissionError(
                "the hotkey listener did not finish starting within "
                f"{_START_TIMEOUT_S:g}s"
            )
        if self._start_error:
            self._thread = None
            raise self._start_error[0]

    def stop(self) -> None:
        """Stop the run loop and release the tap. Idempotent.

        `CFRunLoopStop` on a loop that has not entered `CFRunLoopRun` yet is a
        no-op, which would leave the thread running forever. The retry exists
        for that race and nothing else — `start()` returns as soon as the tap
        is installed, which is deliberately *before* the loop is entered.
        """
        thread = self._thread
        if thread is None:
            return

        quartz = _quartz()
        deadline = _STOP_ATTEMPTS
        while thread.is_alive() and deadline > 0:
            if self._loop is not None:
                quartz.CFRunLoopStop(self._loop)
            thread.join(_STOP_POLL_S)
            deadline -= 1

        if self._port is not None:
            quartz.CGEventTapEnable(self._port, False)

        self._thread = None
        self._loop = None
        self._port = None
        self._source = None

    # -- the tap thread ----------------------------------------------------

    def _run(self) -> None:
        """Install the tap on this thread's run loop, then run it.

        Everything here happens on the tap's own thread because
        `CFRunLoopGetCurrent()` returns *this* thread's loop and there is no
        other way to name it.
        """
        quartz = _quartz()
        try:
            port = quartz.CGEventTapCreate(
                quartz.kCGSessionEventTap,
                quartz.kCGHeadInsertEventTap,
                quartz.kCGEventTapOptionListenOnly,
                quartz.CGEventMaskBit(quartz.kCGEventFlagsChanged),
                self._on_event,
                None,
            )
            if port is None:
                # The preflight said yes and the tap said no. Most often this
                # is a grant that was revoked while the process ran, or a TCC
                # database that has not caught up with a toggle.
                raise HotkeyPermissionError(
                    "macOS refused the event tap even though Input Monitoring "
                    "reported as granted. Toggle the permission off and on "
                    f"again, then restart the daemon.\n\n{_REMEDIATION}"
                )

            source = quartz.CFMachPortCreateRunLoopSource(None, port, 0)
            loop = quartz.CFRunLoopGetCurrent()
            quartz.CFRunLoopAddSource(loop, source, quartz.kCFRunLoopCommonModes)
            quartz.CGEventTapEnable(port, True)

            self._port = port
            self._source = source
            self._loop = loop
        except Exception as exc:  # reported through `start`, not this thread
            self._start_error.append(exc)
            self._ready.set()
            return

        self._ready.set()
        quartz.CFRunLoopRun()

    def _callback_for(self, down: bool) -> HotkeyCallback | None:
        """Which callback a key transition means, in this mode (§5.2).

        `push_to_talk` — down starts, up ends. The guarantee is physical: your
        finger is on the key, so you always know.

        `toggle` — down alternates and up means nothing. A user who chose this
        chose it to be able to let go, so ending on the physical release would
        be the mode failing to be itself. Holding the key does nothing either,
        which matters because a user switching from `push_to_talk` will hold it
        out of habit.

        `vad_auto` — down starts and **nothing here ever ends it**. §5.2 is
        "press to start, silence detection ends the session": the finger still
        opens the microphone, and only the close is automatic. The end comes
        from the audio layer, which is the only place that can see silence.
        That makes this the one mode where the listener cannot guarantee the
        microphone ever closes, and why `[vad_auto] max_seconds` exists.
        """
        if self._config.mode == "push_to_talk":
            return self._on_press if down else self._on_release
        if not down:
            return None
        if self._config.mode == "vad_auto":
            return self._on_press
        # The flip is **not** committed here. If the callback raises — the
        # controller refusing to start, most plausibly — a listener that had
        # already flipped would send a `release` on the next tap for a session
        # that never began, and every tap after that would be inverted. The
        # caller commits on success; see `_on_event`.
        return self._on_press if not self._session_open else self._on_release

    def _on_event(
        self, _proxy: Any, event_type: int, event: Any, _user_info: Any
    ) -> Any:
        """The tap callback. Runs on the tap thread — keep it short.

        Returns the event unmodified. A listen-only tap's return value is
        ignored by the OS; returning the event anyway states the intent at the
        one place a future edit would change it.
        """
        quartz = _quartz()

        # macOS disables a tap whose callback was slow, or when the user
        # revokes the grant. It does not re-enable it, and nothing reports it:
        # the hotkey simply stops working for the rest of the session.
        if event_type in (
            quartz.kCGEventTapDisabledByTimeout,
            quartz.kCGEventTapDisabledByUserInput,
        ):
            if self._port is not None:
                quartz.CGEventTapEnable(self._port, True)
            return event

        if event_type != quartz.kCGEventFlagsChanged:
            return event
        if quartz.CGEventGetIntegerValueField(
            event, quartz.kCGKeyboardEventKeycode
        ) != (self._keycode):
            return event

        down = bool(quartz.CGEventGetFlags(event) & self._flag_bit)
        if down == self._is_down:
            return event
        self._is_down = down

        callback = self._callback_for(down)
        if callback is not None:
            try:
                callback()
            except Exception:
                # An exception propagating from here goes into a pyobjc bridge
                # and then into CFRunLoop's C stack. It is not a traceback the
                # user reads; it is a hotkey that stops working. The callbacks
                # are the controller's, which reports its own errors.
                #
                # It also leaves `toggle` where it was. A flip committed before
                # the callback would invert every tap that followed a single
                # failed start, and the user's only repair would be to press
                # the key an odd number of times without knowing it.
                return event
            if self._config.mode == "toggle" and down:
                self._session_open = not self._session_open
        return event
