#!/usr/bin/env python3
"""Generate the synthetic `history.db` the site export is tested against.

`scripts/export_site_session.py` computes every public number on the landing
page (SITE_PRD §7), and §7.3's regeneration diff is the only thing standing
between that script and the fate `CLAUDE.md`'s own history describes — a
number six documents agree on that nothing re-derives. A diff needs a fixed
input to diff against, and a fixed input that is *real* dictation history is
exactly what SITE_PRD §7.2 rule 1 forbids shipping: the transcript is a
disclosure in the same way the audio is (§10.2), and a committed database is
harder to un-publish than a committed .wav.

So the fixture is invented, and this file is a **generator**, not a checked-in
`.db` — reviewable as a diff, reproducible on any machine, and it is the only
place in the test tree allowed to say what a "collapsed decode" or a
"concurrent pair" looks like at the row level, because SITE_PRD §2.4(c) is a
discrimination table and a table with untested branches is an assertion.

This module writes real rows through `HistoryStore` and `DictationSession` —
the product's own writer — rather than hand-built SQL, for the same reason
`AGENTS.md`'s "call the product's own function" rule exists: a hand-rolled
INSERT is a second implementation of the schema, and its disagreements with
the real one would read as findings about the export instead of about the
generator. The one exception is the same-second duplicate groups (§2.4c),
which need microsecond-level control over `started_at` that the public API's
`datetime.now()`-adjacent flow does not offer — those are built with the
private `HistoryStore._connect()` (same package, same schema constant) so the
DDL is still the product's own.

**What this fixture guarantees is present** (`AGENTS.md`'s rule: state the
guarantee, not just the contents):

- At least 10 clean, eligible rows in the `<= 10s` band (SITE_PRD §2.2 rule 3).
- At least 10 clean, eligible rows in the `7-16s` band (overlapping the above,
  as the real corpus does).
- At least 10 clean, eligible rows in the `>= 60s` band.
- Fewer than 10 rows in `16-60s`, so the "no band exists" path (§2.5) is
  exercised rather than assumed.
- One same-second group of each of the four §2.4(c) discrimination readings:
  duplicate write, parallel-config collision, guard retry, and batch reuse —
  so `export_site_session.py`'s discrimination table has a positive case for
  every branch, not just the drop path the real corpus happened to show.
- Rows with `error IS NOT NULL` and rows with `injected = 0`, so §2.2 rule 1's
  eligibility filter has something to filter.
- Three "hero" / "mid" / "long" sessions carrying `raw_transcript !=
  transcript` and non-empty `fired_entries`, so the export's per-session JSON
  and the widget's raw/processed toggle (§6.5) have a real diff to show
  against a fixture, ahead of SITE_PRD §10.2's real corpus existing.

Usage
-----
    .venv/bin/python tests/fixtures/site/make_fixture.py \\
        --out tests/fixtures/site/history-fixture.db

Run with no arguments it writes to the path above, which is what
`scripts/verify_site_claims.py` reads by default.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from amanuensis.config import HistoryConfig  # noqa: E402
from amanuensis.models.results import GuardOutcome, GuardVerdict  # noqa: E402
from amanuensis.models.session import DictationSession, LatencyBreakdown  # noqa: E402
from amanuensis.storage.history import HistoryStore  # noqa: E402

DEFAULT_OUT: Final = REPO_ROOT / "tests" / "fixtures" / "site" / "history-fixture.db"
ENGINE = "faster_whisper:tiny.en"
EPOCH = datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC)


def _timings(
    *,
    vad_ms: float,
    transcribe_ms: float,
    guard_ms: float = 0.0,
    postprocess_ms: float = 0.4,
    persist_ms: float = 1.1,
    inject_ms: float = 4.0,
    restore_ms: float = 6.0,
    vocab_ms: float = 0.2,
) -> LatencyBreakdown:
    return LatencyBreakdown(
        capture_ms=0.0,  # never read by the export; not worth faking per-row.
        vad_ms=vad_ms,
        vocab_ms=vocab_ms,
        transcribe_ms=transcribe_ms,
        guard_ms=guard_ms,
        postprocess_ms=postprocess_ms,
        persist_ms=persist_ms,
        inject_ms=inject_ms,
        restore_ms=restore_ms,
    )


def _write(
    store: HistoryStore,
    *,
    id_: str,
    started_at: datetime,
    duration_seconds: float,
    raw_transcript: str,
    final_text: str | None = None,
    fired_entries: tuple[str, ...] = (),
    error: str | None = None,
    inject: bool = True,
    guard: GuardVerdict | None = None,
    timings: LatencyBreakdown,
) -> None:
    """Write one row through the real `write_pending` / `mark_injected` path.

    `duration_seconds` cannot be set on `DictationSession` directly — it is
    derived from `len(audio) / sample_rate` — so a fixture row carries a
    silent `float32` buffer of the right length instead of real audio. The
    export never opens the audio; only `duration_seconds()` is read.
    """
    sample_rate = 16000
    audio = np.zeros(int(duration_seconds * sample_rate), dtype=np.float32)
    session = DictationSession(
        id=id_,
        started_at=started_at,
        audio=audio,
        sample_rate=sample_rate,
        raw_transcript=raw_transcript,
        final_text=final_text if final_text is not None else raw_transcript,
        engine=ENGINE,
        timings=timings,
        guard=guard,
        fired_entries=fired_entries,
        error=error,
    )
    wrote = store.write_pending(session)
    if wrote and inject and error is None:
        store.mark_injected(session)


def _band_rows(
    store: HistoryStore,
    *,
    prefix: str,
    start: datetime,
    durations: Sequence[float],
    ms_per_second: float,
    base_ms: float,
) -> None:
    """A run of clean, eligible, single-run rows spanning `durations`."""
    for index, seconds in enumerate(durations):
        transcribe_ms = base_ms + ms_per_second * seconds
        started = start + timedelta(seconds=index * 37)
        _write(
            store,
            id_=f"{prefix}-{index:02d}",
            started_at=started,
            duration_seconds=seconds,
            raw_transcript=f"synthetic dictation number {index} for the {prefix} band",
            fired_entries=("collapse_whitespace",),
            timings=_timings(
                vad_ms=seconds * 0.9,
                transcribe_ms=transcribe_ms,
            ),
            guard=GuardVerdict(
                outcome=GuardOutcome.PASSED,
                retained_seconds=seconds * 0.97,
                coverage=0.94,
            ),
        )


def build(out_path: Path) -> None:
    if out_path.exists():
        out_path.unlink()
    # store_audio stays False throughout this generator, so this should never
    # gain contents — removed defensively in case a future edit flips it.
    audio_dir = out_path.parent / "audio"
    if audio_dir.exists():
        shutil.rmtree(audio_dir)

    store = HistoryStore(
        HistoryConfig(retain=True, store_audio=False), data_dir=out_path.parent
    )
    # HistoryStore derives its own db_path from data_dir/"history.db" — point
    # the caller at the name it actually wrote, since a fixture path other
    # than "history.db" would silently produce the wrong file.
    real_db = store.db_path

    day = EPOCH

    # -- <=10s band: 14 clean rows (n >= 10, SITE_PRD §2.2 rule 3) ----------
    _band_rows(
        store,
        prefix="short",
        start=day,
        durations=[
            2.1,
            3.4,
            4.8,
            5.0,
            5.6,
            6.2,
            6.9,
            7.3,
            8.0,
            8.4,
            8.9,
            9.3,
            9.7,
            9.9,
        ],
        ms_per_second=13.0,
        base_ms=55.0,
    )

    # -- 7-16s band: extend past 10s so the band has its own n >= 10 -------
    # (rows at 7-9.9s above already fall in this band too, as the real corpus
    # does — bands are allowed to overlap; SITE_PRD §2.3 publishes both.)
    _band_rows(
        store,
        prefix="mid-range",
        start=day + timedelta(hours=1),
        durations=[10.5, 11.2, 12.0, 12.8, 13.5, 14.1, 14.9, 15.4, 15.9],
        ms_per_second=13.5,
        base_ms=50.0,
    )

    # -- 16-60s: deliberately fewer than 10, so "no band exists" holds ------
    _band_rows(
        store,
        prefix="gap",
        start=day + timedelta(hours=2),
        durations=[22.0, 35.0, 48.0],
        ms_per_second=14.0,
        base_ms=60.0,
    )

    # -- >=60s band: 11 clean rows -------------------------------------------
    _band_rows(
        store,
        prefix="long",
        start=day + timedelta(hours=3),
        durations=[60.5, 63.0, 66.0, 70.0, 74.5, 78.0, 82.0, 85.5, 88.0, 91.0, 94.0],
        ms_per_second=19.0,
        base_ms=125.0,
    )

    # -- ineligible rows: error set, or never injected ----------------------
    _write(
        store,
        id_="errored-00",
        started_at=day + timedelta(hours=4),
        duration_seconds=6.0,
        # Non-empty so `write_pending` actually inserts a row to exclude —
        # an empty transcript short-circuits the write entirely (§8), which
        # would leave nothing in the fixture for the "error IS NOT NULL"
        # branch of §2.2 rule 1 to filter.
        raw_transcript="partial output before the engine raised",
        error="engine raised RuntimeError",
        inject=False,
        timings=_timings(vad_ms=1.0, transcribe_ms=10.0),
    )
    _write(
        store,
        id_="uninjected-00",
        started_at=day + timedelta(hours=4, minutes=1),
        duration_seconds=8.0,
        raw_transcript="the user released the hotkey and then quit before paste",
        inject=False,
        timings=_timings(vad_ms=7.0, transcribe_ms=110.0),
    )

    # -- collapse incident, for the guard section's own receipt -------------
    _write(
        store,
        id_="collapse-00",
        started_at=day + timedelta(hours=4, minutes=2),
        duration_seconds=30.5,
        raw_transcript="so",
        error=None,
        inject=False,
        guard=GuardVerdict(
            outcome=GuardOutcome.FAILED,
            retained_seconds=29.8,
            coverage=0.083,
            reason="decoded coverage 8.3% below floor; retry did not recover",
            retried=True,
        ),
        timings=_timings(vad_ms=25.0, transcribe_ms=210.0, guard_ms=95.0),
    )

    # -- hero / mid / long demo sessions, with a real rules-pass diff -------
    _write(
        store,
        id_="hero-demo",
        started_at=day + timedelta(hours=5),
        duration_seconds=9.8,
        raw_transcript="  the small conference room needs a  projector bulb",
        final_text="The small conference room needs a projector bulb.",
        fired_entries=("collapse_whitespace", "capitalise_sentences"),
        timings=_timings(vad_ms=6.1, transcribe_ms=134.0, postprocess_ms=0.43),
        guard=GuardVerdict(
            outcome=GuardOutcome.PASSED, retained_seconds=9.5, coverage=0.96
        ),
    )
    _write(
        store,
        id_="mid-demo",
        started_at=day + timedelta(hours=5, minutes=1),
        duration_seconds=29.6,
        raw_transcript=(
            "quarterly numbers are, uh, quarterly numbers are up eleven percent "
            "and — sorry — up twelve percent quarter over quarter"
        ),
        final_text=("Quarterly numbers are up twelve percent quarter over quarter."),
        fired_entries=("collapse_whitespace", "capitalise_sentences"),
        timings=_timings(vad_ms=24.0, transcribe_ms=520.0, postprocess_ms=0.61),
        guard=GuardVerdict(
            outcome=GuardOutcome.PASSED, retained_seconds=28.9, coverage=0.91
        ),
    )
    _write(
        store,
        id_="long-demo",
        started_at=day + timedelta(hours=5, minutes=2),
        duration_seconds=72.4,
        raw_transcript=(
            "this is the long form case where the model has to carry context "
            "across a full minute and change of continuous speech without "
            "any streaming partial results because that is a non goal"
        ),
        final_text=(
            "This is the long-form case where the model has to carry context "
            "across a full minute and change of continuous speech without "
            "any streaming partial results, because that is a non-goal."
        ),
        fired_entries=("collapse_whitespace", "capitalise_sentences"),
        timings=_timings(vad_ms=58.0, transcribe_ms=1420.0, postprocess_ms=0.87),
        guard=GuardVerdict(
            outcome=GuardOutcome.PASSED, retained_seconds=70.1, coverage=0.89
        ),
    )

    # -- §2.4(c) same-second groups, one per discrimination-table row -------
    # Built with the private connect() because these need microsecond-level
    # control over `started_at` that the public write path does not expose.
    connection = store._connect()
    stamp = day + timedelta(hours=6)

    def _raw_insert(**fields: object) -> None:
        columns = ", ".join(fields)
        placeholders = ", ".join("?" for _ in fields)
        connection.execute(
            f"INSERT INTO transcripts ({columns}) VALUES ({placeholders})",
            list(fields.values()),
        )

    common = {
        "engine": ENGINE,
        "error": None,
        "capture_ms": 0.0,
        "vad_ms": 6.0,
        "vocab_ms": 0.2,
        "guard_ms": 0.0,
        "postprocess_ms": 0.4,
        "persist_ms": 1.1,
        "inject_ms": 4.0,
        "restore_ms": 6.0,
        "injected": 1,
    }

    # (a) duplicate write: identical transcript and duration -> dedupe, keep one
    for suffix, micro in (("a", 0), ("b", 11)):
        ts = stamp.replace(microsecond=micro).isoformat()
        _raw_insert(
            id=f"dup-write-{suffix}",
            started_at=ts,
            transcript="the meeting moved to thursday",
            raw_transcript="the meeting moved to thursday",
            duration_seconds=6.0,
            transcribe_ms=88.0,
            guard_outcome=str(GuardOutcome.PASSED),
            guard_coverage=0.95,
            guard_retained_seconds=5.8,
            fired_entries=None,
            **common,
        )

    # (b) parallel configs: differing transcripts, raw present on one only ->
    # drop the whole group. Mirrors the real corpus's 18 dropped rows.
    stamp2 = stamp + timedelta(seconds=90)
    _raw_insert(
        id="parallel-a",
        started_at=stamp2.replace(microsecond=4).isoformat(),
        transcript="the projector needs a new bulb",
        raw_transcript="the projector needs a new bulb",
        duration_seconds=5.0,
        transcribe_ms=200.0,  # inflated by contention
        guard_outcome=str(GuardOutcome.PASSED),
        guard_coverage=0.9,
        guard_retained_seconds=4.8,
        fired_entries=None,
        **common,
    )
    _raw_insert(
        id="parallel-b",
        started_at=stamp2.replace(microsecond=39).isoformat(),
        transcript="the projector needs bulb",
        raw_transcript=None,
        duration_seconds=5.0,
        transcribe_ms=205.0,  # inflated by contention
        guard_outcome=str(GuardOutcome.PASSED),
        guard_coverage=0.88,
        guard_retained_seconds=4.8,
        fired_entries=None,
        **common,
    )

    # (c) a real guard retry sharing a stamp with its own antecedent -> keep
    stamp3 = stamp + timedelta(seconds=180)
    _raw_insert(
        id="retry-a",
        started_at=stamp3.replace(microsecond=2).isoformat(),
        transcript="s",
        raw_transcript="s",
        duration_seconds=12.0,
        transcribe_ms=140.0,
        guard_outcome=str(GuardOutcome.FAILED),
        guard_coverage=0.09,
        guard_retained_seconds=11.6,
        fired_entries=None,
        **common,
    )
    _raw_insert(
        id="retry-b",
        started_at=stamp3.replace(microsecond=17).isoformat(),
        transcript="send the invoice by friday",
        raw_transcript="send the invoice by friday",
        duration_seconds=12.0,
        transcribe_ms=138.0,
        guard_outcome=str(GuardOutcome.RECOVERED),
        guard_coverage=0.93,
        guard_retained_seconds=11.6,
        fired_entries=None,
        **common,
    )

    # (d) batch script reusing a stamp: distinct transcripts, sequential ids,
    # neither a raw/processed mismatch nor a retry outcome -> keep all
    stamp4 = stamp + timedelta(seconds=270)
    for suffix, text, micro in (
        ("batch-01", "first item in the queue", 5),
        ("batch-02", "second item in the queue", 21),
        ("batch-03", "third item in the queue", 44),
    ):
        _raw_insert(
            id=suffix,
            started_at=stamp4.replace(microsecond=micro).isoformat(),
            transcript=text,
            raw_transcript=text,
            duration_seconds=4.0,
            transcribe_ms=70.0,
            guard_outcome=str(GuardOutcome.PASSED),
            guard_coverage=0.95,
            guard_retained_seconds=3.9,
            fired_entries=None,
            **common,
        )

    # Commit before checkpointing: the raw inserts above leave an open write
    # transaction, and `wal_checkpoint(TRUNCATE)` cannot run against one — it
    # fails with "database table is locked" rather than blocking, so the
    # ordering is load-bearing rather than stylistic.
    connection.commit()
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    connection.close()

    print(f"wrote {real_db}")
    if real_db != out_path:
        # data_dir was out_path.parent, so history.db lands beside the name
        # the caller asked for. Move it, and its WAL sidecars if any survived
        # the checkpoint above, to the exact requested path.
        shutil.move(str(real_db), str(out_path))
        for suffix in ("-wal", "-shm"):
            sidecar = real_db.with_name(real_db.name + suffix)
            if sidecar.exists():
                sidecar.unlink()
        print(f"moved to {out_path}")
    if audio_dir.exists():
        shutil.rmtree(audio_dir)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    build(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
