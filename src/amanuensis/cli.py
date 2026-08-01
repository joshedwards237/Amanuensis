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
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from amanuensis import __version__
from amanuensis.config import AppConfig, ConfigError, load_config

if TYPE_CHECKING:  # pragma: no cover — these imports are heavy at runtime
    from amanuensis.audio.vad import TrimResult
    from amanuensis.models.session import LatencyBreakdown

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
        return _transcribe(config, seconds=args.seconds)
    if args.verb == "install":
        return _install(config, skip_download=args.skip_download, clip=args.clip)

    print(
        f"manu {args.verb}: not implemented yet — it is built in "
        f"{_VERB_PHASES[args.verb]}.",
        file=sys.stderr,
    )
    return _EXIT_ERROR


def _transcribe(config: AppConfig, seconds: float) -> int:
    """Record once, transcribe once, print the transcript and the timings.

    The timings are not decoration. G1 cannot be defended without per-stage
    numbers (§5.5), and this verb is the only place in Phase 1 where the whole
    path from microphone to text runs at once — the tier check measures the ASR
    stage in isolation and the benchmark reads from files.

    Imports are local to the function on purpose. Loading CTranslate2 and
    PortAudio to print a usage error would undo the lazy-import discipline the
    rest of the package keeps.
    """
    if seconds <= 0:
        print("manu transcribe: --seconds must be greater than 0", file=sys.stderr)
        return _EXIT_USAGE

    import time

    from amanuensis.audio.capture import AudioCapture, DeviceNotFoundError
    from amanuensis.audio.vad import VoiceActivityDetector
    from amanuensis.engines.faster_whisper import (
        FasterWhisperEngine,
        ModelNotAvailableError,
    )
    from amanuensis.models.session import LatencyBreakdown

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
    _print_timings(timings, trimmed)
    return _EXIT_OK


def _print_timings(timings: LatencyBreakdown, trimmed: TrimResult) -> None:
    """Per-stage timings, plus what the trim actually did.

    The trim line is here because §7.4 makes trimming the dominant latency
    lever and a user comparing two runs needs to see whether the detector
    behaved the same way in both. A `fell_back` trim that went unreported would
    present as the engine having got slower.
    """
    print("timings (ms)")
    print(f"  {'capture_ms':<16} {timings.capture_ms:8.1f}   (excluded from G1)")
    print(f"  {'vad_ms':<16} {timings.vad_ms:8.1f}")
    print(f"  {'transcribe_ms':<16} {timings.transcribe_ms:8.1f}")
    print(
        f"  {'asr_ms':<16} {timings.asr_ms:8.1f}   "
        "<- what the tier check bounds (350 / 700 ms, §7.2)"
    )
    print(
        f"  {'g1_ms':<16} {timings.g1_ms:8.1f}   " "<- G1: 400 ms p50 / 800 ms p95 (§2)"
    )
    print("  postprocess and inject are not built yet (Phase 2a, Phase 3), so")
    print("  g1_ms here is a floor and will grow.")
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
