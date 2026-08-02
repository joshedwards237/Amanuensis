"""Getting text to the cursor on macOS, and the costs of doing it that way.

PRD §7.3 chooses clipboard paste over synthesized keystrokes on latency, and
then spends most of its length on what that choice costs: the user's clipboard
is clobbered, restoring it races with clipboard managers, and — the part §7.3
was amended to say plainly — a clipboard manager capturing the transcript is
that manager working correctly, not a timing artefact. The transcript leaves
the process. On managers with cross-device sync it leaves the machine.

So the tests here are mostly about the failure paths, because the happy path
is three calls and the failure paths are where the product's promises live.

**A failed injection must not also cost the user their clipboard.** If the
permission is missing, nothing is written to the pasteboard at all. Writing
first and discovering afterwards would take a user who cannot dictate and also
delete whatever they had copied.

**The permission check does not type anything.** §6.3 says non-destructive in
the ABC's docstring, and a check that verifies by injecting a test character
is not a check — it is an injection with extra steps, into whatever window
happens to be focused.

**The permission belongs to the hosting binary, not to `manu`.** macOS grants
Accessibility per application, and in Phase 2a `manu` runs inside a terminal.
The check therefore reports the terminal's grant, and remediation that says
"grant Amanuensis access" sends the user looking for an entry that is not
there. This one was found by running the check rather than by reading about
it: both preflight calls returned True on a machine that had never heard of
this project.
"""

from __future__ import annotations

from typing import Any

import pytest

from amanuensis.config import InjectionConfig
from amanuensis.injection import macos as macos_injection
from amanuensis.injection.macos import MacOSInjector, detect_clipboard_manager

V_KEYCODE = 9


class _FakePasteboard:
    def __init__(self, contents: str | None = None) -> None:
        self.contents = contents
        self.writes: list[str] = []
        self.clear_count = 0

    def stringForType_(self, _type: object) -> str | None:
        return self.contents

    def clearContents(self) -> int:
        self.clear_count += 1
        return self.clear_count

    def setString_forType_(self, value: str, _type: object) -> bool:
        self.contents = value
        self.writes.append(value)
        return True


class _FakeApp:
    def __init__(self, bundle_id: str | None, name: str) -> None:
        self._bundle_id = bundle_id
        self._name = name

    def bundleIdentifier(self) -> str | None:
        return self._bundle_id

    def localizedName(self) -> str:
        return self._name


class _FakeAppKit:
    NSPasteboardTypeString = "public.utf8-plain-text"

    def __init__(
        self, pasteboard: _FakePasteboard, running: list[_FakeApp] | None = None
    ) -> None:
        self._pasteboard = pasteboard
        self._running = running or []
        outer = self

        class NSPasteboard:
            @staticmethod
            def generalPasteboard() -> _FakePasteboard:
                return outer._pasteboard

        class NSWorkspace:
            @staticmethod
            def sharedWorkspace() -> Any:
                return outer

        self.NSPasteboard = NSPasteboard
        self.NSWorkspace = NSWorkspace

    def runningApplications(self) -> list[_FakeApp]:
        return self._running


class _FakeQuartz:
    kCGHIDEventTap = 0
    kCGEventFlagMaskCommand = 1 << 20
    kCGSessionEventTap = 1

    def __init__(self, *, may_post: bool = True) -> None:
        self._may_post = may_post
        self.posted: list[tuple[int, bool, int | None, str | None]] = []
        self.preflight_calls = 0

    def CGPreflightPostEventAccess(self) -> bool:
        self.preflight_calls += 1
        return self._may_post

    def CGEventSourceCreate(self, _state: object) -> object:
        return object()

    def CGEventCreateKeyboardEvent(
        self, _source: object, keycode: int, keydown: bool
    ) -> dict[str, Any]:
        return {"keycode": keycode, "down": keydown, "flags": None, "unicode": None}

    def CGEventSetFlags(self, event: dict[str, Any], flags: int) -> None:
        event["flags"] = flags

    def CGEventKeyboardSetUnicodeString(
        self, event: dict[str, Any], _length: int, text: str
    ) -> None:
        event["unicode"] = text

    def CGEventPost(self, _tap: object, event: dict[str, Any]) -> None:
        self.posted.append(
            (event["keycode"], event["down"], event["flags"], event["unicode"])
        )


@pytest.fixture
def frameworks(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Swap both pyobjc bridges for fakes and record the sleeps."""

    def install(
        *,
        clipboard: str | None = "previous clipboard",
        may_post: bool = True,
        running: list[_FakeApp] | None = None,
    ) -> tuple[_FakePasteboard, _FakeQuartz, list[float]]:
        pasteboard = _FakePasteboard(clipboard)
        appkit = _FakeAppKit(pasteboard, running)
        quartz = _FakeQuartz(may_post=may_post)
        slept: list[float] = []
        monkeypatch.setattr(macos_injection, "_appkit", lambda: appkit)
        monkeypatch.setattr(macos_injection, "_quartz", lambda: quartz)
        monkeypatch.setattr(macos_injection, "_sleep", slept.append)
        return pasteboard, quartz, slept

    return install


# ---------------------------------------------------------------------------
# The clipboard strategy
# ---------------------------------------------------------------------------


def test_the_text_reaches_the_pasteboard_and_command_v_is_posted(
    frameworks: Any,
) -> None:
    pasteboard, quartz, _ = frameworks()

    result = MacOSInjector(InjectionConfig()).inject("the small conference room")

    assert result.succeeded is True
    assert result.strategy == "clipboard"
    assert "the small conference room" in pasteboard.writes
    keydowns = [event for event in quartz.posted if event[0] == V_KEYCODE]
    assert len(keydowns) == 2, "one key down and one key up"
    assert keydowns[0][2] == _FakeQuartz.kCGEventFlagMaskCommand


def test_the_previous_clipboard_comes_back(frameworks: Any) -> None:
    """§7.3 mitigates the clobbering by saving and restoring. It does not claim
    the mitigation is complete — see the manager test below."""
    pasteboard, _, _ = frameworks(clipboard="something the user copied")

    MacOSInjector(InjectionConfig()).inject("dictated words")

    assert pasteboard.contents == "something the user copied"


def test_the_restore_waits_for_the_configured_delay(frameworks: Any) -> None:
    """The paste is asynchronous — restoring immediately would race the target
    application reading the pasteboard, which is a different and worse race
    than the clipboard-manager one."""
    _, _, slept = frameworks()

    MacOSInjector(InjectionConfig(restore_delay_ms=150)).inject("words")

    assert slept == [pytest.approx(0.150)]


def test_restore_can_be_turned_off(frameworks: Any) -> None:
    pasteboard, _, _ = frameworks(clipboard="something the user copied")

    MacOSInjector(InjectionConfig(restore_clipboard=False)).inject("dictated words")

    assert pasteboard.contents == "dictated words"


def test_a_clipboard_holding_something_that_is_not_text_is_not_invented(
    frameworks: Any,
) -> None:
    """An image on the pasteboard reads back as None through the string type.
    Restoring `None` as a string would replace the user's image with an empty
    clipboard and report success."""
    pasteboard, _, _ = frameworks(clipboard=None)

    result = MacOSInjector(InjectionConfig()).inject("words")

    assert result.succeeded is True
    assert pasteboard.writes == ["words"]


def test_nothing_is_written_for_an_empty_transcript(frameworks: Any) -> None:
    """Clobbering the clipboard to paste nothing is the worst possible trade."""
    pasteboard, quartz, _ = frameworks()

    result = MacOSInjector(InjectionConfig()).inject("   ")

    assert result.succeeded is True
    assert pasteboard.writes == []
    assert quartz.posted == []


# ---------------------------------------------------------------------------
# The keystroke strategy
# ---------------------------------------------------------------------------


def test_the_keystroke_strategy_never_touches_the_clipboard(frameworks: Any) -> None:
    """`strategy = "keystroke"` exists for users who cannot accept the
    clipboard exposure (§7.3). Touching the pasteboard on that path would
    defeat the only reason the option is offered."""
    pasteboard, quartz, _ = frameworks()

    result = MacOSInjector(InjectionConfig(strategy="keystroke")).inject("hi")

    assert result.strategy == "keystroke"
    assert pasteboard.writes == []
    assert [event[3] for event in quartz.posted if event[1]] == ["h", "i"]


def test_keystrokes_carry_unicode_rather_than_key_codes(frameworks: Any) -> None:
    """Mapping characters to virtual key codes is layout-dependent and would
    type mojibake on a non-US keyboard. `CGEventKeyboardSetUnicodeString`
    sidesteps the layout entirely."""
    _, quartz, _ = frameworks()

    MacOSInjector(InjectionConfig(strategy="keystroke")).inject("é")

    assert [event[3] for event in quartz.posted if event[1]] == ["é"]


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


def test_the_check_reports_accessibility_and_not_input_monitoring(
    frameworks: Any,
) -> None:
    """Two distinct permissions, which is why §9 split Phase 2 in half. The
    injector owns Accessibility; Input Monitoring is the hotkey listener's and
    Phase 2b's. Reporting both here would fail Phase 2a for a permission
    nothing in Phase 2a uses."""
    frameworks(may_post=False)

    status = MacOSInjector(InjectionConfig()).check_permissions()

    assert status.granted is False
    assert status.missing == ("Accessibility",)


def test_the_check_types_nothing(frameworks: Any) -> None:
    """Non-destructive, per the ABC. A check that verifies by injecting would
    put a stray character into whatever window has focus."""
    pasteboard, quartz, _ = frameworks()

    MacOSInjector(InjectionConfig()).check_permissions()

    assert quartz.posted == []
    assert pasteboard.writes == []


def test_remediation_names_the_application_the_grant_attaches_to(
    frameworks: Any,
) -> None:
    """macOS grants Accessibility per application. Running `manu` from a
    terminal means the terminal holds the grant, and telling the user to look
    for "Amanuensis" in the list sends them after an entry that is not there
    until Phase 4 packages an .app."""
    frameworks(may_post=False)

    status = MacOSInjector(InjectionConfig()).check_permissions()

    assert "Accessibility" in status.remediation
    assert "x-apple.systempreferences" in status.remediation


def test_a_missing_permission_does_not_cost_the_user_their_clipboard(
    frameworks: Any,
) -> None:
    """The check runs before the pasteboard is touched. Discovering the
    permission afterwards would leave a user who cannot dictate *and* has lost
    whatever they had copied."""
    pasteboard, quartz, _ = frameworks(clipboard="precious", may_post=False)

    result = MacOSInjector(InjectionConfig()).inject("words")

    assert result.succeeded is False
    assert result.error is not None
    assert pasteboard.writes == []
    assert pasteboard.contents == "precious"
    assert quartz.posted == []


def test_the_keystroke_strategy_checks_the_same_permission(frameworks: Any) -> None:
    """Both strategies post CGEvents; only the payload differs."""
    _, quartz, _ = frameworks(may_post=False)

    result = MacOSInjector(InjectionConfig(strategy="keystroke")).inject("words")

    assert result.succeeded is False
    assert quartz.posted == []


# ---------------------------------------------------------------------------
# Clipboard-manager detection (§7.3, objection O12)
# ---------------------------------------------------------------------------


def test_a_known_manager_is_detected_and_named(frameworks: Any) -> None:
    """§5.4 requires the exposure be visible, and a warning that cannot say
    *which* application is capturing is not something a user can act on."""
    frameworks(running=[_FakeApp("org.p0deje.Maccy", "Maccy")])

    exposure = detect_clipboard_manager()

    assert exposure.detected is True
    assert exposure.manager == "Maccy"


def test_no_known_manager_is_reported_as_ignorance_not_absence(
    frameworks: Any,
) -> None:
    """§7.3: the detection list is incomplete by nature and absence of a
    warning means "no known manager detected", never "no manager present".
    The field name has to carry that or the README is the only place it is
    said."""
    frameworks(running=[_FakeApp("com.apple.finder", "Finder")])

    exposure = detect_clipboard_manager()

    assert exposure.detected is False
    assert exposure.manager is None


def test_an_application_with_no_bundle_identifier_is_skipped(
    frameworks: Any,
) -> None:
    """Helper processes report None, and `None in _MANAGERS` would be a
    TypeError on a code path that runs at every daemon start."""
    frameworks(
        running=[_FakeApp(None, "something"), _FakeApp("com.raycast.macos", "Raycast")]
    )

    exposure = detect_clipboard_manager()

    assert exposure.detected is True
    assert exposure.manager == "Raycast"
