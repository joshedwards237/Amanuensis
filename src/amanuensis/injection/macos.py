"""Text at the cursor on macOS, and the exposure that costs.

PRD §7.3 picks clipboard paste over synthesized keystrokes on latency:
typing a 300-character paragraph one synthetic key event at a time is slow and
breaks in applications with input debouncing, where a pasteboard write plus a
single ⌘V is near-instant and format-safe. Everything else in this module is
about paying for that choice honestly.

**The transcript transits the system clipboard, and that is a privacy surface**
(§7.3, objection O12). A clipboard manager capturing it is that manager
working correctly — not a race, not a timing artefact. `restore_delay_ms`
governs only whether the user's *previous* contents come back; it has no
bearing on whether the transcript was recorded in transit, and several widely
used managers sync across devices, so for those users the transcript leaves
the machine as a direct consequence of the default configuration. §1's promise
is scoped to audio and is technically preserved. No reader parses it that way.

The response is not to hide it: `detect_clipboard_manager` finds known
managers so the exposure can be shown rather than discovered. The detection
table is incomplete by nature — see `ClipboardExposure`.

**pyobjc, not `osascript`.** Shelling out needs no dependency and was rejected
twice over. A process spawn costs 30-80 ms against roughly 100 ms of measured
G1 headroom, and macOS attributes the Accessibility grant to the binary that
posts the event: routing through `osascript` would ask the user to trust
`osascript` itself, which is a wider grant than this app needs and one no
remediation message can describe honestly.

**The grant belongs to the hosting application, not to `manu`.** This was
found by running the check rather than by reading about it — both preflight
calls returned True on a machine that had never heard of this project, because
the terminal running Python already held the grant. Until Phase 4 packages an
`.app`, the entry the user must find in System Settings carries their
terminal's name. The remediation text says so; one that said "grant Amanuensis
access" would send them looking for a row that does not exist.

**Both bridges are imported lazily.** `import AppKit` loads the Objective-C
runtime and the Cocoa frameworks. `manu --help` must not pay that, and neither
should a config error — the same argument `audio/capture.py` makes about
PortAudio. `_appkit()` and `_quartz()` are also what the tests fake, which is
how any of this is testable without a focused window.

What this module does *not* do: decide when to inject, know what a transcript
is, or persist anything. §8's write happens before `inject()` is called, by
the caller, and this module returning `succeeded=False` is precisely the case
that ordering exists for.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Final

from amanuensis.injection.base import TextInjector
from amanuensis.models.results import (
    ClipboardExposure,
    InjectionResult,
    PermissionStatus,
)

if TYPE_CHECKING:  # pragma: no cover — import-time cost, not behaviour
    from amanuensis.config import InjectionConfig

__all__ = ["MacOSInjector", "detect_clipboard_manager"]

#: Virtual key code for `V` on every layout — the code is positional, so this
#: is the physical key, not the character. The character is irrelevant: ⌘V is
#: the paste *shortcut*, which macOS resolves before any layout mapping.
_V_KEYCODE: Final = 9

#: Any key code works for a unicode-payload event; the payload replaces the
#: keystroke entirely. Zero is `A`, chosen because it is unambiguous in a log.
_UNICODE_CARRIER_KEYCODE: Final = 0

#: Bundle identifiers of applications known to keep clipboard history.
#:
#: Two honest caveats, both of which belong in the README (§7.3):
#: incompleteness is structural — anyone can ship a manager tomorrow — and
#: some of these are launchers whose clipboard history is *optional*, so a
#: warning naming Raycast or Alfred may be a false positive for a user who
#: never turned it on. Both errors point the same way: they over-warn about a
#: privacy exposure rather than under-warn, which is the direction to be wrong
#: in.
_CLIPBOARD_MANAGERS: Final[frozenset[str]] = frozenset(
    {
        "com.clipy-app.Clipy",
        "com.fiplab.copyclip",
        "com.fiplab.copyclip2",
        "com.generalarcade.flycut",
        "com.raycast.macos",
        "com.runningwithcrayons.Alfred",
        "com.tapbots.Pastebot2Mac",
        "com.wiheads.paste",
        "org.p0deje.Maccy",
    }
)

_ACCESSIBILITY_PANE: Final = (
    "x-apple.systempreferences:com.apple.preference.security" "?Privacy_Accessibility"
)

_REMEDIATION: Final = f"""\
Amanuensis cannot type into other applications until macOS grants
Accessibility access. Open the pane:

    open "{_ACCESSIBILITY_PANE}"

macOS grants this per application, and it grants it to whatever launched
`manu` — so look for your terminal in the list (Terminal, iTerm, Ghostty,
VS Code), not for "Amanuensis". Toggle it on, then run the command again;
the grant is read once at launch, so an already-running process will not
notice it.

Input Monitoring is a *separate* permission and is not needed for this —
it is what the global hotkey will need, and nothing here uses it yet."""


def _appkit() -> Any:
    """Import Cocoa at the point of use, never at module import."""
    import AppKit

    return AppKit


def _quartz() -> Any:
    """Import Quartz at the point of use, never at module import."""
    import Quartz

    return Quartz


#: Bound at module level so the tests can replace it. The paste is
#: asynchronous — the target application reads the pasteboard on its own run
#: loop — so restoring immediately would race the paste itself, which is a
#: worse race than the clipboard-manager one and entirely self-inflicted.
_sleep = time.sleep


def detect_clipboard_manager() -> ClipboardExposure:
    """Look for a running application known to keep clipboard history.

    Enumerating `NSWorkspace.runningApplications` rather than shelling out to
    `pgrep`: no process spawn, and the bundle identifier is a stable key where
    a process name is not.
    """
    for app in _appkit().NSWorkspace.sharedWorkspace().runningApplications():
        bundle_id = app.bundleIdentifier()
        # Helper processes report None, and `None in frozenset` is fine but
        # `str(None)` matching something is not — skip explicitly.
        if bundle_id is None:
            continue
        if bundle_id in _CLIPBOARD_MANAGERS:
            return ClipboardExposure(detected=True, manager=app.localizedName())
    return ClipboardExposure(detected=False)


class MacOSInjector(TextInjector):
    """Puts text where the cursor is, by pasteboard or by synthetic keys.

    Takes the `[injection]` slice of the config rather than the whole thing
    (§6.3, choice-story #3) — the injector has no business reading `[history]`,
    which is the very next thing in the pipeline it must not couple to.
    """

    def __init__(self, config: InjectionConfig) -> None:
        self._config = config

    # -- the ABC -----------------------------------------------------------

    def inject(self, text: str) -> InjectionResult:
        """Put `text` at the cursor. Never raises; reports instead.

        The permission is checked *first*, before the pasteboard is touched.
        Writing and then discovering the grant is missing would leave a user
        who cannot dictate and has also lost whatever they had copied — a
        failure that costs more than the one it is reporting.
        """
        strategy = self._config.strategy

        if not text.strip():
            # Clobbering the clipboard to paste nothing is the worst available
            # trade. Nothing happened, and nothing failed.
            return InjectionResult(succeeded=True, strategy=strategy)

        status = self.check_permissions()
        if not status.granted:
            return InjectionResult(
                succeeded=False,
                strategy=strategy,
                error=f"missing macOS permission: {', '.join(status.missing)}",
            )

        if strategy == "keystroke":
            self._type(text)
        else:
            self._paste(text)
        return InjectionResult(succeeded=True, strategy=strategy)

    def check_permissions(self) -> PermissionStatus:
        """Can this process post synthetic events? Asked without posting one.

        `CGPreflightPostEventAccess` is the non-destructive half of a
        documented pair; `CGRequestPostEventAccess` is the half that prompts.
        Preflight is the right one at startup — a check that raised a system
        dialog every time the daemon started would train the user to dismiss
        it.

        Only Accessibility is reported. Input Monitoring is a distinct grant
        with a distinct failure mode and belongs to `HotkeyListener` in Phase
        2b; §9 split Phase 2 in half precisely so a failure in one is not
        diagnosed as a failure of the other.
        """
        if _quartz().CGPreflightPostEventAccess():
            return PermissionStatus(granted=True)
        return PermissionStatus(
            granted=False,
            missing=("Accessibility",),
            remediation=_REMEDIATION,
        )

    # -- strategies --------------------------------------------------------

    def _paste(self, text: str) -> None:
        appkit = _appkit()
        pasteboard = appkit.NSPasteboard.generalPasteboard()

        # Read before writing. Returns None when the clipboard holds something
        # that is not text — an image, a file promise — and that None is
        # honoured below rather than written back as an empty string, which
        # would replace the user's image with nothing and call it a restore.
        previous = pasteboard.stringForType_(appkit.NSPasteboardTypeString)

        pasteboard.clearContents()
        pasteboard.setString_forType_(text, appkit.NSPasteboardTypeString)
        self._post_command_v()

        if self._config.restore_clipboard and previous is not None:
            _sleep(self._config.restore_delay_ms / 1000.0)
            pasteboard.clearContents()
            pasteboard.setString_forType_(previous, appkit.NSPasteboardTypeString)

    def _post_command_v(self) -> None:
        quartz = _quartz()
        for keydown in (True, False):
            event = quartz.CGEventCreateKeyboardEvent(None, _V_KEYCODE, keydown)
            quartz.CGEventSetFlags(event, quartz.kCGEventFlagMaskCommand)
            quartz.CGEventPost(quartz.kCGHIDEventTap, event)

    def _type(self, text: str) -> None:
        """Synthesize the text one character at a time.

        The payload is a unicode string rather than a key code because key
        codes are positional and layout-dependent — mapping characters to them
        would type mojibake on any keyboard that is not the developer's.
        """
        quartz = _quartz()
        for character in text:
            for keydown in (True, False):
                event = quartz.CGEventCreateKeyboardEvent(
                    None, _UNICODE_CARRIER_KEYCODE, keydown
                )
                quartz.CGEventKeyboardSetUnicodeString(event, len(character), character)
                quartz.CGEventPost(quartz.kCGHIDEventTap, event)
