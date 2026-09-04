"""`TrayApp` — the §5.4 status surface with a menu, and nothing else.

The menu is a **pure model**: `menu_items()` returns data, and the AppKit code
turns data into `NSMenuItem`s. That split is why almost everything below runs
with no fake framework at all — and it is the only way the error text, which is
the point of the slice, can be asserted on rather than eyeballed.

What these tests are guarding against, specifically: `RecordingIndicator`
already renders all five states, so a `TrayApp` that "shows the state" adds
nothing. What is new is a surface with **room for words** — a glyph cannot say
"Accessibility permission was revoked" — and a persistent clipboard-exposure
row that §5.4 and §7.3 have both assigned to this phase.
"""

from __future__ import annotations

from typing import Any

import pytest

from amanuensis.controllers.dictation_controller import DictationState
from amanuensis.models.results import ClipboardExposure
from amanuensis.ui import indicator as indicator_module
from amanuensis.ui.tray import TrayApp
from test_indicator import _FakeAppKit, _FakeFoundation, _FakeMainQueue

# ---------------------------------------------------------------------------
# State — the half that already worked, kept working
# ---------------------------------------------------------------------------


def test_the_state_row_names_every_state() -> None:
    """§5.4: the user must always know whether the mic is live."""
    tray = TrayApp()
    seen = set()
    for state in DictationState:
        tray.set_state(state)
        row = tray.menu_items()[0]
        assert row.title, f"{state} renders an empty status row"
        seen.add(row.title)
    assert len(seen) == len(DictationState), "two states share a menu row"


def test_recording_says_so_in_words() -> None:
    tray = TrayApp()
    tray.set_state(DictationState.RECORDING)
    assert "RECORDING" in tray.menu_items()[0].title


def test_the_state_is_not_only_in_the_menu() -> None:
    """§5.4: "visible without the tray menu open".

    A menu-bar item whose state can only be read by opening it is the
    requirement restated as its own violation, so the glyph stays in the title.
    """
    tray = TrayApp()
    tray.set_state(DictationState.RECORDING)
    assert tray.title == "●"


# ---------------------------------------------------------------------------
# Errors — the half that is actually new
# ---------------------------------------------------------------------------


def test_an_error_message_reaches_the_menu_in_words() -> None:
    """The whole reason this slice exists. A glyph cannot say what broke."""
    tray = TrayApp()
    tray.set_error("Accessibility permission was revoked")
    titles = [item.title for item in tray.menu_items()]
    assert any("Accessibility permission was revoked" in t for t in titles)


def test_clearing_an_error_removes_the_row() -> None:
    """An error that cannot be cleared is a permanent alarm, which is noise."""
    tray = TrayApp()
    tray.set_error("something failed")
    assert len(tray.menu_items()) > 1
    before = len(tray.menu_items())
    tray.set_error(None)
    assert len(tray.menu_items()) < before
    assert not any("something failed" in i.title for i in tray.menu_items())


def test_a_very_long_error_is_truncated_not_dropped() -> None:
    """A traceback in a menu makes an unusable menu; dropping it hides the
    failure. Truncation is the only answer that does neither."""
    tray = TrayApp()
    tray.set_error("x" * 5000)
    row = next(i for i in tray.menu_items() if i.title.startswith("x"))
    assert len(row.title) < 200
    assert row.title.endswith("…")


def test_an_empty_error_string_is_not_an_error() -> None:
    """`set_error("")` is a caller bug that would otherwise render a blank row
    the user cannot interpret."""
    tray = TrayApp()
    before = len(tray.menu_items())
    tray.set_error("")
    assert len(tray.menu_items()) == before


def test_a_newline_in_an_error_does_not_break_the_row() -> None:
    """Errors in this project are multi-line by habit — see the clipboard
    warning. A menu row is one line."""
    tray = TrayApp()
    tray.set_error("first line\nsecond line")
    row = next(i for i in tray.menu_items() if "first line" in i.title)
    assert "\n" not in row.title
    assert "second line" in row.title


# ---------------------------------------------------------------------------
# Clipboard exposure — §5.4 and §7.3, both assign it here
# ---------------------------------------------------------------------------


def test_a_detected_manager_is_a_persistent_row() -> None:
    tray = TrayApp()
    tray.set_clipboard_exposure(ClipboardExposure(detected=True, manager="Maccy"))
    titles = [i.title for i in tray.menu_items()]
    assert any("Maccy" in t for t in titles)
    assert any("clipboard" in t.lower() for t in titles)


def test_the_exposure_row_survives_a_state_change() -> None:
    """"Persistent" is the requirement. A row that a dictation clears is a
    row that is absent whenever the user looks after using the product."""
    tray = TrayApp()
    tray.set_clipboard_exposure(ClipboardExposure(detected=True, manager="Maccy"))
    for state in DictationState:
        tray.set_state(state)
        assert any("Maccy" in i.title for i in tray.menu_items())


def test_no_manager_detected_shows_no_all_clear() -> None:
    """§7.3, objection O12: the detection list is incomplete by nature, so
    "no known manager detected" is the only true statement available and an
    all-clear is the one a reassuring row would imply."""
    tray = TrayApp()
    tray.set_clipboard_exposure(ClipboardExposure(detected=False))
    for item in tray.menu_items():
        assert "no clipboard" not in item.title.lower()
        assert "safe" not in item.title.lower()
        assert "clear" not in item.title.lower()


# ---------------------------------------------------------------------------
# The boundary — §6.2, a status surface with no business logic
# ---------------------------------------------------------------------------


def test_quit_is_a_callback_not_a_decision() -> None:
    """§6.2. The tray asks; it does not know what stopping means."""
    called: list[bool] = []
    tray = TrayApp(on_quit=lambda: called.append(True))
    quit_item = next(i for i in tray.menu_items() if i.action == "quit")
    assert quit_item.enabled
    tray.activate(quit_item.action)
    assert called == [True]


def test_activating_quit_without_a_handler_does_not_raise() -> None:
    """The daemon wires one; `manu status` and the tests do not."""
    TrayApp().activate("quit")


def test_informational_rows_are_not_clickable() -> None:
    tray = TrayApp()
    tray.set_error("boom")
    tray.set_clipboard_exposure(ClipboardExposure(detected=True, manager="Maccy"))
    for item in tray.menu_items():
        if item.action is None:
            assert not item.enabled


def test_an_unknown_action_is_ignored() -> None:
    """AppKit hands back whatever tag it was given. An unrecognised one is a
    bug in this file, not a reason to kill a daemon holding the microphone."""
    called: list[bool] = []
    tray = TrayApp(on_quit=lambda: called.append(True))
    tray.activate("not-a-real-action")
    assert called == []


def test_set_state_before_show_does_not_raise() -> None:
    """The controller comes up before the run loop, exactly as for the
    indicator — a daemon that crashed on an early state change would fail at
    precisely the moment §5.4 is about."""
    tray = TrayApp()
    tray.set_state(DictationState.RECORDING)
    tray.set_error("early")
    tray.set_clipboard_exposure(ClipboardExposure(detected=True, manager="Maccy"))


# ---------------------------------------------------------------------------
# The AppKit half — one status item, and the menu actually rendered
# ---------------------------------------------------------------------------


class _FakeMenuItem:
    def __init__(self) -> None:
        self.title = ""
        self.enabled: bool | None = None
        #: What AppKit needs in order to reach a handler at all.
        self.target: Any = None
        self.action: str = ""
        self.represented: Any = None
        self.state_value = 0
        self.submenu: Any = None

    @classmethod
    def alloc(cls) -> _FakeMenuItem:
        return cls()

    def init(self) -> _FakeMenuItem:
        return self

    def setTitle_(self, value: str) -> None:
        self.title = value

    def setEnabled_(self, value: bool) -> None:
        self.enabled = value

    def setTarget_(self, value: Any) -> None:
        self.target = value

    def setAction_(self, value: str) -> None:
        self.action = str(value)

    def setState_(self, value: int) -> None:
        self.state_value = value

    def setSubmenu_(self, menu: Any) -> None:
        self.submenu = menu

    def setRepresentedObject_(self, value: Any) -> None:
        self.represented = value

    def representedObject(self) -> Any:
        """The getter. `NSMenuItem` has both and the fake had only the
        setter — the NSRect shape again: invented, not checked."""
        return self.represented


class _FakeMenu:
    def __init__(self) -> None:
        self.items: list[_FakeMenuItem] = []

    @classmethod
    def alloc(cls) -> _FakeMenu:
        return cls()

    def init(self) -> _FakeMenu:
        return self

    def addItem_(self, item: _FakeMenuItem) -> None:
        self.items.append(item)


def test_show_creates_one_status_item_and_attaches_the_menu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two `NSStatusItem`s would put two glyphs in one menu bar. The tray
    composes the indicator precisely so there is one."""
    fake = _FakeAppKit()
    fake.NSMenu = _FakeMenu  # type: ignore[attr-defined]
    fake.NSMenuItem = _FakeMenuItem  # type: ignore[attr-defined]
    foundation = _FakeFoundation(_FakeMainQueue())
    monkeypatch.setattr(indicator_module, "_appkit", lambda: fake)
    monkeypatch.setattr(indicator_module, "_foundation", lambda: foundation)

    tray = TrayApp()
    tray.set_error("Accessibility permission was revoked")
    tray.show()

    assert len(fake.bar.items) == 1, "more than one status item exists"
    item = fake.bar.items[0]
    assert item.menu is not None, "show() attached no menu"
    titles = [row.title for row in item.menu.items]
    assert any("Accessibility permission was revoked" in t for t in titles)
    assert item.button().titles[-1] == "○", "the glyph must stay in the title"


# ---------------------------------------------------------------------------
# Found by the stress pass, not by the tests above
# ---------------------------------------------------------------------------


class _DeferredQueue:
    """Records blocks instead of running them, which is what the real main
    queue does. `_FakeMainQueue` runs them inline, and that is exactly why the
    off-main-thread construction below passed every test until it was looked
    for."""

    def __init__(self) -> None:
        self.blocks: list[Any] = []

    def addOperationWithBlock_(self, block: Any) -> None:
        self.blocks.append(block)

    def drain(self) -> None:
        for block in self.blocks:
            block()
        self.blocks.clear()


def test_the_menu_is_built_on_the_main_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    """AppKit object creation is main-thread work.

    `set_menu` dispatched the *attach*, which made this look right — while
    `NSMenu.alloc()` and every `NSMenuItem` were constructed on whichever
    thread reported the state change, i.e. the worker or the OS event tap.
    `indicator.py`'s preamble names this as the single most likely thing to be
    quietly removed, and it was quietly reintroduced one module over.
    """
    fake = _FakeAppKit()
    allocated: list[int] = []

    class _CountingMenu(_FakeMenu):
        @classmethod
        def alloc(cls) -> _CountingMenu:
            allocated.append(1)
            return cls()

    fake.NSMenu = _CountingMenu  # type: ignore[attr-defined]
    fake.NSMenuItem = _FakeMenuItem  # type: ignore[attr-defined]
    queue = _DeferredQueue()
    monkeypatch.setattr(indicator_module, "_appkit", lambda: fake)
    monkeypatch.setattr(indicator_module, "_foundation", lambda: _FakeFoundation(queue))
    monkeypatch.setattr(indicator_module, "_main_queue", lambda: queue)

    tray = TrayApp()
    tray.show()
    queue.drain()
    allocated.clear()

    tray.set_error("built where?")
    assert allocated == [], "an NSMenu was allocated off the main queue"
    queue.drain()
    assert allocated, "the menu was never built at all"


def test_control_characters_never_reach_a_menu_row() -> None:
    """`str.split()` handles whitespace and leaves NUL, BEL and escapes intact.

    An exception message is arbitrary bytes from somewhere else, and a NUL
    inside an NSString is not a cosmetic problem.
    """
    tray = TrayApp()
    tray.set_error("bad\x00\x07\x1bthing")
    row = next(i for i in tray.menu_items() if "bad" in i.title)
    assert "\x00" not in row.title
    assert "\x07" not in row.title
    assert "\x1b" not in row.title
    assert "badthing" in row.title


def test_a_hostile_manager_name_cannot_break_the_row() -> None:
    """The name is read from the running application (§7.3) — another
    process's string, and treated like one."""
    tray = TrayApp()
    tray.set_clipboard_exposure(
        ClipboardExposure(detected=True, manager="Evil\nApp\x00\n" + "x" * 500)
    )
    row = next(i for i in tray.menu_items() if "clipboard" in i.title.lower())
    assert "\n" not in row.title
    assert "\x00" not in row.title
    assert len(row.title) < 300


def test_a_whitespace_only_error_is_not_an_error() -> None:
    """`_one_line` would reduce it to nothing and render a blank row, which
    the user cannot tell from a rendering fault."""
    tray = TrayApp()
    before = len(tray.menu_items())
    tray.set_error("   \t\n  ")
    assert len(tray.menu_items()) == before


def test_the_quit_item_is_reachable_from_appkit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A menu item with no target and no action renders and does nothing.

    `test_quit_is_a_callback_not_a_decision` above called `tray.activate()`
    directly and passed while the rendered item was inert — the same shape as
    the NSRect fake: a test confirming what the author believed rather than
    what the framework requires. This asserts the wiring AppKit actually needs.

    It matters beyond tidiness. Once the daemon is launched from a desktop
    shortcut there is no terminal to Ctrl-C, so an inert quit item is §5.4's
    recorded failure — "the daemon could not be stopped" — with the escape
    hatch removed again.
    """
    quit_calls: list[bool] = []
    fake = _FakeAppKit()
    fake.NSMenu = _FakeMenu  # type: ignore[attr-defined]
    fake.NSMenuItem = _FakeMenuItem  # type: ignore[attr-defined]
    monkeypatch.setattr(indicator_module, "_appkit", lambda: fake)
    foundation = _FakeFoundation(_FakeMainQueue())
    monkeypatch.setattr(indicator_module, "_foundation", lambda: foundation)

    tray = TrayApp(on_quit=lambda: quit_calls.append(True))
    tray.show()

    rendered = fake.bar.items[0].menu
    row = next(r for r in rendered.items if r.title == "Quit Amanuensis")
    assert row.target is not None, "no target — clicking the quit item does nothing"
    assert row.action, "the quit item has no action"

    # Fire it the way AppKit would: the selector, on the target, with the item.
    getattr(row.target, row.action.replace(":", "_"))(row)
    assert quit_calls == [True], "the action did not reach on_quit"


def test_informational_rows_carry_no_action(monkeypatch: pytest.MonkeyPatch) -> None:
    """A row that does nothing must also look like it does nothing."""
    fake = _FakeAppKit()
    fake.NSMenu = _FakeMenu  # type: ignore[attr-defined]
    fake.NSMenuItem = _FakeMenuItem  # type: ignore[attr-defined]
    monkeypatch.setattr(indicator_module, "_appkit", lambda: fake)
    foundation = _FakeFoundation(_FakeMainQueue())
    monkeypatch.setattr(indicator_module, "_foundation", lambda: foundation)

    tray = TrayApp()
    tray.set_error("something failed")
    tray.show()

    rendered = fake.bar.items[0].menu
    for row in rendered.items:
        if row.title != "Quit Amanuensis":
            assert row.target is None, f"{row.title!r} is wired to an action"


def test_the_hotkey_submenu_offers_every_binding_and_marks_the_live_one() -> None:
    """The operator's right-option double-tap fires another application's
    shortcut, so the binding has to be changeable without editing a file."""
    from amanuensis.hotkey.macos import available_bindings

    tray = TrayApp()
    tray.set_hotkey_options(available_bindings(), "right_option")

    row = next(i for i in tray.menu_items() if i.title.startswith("Hotkey:"))
    assert "Right Option" in row.title, "the live binding is not readable"
    assert len(row.submenu) == len(available_bindings())
    checked = [s for s in row.submenu if s.checked]
    assert len(checked) == 1 and "Right Option" in checked[0].title


def test_choosing_a_binding_hands_the_name_to_the_daemon() -> None:
    """§6.2: the tray does not know what rebinding involves. It hands over a
    name, exactly as Quit hands over nothing."""
    chosen: list[str] = []
    tray = TrayApp(on_hotkey=chosen.append)
    tray.set_hotkey_options(("right_option", "fn"), "right_option")

    row = next(i for i in tray.menu_items() if i.title.startswith("Hotkey:"))
    fn_row = next(s for s in row.submenu if s.title.startswith("Fn"))
    tray.activate(fn_row.action)
    assert chosen == ["fn"]


def test_a_binding_the_listener_does_not_know_is_ignored() -> None:
    """AppKit hands back whatever tag it was given, and a name that is not on
    the offered list is a bug here rather than a reason to rebind to nothing."""
    chosen: list[str] = []
    tray = TrayApp(on_hotkey=chosen.append)
    tray.set_hotkey_options(("right_option",), "right_option")
    tray.activate("hotkey:the_spacebar")
    assert chosen == []


def test_no_hotkey_row_before_the_options_are_supplied() -> None:
    """`manu status` and the tests build a tray with no daemon behind it. An
    empty submenu would offer a choice that goes nowhere."""
    assert not any(i.title.startswith("Hotkey:") for i in TrayApp().menu_items())


def test_the_submenu_rows_are_wired_to_appkit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The parent-menu quit item was inert for a day because nothing checked
    the AppKit wiring. Submenu rows are a second place to make that mistake."""
    fake = _FakeAppKit()
    fake.NSMenu = _FakeMenu  # type: ignore[attr-defined]
    fake.NSMenuItem = _FakeMenuItem  # type: ignore[attr-defined]
    foundation = _FakeFoundation(_FakeMainQueue())
    monkeypatch.setattr(indicator_module, "_appkit", lambda: fake)
    monkeypatch.setattr(indicator_module, "_foundation", lambda: foundation)

    chosen: list[str] = []
    tray = TrayApp(on_hotkey=chosen.append)
    tray.set_hotkey_options(("right_option", "fn"), "right_option")
    tray.show()

    parent = next(
        r for r in fake.bar.items[0].menu.items if r.title.startswith("Hotkey:")
    )
    assert parent.submenu is not None, "the hotkey row has no submenu"
    fn_row = next(r for r in parent.submenu.items if r.title.startswith("Fn"))
    assert fn_row.target is not None, "a submenu row with no target does nothing"
    getattr(fn_row.target, fn_row.action.replace(":", "_"))(fn_row)
    assert chosen == ["fn"]


def test_bindings_used_in_shortcuts_say_so() -> None:
    """The menu offered nine bindings as equals and the operator picked Right
    Command to dodge a double-tap conflict — which fires on every ⌘ shortcut.
    A choice offered without its cost is how someone picks worse than default.
    """
    from amanuensis.hotkey.macos import COLLIDING_BINDINGS, available_bindings

    tray = TrayApp()
    tray.set_hotkey_options(available_bindings(), "right_option")
    row = next(i for i in tray.menu_items() if i.title.startswith("Hotkey:"))

    for sub, name in zip(row.submenu, available_bindings(), strict=True):
        if name in COLLIDING_BINDINGS:
            assert "shortcuts" in sub.title, f"{name} carries no warning"
        else:
            assert "shortcuts" not in sub.title, f"{name} warns without cause"


def test_the_default_binding_is_not_flagged() -> None:
    """`right_option` is the default precisely because it is not used inside
    ordinary shortcuts. If it ever gets flagged, the list is wrong."""
    from amanuensis.hotkey.macos import COLLIDING_BINDINGS

    assert "right_option" not in COLLIDING_BINDINGS


def test_the_mode_submenu_describes_each_mode_rather_than_naming_it() -> None:
    """`vad_auto` in a menu is a puzzle, not a choice. §5.2 already has a
    one-line description of each mode and those are what a user needs."""
    from amanuensis.hotkey.macos import available_modes

    tray = TrayApp()
    tray.set_mode_options(available_modes(), "push_to_talk")
    row = next(i for i in tray.menu_items() if i.title.startswith("Mode:"))

    assert "Hold to talk" in row.title
    titles = [s.title for s in row.submenu]
    assert len(titles) == len(available_modes())
    assert not any("_" in t for t in titles), f"config spellings leaked: {titles}"
    assert sum(s.checked for s in row.submenu) == 1


def test_vad_auto_carries_the_warning_the_spec_gives_implementers() -> None:
    """§5.2 calls it "the mode most likely to misfire". A user picking it from
    a menu deserves the same sentence."""
    from amanuensis.hotkey.macos import available_modes

    tray = TrayApp()
    tray.set_mode_options(available_modes(), "push_to_talk")
    row = next(i for i in tray.menu_items() if i.title.startswith("Mode:"))
    vad = next(s for s in row.submenu if "silence" in s.title)
    assert "⚠" in vad.title


def test_choosing_a_mode_hands_the_name_to_the_daemon() -> None:
    chosen: list[str] = []
    tray = TrayApp(on_mode=chosen.append)
    tray.set_mode_options(("push_to_talk", "toggle"), "push_to_talk")
    row = next(i for i in tray.menu_items() if i.title.startswith("Mode:"))
    toggle_row = next(s for s in row.submenu if "press to stop" in s.title)
    tray.activate(toggle_row.action)
    assert chosen == ["toggle"]


def test_a_mode_action_does_not_fire_the_hotkey_handler() -> None:
    """Both prefixes are checked in one `activate`. A `mode:` verb reaching
    `on_hotkey` would rebind the key to a mode name."""
    hotkeys: list[str] = []
    modes: list[str] = []
    tray = TrayApp(on_hotkey=hotkeys.append, on_mode=modes.append)
    tray.set_hotkey_options(("right_option",), "right_option")
    tray.set_mode_options(("push_to_talk", "toggle"), "push_to_talk")

    tray.activate("mode:toggle")
    assert modes == ["toggle"] and hotkeys == []

    tray.activate("hotkey:right_option")
    assert hotkeys == ["right_option"] and modes == ["toggle"]


def test_no_mode_row_before_the_options_are_supplied() -> None:
    assert not any(i.title.startswith("Mode:") for i in TrayApp().menu_items())
