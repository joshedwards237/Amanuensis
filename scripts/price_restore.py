"""Price the asynchronous clipboard restore from the operator's own history.

D1 asks what the 155 ms buys. It buys worker-thread occupancy between
consecutive dictations, and it costs the serial-worker property that makes
§6.3's focus check meaningful. This measures the benefit side only, from real
rows, so the cost has something to be weighed against.

Contention model, stated so it can be disputed:

    worker_finish(N)      = started_at(N) + duration_seconds(N) + worker_ms(N)
    worker_arrives(N+1)   = started_at(N+1) + duration_seconds(N+1)
    slack                 = worker_arrives(N+1) - worker_finish(N)

worker_ms sums the stages that run ON the worker after capture ends: vad,
transcribe, vocab, postprocess, persist, inject, restore, guard. capture_ms is
excluded because duration_seconds already covers the recording.

If slack >= 0 the worker was idle when the next dictation arrived and the async
restore bought nothing for that pair. If 0 > slack >= -restore_ms, the restore
was the only thing still occupying the worker: those are the pairs the change
would help. If slack < -restore_ms, the worker was busy with real work and
moving the restore off it changes nothing about the wait.

No transcript text is read.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime
from itertools import pairwise
from pathlib import Path

DB = Path.home() / "Library/Application Support/amanuensis/history.db"

WORKER_STAGES = (
    "vad_ms",
    "transcribe_ms",
    "vocab_ms",
    "postprocess_ms",
    "persist_ms",
    "inject_ms",
    "restore_ms",
    "guard_ms",
)


def nearest_rank(values: list[float], pct: float) -> float:
    """Nearest-rank percentile. Never interpolated — HARNESS.md's rule."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    k = max(1, math.ceil(pct / 100.0 * len(ordered)))
    return ordered[k - 1]


def main() -> None:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cols = ", ".join(("started_at", "duration_seconds", *WORKER_STAGES))
    rows = conn.execute(
        f"SELECT {cols} FROM transcripts ORDER BY started_at"
    ).fetchall()
    conn.close()

    parsed = []
    for r in rows:
        start = datetime.fromisoformat(r[0]).timestamp()
        duration = r[1]
        worker_ms = sum(r[2:])
        restore_ms = r[2 + WORKER_STAGES.index("restore_ms")]
        parsed.append((start, duration, worker_ms, restore_ms))

    print(f"rows: {len(parsed)}")
    print(f"range: {rows[0][0][:19]} .. {rows[-1][0][:19]}")

    restores = [p[3] for p in parsed]
    print(
        f"restore_ms      p50 {nearest_rank(restores, 50):7.1f}  "
        f"p95 {nearest_rank(restores, 95):7.1f}  max {max(restores):7.1f}"
    )

    slacks: list[float] = []
    helped = 0
    busy_anyway = 0
    for (s0, d0, w0, r0), (s1, d1, _w1, _r1) in pairwise(parsed):
        worker_finish = s0 + d0 + w0 / 1000.0
        worker_arrives = s1 + d1
        slack = worker_arrives - worker_finish
        slacks.append(slack)
        if slack < 0:
            if slack >= -(r0 / 1000.0):
                helped += 1
            else:
                busy_anyway += 1

    print(f"\nconsecutive pairs: {len(slacks)}")
    print(f"  slack p50  {nearest_rank(slacks, 50):10.1f} s")
    print(f"  slack p05  {nearest_rank(slacks, 5):10.1f} s   (the tight end)")
    print(f"  slack min  {min(slacks):10.1f} s")
    print(f"\n  pairs the async restore would have helped: {helped}")
    print(f"  pairs where the worker was busy with real work anyway: {busy_anyway}")

    tight = sorted(s for s in slacks if s < 60.0)
    print(f"\n  pairs under 60 s apart: {len(tight)}")
    if tight:
        print(f"    tightest five (s): {', '.join(f'{t:.1f}' for t in tight[:5])}")


if __name__ == "__main__":
    main()
