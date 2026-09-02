"""The global hotkey, and the reasons it is the most dangerous thing here.

A `CGEventTap` sees every event of its chosen type on the whole machine. That
is what makes a global hotkey possible and it is also why these tests spend
most of their length on properties that have nothing to do with dictation:

**The tap is listen-only, and that is asserted rather than assumed.** An active
tap can modify or swallow events. A dictation tool that drops a keystroke it
did not mean to drop is a worse failure than one that misses a hotkey — the
first corrupts other applications' input, the second is a hotkey that did not
fire. `kCGEventTapOptionListenOnly` is checked at the call, because it is one
argument position away from being wrong and nothing later would notice.

**Callbacks are transitions, not levels.** macOS reports modifier state as a
flags bitmask on every `flagsChanged` event, so "the option bit is set" fires
repeatedly and fires for the *other* option key. Holding left-option and
tapping right-option must not deliver a press the user did not make, and
releasing right-option while left-option is still held must still deliver a
release. Both are asserted, because a level-triggered reading passes the naive
test and misbehaves on a real keyboard.

**Permission is checked without prompting.** `CGPreflightListenEventAccess` is
the non-prompting half of a documented pair, exactly as
`CGPreflightPostEventAccess` is for Accessibility (Phase 2a). Input Monitoring
is a *different* grant from Accessibility, and a user who granted one usually
believes they granted both — so the remediation names the right pane and says
so.

Quartz is faked throughout. A test that installed a real event tap would need
Input Monitoring granted to the test runner, and would then be watching the
developer's actual keyboard.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from amanuensis.config import HotkeyConfig
from amanuensis.hotkey import macos as macos_hotkey
from amanuensis.hotkey.factory import create_hotkey_listener
from amanuensis.hotkey.macos import (
    MacOSHotkeyListener,
    UnsupportedBindingError,
)
from amanuensis.injection.factory import UnsupportedPlatformError

RIGHT_OPTION_KEYCODE = 61
LEFT_OPTION_KEYCODE = 58

#: The generic "some option key is down" bit. Set while *either* option key is
#: held, which is exactly why the listener cannot use it — see
#: `test_release_fires_while_the_other_option_key_is_held`.
ALTERNATE_MASK = 0x00080000
#: The device-dependent per-side bits (IOKit `IOLLEvent.h`, `NX_DEVICE*`).
#: These are the ones that answer "is *this* key down".
RIGHT_OPTION_BIT = 0x000040
LEFT_OPTION_BIT = 0x000020


class _FakeMachPort:
    def __init__(self) -> None:
        self.enabled: list[bool] = []


class _FakeQuartz:
    """Enough of Quartz to install a tap, run a loop, and post fake events.

    `CFRunLoopRun` blocks like the real one does — on an event the fake
    `CFRunLoopStop` sets — because the listener's whole threading contract is
    that `start()` returns while the loop is still running.
    """

    kCGSessionEventTap = "session"
    kCGHeadInsertEventTap = "head"
    kCGEventTapOptionListenOnly = "listen-only"
    kCGEventTapOptionDefault = "default"
    kCGEventFlagsChanged = 12
    kCGEventTapDisabledByTimeout = 0xFFFFFFFE
    kCGEventTapDisabledByUserInput = 0xFFFFFFFF
    kCGEventFlagMaskAlternate = ALTERNATE_MASK
    kCGEventFlagMaskCommand = 0x00100000
    kCGEventFlagMaskControl = 0x00040000
    kCGEventFlagMaskShift = 0x00020000
    kCGEventFlagMaskSecondaryFn = 0x00800000
    kCGKeyboardEventKeycode = 9
    kCFRunLoopCommonModes = "common"

    def __init__(self, *, granted: bool = True, tap_fails: bool = False) -> None:
        self.granted = granted
        self.tap_fails = tap_fails
        self.tap_calls: list[dict[str, Any]] = []
        self.port: _FakeMachPort | None = None
        self.callback: Any = None
        self.added_sources: list[tuple[Any, Any, Any]] = []
        self.running = threading.Event()
        self.stopped = threading.Event()
        self.loops_run = 0
        self.removed_sources: list[Any] = []

    # -- permission --------------------------------------------------------

    def CGPreflightListenEventAccess(self) -> bool:
        return self.granted

    # -- tap ---------------------------------------------------------------

    def CGEventMaskBit(self, event_type: int) -> int:
        return 1 << event_type

    def CGEventTapCreate(
        self,
        tap: str,
        place: str,
        options: str,
        mask: int,
        callback: Any,
        user_info: Any,
    ) -> _FakeMachPort | None:
        self.tap_calls.append(
            {
                "tap": tap,
                "place": place,
                "options": options,
                "mask": mask,
                "user_info": user_info,
            }
        )
        if self.tap_fails:
            return None
        self.callback = callback
        self.port = _FakeMachPort()
        return self.port

    def CGEventTapEnable(self, port: _FakeMachPort, enabled: bool) -> None:
        port.enabled.append(enabled)

    def CFMachPortCreateRunLoopSource(
        self, _allocator: Any, port: _FakeMachPort, _order: int
    ) -> str:
        return f"source-for-{id(port)}"

    def CFMachPortInvalidate(self, port: _FakeMachPort) -> None:
        port.enabled.append(False)

    # -- run loop ----------------------------------------------------------

    def CFRunLoopGetCurrent(self) -> str:
        return "current-loop"

    def CFRunLoopAddSource(self, loop: Any, source: Any, mode: Any) -> None:
        self.added_sources.append((loop, source, mode))

    def CFRunLoopRemoveSource(self, _loop: Any, source: Any, _mode: Any) -> None:
        self.removed_sources.append(source)

    def CFRunLoopRun(self) -> None:
        self.loops_run += 1
        self.running.set()
        self.stopped.wait(5.0)
        self.stopped.clear()
        self.running.clear()

    def CFRunLoopStop(self, _loop: Any) -> None:
        self.stopped.set()

    # -- events ------------------------------------------------------------

    def CGEventGetIntegerValueField(self, event: dict[str, Any], field: int) -> int:
        assert field == self.kCGKeyboardEventKeycode
        return int(event["keycode"])

    def CGEventGetFlags(self, event: dict[str, Any]) -> int:
        return int(event["flags"])

    # -- the test's own handle --------------------------------------------

    def deliver(self, keycode: int, flags: int, event_type: int | None = None) -> Any:
        """Call the installed tap callback the way the OS would."""
        assert self.callback is not None, "no tap callback was installed"
        kind = self.kCGEventFlagsChanged if event_type is None else event_type
        return self.callback("proxy", kind, {"keycode": keycode, "flags": flags}, None)


class _Recorder:
    def __init__(self) -> None:
        self.events: list[str] = []

    def press(self) -> None:
        self.events.append("press")

    def release(self) -> None:
        self.events.append("release")


@pytest.fixture
def quartz(monkeypatch: pytest.MonkeyPatch) -> _FakeQuartz:
    fake = _FakeQuartz()
    monkeypatch.setattr(macos_hotkey, "_quartz", lambda: fake)
    return fake


@pytest.fixture
def listener(quartz: _FakeQuartz) -> Any:
    made = MacOSHotkeyListener(HotkeyConfig())
    yield made
    if made.is_running:
        made.stop()


# ---------------------------------------------------------------------------
# The tap itself
# ---------------------------------------------------------------------------


def test_tap_is_listen_only(listener: MacOSHotkeyListener, quartz: _FakeQuartz) -> None:
    """The single most consequential argument in this module.

    An active tap can rewrite or discard the events it sees — every modifier
    press on the machine, in this case. Listen-only is not a preference.
    """
    recorder = _Recorder()
    listener.start(recorder.press, recorder.release)

    assert len(quartz.tap_calls) == 1
    assert quartz.tap_calls[0]["options"] == quartz.kCGEventTapOptionListenOnly


def test_tap_watches_only_flags_changed(
    listener: MacOSHotkeyListener, quartz: _FakeQuartz
) -> None:
    """A tap watching keyDown would see every keystroke the user types."""
    recorder = _Recorder()
    listener.start(recorder.press, recorder.release)

    assert quartz.tap_calls[0]["mask"] == 1 << quartz.kCGEventFlagsChanged


def test_start_returns_while_the_loop_is_still_running(
    listener: MacOSHotkeyListener, quartz: _FakeQuartz
) -> None:
    """§6.3: `start` returns once the tap is installed, not when it stops."""
    recorder = _Recorder()
    listener.start(recorder.press, recorder.release)

    assert quartz.running.wait(5.0), "the run loop never started"
    assert listener.is_running


def test_stop_is_idempotent(listener: MacOSHotkeyListener, quartz: _FakeQuartz) -> None:
    recorder = _Recorder()
    listener.start(recorder.press, recorder.release)
    quartz.running.wait(5.0)

    listener.stop()
    listener.stop()

    assert not listener.is_running


def test_starting_twice_is_refused(
    listener: MacOSHotkeyListener, quartz: _FakeQuartz
) -> None:
    """Two taps on one listener is two callbacks per keypress, silently."""
    recorder = _Recorder()
    listener.start(recorder.press, recorder.release)

    with pytest.raises(RuntimeError, match="already"):
        listener.start(recorder.press, recorder.release)


# ---------------------------------------------------------------------------
# Press and release, as transitions
# ---------------------------------------------------------------------------


def test_press_and_release_fire_for_the_bound_key(
    listener: MacOSHotkeyListener, quartz: _FakeQuartz
) -> None:
    recorder = _Recorder()
    listener.start(recorder.press, recorder.release)

    quartz.deliver(RIGHT_OPTION_KEYCODE, ALTERNATE_MASK | RIGHT_OPTION_BIT)
    quartz.deliver(RIGHT_OPTION_KEYCODE, 0)

    assert recorder.events == ["press", "release"]


def test_other_modifier_keys_are_ignored(
    listener: MacOSHotkeyListener, quartz: _FakeQuartz
) -> None:
    """The tap sees every modifier on the machine. Most are not ours."""
    recorder = _Recorder()
    listener.start(recorder.press, recorder.release)

    quartz.deliver(LEFT_OPTION_KEYCODE, ALTERNATE_MASK | LEFT_OPTION_BIT)
    quartz.deliver(LEFT_OPTION_KEYCODE, 0)

    assert recorder.events == []


def test_a_repeated_press_does_not_fire_twice(
    listener: MacOSHotkeyListener, quartz: _FakeQuartz
) -> None:
    """A duplicate down-event must not start a second capture over a running one.

    Nothing in normal operation produces this — modifier keys do not
    auto-repeat `flagsChanged`. It is asserted because the cost of the guard
    is one boolean and the cost of not having it is two overlapping sessions,
    which is the hazard §6.3's concurrency model spends a paragraph on.
    """
    recorder = _Recorder()
    listener.start(recorder.press, recorder.release)

    quartz.deliver(RIGHT_OPTION_KEYCODE, ALTERNATE_MASK | RIGHT_OPTION_BIT)
    quartz.deliver(RIGHT_OPTION_KEYCODE, ALTERNATE_MASK | RIGHT_OPTION_BIT)

    assert recorder.events == ["press"]


def test_release_fires_while_the_other_option_key_is_held(
    listener: MacOSHotkeyListener, quartz: _FakeQuartz
) -> None:
    """The generic alternate bit stays set when left-option is down.

    This is the failure a naive `flags & kCGEventFlagMaskAlternate` reading
    produces: the user lets go of the hotkey, the generic mask still shows
    alternate because the *other* option key is held, and the recording never
    stops. The per-side device bit is the one that answers the question asked.
    """
    recorder = _Recorder()
    listener.start(recorder.press, recorder.release)

    quartz.deliver(RIGHT_OPTION_KEYCODE, ALTERNATE_MASK | RIGHT_OPTION_BIT)
    # Left option goes down: same generic bit, different key and different
    # device bit. Then right option comes up while left is still held — the
    # generic mask is unchanged and only the right-side bit clears.
    quartz.deliver(
        LEFT_OPTION_KEYCODE, ALTERNATE_MASK | RIGHT_OPTION_BIT | LEFT_OPTION_BIT
    )
    quartz.deliver(RIGHT_OPTION_KEYCODE, ALTERNATE_MASK | LEFT_OPTION_BIT)

    assert recorder.events == ["press", "release"]


def test_a_raising_callback_does_not_kill_the_tap(
    listener: MacOSHotkeyListener, quartz: _FakeQuartz
) -> None:
    """An exception out of the callback would leave the tap installed and dead.

    The event tap runs on a CFRunLoop inside a pyobjc bridge. An exception
    propagating into that C stack is not a traceback the user sees; it is a
    hotkey that stops working for the rest of the session.
    """
    recorder = _Recorder()

    def explode() -> None:
        raise RuntimeError("the controller is having a day")

    listener.start(explode, recorder.release)

    quartz.deliver(RIGHT_OPTION_KEYCODE, ALTERNATE_MASK | RIGHT_OPTION_BIT)
    quartz.deliver(RIGHT_OPTION_KEYCODE, 0)

    assert recorder.events == ["release"]


def test_the_event_is_returned_unmodified(
    listener: MacOSHotkeyListener, quartz: _FakeQuartz
) -> None:
    """Listen-only ignores the return value; returning the event says so anyway."""
    recorder = _Recorder()
    listener.start(recorder.press, recorder.release)

    event = {
        "keycode": RIGHT_OPTION_KEYCODE,
        "flags": ALTERNATE_MASK | RIGHT_OPTION_BIT,
    }
    returned = quartz.callback("proxy", quartz.kCGEventFlagsChanged, event, None)

    assert returned is event


def test_a_timed_out_tap_is_re_enabled(
    listener: MacOSHotkeyListener, quartz: _FakeQuartz
) -> None:
    """macOS disables a tap whose callback was slow. It does not re-enable it.

    Listen-only taps are still subject to this. Without the re-enable the
    hotkey stops working permanently, at the moment the machine was busiest,
    with no error anywhere.
    """
    recorder = _Recorder()
    listener.start(recorder.press, recorder.release)
    assert quartz.port is not None
    before = len(quartz.port.enabled)

    quartz.deliver(0, 0, event_type=quartz.kCGEventTapDisabledByTimeout)

    assert quartz.port.enabled[before:] == [True]


# ---------------------------------------------------------------------------
# Permission — Input Monitoring, not Accessibility
# ---------------------------------------------------------------------------


def test_permission_check_does_not_prompt(
    listener: MacOSHotkeyListener, quartz: _FakeQuartz
) -> None:
    """Preflight, never request. A daemon that prompts at every start trains
    the user to dismiss the dialog that matters."""
    status = listener.check_permissions()

    assert status.granted
    assert not hasattr(quartz, "CGRequestListenEventAccess")


def test_missing_permission_names_input_monitoring(
    quartz: _FakeQuartz, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not Accessibility. They are separate grants with separate panes, and a
    user who granted one for Phase 2a's injection will believe they granted
    both."""
    quartz.granted = False
    listener = MacOSHotkeyListener(HotkeyConfig())

    status = listener.check_permissions()

    assert not status.granted
    assert status.missing == ("Input Monitoring",)
    assert "Input Monitoring" in status.remediation
    assert "Accessibility" in status.remediation  # says it is the *other* one


def test_start_without_permission_raises_with_the_remediation(
    quartz: _FakeQuartz,
) -> None:
    """§6.3: `start` raises if the OS refuses the tap. It refuses before it
    tries, so the message can be the actionable one rather than 'None'."""
    quartz.granted = False
    listener = MacOSHotkeyListener(HotkeyConfig())
    recorder = _Recorder()

    with pytest.raises(macos_hotkey.HotkeyPermissionError) as caught:
        listener.start(recorder.press, recorder.release)

    assert "Input Monitoring" in str(caught.value)
    assert quartz.tap_calls == [], "no tap should be attempted without the grant"


def test_a_refused_tap_raises_rather_than_returning_quietly(
    quartz: _FakeQuartz,
) -> None:
    """`CGEventTapCreate` returns None on failure. A listener that stored the
    None and reported `is_running` would be a hotkey that never fires and
    never says why."""
    quartz.tap_fails = True
    listener = MacOSHotkeyListener(HotkeyConfig())
    recorder = _Recorder()

    with pytest.raises(macos_hotkey.HotkeyPermissionError):
        listener.start(recorder.press, recorder.release)

    assert not listener.is_running


# ---------------------------------------------------------------------------
# Bindings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("binding", "keycode"),
    [
        ("right_option", 61),
        ("left_option", 58),
        ("right_command", 54),
        ("left_command", 55),
        ("right_shift", 60),
        ("fn", 63),
    ],
)
def test_supported_bindings_resolve(
    quartz: _FakeQuartz, binding: str, keycode: int
) -> None:
    listener = MacOSHotkeyListener(HotkeyConfig(binding=binding))
    assert listener.keycode == keycode


def test_an_unsupported_binding_is_refused_by_name(quartz: _FakeQuartz) -> None:
    """§5.3 leaves `binding` a free string, so the rejection lands here — and
    it lists what does work, because a user editing a TOML file cannot guess
    the spelling this table uses."""
    with pytest.raises(UnsupportedBindingError) as caught:
        MacOSHotkeyListener(HotkeyConfig(binding="f13"))

    assert "f13" in str(caught.value)
    assert "right_option" in str(caught.value)


def test_a_mode_this_listener_does_not_implement_is_refused(
    quartz: _FakeQuartz,
) -> None:
    """Accepting an unknown mode and behaving as push-to-talk would be a mode
    that silently does something else.

    Replaced 2026-09-02: this test used to assert that `toggle` and `vad_auto`
    were refused as unbuilt, which was true for two phases and is the thing
    Phase 4 changed. Config validation rejects unknown modes first, so reaching
    here means a caller constructed `HotkeyConfig` directly — which the tests
    do constantly.
    """
    with pytest.raises(UnsupportedBindingError) as caught:
        MacOSHotkeyListener(HotkeyConfig(mode="telepathy"))

    assert "telepathy" in str(caught.value)
    assert "push_to_talk" in str(caught.value), "the error must name what works"


# ---------------------------------------------------------------------------
# The factory
# ---------------------------------------------------------------------------


def test_factory_builds_the_macos_listener(quartz: _FakeQuartz) -> None:
    made = create_hotkey_listener(HotkeyConfig(), platform="darwin")
    assert isinstance(made, MacOSHotkeyListener)


def test_factory_refuses_other_platforms() -> None:
    with pytest.raises(UnsupportedPlatformError) as caught:
        create_hotkey_listener(HotkeyConfig(), platform="linux")

    assert "linux" in str(caught.value)


# ---------------------------------------------------------------------------
# `toggle` — press to start, press again to stop (§5.2, Phase 4)
# ---------------------------------------------------------------------------


@pytest.fixture
def toggle_listener(quartz: _FakeQuartz) -> Any:
    made = MacOSHotkeyListener(HotkeyConfig(mode="toggle"))
    yield made
    if made.is_running:
        made.stop()


def _tap(quartz: _FakeQuartz) -> None:
    """One complete physical press and release of the bound key."""
    quartz.deliver(RIGHT_OPTION_KEYCODE, ALTERNATE_MASK | RIGHT_OPTION_BIT)
    quartz.deliver(RIGHT_OPTION_KEYCODE, 0)


def test_toggle_starts_on_the_first_tap_and_stops_on_the_second(
    toggle_listener: MacOSHotkeyListener, quartz: _FakeQuartz
) -> None:
    recorder = _Recorder()
    toggle_listener.start(recorder.press, recorder.release)

    _tap(quartz)
    assert recorder.events == ["press"], "the first tap must start a session"
    _tap(quartz)
    assert recorder.events == ["press", "release"]


def test_toggle_alternates_indefinitely(
    toggle_listener: MacOSHotkeyListener, quartz: _FakeQuartz
) -> None:
    recorder = _Recorder()
    toggle_listener.start(recorder.press, recorder.release)

    for _ in range(5):
        _tap(quartz)
    assert recorder.events == ["press", "release", "press", "release", "press"]


def test_toggle_ignores_the_physical_release(
    toggle_listener: MacOSHotkeyListener, quartz: _FakeQuartz
) -> None:
    """The whole point of the mode. Letting go must not end the session —
    that is `push_to_talk`, and a user who chose `toggle` chose it to be able
    to let go."""
    recorder = _Recorder()
    toggle_listener.start(recorder.press, recorder.release)

    quartz.deliver(RIGHT_OPTION_KEYCODE, ALTERNATE_MASK | RIGHT_OPTION_BIT)
    quartz.deliver(RIGHT_OPTION_KEYCODE, 0)
    quartz.deliver(RIGHT_OPTION_KEYCODE, 0)  # a stray up-event

    assert recorder.events == ["press"]


def test_toggle_holding_the_key_does_not_stop_it(
    toggle_listener: MacOSHotkeyListener, quartz: _FakeQuartz
) -> None:
    """Holding is how `push_to_talk` is used, and a user switching modes will
    do it out of habit. Holding must not end the session, and releasing after
    a long hold must not either."""
    recorder = _Recorder()
    toggle_listener.start(recorder.press, recorder.release)

    quartz.deliver(RIGHT_OPTION_KEYCODE, ALTERNATE_MASK | RIGHT_OPTION_BIT)
    quartz.deliver(RIGHT_OPTION_KEYCODE, ALTERNATE_MASK | RIGHT_OPTION_BIT)
    quartz.deliver(RIGHT_OPTION_KEYCODE, 0)

    assert recorder.events == ["press"]


def test_push_to_talk_is_unchanged_by_the_toggle_work(
    listener: MacOSHotkeyListener, quartz: _FakeQuartz
) -> None:
    """The regression that would matter most: the default mode still ends on
    release."""
    recorder = _Recorder()
    listener.start(recorder.press, recorder.release)

    _tap(quartz)
    assert recorder.events == ["press", "release"]


def test_toggle_is_accepted_by_the_listener() -> None:
    """It refused with "not built yet — Phase 2b is push_to_talk only"."""
    MacOSHotkeyListener(HotkeyConfig(mode="toggle"))
