#!/usr/bin/env python3
"""Compute every number the landing page shows, from `history.db`.

The page's whole claim is that its figures are the product's own measurements
rather than assertions, and SITE_PRD §7 is the machinery that makes that true
mechanically instead of by discipline. This script is that machinery. Nothing
on the page is typed by a human: the components read `claims.json` and the
per-session JSON this writes, and CI fails the build if a component contains a
millisecond literal at all.

Three rules here are not style, and each exists because its absence was a
defect in an earlier revision of the spec.

**Sessions come from a committed allowlist, never from a query** (§7.2 rule 1).
`history.db` is the author's real dictation history. A query returns whatever
was last said into the microphone, and `storage/history.py` already ships a
`latest()` helper that is exactly what a hurried implementer reaches for. §10.2
is careful about publishing the audio; the transcript is the same disclosure in
a different encoding, and an earlier revision routed this pipeline straight
through the database holding it with no rule against selecting from it.

**Columns come from an allowlist, never `SELECT *`** (§7.2 rule 2). The schema
grows by migration — `restore_ms`, then five guard columns, then
`raw_transcript`, `fired_entries`, `vocab_ms`. A column added next phase must
not become public because nobody thought about it.

**The band is chosen by the specification, not by the data** (§2.2 rule 5).
PRD §2 binds G1 at a ten-second utterance, so the headline band is `<= 10 s`.
Revision 2 of the spec picked `7-16 s` from five candidates — half the rows and
a p95 47% better — and then attributed it to "a ten-second utterance". That is
the failure the claims register exists to prevent, committed inside the claims
register. `HEADLINE_BAND` is a constant here so the choice cannot be re-made at
render time, and §12.1 asserts it from `claims.json`.

`percentile` is imported from the product rather than reimplemented
--------------------------------------------------------------------
`CLAUDE.md` records that two of the three problems reported from measurement in
Phase 3 were in the harness rather than the product, and names the remedy: call
the product's own function. A reimplemented percentile is a second
implementation whose disagreements read as findings about the product.

The cost, recorded because SITE_PRD §7.2 rule 4 asks for it to be: importing
`amanuensis.tier` pulls `numpy`, `amanuensis.audio.vad` and
`amanuensis.engines.faster_whisper`, and through them `faster-whisper`,
CTranslate2 and the Silero ONNX asset. Installing an ASR runtime in a Pages job
to sort a list is the wrong trade. **The fix is to extract `percentile` into a
dependency-free module that `tier.py` imports**, which is a change to `src/` and
is therefore deferred to the Phase 3 gate rather than made here. Until then this
import is correct and heavy, in that order of priority.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

_REPO_ROOT: Final = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from amanuensis.tier import percentile  # noqa: E402

#: Every column this script is permitted to read. Anything not named here is
#: invisible to the page, including columns that do not exist yet.
COLUMNS: Final[tuple[str, ...]] = (
    "id",
    "started_at",
    "transcript",
    "raw_transcript",
    "fired_entries",
    "duration_seconds",
    "engine",
    "error",
    "injected",
    "capture_ms",
    "vad_ms",
    "transcribe_ms",
    "postprocess_ms",
    "persist_ms",
    "inject_ms",
    "restore_ms",
    "guard_ms",
    "vocab_ms",
    "guard_outcome",
    "guard_coverage",
    "guard_retained_seconds",
)

#: The stages that make up `g1_ms` — hotkey release to text fully present.
#: `capture_ms` is excluded because the time the user spent speaking is theirs;
#: `restore_ms` is excluded because it happens after the text is on screen.
#: The trim stage's column is `vad_ms`: the schema is named after the mechanism,
#: the page after the effect, and the page shows the columns, so the mismatch is
#: carried explicitly rather than quietly renamed.
G1_STAGES: Final[tuple[tuple[str, str], ...]] = (
    ("vad_ms", "trim"),
    ("transcribe_ms", "transcribe"),
    ("guard_ms", "guard"),
    ("postprocess_ms", "postprocess"),
    ("persist_ms", "persist"),
    ("inject_ms", "inject"),
)

#: PRD §2 binds G1 at a ten-second utterance. See the module docstring.
HEADLINE_BAND: Final = "lte_10s"

#: G1's targets, from PRD §2.
TARGET_P50_MS: Final = 400.0
TARGET_P95_MS: Final = 800.0

#: §2.2 rule 3 — a band is publishable only with at least this many rows after
#: exclusions. Below it the page says no band exists rather than showing a
#: percentile over a handful of observations.
MIN_BAND_N: Final = 10

BANDS: Final[tuple[tuple[str, str, float, float], ...]] = (
    ("lte_10s", "≤ 10 s", 0.0, 10.0),
    ("band_7_16s", "7–16 s", 7.0, 16.0),
    ("band_16_60s", "16–60 s", 16.0, 60.0),
    ("gte_60s", "≥ 60 s", 60.0, float("inf")),
)


class ExportError(RuntimeError):
    """Refusal. Always names what was missing and what the caller should do."""


@dataclass(frozen=True)
class GroupVerdict:
    """One same-second group of rows, and what to do with it (§2.4c)."""

    second: str
    reading: str
    ids: tuple[str, ...]
    dropped: tuple[str, ...]


def _rows(db: Path) -> list[dict[str, Any]]:
    if not db.exists():
        raise ExportError(
            f"no database at {db}. This script refuses to invent numbers; "
            "point --db at a real history.db or generate the fixture with "
            "tests/fixtures/site/make_fixture.py."
        )
    connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        connection.row_factory = sqlite3.Row
        columns = ", ".join(COLUMNS)
        cursor = connection.execute(f"SELECT {columns} FROM transcripts")
        rows = [dict(row) for row in cursor]
    finally:
        connection.close()
    if not rows:
        raise ExportError(
            f"{db} has no rows. An empty database produces zeroes that look "
            "like measurements; refusing rather than emitting them."
        )
    return rows


def discriminate(group: list[dict[str, Any]]) -> str:
    """Decide what a same-second group of rows actually is (§2.4c).

    Order matters. A duplicate write and a parallel-configuration collision
    both show two rows with one timestamp; only the transcripts tell them
    apart, and only a retry outcome distinguishes a real product cost from
    contention. Asserting "these are concurrent" from the timestamp alone was
    the objection that produced this table.
    """
    transcripts = {row["transcript"] for row in group}
    durations = {round(float(row["duration_seconds"]), 3) for row in group}
    if len(transcripts) == 1 and len(durations) == 1:
        return "duplicate_write"
    if any(row["guard_outcome"] == "recovered" for row in group):
        return "guard_retry"
    has_raw = {row["raw_transcript"] is not None for row in group}
    if len(has_raw) > 1 and len(transcripts) > 1:
        return "parallel_config"
    return "batch_stamp_reuse"


def partition(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[GroupVerdict]]:
    """Split eligible rows from excluded ones, and say why for each group.

    The rule groups on `started_at` truncated to the second. It is written
    against the stored format deliberately: `started_at` is a microsecond ISO
    string, so an earlier revision's "a row whose started_at is shared with
    another row" was string equality that matched nothing. It would have logged
    "0 dropped" forever while reproducing none of the exclusions the register
    depends on — a rule that cannot fire, inside the mechanism the spec calls
    the whole defence.
    """
    usable = [r for r in rows if r["error"] is None and int(r["injected"]) == 1]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in usable:
        groups[str(row["started_at"])[:19]].append(row)

    eligible: list[dict[str, Any]] = []
    verdicts: list[GroupVerdict] = []
    for second, group in sorted(groups.items()):
        if len(group) == 1:
            eligible.extend(group)
            continue
        reading = discriminate(group)
        ids = tuple(str(r["id"]) for r in group)
        if reading == "parallel_config":
            kept: list[dict[str, Any]] = []
            dropped = ids
        elif reading == "duplicate_write":
            kept = [group[0]]
            dropped = ids[1:]
        else:
            kept = group
            dropped = ()
        eligible.extend(kept)
        verdicts.append(GroupVerdict(second, reading, ids, dropped))
    return eligible, verdicts


def g1_ms(row: dict[str, Any]) -> float:
    return sum(float(row[column] or 0.0) for column, _ in G1_STAGES)


def _band(rows: list[dict[str, Any]], lo: float, hi: float) -> list[float]:
    return [g1_ms(r) for r in rows if lo <= float(r["duration_seconds"]) <= hi]


def build_claims(
    eligible: list[dict[str, Any]], total: int, verdicts: list[GroupVerdict]
) -> dict[str, Any]:
    bands: dict[str, Any] = {}
    for key, label, lo, hi in BANDS:
        samples = _band(eligible, lo, hi)
        entry: dict[str, Any] = {
            "label": label,
            "n": len(samples),
            "min_s": lo,
            "max_s": None if hi == float("inf") else hi,
            "publishable": len(samples) >= MIN_BAND_N,
        }
        if entry["publishable"]:
            entry["p50_ms"] = round(percentile(samples, 50), 1)
            entry["p95_ms"] = round(percentile(samples, 95), 1)
        bands[key] = entry

    if not bands[HEADLINE_BAND]["publishable"]:
        raise ExportError(
            f"the headline band {HEADLINE_BAND!r} has "
            f"{bands[HEADLINE_BAND]['n']} rows, below the {MIN_BAND_N} §2.2 "
            "rule 3 requires. The page cannot lead with a percentile over "
            "fewer observations, and the band is not swapped for a better-"
            "populated one — that is the outcome-selection §2.2 rule 5 forbids."
        )

    postprocess = [
        float(r["postprocess_ms"]) for r in eligible if r["raw_transcript"] is not None
    ]
    dropped = sum(len(v.dropped) for v in verdicts)
    return {
        "_generated_by": (
            "scripts/export_site_session.py" " — do not hand-edit; CI diffs this"
        ),
        "rows_total": total,
        "rows_excluded": dropped,
        "exclusion_log": [
            {
                "group": v.second,
                "reading": v.reading,
                "rows": list(v.ids),
                "dropped": list(v.dropped),
            }
            for v in verdicts
        ],
        "headline_band": HEADLINE_BAND,
        "targets": {"p50_ms": TARGET_P50_MS, "p95_ms": TARGET_P95_MS},
        "bands": bands,
        "postprocess": {
            "n": len(postprocess),
            "p50_ms": round(percentile(postprocess, 50), 4) if postprocess else None,
            "p95_ms": round(percentile(postprocess, 95), 4) if postprocess else None,
        },
    }


def build_session(row: dict[str, Any]) -> dict[str, Any]:
    stages = [
        {
            "key": column.removesuffix("_ms"),
            "label": label,
            "ms": round(float(row[column] or 0.0), 4),
            "in_g1": True,
        }
        for column, label in G1_STAGES
    ]
    stages.append(
        {
            "key": "restore",
            "label": "restore",
            "ms": round(float(row["restore_ms"] or 0.0), 4),
            "in_g1": False,
        }
    )
    fired = str(row["fired_entries"] or "")
    return {
        "id": str(row["id"]),
        "recorded_on": str(row["started_at"])[:10],
        "duration_s": round(float(row["duration_seconds"]), 3),
        "engine": str(row["engine"]),
        "tier": "A",
        "transcript": str(row["transcript"]),
        "raw_transcript": row["raw_transcript"],
        "fired_entries": [e.strip() for e in fired.split(",") if e.strip()],
        "stages": stages,
        "g1_ms": round(g1_ms(row), 1),
        "restore_ms": round(float(row["restore_ms"] or 0.0), 1),
        "guard": {
            "outcome": row["guard_outcome"],
            "coverage": row["guard_coverage"],
            "retained_seconds": row["guard_retained_seconds"],
        },
        "row": {column: row[column] for column in COLUMNS},
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="history.db to read")
    parser.add_argument(
        "--allowlist",
        type=Path,
        required=True,
        help="committed JSON naming the sessions that may be published (§7.2 rule 1)",
    )
    parser.add_argument("--out", type=Path, required=True, help="site/src/data")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        if not args.allowlist.exists():
            raise ExportError(
                f"no allowlist at {args.allowlist}. This script never queries "
                "for a session — publication is a committed decision, not an "
                "ORDER BY. See SITE_PRD §7.2 rule 1."
            )
        allowlist = json.loads(args.allowlist.read_text())
        wanted = [str(entry["id"]) for entry in allowlist["sessions"]]
        if not wanted:
            raise ExportError(f"{args.allowlist} names no sessions.")

        rows = _rows(args.db)
        eligible, verdicts = partition(rows)
        claims = build_claims(eligible, len(rows), verdicts)
        _write(args.out / "claims.json", claims)

        by_id = {str(r["id"]): r for r in rows}
        for session_id in wanted:
            if session_id not in by_id:
                raise ExportError(
                    f"allowlist names {session_id!r}, which is not in {args.db}. "
                    "Refusing rather than skipping: a silently absent hero "
                    "session renders an empty widget that still looks correct."
                )
            _write(
                args.out / "sessions" / f"{session_id}.json",
                build_session(by_id[session_id]),
            )
    except ExportError as exc:
        print(f"export refused: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        head = claims["bands"][HEADLINE_BAND]
        print(f"rows {claims['rows_total']}, excluded {claims['rows_excluded']}")
        for verdict in verdicts:
            print(
                f"  group {verdict.second}  {verdict.reading}  "
                f"dropped {len(verdict.dropped)}"
            )
        print(
            f"headline band {HEADLINE_BAND}: n={head['n']} "
            f"p50={head['p50_ms']} p95={head['p95_ms']}"
        )
        print(f"sessions: {', '.join(wanted)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
