"""The `manu` command surface.

Phase 0 fixed four verbs — `daemon`, `toggle`, `status`, `history` — on the
grounds that §6.1's process model is the public contract and a CLI that grows
verbs one phase at a time is a CLI whose shape is decided by implementation
order. Phase 1 adds two more, and the reason the original argument does not
cover them is worth stating: **neither talks to a daemon.**

- `transcribe` is a one-shot diagnostic. PRD §9 names it as a Phase 1
  deliverable — it records from the microphone, prints the transcript and the
  per-stage timings, and exits. There is no resident process involved.
- `install` runs the setup §7.2 describes and never names an entry point for:
  download the weights once, measure this machine's ASR stage against the
  350/700 ms thresholds, and record the tier. §7.2 says "re-running the install
  check is how it changes", which presumes a command that did not exist.

Both are recorded as findings in `docs/gates/phase-1.md`; §6.1's claim was
about the daemon's surface and remains true of it.

`manu toggle` still deserves its note. It is IPC to a running daemon, for
people driving Amanuensis from an external hotkey manager. The transport is a
unix socket on macOS and would be a named pipe on Windows — which is exactly
why the transport does not appear in the CLI contract (portability floor item
3, PRD §7.3).

Configuration is loaded here, once, and passed down explicitly — there is no
ambient accessor to reach for further in (§6.3). Errors are reported as
sentences on stderr, not tracebacks: the user is looking at a TOML file they
just edited, or at a machine with no model on it, and a stack trace tells them
nothing about either.

Phase 2a added `--inject` to `transcribe`, and with it the §8 persist-before-
inject ordering, written here because `DictationController` did not exist yet.
**Phase 2b lifted that function into the controller, unchanged**, and this
module now imports it — the guarantee changed address, not content, and there
is exactly one copy of it in the product.

`--inject` is opt-in. Typing into whatever window happens to be focused is not
something a diagnostic verb should do by surprise.

Phase 2b also makes `daemon` do something. It is the only verb that holds the
microphone permanently and the only one that installs an event tap, so it is
also the only one that must report both macOS grants before it starts: a daemon
that discovers a missing permission on the user's first dictation has already
recorded ten seconds of audio it cannot deliver.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from amanuensis import __version__
from amanuensis.config import AppConfig, ConfigError, InjectionConfig, load_config
from amanuensis.models.results import ClipboardExposure
from amanuensis.postprocess.base import TracedPostProcessor
from amanuensis.postprocess.registry import build_chain

if TYPE_CHECKING:  # pragma: no cover — these imports are heavy at runtime
    from amanuensis.audio.vad import TrimResult
    from amanuensis.injection.base import TextInjector
    from amanuensis.models.session import LatencyBreakdown
    from amanuensis.storage.history import HistoryStore

__all__ = ["build_parser", "main"]

_EXIT_USAGE = 2
_EXIT_ERROR = 1
_EXIT_OK = 0

#: Verb -> the phase that makes it do something. Kept in one place so that
#: `manu daemon` and the tests cannot disagree about what is built.
#:
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
    history_parser = subparsers.add_parser(
        "history", help="list or purge stored transcripts"
    )
    history_parser.add_argument(
        "--last",
        action="store_true",
        help=(
            "print the most recent transcript, including one the collapse "
            "guard declined to inject"
        ),
    )
    history_parser.add_argument(
        "--raw",
        action="store_true",
        help="show the decoder's own words, before post-processing",
    )
    history_parser.add_argument(
        "--pending",
        action="store_true",
        help="list transcripts written before a failed injection (§5.5)",
    )
    history_parser.add_argument(
        "--limit", type=int, default=20, metavar="N", help="how many to list"
    )
    history_parser.add_argument(
        "--purge",
        action="store_true",
        help="delete every stored transcript, pending file and audio recording",
    )
    history_parser.add_argument(
        "--yes",
        action="store_true",
        help="skip --purge's confirmation prompt (for scripts)",
    )

    transcribe = subparsers.add_parser(
        "transcribe", help="record from the microphone once and print the transcript"
    )
    transcribe.add_argument(
        "--seconds",
        type=float,
        default=10.0,
        metavar="N",
        # PRD §2 binds G1 to a ten-second utterance, so that is the default and
        # this flag is how you depart from it.
        help="how long to record (default: 10, the utterance G1 is defined against)",
    )
    transcribe.add_argument(
        "--inject",
        action="store_true",
        # Opt-in, because the alternative is a diagnostic command that types
        # into whatever window the user happened to leave focused.
        help="paste the transcript at the cursor (Phase 2a; needs Accessibility)",
    )

    vocab = subparsers.add_parser("vocab", help="inspect vocabulary.toml (PRD §5.6)")
    vocab_sub = vocab.add_subparsers(dest="vocab_action", metavar="ACTION")
    check = vocab_sub.add_parser(
        "check", help="show which entries would fire on some text"
    )
    check.add_argument(
        "text",
        nargs="?",
        help="text to run the [replace] map over; omit with --app",
    )
    check.add_argument(
        "--app",
        action="store_true",
        # `[boost.apps]` is keyed on an identifier the product never displays,
        # so without this the feature serves a user who edits TOML *and* can
        # name their applications the way macOS does (choice-story #7). §6.1's
        # argument against new verbs is that they duplicate a text editor;
        # printing a bundle identifier duplicates nothing the user can do.
        help="print the frontmost application's bundle id and its boost terms",
    )

    install = subparsers.add_parser(
        "install",
        help="download the model once and measure this machine's tier",
    )
    install.add_argument(
        "--skip-download",
        action="store_true",
        help="re-measure the tier without re-fetching weights already on disk",
    )
    install.add_argument(
        "--clip",
        type=Path,
        metavar="PATH",
        help="reference clip for the timed check (default: the bundled one)",
    )

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
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"manu: {exc}", file=sys.stderr)
        return _EXIT_ERROR

    if args.verb == "transcribe":
        return _transcribe(config, seconds=args.seconds, inject=args.inject)
    if args.verb == "install":
        return _install(config, skip_download=args.skip_download, clip=args.clip)
    if args.verb == "daemon":
        return _daemon(config)
    if args.verb in ("toggle", "status"):
        return _control(args.verb)
    if args.verb == "history":
        return _history(config, args)
    if args.verb == "vocab":
        if args.vocab_action != "check":
            print("manu vocab: try `manu vocab check --help`.", file=sys.stderr)
            return _EXIT_USAGE
        return _vocab_check(text=args.text, show_app=args.app)

    # Every verb the parser accepts is dispatched above. argparse rejects
    # anything else before reaching here, so this is unreachable rather than a
    # fallback — and it says so instead of pretending to handle a case.
    raise AssertionError(f"unrouted verb {args.verb!r}")


def _control(verb: str) -> int:
    """`manu toggle` and `manu status` — one verb to a running daemon.

    The transport is resolved through `ipc/factory.py`, and the unix socket
    does not appear here: §7.3's floor item 3 says it "must not appear in the
    CLI contract as though it were the interface", and this function is that
    contract.

    A daemon that is not running is reported as exactly that. §7.6 makes the
    distinction a requirement — "nothing is listening" and "the daemon says it
    is idle" are different facts, and reporting the first as the second is a
    claim about the microphone nobody checked.
    """
    from amanuensis.ipc.base import ControlRequestError
    from amanuensis.ipc.factory import UnsupportedPlatformError, create_transport

    try:
        transport = create_transport()
    except (UnsupportedPlatformError, ValueError) as exc:
        print(f"manu {verb}: {exc}", file=sys.stderr)
        return _EXIT_ERROR

    try:
        response = transport.request(verb)
    except ControlRequestError as exc:
        print(f"manu {verb}: {exc}", file=sys.stderr)
        print("  Start one with `manu daemon`.", file=sys.stderr)
        return _EXIT_ERROR

    stream = sys.stdout if response.ok else sys.stderr
    print(response.detail, file=stream)
    return _EXIT_OK if response.ok else _EXIT_ERROR


def _history(config: AppConfig, args: argparse.Namespace) -> int:
    """`manu history` and its flags. §5.5's retention half, read side.

    The default listing exists because §5.5 gap 3's complaint was that the
    `pending/` orphans were "a file the user was never told about and no command
    surfaced" — so a pending count is a **footer on the default output**, not
    something behind a flag the user would have to know to ask for.
    """
    from amanuensis.storage.history import HistoryStore

    store = HistoryStore(config.history)

    if args.purge:
        return _history_purge(store, assume_yes=args.yes)
    if args.last:
        return _history_last(config, raw=args.raw)
    if args.pending:
        found = store.pending()
        if not found:
            print("no pending transcripts.")
            return _EXIT_OK
        print(f"{len(found)} transcript(s) written before a failed injection:")
        for item in found:
            print(f"  {item.started_at}  {store.pending_dir / (item.id + '.json')}")
            print(f"    {item.transcript.strip()[:100]}")
        return _EXIT_OK

    rows = store.recent(limit=args.limit)
    if not rows:
        print("no transcripts yet.")
    for item in rows:
        mark = " " if item.injected else "!"
        text = (item.raw_transcript if args.raw else item.transcript) or ""
        first = text.strip().splitlines()[0] if text.strip() else "(empty)"
        print(f"{mark} {item.started_at}  {first[:90]}")

    orphans = store.pending()
    if orphans:
        # The footer, not a flag. See the docstring.
        print()
        print(
            f"{len(orphans)} transcript(s) are waiting from failed injections — "
            "`manu history --pending`"
        )
    return _EXIT_OK


def _history_purge(store: HistoryStore, assume_yes: bool) -> int:
    """Delete everything, after asking.

    §5.5 says `--purge` wipes it and does not say it asks. Asking is added here
    because the artefact it wipes is the one §8 exists to preserve, and because
    the flag is one character away from `--pending`.
    """
    if not assume_yes:
        print(
            f"This deletes every transcript and recording under {store.db_path.parent}."
        )
        print("It cannot be undone.")
        try:
            answer = input("Type 'purge' to confirm: ")
        except (EOFError, KeyboardInterrupt):
            print()
            answer = ""
        if answer.strip() != "purge":
            print("nothing was deleted.")
            return _EXIT_OK

    result = store.purge()
    print(
        f"purged {result.rows_removed} transcript(s) and "
        f"{result.files_removed} file(s)."
    )
    # §5.5 already declines to claim secure erasure, and repeating the honest
    # version here is cheaper than a user inferring the stronger one.
    print(
        "Amanuensis does not claim secure erasure — full-disk encryption is "
        "what makes residue unreadable."
    )
    return _EXIT_OK


def _history_last(config: AppConfig, raw: bool = False) -> int:
    """Print the most recent transcript. The whole of `history` that exists.

    Pulled forward from Phase 3 by objection O2, and no further. §5.7 refuses
    to inject a transcript the decoder destroyed, and that refusal is only
    defensible if the words are reachable — §8 makes them *present*, which is
    not the same thing. Everything else `manu history` will do — search,
    filtering, purge, the retention half — stays in Phase 3, and the bare verb
    still says so.
    """
    from amanuensis.storage.history import HistoryStore

    found = HistoryStore(config.history).latest()
    if found is None:
        print("no transcripts yet.")
        return _EXIT_OK

    # The status line comes first because it changes how the transcript below
    # should be read: words that never reached the cursor are words the user is
    # about to paste somewhere themselves.
    if not found.injected:
        note = "not injected"
        if found.guard_outcome == "failed":
            note += " — the collapse guard refused it (§5.7)"
        print(f"{found.started_at}  [{note}]")
    else:
        print(found.started_at)
    print()
    if raw:
        print(found.raw_transcript or found.transcript)
        return _EXIT_OK

    print(found.transcript)
    if found.raw_transcript is not None and found.raw_transcript != found.transcript:
        # Both, when they differ (choice-story #10). B0 made "did the processors
        # change my words?" answerable for the first time, and the only viewer
        # of that data was about to ship with no way to ask it — which is
        # dictionary objection O5's complaint surviving its own fix.
        print()
        print("raw (before post-processing):")
        print(found.raw_transcript)
    return _EXIT_OK


def _vocab_check(text: str | None, show_app: bool) -> int:
    """Show what `vocabulary.toml` would do, and where it lives.

    The only `manu vocab` verb. `add`, `list` and `boost` were rejected: §6.1
    treats the verb set as the process model's public contract, and they are a
    second way to do what a text editor already does. This is the one operation
    the file cannot perform on itself.

    **It re-reads the file directly rather than through a loader**, which is the
    point rather than an implementation detail (choice-story #5). A user who
    edits `vocabulary.toml` while the daemon is running never meets the startup
    parse error — the daemon keeps its last good map and degrades rather than
    stalling — so this is where a broken file has to become legible, with the
    key named.
    """
    from amanuensis.postprocess.vocabulary import (
        default_vocabulary_path,
        load_vocabulary,
    )

    path = default_vocabulary_path()
    try:
        vocabulary = load_vocabulary(path)
    except ConfigError as exc:
        print(f"manu vocab check: {exc}", file=sys.stderr)
        return _EXIT_ERROR

    print(f"{path}  ({vocabulary.entry_count} [replace] entries)")
    for warning in vocabulary.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if show_app:
        from amanuensis.injection.factory import (
            UnsupportedPlatformError,
            create_injector,
        )

        try:
            injector = create_injector(InjectionConfig())
            bundle = injector.focus_identity()
        except UnsupportedPlatformError as exc:
            print(f"manu vocab check: {exc}", file=sys.stderr)
            return _EXIT_ERROR
        print()
        print(f"frontmost application: {bundle or '(cannot tell)'}")
        terms = vocabulary.terms_for(bundle)
        scoped = bundle is not None and bundle in vocabulary.boost_by_app
        source = "[boost.apps]" if scoped else "[boost] terms"
        print(f"boost terms ({source}): {', '.join(terms) if terms else '(none)'}")

    if text is None:
        if not show_app:
            print()
            print("nothing to check — pass some text, or --app.")
        return _EXIT_OK

    replaced, fired = vocabulary.apply(text)
    print()
    print(replaced)
    print()
    if fired:
        for entry in fired:
            key = entry.split(":", 1)[1]
            print(f"  {key!r} -> {vocabulary.replacements[key]!r}")
    else:
        print("  no entries fired.")
    return _EXIT_OK


def _transcribe(config: AppConfig, seconds: float, inject: bool = False) -> int:
    """Record once, transcribe once, print the transcript and the timings.

    The timings are not decoration. G1 cannot be defended without per-stage
    numbers (§5.5), and this verb is the only place before Phase 2b where the
    whole path from microphone to text runs at once — the tier check measures
    the ASR stage in isolation and the benchmark reads from files.

    With `--inject`, the permission check and the clipboard-exposure warning
    both run **before** the microphone opens. A user who is going to be told
    they lack Accessibility should be told it before they speak for ten
    seconds, not after; and a user who is about to put a transcript on a
    clipboard a manager is recording should learn that while they can still
    press Ctrl-C.

    Imports are local to the function on purpose. Loading CTranslate2 and
    PortAudio to print a usage error would undo the lazy-import discipline the
    rest of the package keeps.
    """
    if seconds <= 0:
        print("manu transcribe: --seconds must be greater than 0", file=sys.stderr)
        return _EXIT_USAGE

    import uuid
    from datetime import UTC, datetime

    from amanuensis.audio.capture import AudioCapture, DeviceNotFoundError
    from amanuensis.audio.vad import VoiceActivityDetector
    from amanuensis.controllers.dictation_controller import deliver
    from amanuensis.engines.faster_whisper import (
        FasterWhisperEngine,
        ModelNotAvailableError,
    )
    from amanuensis.models.session import DictationSession, LatencyBreakdown

    # Both or neither, and the type says so. `history` was previously bound
    # only inside the branch below, which mypy accepts and a future edit would
    # break silently — on the one path where the §8 guarantee lives.
    from amanuensis.postprocess.vocabulary import VocabularyLoader

    vocabulary = VocabularyLoader()
    try:
        processors = build_chain(config.postprocess, vocabulary)
    except ValueError as exc:
        print(f"manu transcribe: {exc}", file=sys.stderr)
        return _EXIT_ERROR

    injector: TextInjector | None = None
    history: HistoryStore | None = None
    if inject:
        from amanuensis.injection.factory import (
            UnsupportedPlatformError,
            create_injector,
        )
        from amanuensis.injection.macos import detect_clipboard_manager
        from amanuensis.storage.history import HistoryStore

        try:
            injector = create_injector(config.injection)
        except UnsupportedPlatformError as exc:
            print(f"manu transcribe: {exc}", file=sys.stderr)
            return _EXIT_ERROR

        # Before the microphone opens, not after: the first injection costs
        # ~165 ms of pyobjc import and it would otherwise land on the run the
        # user is timing. Phase 2a used to get this by accident.
        injector.warm_up()

        status = injector.check_permissions()
        if not status.granted:
            print(f"manu transcribe: {status.remediation}", file=sys.stderr)
            return _EXIT_ERROR

        # Each strategy has a stated cost and each cost gets surfaced. The
        # symmetry is the point: a user who switched to `keystroke` to escape
        # the clipboard exposure should not discover the substitution problem
        # from their own transcript.
        for warning in (
            _clipboard_warning(config.injection, detect_clipboard_manager()),
            _keystroke_warning(config.injection),
        ):
            if warning is not None:
                print(warning, file=sys.stderr)
                print(file=sys.stderr)

        history = HistoryStore(config.history)

    timings = LatencyBreakdown()

    try:
        engine = FasterWhisperEngine(config.engine)
        detector = VoiceActivityDetector(config.vad)
        print(
            f"loading {engine.model_name} ({engine.cpu_threads} threads)...",
            flush=True,
        )
        detector.load()
        engine.load()
        engine.warm_up()
    except (ModelNotAvailableError, ValueError) as exc:
        print(f"manu transcribe: {exc}", file=sys.stderr)
        return _EXIT_ERROR

    capture = AudioCapture(config.audio)
    try:
        print(f"recording for {seconds:g}s — speak now.", flush=True)
        started = time.perf_counter()
        audio = capture.record(seconds)
        timings.capture_ms = (time.perf_counter() - started) * 1000.0
    except DeviceNotFoundError as exc:
        print(f"manu transcribe: {exc}", file=sys.stderr)
        return _EXIT_ERROR

    if len(audio) == 0:
        print("manu transcribe: no audio was captured", file=sys.stderr)
        return _EXIT_ERROR

    # G1's clock starts here — at the point a hotkey would have been released.
    started = time.perf_counter()
    trimmed = detector.trim(audio, config.audio.sample_rate)
    timings.vad_ms = (time.perf_counter() - started) * 1000.0

    started = time.perf_counter()
    raw_text = engine.transcribe(trimmed.audio, config.audio.sample_rate).text
    timings.transcribe_ms = (time.perf_counter() - started) * 1000.0

    # This verb exists to measure the whole path, so it runs the configured
    # chain rather than printing the decoder's output and calling it the
    # product. Before Phase 3 it printed a `g1_ms` with a stage missing and said
    # so in a footnote; a number that needs a footnote to be read correctly is
    # the shape this project has already been misled by twice.
    session = DictationSession(
        id=uuid.uuid4().hex,
        started_at=datetime.now(UTC),
        audio=None,  # §5.5: audio is stored only behind `store_audio`
        sample_rate=config.audio.sample_rate,
        raw_transcript=raw_text,
        engine=f"{config.engine.backend}:{engine.model_name}",
        timings=timings,
    )
    text = raw_text
    started = time.perf_counter()
    for processor in processors:
        if isinstance(processor, TracedPostProcessor):
            text, acted = processor.process_traced(text, session)
            session.fired_entries += acted
        else:
            text = processor.process(text, session)
    timings.postprocess_ms = (time.perf_counter() - started) * 1000.0
    if processors:
        session.final_text = text

    print()
    print(text.strip() or "(nothing was transcribed)")
    if session.fired_entries:
        # Which rules acted, not just that the text changed. A user comparing
        # this against what they said needs to know whether the product edited
        # it or the decoder heard it that way (dictionary objection O5).
        print(f"  [{', '.join(session.fired_entries)}]")
    print()

    exit_code = _EXIT_OK
    if injector is not None and history is not None:
        result = deliver(session, history, injector)
        if result.succeeded:
            print(f"injected via {result.strategy}.")
        else:
            # Not an error the user can lose anything to — §8's write already
            # ran. Say where the words are rather than only that it failed.
            where = history.db_path if config.history.retain else history.pending_dir
            print(f"injection failed: {result.error}", file=sys.stderr)
            print(
                f"your transcript was persisted before injection was attempted "
                f"({where})",
                file=sys.stderr,
            )
            exit_code = _EXIT_ERROR
        print()

    _print_timings(timings, trimmed, injected=injector is not None)
    return exit_code


def _daemon(config: AppConfig) -> int:
    """Hold the model, hold the microphone, and answer the hotkey.

    The order of what happens here is the phase's argument, not an
    implementation detail:

    1. **Both permissions are checked before anything is loaded.** Accessibility
       (injection) and Input Monitoring (the hotkey) are separate macOS grants
       in separate panes, and a daemon that discovers a missing one on the
       user's first dictation has already recorded ten seconds of audio it
       cannot deliver.
    2. **The orphan sweep runs before the microphone opens** (§5.5 gap 2). It
       is the only thing that ever expires a `retain = false` transcript, and
       the count of what remains is — until `manu history` arrives in Phase 3 —
       the only place the user is told those files exist.
    3. **The controller starts before the run loop.** Loading the model and
       warming the injector take seconds and milliseconds respectively; both
       land here rather than on the first dictation.
    4. **The indicator's run loop is last, on the main thread, and blocks.**
       §6.3 puts the tray on the main thread because a macOS status item
       requires it, and every other thread in the daemon is arranged around
       that one fact.

    Ctrl-C is handled through the run loop rather than by letting
    `KeyboardInterrupt` unwind: the interpreter's default cannot interrupt
    `NSApplication.run()`, so a plain Ctrl-C would leave a daemon holding the
    microphone with no indicator to say so.
    """
    import dataclasses
    import signal
    import threading

    from amanuensis.audio.capture import AudioCapture, DeviceNotFoundError
    from amanuensis.audio.vad import SilenceWatcher, VoiceActivityDetector
    from amanuensis.controllers.dictation_controller import (
        DictationController,
        DictationState,
    )
    from amanuensis.engines.faster_whisper import (
        FasterWhisperEngine,
        ModelNotAvailableError,
    )
    from amanuensis.hotkey.factory import create_hotkey_listener
    from amanuensis.hotkey.macos import HotkeyPermissionError, UnsupportedBindingError
    from amanuensis.injection.factory import UnsupportedPlatformError, create_injector
    from amanuensis.injection.macos import detect_clipboard_manager
    from amanuensis.ipc.base import Response, make_handler
    from amanuensis.ipc.factory import create_transport
    from amanuensis.ipc.macos import AlreadyRunningError
    from amanuensis.storage.history import HistoryStore
    from amanuensis.ui.overlay import RecordingOverlay
    from amanuensis.ui.tray import TrayApp

    try:
        injector = create_injector(config.injection)
        listener = create_hotkey_listener(config.hotkey)
    except (UnsupportedPlatformError, UnsupportedBindingError) as exc:
        print(f"manu daemon: {exc}", file=sys.stderr)
        return _EXIT_ERROR

    # Both grants, before anything is loaded and before the microphone opens.
    # Reported together rather than one at a time: a user who fixes one and
    # restarts only to be told about the other has been sent to System
    # Settings twice for a condition that was fully known the first time.
    missing = [
        status
        for status in (injector.check_permissions(), listener.check_permissions())
        if not status.granted
    ]
    if missing:
        for status in missing:
            print(f"manu daemon: {status.remediation}", file=sys.stderr)
            print(file=sys.stderr)
        return _EXIT_ERROR

    # §9's single-instance guard. A daemon started 2026-08-07 was still live
    # when a second was started for the Phase 3 gate: both event taps saw the
    # binding, both held the microphone, both decoded and both injected. Every
    # row in `history.db` doubled, every transcript pasted twice, and
    # `transcribe_ms` ran 3854-5236 ms against ~890 ms single-process. It
    # survived two days because the only visible symptom was a double paste in
    # one application.
    #
    # Position matters in both directions. It is claimed **before** anything is
    # taken — the event tap, the microphone, the status item — rather than at
    # `control.serve` below, which is where the bind used to happen and is
    # three acquisitions too late; §5.4 calls the intermediate state a privacy
    # problem in its own right, because the indicator on one daemon reads
    # *idle* while the other is recording. And it is claimed **after** the
    # binding and permission refusals above, which take nothing: being told
    # your hotkey is unsupported should not require being the only daemon.
    control = create_transport()
    try:
        control.claim()
    except AlreadyRunningError as exc:
        print(f"manu daemon: {exc}", file=sys.stderr)
        return _EXIT_ERROR

    exposure = detect_clipboard_manager()
    for warning in (
        _clipboard_warning(config.injection, exposure),
        _keystroke_warning(config.injection),
    ):
        if warning is not None:
            print(warning, file=sys.stderr)
            print(file=sys.stderr)

    history = HistoryStore(config.history)
    swept = history.sweep()
    if swept.removed or swept.remaining:
        print(
            f"pending transcripts: {swept.removed} expired, "
            f"{swept.remaining} still recoverable in {history.pending_dir}",
            flush=True,
        )

    # Built eagerly, before the model loads. A chain naming something that is
    # not built is a daemon that refuses to start with a sentence, rather than
    # a dictation that silently skips a stage — which is the failure Phase 2b
    # spent a gate note on.
    from amanuensis.postprocess.vocabulary import VocabularyLoader

    # One loader, shared by the chain and the controller. `[boost]` reads the
    # same snapshot before the decode that `[replace]` reads after it, so a user
    # editing their file mid-session cannot have the edit land on one half and
    # not the other.
    vocabulary = VocabularyLoader()
    try:
        processors = build_chain(config.postprocess, vocabulary)
    except ValueError as exc:
        print(f"manu daemon: {exc}", file=sys.stderr)
        return _EXIT_ERROR
    for warning in vocabulary.refresh().warnings:
        print(f"vocabulary.toml: {warning}", file=sys.stderr)
    if vocabulary.error is not None:
        print(f"vocabulary.toml: {vocabulary.error}", file=sys.stderr)

    try:
        engine = FasterWhisperEngine(config.engine)
        detector = VoiceActivityDetector(config.vad)
        capture = AudioCapture(config.audio)
        print(
            f"loading {engine.model_name} ({engine.cpu_threads} threads)...", flush=True
        )
    except (ModelNotAvailableError, ValueError) as exc:
        print(f"manu daemon: {exc}", file=sys.stderr)
        return _EXIT_ERROR

    # Phase 4: `TrayApp` composes the Phase 2b indicator rather than replacing
    # it, so there is still exactly one status item — and the exposure the
    # startup warning above prints to a terminal nobody is watching now has a
    # persistent home (§5.4, §7.3).
    tray = TrayApp()
    # An overlay failure reports through the tray rather than killing the
    # daemon: it runs inside an NSBlockOperation, where an uncaught Python
    # exception crosses the PyObjC bridge as an NSException and terminates
    # the process — which it did on 2026-09-02, over a confidence feature.
    overlay = RecordingOverlay(config.feedback, on_error=tray.set_error)

    def _on_state_change(state: DictationState) -> None:
        # Two surfaces, one state, and the fan-out lives here rather than in
        # either of them: §6.2 makes the tray a status surface, and a tray that
        # drove the overlay would be a tray that owned another component's
        # lifetime.
        tray.set_state(state)
        overlay.set_state(state)

    tray.set_clipboard_exposure(
        exposure if config.injection.warn_on_clipboard_manager else None
    )
    controller = DictationController(
        config=config,
        engine=engine,
        injector=injector,
        processors=processors,
        history=history,
        capture=capture,
        detector=detector,
        on_state_change=_on_state_change,
        vocabulary=vocabulary,
    )

    # The waveform needs the audio while it is arriving, and so does
    # `vad_auto`. `set_observer` holds one callback, so the fan-out lives here
    # for the same reason `_on_state_change` does: neither component should own
    # the other's lifetime, and this thread has a deadline.
    observers: list[Any] = []

    def _level_for_overlay(block: Any) -> None:
        import numpy as np

        if block.size:
            overlay.set_level(
                float(np.sqrt(np.mean(np.square(block.astype(np.float64)))))
            )

    observers.append(_level_for_overlay)

    # §5.2's third mode. The watcher is built and fed **always**, and consults
    # the live mode before acting — rather than being wired only when the
    # daemon happens to start in `vad_auto`. That is what makes the mode
    # switchable from the tray: conditional wiring at start-up would mean
    # choosing `vad_auto` from a menu produced a mode with nothing ending it.
    hotkey_state = {"mode": config.hotkey.mode, "binding": config.hotkey.binding}
    watcher = SilenceWatcher(config.vad_auto, config.audio.sample_rate)

    def _watch(block: Any) -> None:
        if hotkey_state["mode"] != "vad_auto":
            return
        if watcher.feed(block):
            # Handed to a thread rather than done here: this is the PortAudio
            # callback and §6.3 forbids blocking it.
            threading.Thread(
                target=controller.end_session,
                name="amanuensis-vad-auto-end",
                daemon=True,
            ).start()

    observers.append(_watch)

    def _start_session() -> None:
        # Silence has to be re-earned every session, or the second dictation
        # inherits the first one's trailing quiet and ends immediately.
        watcher.reset()
        controller.start_session()

    def _fan_out(block: Any) -> None:
        for observer in observers:
            observer(block)

    capture.set_observer(_fan_out)

    def _on_release() -> None:
        # The listener's callbacks return nothing, deliberately: there is
        # nothing useful a callback could hand back to a thread that must not
        # wait for it (§6.3). The session is observed through history and the
        # tray, never through this return.
        controller.end_session()

    try:
        controller.start()
        listener.start(_start_session, _on_release)
    except (ModelNotAvailableError, DeviceNotFoundError, HotkeyPermissionError) as exc:
        controller.shutdown()
        print(f"manu daemon: {exc}", file=sys.stderr)
        return _EXIT_ERROR

    # §7.3 floor item 3, and §7.6's authority model. The acceptor runs on its
    # own thread and must not block: `toggle` returns as soon as the controller
    # has been told, never when the dictation finishes.
    def _status() -> Response:
        # Deliberately no transcript content. §7.6 forbids it — a `status` that
        # returned the last transcript would open an egress path G3's packet
        # capture cannot see.
        return Response(
            ok=True,
            detail=(
                f"running: model {config.engine.model}, "
                f"mode {config.hotkey.mode}, state {tray.state.value}"
            ),
        )

    def _toggle() -> Response:
        if tray.state is DictationState.RECORDING:
            controller.end_session()
            return Response(ok=True, detail="stopping")
        _start_session()
        return Response(ok=True, detail="recording")

    # Already claimed at the top of `_daemon`; this only starts accepting.
    control.serve(make_handler({"status": _status, "toggle": _toggle}))

    # The hotkey picker (§5.3's `[hotkey] binding`, offered from the tray
    # because the operator's right-option double-tap fires another
    # application's shortcut). The tray renders a list and hands back a name;
    # everything that changing a binding actually involves lives here, which is
    # §6.2's boundary.
    from amanuensis.config import (
        default_config_path,
        write_hotkey_binding,
        write_hotkey_mode,
    )
    from amanuensis.hotkey.macos import available_bindings, available_modes

    listener_box = {"current": listener}

    def _rebuild_listener(what: str, **changes: str) -> bool:
        """Swap the event tap for one built from `changes`. True on success.

        Shared by the binding and mode pickers: the delicate part is the window
        between stopping one tap and starting another, where a raise leaves a
        daemon with no hotkey at all, and two copies of that would drift.
        """
        old = listener_box["current"]
        try:
            # Persist first. A setting that works this session and is gone
            # after a restart is worse than one that never changed, because
            # the user stops trusting the menu.
            if "binding" in changes:
                write_hotkey_binding(default_config_path(), changes["binding"])
            if "mode" in changes:
                write_hotkey_mode(default_config_path(), changes["mode"])
            replacement = create_hotkey_listener(
                dataclasses.replace(
                    config.hotkey,
                    binding=changes.get("binding", hotkey_state["binding"]),
                    mode=changes.get("mode", hotkey_state["mode"]),
                )
            )
            old.stop()
            replacement.start(_start_session, _on_release)
        except Exception as exc:
            tray.set_error(f"could not switch to {what}: {exc}")
            # The old tap is already stopped in the failure window between
            # `old.stop()` and a raise from `start`; restarting it is the only
            # thing that leaves a usable daemon.
            try:
                if not old.is_running:
                    old.start(_start_session, _on_release)
            except Exception:
                tray.set_error(
                    f"the hotkey is not listening after failing to switch to "
                    f"{what}. Restart the daemon."
                )
            return False
        listener_box["current"] = replacement
        hotkey_state.update(changes)
        tray.set_error(None)
        print(f"{what} (written to {default_config_path()})")
        return True

    def _change_hotkey(name: str) -> None:
        if _rebuild_listener(f"hotkey is now {name}", binding=name):
            tray.set_hotkey_options(available_bindings(), name)

    def _change_mode(name: str) -> None:
        if _rebuild_listener(f"mode is now {name}", mode=name):
            # A mode switch mid-session would leave a capture nothing ends.
            watcher.reset()
            tray.set_mode_options(available_modes(), name)

    tray.set_on_hotkey(_change_hotkey)
    tray.set_on_mode(_change_mode)
    tray.set_hotkey_options(available_bindings(), config.hotkey.binding)
    tray.set_mode_options(available_modes(), config.hotkey.mode)
    tray.set_on_quit(tray.stop)
    signal.signal(signal.SIGINT, lambda *_: tray.stop())
    signal.signal(signal.SIGTERM, lambda *_: tray.stop())

    print(
        f"listening — hold {config.hotkey.binding} to dictate. Ctrl-C to stop.",
        flush=True,
    )
    tray.show()
    try:
        tray.run()
    finally:
        # Whatever ended the loop, the microphone is released and the tap is
        # torn down. A daemon that exits still holding either is §5.4's
        # failure with the tray already gone.
        control.stop()
        listener_box["current"].stop()
        controller.shutdown()
        # The panel says the microphone is live. It outlives neither.
        overlay.hide()
        print("stopped.")
    return _EXIT_OK


def _clipboard_warning(
    config: InjectionConfig, exposure: ClipboardExposure
) -> str | None:
    """What to tell the user about the transcript transiting their clipboard.

    Returns None when there is nothing to say — and prints no all-clear, ever.
    §7.3 is explicit that the detection list is incomplete by nature, so
    "no known manager detected" is the only true statement available and
    "no manager present" is the one a reassuring message would imply.

    This is the Phase 2a stand-in for §5.4's tray indicator. The tray is
    Phase 4 and does not exist; the obligation to make the exposure visible
    rather than silent does exist, and it exists now, because `--inject` is
    the first thing that puts a transcript on the clipboard.
    """
    if config.strategy != "clipboard":
        # The user who chose `keystroke` chose it to avoid exactly this. §5.4
        # scopes the indicator to the clipboard strategy for that reason.
        return None
    if not config.warn_on_clipboard_manager:
        return None
    if not exposure.detected:
        return None

    return (
        f"clipboard exposure: {exposure.manager} is running and keeps "
        "clipboard history.\n"
        "  Your transcript transits the system clipboard, so it may be "
        "recorded there —\n"
        "  and some managers sync across devices, which means it can leave "
        "this machine.\n"
        "  This is the manager working correctly, not a bug (§7.3). Use "
        '[injection] strategy =\n  "keystroke" to avoid it, or '
        "warn_on_clipboard_manager = false to silence this."
    )


def _keystroke_warning(config: InjectionConfig) -> str | None:
    """What `strategy = "keystroke"` costs, measured rather than assumed.

    §7.3 offers this strategy to users who cannot accept the clipboard
    exposure, and states its cost as being slower and more failure-prone. The
    Phase 2a gate measured a third cost that is larger than both: **synthetic
    keystrokes are subject to the target application's text substitution.**
    Into TextEdit,

        don't use --dashes... "quoted" and i said so

    arrives as

        don't use —dashes… "quoted" and I said so

    Five changes — smart quotes twice, an em dash, an ellipsis, and an
    autocapitalised "i". Pasting the identical string is byte-identical.

    Nothing in Amanuensis can reach into another application's substitution
    settings, so this cannot be fixed here; it can only be said. It lands on
    §4's privacy-motivated primary user, who is precisely the person this
    strategy exists for, and it undercuts §1's claim to produce the text the
    user meant — a tool that resolves your self-corrections and then rewrites
    your punctuation has moved the problem rather than solved it.
    """
    if config.strategy != "keystroke":
        return None

    return (
        "keystroke strategy: the target application may rewrite what is typed.\n"
        "  macOS text substitution — smart quotes, em dashes, ellipses, "
        "autocapitalisation —\n"
        "  applies to synthetic keystrokes as it does to real ones, and "
        "Amanuensis cannot\n"
        "  turn it off in another application. Measured into TextEdit: five "
        "substitutions\n"
        "  in one sentence. Clipboard paste is byte-identical. Turn the "
        "substitutions off in\n"
        '  the target app, or use [injection] strategy = "clipboard".'
    )


def _print_timings(
    timings: LatencyBreakdown, trimmed: TrimResult, injected: bool = False
) -> None:
    """Per-stage timings, plus what the trim actually did.

    The trim line is here because §7.4 makes trimming the dominant latency
    lever and a user comparing two runs needs to see whether the detector
    behaved the same way in both. A `fell_back` trim that went unreported would
    present as the engine having got slower.

    `g1_ms` is labelled a floor whenever a stage is missing, because this
    project has twice been misled by a number reported without the condition
    it was measured under.
    """
    print("timings (ms)")
    print(f"  {'capture_ms':<16} {timings.capture_ms:8.1f}   (excluded from G1)")
    print(f"  {'vad_ms':<16} {timings.vad_ms:8.1f}")
    print(f"  {'transcribe_ms':<16} {timings.transcribe_ms:8.1f}")
    print(
        f"  {'asr_ms':<16} {timings.asr_ms:8.1f}   "
        "<- what the tier check bounds (350 / 700 ms, §7.2)"
    )
    if injected:
        print(f"  {'persist_ms':<16} {timings.persist_ms:8.1f}")
        print(f"  {'inject_ms':<16} {timings.inject_ms:8.1f}")
        print(
            f"  {'restore_ms':<16} {timings.restore_ms:8.1f}   "
            "(excluded from G1 — runs after the text is present, §2)"
        )
    print(
        f"  {'g1_ms':<16} {timings.g1_ms:8.1f}   " "<- G1: 400 ms p50 / 800 ms p95 (§2)"
    )
    if injected:
        pass
    else:
        print("  postprocess and inject are not in this run, so g1_ms here is a")
        print("  floor and will grow. `--inject` adds the two Phase 2a stages.")
    print()
    fallback = (
        " — NO SPEECH DETECTED, audio passed through whole" if trimmed.fell_back else ""
    )
    print(
        f"trim: {trimmed.original_seconds:.1f}s -> {trimmed.retained_seconds:.1f}s "
        f"({trimmed.speech_segments} speech segment(s)){fallback}"
    )


def _install(config: AppConfig, skip_download: bool, clip: Path | None) -> int:
    """Fetch the weights once, then measure and record this machine's tier.

    The two halves are deliberately separate. §7.2: "Model download is not part
    of the timed check. It is a one-time install cost and timing it would
    measure the network." `--skip-download` exists so re-measuring a tier does
    not re-fetch weights that are already on disk.
    """
    from amanuensis.engines.faster_whisper import (
        ModelNotAvailableError,
        WeightsDigestError,
        download_weights,
        resolve_device,
        resolve_model_name,
        resolve_model_path,
        verify_weights,
    )
    from amanuensis.tier import (
        TIER_A_P50_MS,
        TIER_A_P95_MS,
        ReferenceClipMissingError,
        record_tier,
        run_tier_check,
    )

    try:
        device = resolve_device(config.engine.device)
        model = resolve_model_name(config.engine.model, device)
    except ValueError as exc:
        print(f"manu install: {exc}", file=sys.stderr)
        return _EXIT_ERROR

    if not skip_download:
        print(f"downloading {model} — this is the only network access Amanuensis")
        print("makes, and it happens once (goal G3, §7.6).", flush=True)
        try:
            path = download_weights(model)
        except WeightsDigestError as exc:
            # Distinct from a failed download, and worth its own exit path: the
            # bytes arrived and are not the bytes this project recorded.
            print(f"manu install: {exc}", file=sys.stderr)
            return _EXIT_ERROR
        except Exception as exc:  # hub raises several unrelated types
            print(f"manu install: could not download {model}: {exc}", file=sys.stderr)
            return _EXIT_ERROR
        print(f"weights at {path}")
    else:
        try:
            path = resolve_model_path(model)
        except ModelNotAvailableError as exc:
            print(f"manu install: {exc}", file=sys.stderr)
            return _EXIT_ERROR

    # `download_weights` already refused a mismatch — this re-checks so the user
    # is told the verification happened. Deliberate second hash: it costs about
    # a fifth of a second on a one-time install, and an enforcement nobody can
    # see is one a later refactor removes without anything noticing. It also
    # covers `--skip-download`, where nothing verified the on-disk copy at all.
    try:
        verification = verify_weights(path, model)
    except WeightsDigestError as exc:
        print(f"manu install: {exc}", file=sys.stderr)
        return _EXIT_ERROR
    if verification.verified:
        print(
            f"checksums verified — {verification.files_checked} files match the "
            f"digests recorded for this pinned revision (§7.6)"
        )
    else:
        # Not a pass. §7.6: a model with no recorded digests is reported as
        # unverified rather than silently accepted.
        print(f"NOT verified — no digests are recorded for {model} (§7.6)")

    try:
        result = run_tier_check(config, clip_path=clip)
    except (ReferenceClipMissingError, ModelNotAvailableError) as exc:
        print(f"manu install: {exc}", file=sys.stderr)
        return _EXIT_ERROR

    written = record_tier(result)
    print()
    print(f"Tier {result.tier}")
    print(f"  p50 {result.p50_ms:.1f} ms   (threshold {TIER_A_P50_MS:.0f} ms)")
    print(f"  p95 {result.p95_ms:.1f} ms   (threshold {TIER_A_P95_MS:.0f} ms)")
    print(
        f"  model {result.model}, {result.cpu_threads} threads, "
        f"{result.runs} runs on a {result.clip_seconds:.1f}s clip"
    )
    if result.g1_binds:
        print("  G1 binds on this machine and is published as a guarantee (§2).")
    else:
        print("  G1-CPU applies (§2). The measured number is published; nothing halts.")
    print(f"  recorded at {written}")
    return _EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
