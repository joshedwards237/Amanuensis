"""Escape cancels a latched session, and takes no keystroke surface to do it.

`docs/superpowers/specs/overlay-controls.md` §11 deferred this on the grounds
that an Escape binding "means a second tap over every keystroke on the machine".
That is true of a `CGEventTap` and false of `RegisterEventHotKey`, which is what
this module uses — the OS delivers one combination and never sends the process
any other key.

**What these tests cannot do is the important part.** Measured 2026-09-17: under
a bare `NSRunLoop`, `InstallEventHandler` returns 0, `RegisterEventHotKey`
returns 0 with a non-null ref, and the handler never fires. Carbon's dispatcher
is pumped by `NSApplication`. So a test asserting "registration returned 0"
asserts the broken configuration as happily as the working one, and none of
these assert it. The delivery reading is the operator runbook's.
"""

from __future__ import annotations

import ctypes
from typing import Any

import pytest

from amanuensis.hotkey import escape as escape_module
from amanuensis.hotkey.escape import ESCAPE_KEYCODE, EscapeHotkey


class _FakeCarbon:
    """Records what was asked of Carbon, and can refuse the way Carbon does."""

    def __init__(
        self, *, install_status: int = 0, register_status: int = 0
    ) -> None:
        self.install_status = install_status
        self.register_status = register_status
        self.registered_keycodes: list[int] = []
        self.registered_modifiers: list[int] = []
        self.unregister_calls = 0

    def GetApplicationEventTarget(self) -> int:
        return 0xBEEF

    def InstallEventHandler(
        self,
        _target: Any,
        _handler: Any,
        _count: int,
        _spec: Any,
        _data: Any,
        out_ref: Any,
    ) -> int:
        if self.install_status == 0:
            out_ref._obj.value = 0x1111
        return self.install_status

    def RegisterEventHotKey(
        self,
        keycode: int,
        modifiers: int,
        _hotkey_id: Any,
        _target: Any,
        _options: int,
        out_ref: Any,
    ) -> int:
        self.registered_keycodes.append(keycode)
        self.registered_modifiers.append(modifiers)
        if self.register_status == 0:
            out_ref._obj.value = 0x2222
        return self.register_status

    def UnregisterEventHotKey(self, _ref: Any) -> int:
        self.unregister_calls += 1
        return 0


@pytest.fixture
def carbon(monkeypatch: pytest.MonkeyPatch) -> _FakeCarbon:
    fake = _FakeCarbon()
    monkeypatch.setattr(escape_module, "carbon", lambda: fake)
    return fake


def test_it_registers_escape_with_no_modifiers(carbon: _FakeCarbon) -> None:
    """The keycode is the assertion, not the call count.

    `RegisterEventHotKey` takes a virtual key code, and registering the wrong
    one produces a product that works perfectly and cancels on a key nobody
    pressed. 53 is Escape in `Events.h`.
    """
    hotkey = EscapeHotkey(lambda: None)

    assert hotkey.register() is True
    assert carbon.registered_keycodes == [ESCAPE_KEYCODE]
    assert carbon.registered_modifiers == [0]


def test_registering_twice_takes_escape_once(carbon: _FakeCarbon) -> None:
    """Two latches without an intervening release must not stack registrations.

    Each `RegisterEventHotKey` needs its own `Unregister`, so a second
    registration over the top leaks the first — and a leaked registration is a
    dead Escape key for every application on the machine, not just this one.
    """
    hotkey = EscapeHotkey(lambda: None)

    hotkey.register()
    hotkey.register()

    assert carbon.registered_keycodes == [ESCAPE_KEYCODE]


def test_unregistering_is_idempotent_and_safe_before_registering(
    carbon: _FakeCarbon,
) -> None:
    """It is called from several end paths and from shutdown, all of which run.

    The state machine has more ways out than in — a finished session, an abort,
    an error, a daemon stopping — and making each one prove it is the only
    caller is how one of them ends up not calling it at all.
    """
    hotkey = EscapeHotkey(lambda: None)

    hotkey.unregister()
    assert carbon.unregister_calls == 0

    hotkey.register()
    hotkey.unregister()
    hotkey.unregister()

    assert carbon.unregister_calls == 1
    assert hotkey.registered is False


def test_a_refused_registration_is_reported_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The caller is a latch that has already happened.

    Failing the dictation because a convenience key was unavailable would trade
    the user's words for their shortcut. `register` returns False, the daemon
    says so in the tray, and the ✕ control is still the way out — which is what
    §11 meant by calling it the only cancel affordance.
    """
    refusing = _FakeCarbon(register_status=-9878)
    monkeypatch.setattr(escape_module, "carbon", lambda: refusing)
    hotkey = EscapeHotkey(lambda: None)

    assert hotkey.register() is False
    assert hotkey.registered is False


def test_a_refused_handler_install_does_not_leave_a_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Order matters: the handler goes in first, the hotkey second.

    If the handler fails and the hotkey is registered anyway, Escape is taken
    from the whole machine and delivered to nothing — the worst of both, and
    invisible until somebody presses it in another application.
    """
    refusing = _FakeCarbon(install_status=-50)
    monkeypatch.setattr(escape_module, "carbon", lambda: refusing)
    hotkey = EscapeHotkey(lambda: None)

    assert hotkey.register() is False
    assert refusing.registered_keycodes == []


def test_a_missing_carbon_is_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    """ctypes buys no dependency and costs a load that can fail."""

    def _unavailable() -> Any:
        raise OSError("Carbon did not load")

    monkeypatch.setattr(escape_module, "carbon", _unavailable)

    assert EscapeHotkey(lambda: None).register() is False


def test_the_callback_survives_a_raising_handler(carbon: _FakeCarbon) -> None:
    """An exception out of `_dispatch` unwinds into C.

    Same reasoning as `hotkey/macos.py:_fire`: what reaches the user is not a
    traceback, it is a key that quietly stopped working.
    """
    hotkey = EscapeHotkey(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    hotkey.register()

    assert hotkey._dispatch(None, None, None) == 0


def test_carbon_exposes_the_symbols_this_module_calls() -> None:
    """A contract test against the framework, not the fake.

    Every assertion above runs through a stand-in this repository wrote, so it
    can only confirm the module calls what the fake was built to receive. Two of
    three framework calls added on 2026-09-17 were wrong in exactly that way —
    a flat `NSRect` and an invented `CATransaction` shape — and both had a green
    suite.
    """
    if not hasattr(ctypes, "cdll"):  # pragma: no cover
        pytest.skip("ctypes unavailable")
    try:
        library = escape_module.carbon()
    except OSError:  # pragma: no cover — not macOS
        pytest.skip("Carbon is not present")

    for name in (
        "GetApplicationEventTarget",
        "InstallEventHandler",
        "RegisterEventHotKey",
        "UnregisterEventHotKey",
    ):
        assert hasattr(library, name), f"Carbon has no {name} — escape.py calls it"


def test_a_real_registration_round_trips() -> None:
    """Take Escape from the real OS and give it back.

    This is as far as an automated test can go, and the limit is worth stating
    where somebody will read it: it proves the OS **accepted** the registration.
    It does not prove the handler ever runs — under a bare `NSRunLoop` it does
    not, with every status still 0. The daemon runs `NSApplication` through the
    tray, which is where that difference lives, and confirming it is the
    runbook's job rather than this file's.
    """
    try:
        escape_module.carbon()
    except OSError:  # pragma: no cover — not macOS
        pytest.skip("Carbon is not present")

    hotkey = EscapeHotkey(lambda: None)
    try:
        assert hotkey.register() is True, "the OS refused a plain Escape hotkey"
        assert hotkey.registered is True
    finally:
        hotkey.unregister()
    assert hotkey.registered is False
