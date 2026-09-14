#!/usr/bin/env python3
"""Ask every API that could register this process, and report which one works.

Three fixes for the same defect have now shipped on hypotheses that could not
be tested where they were written. Both development machines run macOS 27.0
with both grants already held, so the one state that matters — a fresh client
on 26.6 — is unreachable here by construction. This script exists to stop
guessing: it runs on the machine that actually fails, calls each candidate in
turn, and reports what each one returned.

It is a maintainer's diagnostic and nothing under `src/` imports it.

**It deliberately raises permission dialogs.** That is the behaviour under
test. Dismissing them is fine — the question is whether they appear at all, and
whether a row shows up in Settings afterwards either way.

Usage, from the checkout, with the virtualenv active:

    python scripts/diagnose_permissions.py
"""

from __future__ import annotations

import ctypes
import os
import platform
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _line(label: str, value: object) -> None:
    print(f"{label:.<44} {value}")


def _attempt(label: str, call: Callable[[], Any]) -> None:
    """Run one candidate and report what it did, never raising."""
    try:
        result = call()
    except Exception as exc:  # a diagnostic reports failures, it never raises
        _line(label, f"RAISED {type(exc).__name__}: {exc}")
        return
    _line(label, f"returned {result!r}")


# IOKit's HID access API, reached through ctypes rather than pyobjc.
#
# `pyobjc-framework-IOKit` **does not exist on PyPI** and no installed pyobjc
# package exports these symbols, so the choice was ctypes or nothing. ctypes
# costs no dependency at all, which is strictly better than the fifth pyobjc
# framework this was expected to need — and costs a hand-declared signature
# instead, which crashes rather than raises when it is wrong. Hence the explicit
# argtypes and restype below, and the guard around the load.
#
# Values are from IOKit's headers. `IOHIDCheckAccess` is the interesting one:
# unlike `CGPreflightListenEventAccess`, which answers a bool, it separates
# **denied** from **unknown** — and "unknown" means *this client has never been
# asked*, which is exactly the state that produced an empty Settings pane and
# four findings in this lane.
_IOKIT_PATH = "/System/Library/Frameworks/IOKit.framework/IOKit"

_REQUEST_TYPES = {"PostEvent (Accessibility)": 0, "ListenEvent (Input Monitoring)": 1}
_ACCESS_NAMES = {0: "granted", 1: "denied", 2: "unknown — never asked"}


def _probe_iokit() -> None:
    """Read IOKit's view of both grants, then ask for Input Monitoring.

    Only `ListenEvent` is *requested*. Accessibility already has a call that
    works (`AXIsProcessTrustedWithOptions`), and a second dialog for a grant
    that is already handled would make this harder to read, not easier.
    """
    try:
        iokit = ctypes.cdll.LoadLibrary(_IOKIT_PATH)
    except OSError as exc:
        _line("IOKit", f"could not load {_IOKIT_PATH}: {exc}")
        return

    try:
        check = iokit.IOHIDCheckAccess
        request = iokit.IOHIDRequestAccess
    except AttributeError as exc:
        _line("IOKit", f"symbol missing: {exc}")
        return

    check.argtypes = [ctypes.c_uint32]
    check.restype = ctypes.c_uint32
    request.argtypes = [ctypes.c_uint32]
    request.restype = ctypes.c_bool

    def _describe(value: int) -> str:
        code = check(value)
        return _ACCESS_NAMES.get(code, f"unrecognised code {code}")

    for label, value in _REQUEST_TYPES.items():
        _attempt(f"IOHIDCheckAccess({label})", lambda v=value: _describe(v))

    _attempt(
        "IOHIDRequestAccess(ListenEvent)",
        lambda: request(_REQUEST_TYPES["ListenEvent (Input Monitoring)"]),
    )


def main() -> int:
    print("=" * 72)
    print("Amanuensis permission diagnostic")
    print("=" * 72)
    print()

    print("-- environment " + "-" * 57)
    _line("macOS", platform.mac_ver()[0] or "not macOS")
    _line("python", sys.version.split()[0])
    _line("python executable", sys.executable)

    try:
        import amanuensis
        import amanuensis.injection.macos as inj

        _line("amanuensis package", Path(amanuensis.__file__).parent)
        _line("injection module", inj.__file__)
        source = Path(inj.__file__).read_text(encoding="utf-8")
        _line("has AXIsProcessTrustedWithOptions", "AXIsProcess" in source)
        _line("has CGRequestPostEventAccess", "CGRequestPostEventAccess" in source)
    except Exception as exc:
        _line("amanuensis import", f"FAILED: {exc}")
        print("\nThe package is not importable. Nothing below will mean anything.")
        return 1

    print()
    print("-- which terminal holds the grant " + "-" * 38)
    # macOS attaches both grants to the application that launched this process,
    # not to python and not to `manu`. Naming it removes the commonest dead end.
    _line("TERM_PROGRAM", os.environ.get("TERM_PROGRAM", "(unset)"))
    try:
        ppid = os.getppid()
        name = subprocess.run(
            ["ps", "-o", "comm=", "-p", str(ppid)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
        _line("parent process", name or "(unknown)")
    except (OSError, subprocess.SubprocessError) as exc:
        _line("parent process", f"could not determine: {exc}")

    print()
    print("-- current grant state (these never prompt) " + "-" * 28)
    try:
        import Quartz

        _attempt("CGPreflightPostEventAccess (Accessibility)",
                 Quartz.CGPreflightPostEventAccess)
        _attempt("CGPreflightListenEventAccess (Input Monitoring)",
                 Quartz.CGPreflightListenEventAccess)
    except ImportError as exc:
        _line("Quartz", f"NOT IMPORTABLE: {exc}")

    print()
    print("-- candidates that should register this process " + "-" * 24)
    print("   Dialogs may appear now. Note which ones do.")
    print()

    try:
        import HIServices

        _attempt(
            "AXIsProcessTrustedWithOptions(prompt=True)",
            lambda: HIServices.AXIsProcessTrustedWithOptions(
                {HIServices.kAXTrustedCheckOptionPrompt: True}
            ),
        )
    except ImportError as exc:
        _line("HIServices", f"NOT IMPORTABLE: {exc}")

    try:
        import Quartz

        _attempt("CGRequestPostEventAccess (Accessibility)",
                 Quartz.CGRequestPostEventAccess)
        _attempt("CGRequestListenEventAccess (Input Monitoring)",
                 Quartz.CGRequestListenEventAccess)
    except ImportError as exc:
        _line("Quartz", f"NOT IMPORTABLE: {exc}")

    _probe_iokit()

    print()
    print("=" * 72)
    print("Now open BOTH panes and report what is in each list:")
    print()
    print('  open "x-apple.systempreferences:com.apple.preference.security'
          '?Privacy_Accessibility"')
    print('  open "x-apple.systempreferences:com.apple.preference.security'
          '?Privacy_ListenEvent"')
    print()
    print("For each pane, three things:")
    print("  1. Is your terminal listed at all (on or off)?")
    print("  2. Are ANY other applications listed?")
    print("  3. Did a dialog appear while this script ran, and for which line?")
    print()
    print("The line that decides the next change is")
    print("`IOHIDRequestAccess(ListenEvent)` — whether IT raised a dialog, as")
    print("distinct from the Accessibility one. Input Monitoring is the grant")
    print("that still has no working prompt.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
