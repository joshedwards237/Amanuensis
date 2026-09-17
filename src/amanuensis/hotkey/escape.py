"""Escape cancels a latched session, and costs no keystroke surface.

**§11 of `docs/superpowers/specs/overlay-controls.md` said this could not
cheaply be added, and it was right about the mechanism it considered.** The
recorded reasoning:

> `hotkey/macos.py` watches `kCGEventFlagsChanged` only and refuses `keyDown`
> by design — "a tap that watched keyDown would see every character the user
> types, which is a much larger surface than a dictation hotkey needs." An
> Escape binding means a second tap over every keystroke on the machine, which
> is a §7.6 decision, not a UI one.

That is true of a `CGEventTap`, and a tap is what §11 had in mind. It is not
true of **`RegisterEventHotKey`**, which asks the OS for one key combination
and receives only that combination. There is no callback for any other key,
because the process is never sent one. So the §7.6 objection does not apply to
this mechanism, and the feature arrives without the cost that deferred it.

What it costs instead is stated here rather than discovered later.

* **Escape belongs to this process while registered**, system-wide. Every other
  application stops seeing it. That is why registration is **scoped to a
  latched session** — it goes in when the latch closes and comes out when the
  session ends. A hands-free dictation is a window in which the user is
  speaking rather than pressing Escape at something else; the whole rest of the
  day, Escape is nobody's but the frontmost app's.
* **A leaked registration is a broken Escape key** for the machine, not just
  for this product. `unregister` is therefore idempotent and is called from the
  session-end path *and* from `stop()`, and the daemon's shutdown runs it even
  when the session ended badly.

**Carbon, through ctypes.** There is no pyobjc package exporting these symbols,
which is the same situation `IOHIDRequestAccess` is in one module over, and the
same answer: ctypes costs no dependency and costs a hand-declared signature
instead. Hence the explicit `argtypes`/`restype` and the guard around the load.

**Registration succeeding does not mean the callback will ever run**, and this
is the part worth reading twice. Measured 2026-09-17: under a bare
`NSRunLoop`, `InstallEventHandler` returns 0, `RegisterEventHotKey` returns 0
and a non-null ref, and **the handler never fires**. Carbon's event dispatcher
is pumped by `NSApplication`, not by a run loop alone. Under
`NSApplication`'s event dispatch the same code fires immediately.

That is the exact shape of `CGRequestPostEventAccess`, which shipped with 707
green tests and registered nothing: an API that reports success and does not do
the thing. The daemon runs `NSApplication` through `TrayApp.run`, so this works
where it ships — but nothing in this module can prove that, and a test that
asserted "registration returned 0" would be asserting the failing case as
readily as the working one.
"""

from __future__ import annotations

import ctypes
import threading
from collections.abc import Callable
from typing import Any, Final

__all__ = [
    "ESCAPE_KEYCODE",
    "EscapeHotkey",
    "carbon",
]

_CARBON_PATH: Final = "/System/Library/Frameworks/Carbon.framework/Carbon"

#: Virtual key code for Escape. From `Events.h`; stable since the NeXT era and
#: not layout-dependent — the code identifies the physical key, which is what
#: `RegisterEventHotKey` wants.
ESCAPE_KEYCODE: Final = 53

#: `'keyb'` and `kEventHotKeyPressed`, from `CarbonEvents.h`. Registering the
#: *released* variant instead would fire when the user lets go, which for a key
#: that cancels is a difference the user would feel on a key-repeat.
_EVENT_CLASS_KEYBOARD: Final = 0x6B657962
_EVENT_HOT_KEY_PRESSED: Final = 5

#: A four-character code identifying our hotkeys to Carbon. `'AMNU'`. It only
#: has to be distinct from other registrations in the same process.
_SIGNATURE: Final = 0x414D4E55

#: No modifiers. Plain Escape — see the module docstring on why that is
#: acceptable only because registration is scoped to a latched session.
_NO_MODIFIERS: Final = 0


class _EventTypeSpec(ctypes.Structure):
    _fields_ = (("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32))


class _EventHotKeyID(ctypes.Structure):
    _fields_ = (("signature", ctypes.c_uint32), ("id", ctypes.c_uint32))


#: The C signature Carbon calls back on. Kept at module scope because a
#: `CFUNCTYPE` instance must outlive the registration that uses it — a local
#: one is garbage collected and the callback becomes a jump into freed memory,
#: which is a crash rather than a missed keypress.
_HANDLER_TYPE = ctypes.CFUNCTYPE(
    ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
)


def carbon() -> Any:
    """Load Carbon and declare the four signatures. Raises `OSError` if absent.

    A seam as well as a loader: tests replace this rather than the class, the
    same arrangement `hotkey/macos.py` uses for Quartz and IOKit.
    """
    library = ctypes.cdll.LoadLibrary(_CARBON_PATH)
    library.GetApplicationEventTarget.restype = ctypes.c_void_p
    library.InstallEventHandler.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(_EventTypeSpec),
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    library.InstallEventHandler.restype = ctypes.c_int32
    library.RegisterEventHotKey.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
        _EventHotKeyID,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    library.RegisterEventHotKey.restype = ctypes.c_int32
    library.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
    library.UnregisterEventHotKey.restype = ctypes.c_int32
    return library


class EscapeHotkey:
    """Plain Escape, registered only for as long as a latched session runs."""

    def __init__(self, on_escape: Callable[[], None]) -> None:
        self._on_escape = on_escape
        self._hotkey_ref: Any = None
        self._handler: Any = None
        self._handler_ref: Any = None
        #: Guards the registration pair against a latch and a session end
        #: arriving from two threads, which they do: the latch is set on the
        #: event-tap thread and the end can come from the VAD watcher.
        self._lock = threading.Lock()

    @property
    def registered(self) -> bool:
        return self._hotkey_ref is not None

    def register(self) -> bool:
        """Take Escape. Returns whether the OS accepted it.

        False rather than an exception: the caller is a latch that has already
        happened, and a session that cannot be cancelled with a key is worse
        than one that can but is not a reason to fail the dictation. The ✕
        control remains, which is why §11 called it the only cancel affordance.
        """
        with self._lock:
            if self._hotkey_ref is not None:
                return True
            try:
                library = carbon()
            except OSError:
                return False

            target = library.GetApplicationEventTarget()
            # The handler is installed per registration rather than once at
            # construction, so a failed load leaves nothing behind to unwind.
            self._handler = _HANDLER_TYPE(self._dispatch)
            spec = _EventTypeSpec(_EVENT_CLASS_KEYBOARD, _EVENT_HOT_KEY_PRESSED)
            handler_ref = ctypes.c_void_p()
            status = library.InstallEventHandler(
                target,
                ctypes.cast(self._handler, ctypes.c_void_p),
                1,
                ctypes.byref(spec),
                None,
                ctypes.byref(handler_ref),
            )
            if status != 0:
                self._handler = None
                return False

            hotkey_ref = ctypes.c_void_p()
            status = library.RegisterEventHotKey(
                ESCAPE_KEYCODE,
                _NO_MODIFIERS,
                _EventHotKeyID(_SIGNATURE, 1),
                target,
                0,
                ctypes.byref(hotkey_ref),
            )
            if status != 0:
                self._handler = None
                return False
            self._handler_ref = handler_ref
            self._hotkey_ref = hotkey_ref
            return True

    def unregister(self) -> None:
        """Give Escape back. Idempotent, and safe to call having never taken it.

        Idempotent because it is called from two paths that can both run — the
        session ending and the daemon stopping — and because a leaked
        registration is not this product's bug to have, it is a broken Escape
        key on the user's machine.
        """
        with self._lock:
            if self._hotkey_ref is None:
                return
            try:
                carbon().UnregisterEventHotKey(self._hotkey_ref)
            except OSError:  # pragma: no cover — it loaded to get here
                pass
            self._hotkey_ref = None
            self._handler_ref = None
            self._handler = None

    def _dispatch(
        self, _next: Any, _event: Any, _user_data: Any
    ) -> int:  # pragma: no cover — driven by Carbon
        """Carbon's callback. Runs on the main thread, inside its dispatcher.

        Swallows, for `hotkey/macos.py:_fire`'s reason exactly: an exception
        from here unwinds into C, where it is not a traceback anybody reads —
        it is a key that quietly stops working.
        """
        try:
            self._on_escape()
        except Exception:
            pass
        return 0
