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
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

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

    manu = str(REPO_ROOT / ".venv" / "bin" / "manu")
    samples = max(4, int(args.seconds) + 6)

    print()
    print(f"2/3. Full transcribe cycle under observation ({args.seconds:g}s capture)")
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
            "import socket, time;"
            "s = socket.create_connection(('example.com', 80), timeout=10);"
            "s.sendall(b'GET / HTTP/1.0\\r\\nHost: example.com\\r\\n\\r\\n');"
            "s.recv(1024);"
            "time.sleep(3);"
            "s.close()",
        ],
        samples=8,
    )
    report(control)

    if args.tcpdump:
        print()
        print("  --tcpdump requested. Run this by hand; it needs root and this")
        print("  script will not ask for your password:")
        print(f"    sudo /usr/sbin/tcpdump -ni any -c 200 &")
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
    print(f"  {len(subject.sockets)} sockets and "
          f"{subject.bytes_in + subject.bytes_out} bytes for a full transcribe "
          f"cycle,")
    print(f"  against {len(control.sockets)} sockets and "
          f"{control.bytes_in + control.bytes_out} bytes for a control that "
          f"deliberately")
    print("  opened one. The instrument works and the runtime is silent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
