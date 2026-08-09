#!/usr/bin/env python3
"""Phase 2a gate: does injection actually land, in each named application?

PRD §9's Phase 2a gate says "Dictate into TextEdit, VS Code, Chrome, and a
terminal. Report where it fails", and rejects if two or more fail or if a
*native* text field fails. Done by hand that is four ten-second dictations,
judged by eye, unreproducible, and impossible to re-run after a change. This
script does the same thing as a measurement.

**It reads the text back through the Accessibility API.** For each target it
resolves the application, finds its focused UI element, records the value
before injection, injects a unique marker, and reads the value again. The
target either contains the marker or it does not. Nothing is judged by eye.

**The read-back is an instrument, so it gets a control.** A run that reads
back an empty string can mean two things — injection failed, or the reader is
broken — and those are opposite conclusions. So the pre-injection read has to
*succeed* before the result counts: an `AXError` before injecting reports
UNVERIFIED, never FAIL. This project has shipped two gates that passed by
measuring nothing (AGENTS.md GOTCHAS); a gate that *fails* by measuring
nothing is the same bug wearing a different hat.

The system-wide focused-element query (`AXUIElementCreateSystemWide` +
`kAXFocusedUIElementAttribute`) returns `kAXErrorCannotComplete` here even
with Accessibility granted. Scoping the query to the target application's own
PID works. That is why this resolves a bundle identifier first rather than
just asking what has focus.

What it does not test: ASR. The engine is not loaded and the microphone is not
opened. This exercises `MacOSInjector` and the §8 ordering around it, which is
what Phase 2a builds — the full path from microphone to cursor is Phase 2b's
gate, where it is measured end to end for G1.

Usage:

    python scripts/gate_2a_inject.py --all
    python scripts/gate_2a_inject.py --app textedit --strategy keystroke
    python scripts/gate_2a_inject.py --app chrome --keep-open
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import AppKit  # noqa: E402
import ApplicationServices as AS  # noqa: E402

from amanuensis.config import InjectionConfig  # noqa: E402
from amanuensis.injection.macos import MacOSInjector  # noqa: E402

#: How long to wait for an application to come forward and settle before
#: asking it anything. Generous: a cold VS Code launch is not fast, and a
#: read taken too early reports UNVERIFIED for a reason that is not the
#: product's.
_ACTIVATE_SETTLE_S = 2.5
#: How long to wait after posting the paste before reading the value back.
#: The paste is asynchronous — the target reads the pasteboard on its own run
#: loop — so reading immediately would measure the race, not the injection.
_INJECT_SETTLE_S = 1.0
#: How long to wait for a cold application launch to register. Electron
#: editors are not fast from cold, and an impatient harness reports the wait
#: as a result.
_LAUNCH_TIMEOUT_S = 25.0
#: How long to give the Accessibility tree to appear after asking for it.
_READER_TIMEOUT_S = 8.0
#: Extra settle per synthesized character. Keystroke injection is not atomic
#: the way a paste is; the target drains the events at its own pace.
_PER_CHARACTER_SETTLE_S = 0.05


@dataclass(frozen=True)
class Target:
    key: str
    name: str
    bundle_id: str
    #: Keystroke that puts a text field in focus, as a System Events phrase.
    #: Sent through osascript rather than through our own injector, because a
    #: verification harness that shares a mechanism with the thing under test
    #: cannot distinguish "injection works" from "the harness works".
    focus_script: str | None
    #: True when the focused field is a native AppKit text view. §9 rejects on
    #: a native-field failure specifically — a hostile Electron target is a
    #: known hazard, a broken injector is not.
    native: bool
    notes: str = ""


_TARGETS: tuple[Target, ...] = (
    Target(
        key="textedit",
        name="TextEdit",
        bundle_id="com.apple.TextEdit",
        focus_script='tell application "TextEdit" to make new document',
        native=True,
        notes="native NSTextView — the field §9 rejects on",
    ),
    Target(
        key="terminal",
        name="Terminal",
        bundle_id="com.apple.Terminal",
        # A fresh window, so the marker lands on an empty prompt rather than
        # halfway through whatever was being typed.
        focus_script='tell application "Terminal" to do script ""',
        native=True,
        notes="native, but the focused element is a terminal view",
    ),
    Target(
        key="vscode",
        name="Visual Studio Code",
        bundle_id="com.microsoft.VSCode",
        focus_script=(
            'tell application "System Events" to keystroke "n" using command down'
        ),
        native=False,
        notes="Electron — a failure here is a §10 known hazard, not a reject",
    ),
    Target(
        key="chrome",
        name="Google Chrome",
        bundle_id="com.google.Chrome",
        # The omnibox rather than page content: no navigation, no page to
        # host, and it is still a Chrome text field. Page-content injection is
        # covered by the --page flag below.
        focus_script=(
            'tell application "System Events" to keystroke "l" using command down'
        ),
        native=False,
        notes="Electron/Blink — omnibox unless --page is given",
    ),
)

_BY_KEY = {target.key: target for target in _TARGETS}

_PAGE_HTML = """<!doctype html>
<meta charset="utf-8">
<title>Amanuensis Phase 2a gate</title>
<body style="font: 16px system-ui; padding: 2rem">
<p>Phase 2a injection target. The textarea below has focus.</p>
<textarea autofocus rows="6" cols="60" style="font: 16px monospace"></textarea>
</body>
"""


def _pid_for(bundle_id: str) -> int | None:
    for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
        if app.bundleIdentifier() == bundle_id:
            pid: int = app.processIdentifier()
            return pid
    return None


def _await_pid(bundle_id: str, timeout_s: float = _LAUNCH_TIMEOUT_S) -> int | None:
    """Poll until the application registers, or give up.

    A fixed sleep was the first version and it reported a cold VS Code launch
    as "application is not running" — an UNVERIFIED caused entirely by the
    harness being impatient. The distinction matters: this gate's whole job is
    to tell a real injection failure apart from a measurement that did not
    happen, and a timeout dressed as a result is the second thing pretending
    to be the first.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        pid = _pid_for(bundle_id)
        if pid is not None:
            return pid
        time.sleep(0.25)
    return None


def _osascript(script: str) -> None:
    subprocess.run(
        ["/usr/bin/osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _focused_value(pid: int) -> tuple[int, str | None]:
    """Read the focused element's value. Returns (AXError, value).

    A non-zero error is an instrument failure, not a product failure, and the
    caller must treat it that way.

    `AXManualAccessibility` is set first because Electron applications ship
    their accessibility tree switched off and build it on request. Without it
    VS Code answers `kAXErrorNoValue` (-25212) to every query and reads as
    unmeasurable — which is how this harness first reported it, until a
    throwaway probe set the flag by hand and the next run "passed" for a
    reason that was not in the script. A gate whose result depends on
    something a previous command did is not a gate.
    """
    app = AS.AXUIElementCreateApplication(pid)
    AS.AXUIElementSetAttributeValue(app, "AXManualAccessibility", True)
    err, focused = AS.AXUIElementCopyAttributeValue(
        app, AS.kAXFocusedUIElementAttribute, None
    )
    if err != 0 or focused is None:
        return err, None
    err, value = AS.AXUIElementCopyAttributeValue(focused, AS.kAXValueAttribute, None)
    if err != 0:
        return err, None
    return 0, value if isinstance(value, str) else ""


def _await_readable(
    pid: int, timeout_s: float = _READER_TIMEOUT_S
) -> tuple[int, str | None]:
    """Poll the reader until it can see the application, or give up.

    Setting `AXManualAccessibility` does not make an Electron accessibility
    tree appear synchronously — it asks for one to be built. A cold VS Code
    answers `kAXErrorNoValue` for a second or two afterwards and then starts
    answering properly. The first version of this harness read once, got the
    -25212, and reported UNVERIFIED; a later run passed only because a
    throwaway probe had set the flag minutes earlier. Both readings were about
    the harness, not the product.
    """
    deadline = time.monotonic() + timeout_s
    err, value = _focused_value(pid)
    while (err != 0 or value is None) and time.monotonic() < deadline:
        time.sleep(0.5)
        err, value = _focused_value(pid)
    return err, value


@dataclass(frozen=True)
class Outcome:
    target: Target
    verdict: str  # PASS | FAIL | UNVERIFIED
    detail: str


def _run_one(target: Target, strategy: str, page: bool, keep_open: bool) -> Outcome:
    marker = f"amanuensis-2a-{uuid.uuid4().hex[:8]}"

    if target.key == "chrome" and page:
        page_file = Path(__file__).resolve().parent.parent / ".gate-2a-target.html"
        page_file.write_text(_PAGE_HTML, encoding="utf-8")
        subprocess.run(
            ["/usr/bin/open", "-a", target.name, str(page_file)], check=False
        )
    else:
        subprocess.run(["/usr/bin/open", "-a", target.name], check=False)

    pid = _await_pid(target.bundle_id)
    if pid is None:
        return Outcome(
            target,
            "UNVERIFIED",
            f"did not register within {_LAUNCH_TIMEOUT_S:.0f}s of `open -a`",
        )
    time.sleep(_ACTIVATE_SETTLE_S)

    if target.focus_script is not None and not (target.key == "chrome" and page):
        _osascript(target.focus_script)
        time.sleep(_ACTIVATE_SETTLE_S)

    # The control. A read that fails here means the instrument is down, and
    # any verdict drawn from the read afterwards would be unearned — so the
    # run degrades to a human check rather than inventing a verdict. Some
    # Electron applications never expose `AXFocusedUIElement` at all
    # (kAXErrorNoValue, -25212), even after `AXManualAccessibility` is set.
    err, before = _await_readable(pid)
    readable = err == 0 and before is not None

    injector = MacOSInjector(InjectionConfig(strategy=strategy))
    result = injector.inject(marker)
    if not result.succeeded:
        return Outcome(target, "FAIL", f"injector reported: {result.error}")

    if not readable:
        time.sleep(_INJECT_SETTLE_S)
        return Outcome(
            target,
            "MANUAL",
            f"the reader cannot see this application (AXError {err}), so the "
            f"injection was performed and must be confirmed by eye: look for "
            f"{marker!r} in {target.name}",
        )

    # Keystroke injection posts two CGEvents per character and the target
    # drains them on its own run loop, so the settle has to scale with the
    # text. A fixed wait read an empty field for a 22-character marker and a
    # populated one for 14 — which is a harness artefact reported as a
    # native-field FAIL, the single most consequential verdict this gate can
    # return.
    settle = _INJECT_SETTLE_S
    if strategy == "keystroke":
        settle += _PER_CHARACTER_SETTLE_S * len(marker)
    time.sleep(settle)
    err, after = _focused_value(pid)
    if err != 0 or after is None:
        return Outcome(
            target,
            "UNVERIFIED",
            f"could not read the focused element after injecting (AXError {err})",
        )

    if marker in after:
        return Outcome(
            target, "PASS", f"marker found in the focused field ({strategy})"
        )

    # "Landed but was rewritten" and "did not land" are different findings with
    # different remedies, and a bare `marker not in after` collapses them. The
    # keystroke strategy hits the first: macOS text substitution rewrote the
    # injected text inside the target application, so a case-insensitive hit
    # means injection worked and exactness did not.
    if marker.lower() in after.lower():
        return Outcome(
            target,
            "ALTERED",
            f"the text arrived and was rewritten by the target application "
            f"({strategy}). Injection works; the transcript does not survive "
            f"verbatim. See §7.3 on text substitution.",
        )

    return Outcome(
        target,
        "FAIL",
        f"marker absent. before={before[-40:]!r} after={after[-40:]!r}",
    )


def _report(outcomes: list[Outcome]) -> int:
    print()
    print("Phase 2a injection gate")
    print("=" * 72)
    for outcome in outcomes:
        kind = "native" if outcome.target.native else "non-native"
        print(f"{outcome.verdict:<11} {outcome.target.name:<22} ({kind})")
        print(f"            {outcome.detail}")
        if outcome.target.notes:
            print(f"            note: {outcome.target.notes}")
    print("=" * 72)

    failures = [o for o in outcomes if o.verdict == "FAIL"]
    altered = [o for o in outcomes if o.verdict == "ALTERED"]
    native_failures = [o for o in failures if o.target.native]
    unverified = [o for o in outcomes if o.verdict == "UNVERIFIED"]
    manual = [o for o in outcomes if o.verdict == "MANUAL"]

    print(
        f"{len(failures)} failure(s), {len(manual)} awaiting a human, "
        f"{len(unverified)} unverified."
    )
    if unverified or manual:
        print(
            "Neither MANUAL nor UNVERIFIED is a pass. The reject conditions below\n"
            "are evaluated over what was actually measured, and a target the reader\n"
            "could not see has not been measured — a human has to close it."
        )

    # §9's reject conditions, evaluated rather than described.
    rejects = []
    if len(failures) >= 2:
        rejects.append(f"injection failed in {len(failures)} of the four applications")
    if native_failures:
        names = ", ".join(o.target.name for o in native_failures)
        rejects.append(f"injection failed in a native text field ({names})")

    if altered:
        print()
        print(
            "ALTERED is not a §9 reject — the text reached the cursor, which is what\n"
            "G4 and the gate's reject conditions are about. It is a finding, and a\n"
            "serious one: the transcript does not arrive verbatim."
        )

    if rejects:
        print()
        print("REJECT:")
        for reason in rejects:
            print(f"  - {reason}")
        return 1

    if failures:
        print()
        print(
            "One non-native failure is a §10 known hazard, not a reject. Enumerate\n"
            "it in the gate record and carry a per-app strategy override."
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--app", choices=sorted(_BY_KEY), help="run one target")
    parser.add_argument("--all", action="store_true", help="run all four targets")
    parser.add_argument(
        "--strategy",
        choices=("clipboard", "keystroke"),
        default="clipboard",
        help="which injection strategy to exercise (default: clipboard)",
    )
    parser.add_argument(
        "--page",
        action="store_true",
        help="for Chrome, inject into a page textarea rather than the omnibox",
    )
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="leave the documents this opened on screen",
    )
    args = parser.parse_args()

    if not args.all and args.app is None:
        parser.error("give --app NAME or --all")

    targets = list(_TARGETS) if args.all else [_BY_KEY[args.app]]

    print(f"strategy: {args.strategy}")
    print("Do not touch the keyboard or mouse while this runs — it depends on")
    print("which application has focus.")
    print()

    outcomes = []
    for target in targets:
        print(f"-> {target.name} ...", flush=True)
        outcomes.append(_run_one(target, args.strategy, args.page, args.keep_open))

    return _report(outcomes)


if __name__ == "__main__":
    sys.exit(main())
