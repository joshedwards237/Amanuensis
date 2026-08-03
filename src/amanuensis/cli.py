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

Phase 2a adds `--inject` to `transcribe`, and with it `_deliver` — the §8
persist-before-inject ordering, in one function, deliberately small enough to
read in one go. It lives here rather than in `DictationController` because the
controller is Phase 2b and this ordering is Phase 2a's whole point; when the
controller arrives it lifts this function and the CLI stops owning it. Until
then, this is the only place in the product where the guarantee is enforced,
which is why it is tested directly rather than through the microphone.

`--inject` is opt-in. Typing into whatever window happens to be focused is not
something a diagnostic verb should do by surprise.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from amanuensis import __version__
from amanuensis.config import AppConfig, ConfigError, InjectionConfig, load_config
from amanuensis.models.results import ClipboardExposure, InjectionResult

if TYPE_CHECKING:  # pragma: no cover — these imports are heavy at runtime
    from amanuensis.audio.vad import TrimResult
    from amanuensis.injection.base import TextInjector
    from amanuensis.models.session import DictationSession, LatencyBreakdown
    from amanuensis.storage.history import HistoryStore

__all__ = ["build_parser", "main"]

_EXIT_USAGE = 2
_EXIT_ERROR = 1
_EXIT_OK = 0

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

    print(
        f"manu {args.verb}: not implemented yet — it is built in "
        f"{_VERB_PHASES[args.verb]}.",
        file=sys.stderr,
    )
    return _EXIT_ERROR


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
    from amanuensis.engines.faster_whisper import (
        FasterWhisperEngine,
        ModelNotAvailableError,
    )
    from amanuensis.models.session import DictationSession, LatencyBreakdown

    # Both or neither, and the type says so. `history` was previously bound
    # only inside the branch below, which mypy accepts and a future edit would
    # break silently — on the one path where the §8 guarantee lives.
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
    text = engine.transcribe(trimmed.audio, config.audio.sample_rate)
    timings.transcribe_ms = (time.perf_counter() - started) * 1000.0

    print()
    print(text.strip() or "(nothing was transcribed)")
    print()

    exit_code = _EXIT_OK
    if injector is not None and history is not None:
        session = DictationSession(
            id=uuid.uuid4().hex,
            started_at=datetime.now(UTC),
            audio=None,  # §5.5: audio is stored only behind `store_audio`
            sample_rate=config.audio.sample_rate,
            raw_transcript=text,
            engine=f"{config.engine.backend}:{engine.model_name}",
            timings=timings,
        )
        result = _deliver(session, history, injector)
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


class _TranscriptStore(Protocol):
    """The two operations `_deliver` needs from a history store.

    Narrower than `HistoryStore` on purpose: the ordering below is the §8
    guarantee, and a protocol that admitted `purge` would invite a future
    version of this function to do something other than persist and mark.
    """

    def write_pending(self, session: DictationSession) -> bool: ...

    def mark_injected(self, session: DictationSession) -> None: ...


def _deliver(
    session: DictationSession,
    history: _TranscriptStore,
    injector: TextInjector,
) -> InjectionResult:
    """Persist, then inject, then mark. In that order, always.

    PRD §8: *never lose a transcript — write to history before injection*.
    Everything else in this function is subordinate to those three calls being
    in that sequence, and the sequence is what the test asserts.

    Three deliberate choices:

    **`mark_injected` runs only on success.** Failure is the absence of a
    call, not a branch — the case the guarantee protects needs no code, which
    means it cannot be broken by editing the code that handles success.

    **An injector that raises is caught.** The ABC says `inject` reports
    rather than raises, and a pyobjc bridge is exactly the sort of thing that
    violates a contract like that at the worst moment. The words are already
    safe by then; catching is what turns a traceback into a sentence and stops
    `mark_injected` running on a path that did not succeed.

    **Both stages are timed into `LatencyBreakdown`.** G1's clock starts at
    hotkey release and both of these happen after it (§2). A stage with no
    field to record into is a stage that cannot be defended when G1 is missed
    — the lesson `vad_ms` taught one phase ago.
    """
    started = time.perf_counter()
    persisted = history.write_pending(session)
    session.timings.persist_ms = (time.perf_counter() - started) * 1000.0

    if not persisted:
        # choice-story #7: a session that never reaches injection leaves
        # nothing behind. Pasting an empty string would still clobber the
        # clipboard, which is a real cost for no benefit whatsoever.
        return InjectionResult(
            succeeded=False, strategy="none", error="nothing was transcribed"
        )

    text = session.final_text or session.raw_transcript or ""

    started = time.perf_counter()
    try:
        result = injector.inject(text)
    except Exception as exc:  # the ABC forbids this; the bridge may not comply
        result = InjectionResult(
            succeeded=False,
            strategy="unknown",
            error=f"the injector raised: {exc!r}",
        )
    session.timings.inject_ms = (time.perf_counter() - started) * 1000.0

    if result.succeeded:
        history.mark_injected(session)
    return result


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
        f"  {'g1_ms':<16} {timings.g1_ms:8.1f}   " "<- G1: 400 ms p50 / 800 ms p95 (§2)"
    )
    if injected:
        print("  post-processing is not built yet (Phase 3), so g1_ms here is")
        print("  still a floor. Injection and the §8 write are in it.")
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
        download_weights,
        resolve_device,
        resolve_model_name,
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
        except Exception as exc:  # hub raises several unrelated types
            print(f"manu install: could not download {model}: {exc}", file=sys.stderr)
            return _EXIT_ERROR
        print(f"weights at {path}")

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
