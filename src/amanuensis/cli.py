"""The `manu` command surface.

Four verbs, fixed by §6.1's process model: `daemon`, `toggle`, `status`,
`history`. All four exist from Phase 0 and none of them work yet — each fails
with the phase that builds it. Growing the verb set one phase at a time was
the obvious alternative and was rejected: it lets implementation order decide
the shape of the public interface, and the interface is the part users write
scripts against.

`manu toggle` deserves a note. It is IPC to a running daemon, for people
driving Amanuensis from an external hotkey manager. The transport is a unix
socket on macOS and would be a named pipe on Windows — which is exactly why
the transport does not appear in the CLI contract (portability floor item 3,
PRD §7.3). `toggle` is the interface; the socket is an implementation detail
that must not leak into a help string.

Configuration is loaded here, once, and would be passed down explicitly from
here — there is no ambient accessor to reach for further in (§6.3). A config
error is reported as a sentence on stderr, not a traceback: the user is
looking at a TOML file they just edited, and a stack trace tells them nothing
about which line is wrong.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from amanuensis import __version__
from amanuensis.config import ConfigError, load_config

__all__ = ["build_parser", "main"]

_EXIT_USAGE = 2
_EXIT_ERROR = 1

#: Verb -> the phase that makes it do something. Kept in one place so that
#: `manu daemon` and the tests cannot disagree about what is built.
_VERB_PHASES = {
    "daemon": "Phase 2b",
    "toggle": "Phase 2b",
    "status": "Phase 2b",
    "history": "Phase 3",
}


def build_parser() -> argparse.ArgumentParser:
    """The full `manu` parser. Separate from `main` so tests can inspect it."""
    parser = argparse.ArgumentParser(
        prog="manu",
        description=(
            "Fully local dictation. Press a hotkey, speak, release — your "
            "words appear at the cursor. No account, no network at runtime."
        ),
    )
    parser.add_argument("--version", action="version", version=f"manu {__version__}")
    parser.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        help="path to config.toml (default: the platform config directory)",
    )

    subparsers = parser.add_subparsers(dest="verb", metavar="COMMAND")
    subparsers.add_parser(
        "daemon", help="run the background process that holds the model resident"
    )
    subparsers.add_parser("toggle", help="start or stop dictation in a running daemon")
    subparsers.add_parser("status", help="report daemon, model, and permission state")
    subparsers.add_parser("history", help="list or purge stored transcripts")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the `manu` console script.

    Returns an exit code rather than calling `sys.exit`, so that tests can
    assert on it without catching `SystemExit`. `--help` and `--version` still
    exit through argparse, which is the behaviour users expect.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verb is None:
        parser.print_usage(sys.stderr)
        print("manu: a command is required. Try `manu --help`.", file=sys.stderr)
        return _EXIT_USAGE

    try:
        load_config(args.config)
    except ConfigError as exc:
        print(f"manu: {exc}", file=sys.stderr)
        return _EXIT_ERROR

    print(
        f"manu {args.verb}: not implemented yet — it is built in "
        f"{_VERB_PHASES[args.verb]}. Phase 0 is scaffolding: contracts and "
        "toolchain only.",
        file=sys.stderr,
    )
    return _EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
