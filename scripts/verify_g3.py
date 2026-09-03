#!/usr/bin/env python3
"""G3 verification — prove the runtime opens no network connection.

PRD §9's Phase 1 gate:

> Run the daemon under packet capture through a full transcribe cycle and
> report whether any network traffic occurred. This is the earliest point a
> model loads, and therefore the earliest point a Hugging Face cache-miss fetch
> would fire. [...] Confirm the model resolves from a local path, not a
> repository ID.

Four checks, and the order is deliberate — the weakest evidence is listed
first so nobody stops reading at it.

**1. Structural.** `resolve_model_path` is called and its result asserted to be
an existing local directory. This is the cheapest check and the only one that
holds on a machine this script never runs on: `FasterWhisperEngine.load` passes
that path to `WhisperModel`, and the resolver uses `local_files_only=True`, so
there is no code path in which the runtime fetches. Everything below is
confirmation that the structure does what it claims.

**2. Sockets.** A full `manu transcribe` cycle runs as a subprocess while
`lsof` polls it for open internet sockets. Zero sockets is a stronger claim
than zero bytes: a connection that opened and sent nothing would still be a G3
violation, because it tells a network observer that Amanuensis is running.

**3. Bytes.** `nettop` attributes byte counts to the process. Unprivileged and
per-process, which is *better* evidence than an interface-wide `tcpdump` for
this question — a busy machine's `tcpdump` output has to be filtered down to
this process anyway, and the filtering is where a mistake hides. `--tcpdump`
still exists for anyone who wants the interface-wide capture; it needs root.

**4. A positive control.** This is the check that makes the other three mean
anything. A measurement that reports "no traffic" is worthless until it has
been shown capable of reporting traffic — and this project has already shipped
one instrument that passed by measuring nothing (`sentinel-integrity-check.sh`
globbed the wrong extension and exited 0 with "OK (0 checked)"). So the same
harness runs a subprocess that deliberately opens a connection, and the run
**fails** if that control comes back clean.

Usage
-----
    .venv/bin/python scripts/verify_g3.py
    .venv/bin/python scripts/verify_g3.py --seconds 5
    sudo .venv/bin/python scripts/verify_g3.py --tcpdump
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

POLL_INTERVAL_S = 0.25


@dataclass
class Observation:
    """What the network looked like around one subprocess."""

    label: str
    sockets: list[str] = field(default_factory=list)
    bytes_in: int = 0
    bytes_out: int = 0
    exit_code: int | None = None
    output: str = ""

    @property
    def saw_traffic(self) -> bool:
        return bool(self.sockets) or self.bytes_in > 0 or self.bytes_out > 0


#: The positive control, defined once because there are now two callers.
#: It **holds the connection open** while it sleeps. An earlier version
#: fetched and exited, which validated the byte meter and left the socket
#: poller unproven — it reported zero sockets on a run that had certainly
#: opened one, because `lsof` samples every 250 ms and a fast HTTP round trip
#: closes in less. A control exercising one of two instruments licenses a clean
#: reading from the other.
CONTROL_SNIPPET: Final = (
    "import socket, time;"
    "s = socket.create_connection(('example.com', 80), timeout=10);"
    "s.sendall(b'GET / HTTP/1.0\\r\\nHost: example.com\\r\\n\\r\\n');"
    "s.recv(1024);"
    "time.sleep(3);"
    "s.close()"
)


def poll_sockets(pid: int, stop: threading.Event, found: list[str]) -> None:
    """Record every internet socket this pid holds, until it exits.

    `lsof -i` on a pid that has none prints nothing and exits 1, which is the
    normal case here — so a non-zero exit is not treated as an error.
    """
    while not stop.is_set():
        result = subprocess.run(
            ["/usr/sbin/lsof", "-nP", "-a", "-i", "-p", str(pid)],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines()[1:]:
            if line and line not in found:
                found.append(line)
        stop.wait(POLL_INTERVAL_S)


def read_bytes(pid: int, samples: int) -> tuple[int, int]:
    """Peak cumulative bytes in/out attributed to `pid` by `nettop`.

    Cumulative rather than delta: nettop reports totals for the process, and
    what this check wants to know is whether the number was ever above zero.
    """
    result = subprocess.run(
        ["/usr/bin/nettop", "-x", "-P", "-L", str(samples), "-p", str(pid)],
        capture_output=True,
        text=True,
    )
    peak_in = peak_out = 0
    for line in result.stdout.splitlines():
        parts = line.split(",")
        if len(parts) < 6 or not parts[1]:
            continue
        try:
            peak_in = max(peak_in, int(parts[4] or 0))
            peak_out = max(peak_out, int(parts[5] or 0))
        except ValueError:
            continue
    return peak_in, peak_out


def find_daemons() -> list[int]:
    """Every running `manu daemon`, by PID.

    Matched on the command line rather than a pidfile because there is no
    pidfile: the daemon's rendezvous point is the IPC socket, and that carries
    no PID (§7.6 keeps the transport's payload to two verbs).

    Returns a **list**, and the caller refuses on more than one rather than
    taking the first. Two daemons share one hotkey — they both inject and both
    persist every dictation — and observing one of two while the other is also
    on the network would be a clean reading of half the product. This project
    has had two running at once, in this phase.

    `pgrep -f` matches its own command line and this process's, so both are
    excluded explicitly; without that, "is a daemon running" answers yes to
    the question being asked.
    """
    result = subprocess.run(
        ["/usr/bin/pgrep", "-f", "manu daemon"],
        capture_output=True,
        text=True,
    )
    mine = {os.getpid(), os.getppid()}
    return [
        int(line)
        for line in result.stdout.split()
        if line.isdigit() and int(line) not in mine
    ]


def observe_pid(label: str, pid: int, seconds: float, samples: int) -> Observation:
    """Watch a process this script did not start, for a fixed window.

    §9 requires the Phase 4 capture against **the assembled product** — tray
    running, socket acceptor listening, a real dictation performed. `observe`
    below cannot do that: it watches only the subprocess it spawns, so a daemon
    running alongside it is a different PID and entirely invisible. That is a
    check passing on an adjacent signal, and the Phase 4 runbook told the
    operator to run it that way before anyone noticed.

    Note what a clean result here does and does not mean. `lsof -i` counts
    **internet** sockets, so the daemon's unix domain socket is correctly not
    among them — a unix socket is not a network socket and cannot be reached
    from off the machine. That is a fact about the transport's design, not
    something this observation establishes.
    """
    observation = Observation(label=label)
    stop = threading.Event()
    watcher = threading.Thread(
        target=poll_sockets, args=(pid, stop, observation.sockets)
    )
    watcher.start()

    meter = {"result": (0, 0)}

    def sample_bytes() -> None:
        meter["result"] = read_bytes(pid, samples)

    metering = threading.Thread(target=sample_bytes)
    metering.start()

    time.sleep(seconds)
    stop.set()
    watcher.join()
    metering.join()

    observation.exit_code = 0
    observation.bytes_in, observation.bytes_out = meter["result"]
    return observation


def observe(label: str, command: Sequence[str], samples: int) -> Observation:
    """Run a command and watch its network behaviour for its whole lifetime."""
    observation = Observation(label=label)
    process = subprocess.Popen(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    stop = threading.Event()
    watcher = threading.Thread(
        target=poll_sockets, args=(process.pid, stop, observation.sockets)
    )
    watcher.start()

    meter = {"result": (0, 0)}

    def sample_bytes() -> None:
        meter["result"] = read_bytes(process.pid, samples)

    metering = threading.Thread(target=sample_bytes)
    metering.start()

    stdout, _ = process.communicate()
    stop.set()
    watcher.join()
    metering.join()

    observation.exit_code = process.returncode
    observation.output = stdout or ""
    observation.bytes_in, observation.bytes_out = meter["result"]
    return observation


def check_model_path() -> tuple[bool, str]:
    """Check 1 — the resolver hands back a directory, not a repository ID."""
    from amanuensis.config import AppConfig
    from amanuensis.engines.faster_whisper import (
        ModelNotAvailableError,
        resolve_device,
        resolve_model_name,
        resolve_model_path,
    )

    config = AppConfig()
    device = resolve_device(config.engine.device)
    model = resolve_model_name(config.engine.model, device)
    try:
        path = resolve_model_path(model)
    except ModelNotAvailableError as exc:
        return False, f"{model}: {exc}"

    if not path.is_dir():
        return False, f"{model} resolved to {path}, which is not a directory"
    if not path.is_absolute():
        return False, f"{model} resolved to a relative path: {path}"
    return True, f"{model} -> {path}"


def report(observation: Observation) -> None:
    print(f"  exit code      {observation.exit_code}")
    print(f"  sockets        {len(observation.sockets)}")
    for socket in observation.sockets:
        print(f"                 {socket}")
    print(f"  bytes in/out   {observation.bytes_in} / {observation.bytes_out}")


def _manu_binary() -> str:
    """Locate the `manu` this interpreter belongs to.

    Was `REPO_ROOT / ".venv" / "bin" / "manu"`, which assumes the virtualenv
    lives inside the checkout. It does not in a `git worktree`: the venv stays
    in the original clone, `.venv` is gitignored so it never follows, and this
    script died with `FileNotFoundError` in the phase whose gate it is.

    `sys.executable` is the interpreter actually running, so its sibling is the
    right console script whether that is a lobby checkout, a worktree, or a venv
    somewhere else entirely. `shutil.which` is the fallback for a system
    install, and a clear error beats a traceback if neither works — the point of
    this script is to be runnable at a gate.
    """
    candidate = Path(sys.executable).parent / "manu"
    if candidate.is_file():
        return str(candidate)

    found = shutil.which("manu")
    if found:
        return found

    raise SystemExit(
        f"cannot find the `manu` console script.\n"
        f"  looked beside this interpreter: {candidate}\n"
        f"  and on PATH.\n"
        f"  Install the package (`pip install -e .`) into the environment you "
        f"are running this with."
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_g3.py",
        description=(
            "Verify goal G3 — no network at runtime — by running a full "
            "transcribe cycle under socket and byte observation, with a "
            "positive control that proves the instrument works."
        ),
    )
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument(
        "--daemon",
        type=float,
        metavar="SECONDS",
        default=0.0,
        help=(
            "observe a already-running `manu daemon` for SECONDS instead of "
            "spawning `manu transcribe`. This is what §9's Phase 4 gate asks "
            "for — the capture against the assembled product, tray drawn and "
            "IPC acceptor listening — and it is not what the default mode "
            "measures: that watches only the subprocess it starts, so a daemon "
            "running alongside it is a different pid and invisible. Dictate "
            "during the window"
        ),
    )
    parser.add_argument(
        "--inject",
        action="store_true",
        help=(
            "observe `manu transcribe --inject` instead. Phase 2a added the "
            "clipboard and the pyobjc bridges to the runtime path, and a "
            "dependency that was not in the tree when G3 was last verified is "
            "exactly what this check exists to catch"
        ),
    )
    parser.add_argument(
        "--tcpdump",
        action="store_true",
        help="also run an interface-wide packet capture (needs root)",
    )
    args = parser.parse_args(argv)

    print("=" * 70)
    print("G3 VERIFICATION — no network at runtime")
    print("=" * 70)

    print()
    print("1. Model resolution (structural)")
    resolved, detail = check_model_path()
    print(f"  {'PASS' if resolved else 'FAIL'}  {detail}")
    if resolved:
        print("  The path is what FasterWhisperEngine.load hands to WhisperModel.")
        print("  resolve_model_path uses local_files_only=True, so a cold cache")
        print("  raises rather than fetching — there is no fetching code path.")

    manu = _manu_binary()
    samples = max(4, int(args.seconds) + 6)

    print()
    print(f"2/3. Full transcribe cycle under observation ({args.seconds:g}s capture)")
    if args.daemon:
        pids = find_daemons()
        if len(pids) > 1:
            raise SystemExit(
                f"{len(pids)} daemons are running: {pids}.\n"
                "  Two share one hotkey and both inject and both persist every\n"
                "  dictation, and observing one while the other is also live\n"
                "  would be a clean reading of half the product. Quit all but\n"
                "  one from its menu-bar icon, then run this again."
            )
        pid = pids[0] if pids else None
        if pid is None:
            raise SystemExit(
                "no running `manu daemon` found.\n"
                "  Start one (the Desktop shortcut, or `manu daemon`), leave the\n"
                "  tray up, then run this again and dictate during the window."
            )
        print(f"\n2/3. The assembled daemon under observation (pid {pid})")
        print(f"     Watching for {args.daemon:g}s — **dictate now**, so the")
        print("     window covers a real hotkey press, decode and injection.")
        subject = observe_pid(
            f"manu daemon (pid {pid})", pid, args.daemon, samples
        )
        print(f"  sockets        {len(subject.sockets)}")
        for line in subject.sockets:
            print(f"                 {line}")
        print(f"  bytes in/out   {subject.bytes_in} / {subject.bytes_out}")
        print()
        print("  NOTE: this observes whatever the daemon did during the window.")
        print("  If you did not dictate, it is a reading of an idle process and")
        print("  §9 asks for the assembled product *working*. Say which, in the")
        print("  gate record.")
        control = observe(
            "a deliberate fetch",
            [sys.executable, "-c", CONTROL_SNIPPET],
            samples,
        )
        print("\n4. Positive control — the instrument must be able to see traffic")
        print(f"  sockets        {len(control.sockets)}")
        print(f"  bytes in/out   {control.bytes_in} / {control.bytes_out}")
        print()
        print("=" * 70)
        if subject.saw_traffic:
            print("G3 (daemon): FAIL — the assembled daemon touched the network")
            return 1
        if not control.saw_traffic:
            print("G3 (daemon): INCONCLUSIVE — the control saw nothing either,")
            print("  so this instrument cannot distinguish silence from blindness.")
            return 1
        print("G3 (daemon): PASS")
        print(f"  0 internet sockets and 0 bytes over {args.daemon:g}s of a running")
        print("  daemon with the tray drawn and the IPC acceptor listening,")
        print(f"  against {len(control.sockets)} socket(s) and "
              f"{control.bytes_in + control.bytes_out} bytes for a control.")
        print()
        print("  Scope, and it must travel with this result (choice-story #11):")
        print("  - Amanuensis's own sockets only. Nothing about the rest of")
        print("    the machine.")
        print("  - The unix socket behind `manu status`/`manu toggle` is not an")
        print("    internet socket and is correctly absent here; that is a property")
        print("    of the transport, not a finding of this capture.")
        print("  - Transcripts transit the system clipboard by default, where")
        print("    another process may capture them. Measured: Maccy 2.7.0 captured")
        print("    every one. That path is invisible to packet capture.")
        return 0

    subject = observe(
        "manu transcribe" + (" --inject" if args.inject else ""),
        [manu, "transcribe", "--seconds", str(args.seconds)]
        + (["--inject"] if args.inject else []),
        samples,
    )
    report(subject)

    print()
    print("4. Positive control — the instrument must be able to see traffic")
    # The control **holds the connection open** while it sleeps. An earlier
    # version fetched and exited, which validated the byte meter and left the
    # socket poller unproven — it reported zero sockets on a run that had
    # certainly opened one, because `lsof` samples every 250 ms and a fast
    # HTTP round trip closes in less. A control that only exercises one of two
    # instruments licenses a clean reading from the other.
    control = observe(
        "control",
        [
            sys.executable,
            "-c",
            CONTROL_SNIPPET,
        ],
        samples=8,
    )
    report(control)

    if args.tcpdump:
        print()
        print("  --tcpdump requested. Run this by hand; it needs root and this")
        print("  script will not ask for your password:")
        print("    sudo /usr/sbin/tcpdump -ni any -c 200 &")
        print(f"    {manu} transcribe --seconds {args.seconds:g}")
        print("  Interface-wide capture also sees every other process on the")
        print("  machine, which is why it is not the primary evidence here.")

    print()
    print("=" * 70)
    failures = []
    if not resolved:
        failures.append("model did not resolve to a local directory")
    if subject.saw_traffic:
        failures.append("the transcribe cycle touched the network")
    if subject.exit_code != 0:
        failures.append(f"the transcribe cycle exited {subject.exit_code}")
    # Each instrument is validated separately. A control that exercises only
    # one of them licenses a clean reading from the other, which is how a
    # measurement that measures nothing passes.
    if not control.sockets:
        failures.append(
            "THE CONTROL SHOWED NO SOCKETS — the lsof poller is not measuring "
            "anything, so the subject's socket count proves nothing"
        )
    if control.bytes_in + control.bytes_out == 0:
        failures.append(
            "THE CONTROL MOVED NO BYTES — the nettop meter is not measuring "
            "anything, so the subject's byte count proves nothing"
        )

    if failures:
        print("G3: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("G3: PASS")
    print(
        f"  {len(subject.sockets)} sockets and "
        f"{subject.bytes_in + subject.bytes_out} bytes for a full transcribe "
        f"cycle,"
    )
    print(
        f"  against {len(control.sockets)} sockets and "
        f"{control.bytes_in + control.bytes_out} bytes for a control that "
        f"deliberately"
    )
    print("  opened one. The instrument works and the runtime is silent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
