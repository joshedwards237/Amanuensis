#!/usr/bin/env python3
"""The Phase 3 gate: edit rate, the latency ceilings, and the instrument check.

§9's gate is ten real dictations of ≥ 60 seconds, reported on edit rate. This
script computes that from the daemon's own `history.db` rows, so the number
comes from the product measuring itself rather than from a harness re-running
the pipeline — the same discipline `measure_g1.py` follows.

**It is built to fail**, which is not decoration. Objection O4 established that
the gate as §9 wrote it had no reachable failing state: the reject clause
pre-excused proper-noun edit rate on the grounds that it "points at §5.6's
vocabulary mechanisms", and Phase 3 *builds* §5.6; G2's threshold is movable;
and §2's 909 ms prediction covers any G1 miss. Every outcome was
pre-authorised. So this script enforces the three remedies rather than leaving
them to whoever writes the record:

1. **A minimum instrument.** A frozen *empty* `vocabulary.toml` satisfies a
   SHA-256 and measures nothing. The gate refuses unless the dictionary has
   entries, the chain names `vocabulary`, and at least one `[replace]` entry
   actually fired across the set.
2. **The freeze.** The dictionary moves edit rate by construction (dictionary
   objection O6), so entries written against the test set measure nothing. The
   gate refuses if `vocabulary.toml` was modified after the first dictation.
3. **Two derived latency ceilings.** `postprocess_ms` p95 ≤ 5 ms — 100× the
   measured rules floor of 0.0505 ms, and *below* the 12.01 ms p50 that a loop
   of `re.sub` costs at 1000 entries, so it catches the specific regression
   §5.6's 70× measurement warns about. `vocab_ms` p95 ≤ 10 ms, because that is
   the one stage whose cost scales with a file the **user** writes.

**And its own control can fail.** `verify_guard.py`'s first version used a
positive control that reproduced nothing, so it ran its negative control twice
and printed PASS — the fourth instance in this repository of a check that could
not fail. The edit-rate function here is exercised against a pair known to
differ before it is trusted on real data, and a control that produces no edits
exits non-zero.

Workflow
--------
    # 1. Freeze the dictionary, turn on store_audio, then dictate ten times.
    # 2. Emit a template to write your corrections into:
    .venv/bin/python scripts/gate_phase3.py --emit-corrections corrections.json
    # 3. Edit that file: replace each "corrected" with what you MEANT to say.
    # 4. Score it:
    .venv/bin/python scripts/gate_phase3.py --corrections corrections.json

Edit rate is *what fraction of words needed manual correction*, which is not
WER: it is measured against what the user would have typed, not against a
reference transcript, and §2 is explicit that WER is not the product goal.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

#: §9's gate. Ten dictations, each at least a minute of speech.
REQUIRED_DICTATIONS = 10
MIN_SECONDS = 60.0

#: Derived in the spec, not picked. See the module docstring.
POSTPROCESS_P95_CEILING_MS = 5.0
VOCAB_P95_CEILING_MS = 10.0

#: G2's provisional threshold (§2). Confirming or moving it is a legitimate
#: outcome of this gate; moving it without stating the reason is not.
G2_EDIT_RATE = 0.05


@dataclass
class Failure:
    """One reason the gate does not pass. Collected, never raised.

    All of them are reported together: a gate that stops at the first problem
    sends the operator round the loop once per problem, and each loop is ten
    sixty-second dictations.
    """

    code: str
    detail: str


@dataclass
class Corrections:
    rows: dict[str, str] = field(default_factory=dict)


def _words(text: str) -> list[str]:
    return text.split()


def _bare(word: str) -> str:
    return re.sub(r"[^\w%]", "", word).lower()


@dataclass
class EditResult:
    reference_words: int
    edits: int
    classes: dict[str, int]

    @property
    def rate(self) -> float:
        return self.edits / self.reference_words if self.reference_words else 0.0


def classify_edits(
    injected: str, corrected: str, vocabulary_terms: set[str]
) -> EditResult:
    """Word-level edit count between what landed and what the user meant.

    `difflib` rather than `jiwer`: the alignment is the same shape and it costs
    no dependency, which CLAUDE.md asks for. The classification is what §9's
    reject clause needs, and the classes are its vocabulary rather than mine:

    - **punctuation** / **capitalisation** — the classes the rules chain should
      have caught. These are what reject the phase.
    - **vocabulary** — a word the frozen dictionary *covers* and still got
      wrong. §9's clause was amended (objection O4, choice-story #8) to count
      only these among proper nouns: un-excusing the class wholesale would fail
      the gate on the corpus's scope rather than the dictionary's misses.
    - **other** — everything else, which is ASR mistranscription the chain
      cannot reach. `04-rules-only.md` measured this at 87.2% of corpus errors.
    """
    left, right = _words(injected), _words(corrected)
    matcher = difflib.SequenceMatcher(
        a=[_bare(w) for w in left], b=[_bare(w) for w in right], autojunk=False
    )

    classes = {"punctuation": 0, "capitalisation": 0, "vocabulary": 0, "other": 0}
    edits = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Same words modulo punctuation and case — so any difference in the
            # surface forms is exactly a punctuation or capitalisation edit.
            for offset in range(i2 - i1):
                before, after = left[i1 + offset], right[j1 + offset]
                if before == after:
                    continue
                edits += 1
                if before.lower() == after.lower():
                    classes["capitalisation"] += 1
                else:
                    classes["punctuation"] += 1
            continue

        span = max(i2 - i1, j2 - j1)
        edits += span
        for offset in range(j2 - j1):
            wanted = _bare(right[j1 + offset])
            if wanted in vocabulary_terms:
                classes["vocabulary"] += 1
            else:
                classes["other"] += 1
        # A deletion has no right-hand word to classify; charge the remainder to
        # `other` rather than dropping it, or the class counts stop summing to
        # the edit count and the report quietly under-states.
        classes["other"] += max(0, (i2 - i1) - (j2 - j1))

    return EditResult(reference_words=len(right), edits=edits, classes=classes)


def _self_check() -> list[Failure]:
    """The positive control, and it exits non-zero when it catches nothing.

    A check that has never failed has not been tested, and a control that
    reproduces nothing measures the other control twice. Three cases, each
    aimed at one class the reject clause distinguishes.
    """
    problems: list[Failure] = []

    identical = classify_edits("the same words", "the same words", set())
    if identical.edits != 0:
        problems.append(
            Failure("control", f"identical text reported {identical.edits} edits")
        )

    punctuation = classify_edits("hello there", "hello there.", set())
    if punctuation.edits == 0:
        problems.append(
            Failure("control", "a missing full stop produced no edit — see O4")
        )

    vocab = classify_edits(
        "open the breadshoe", "open the spreadsheet", {"spreadsheet"}
    )
    if vocab.edits == 0 or vocab.classes["vocabulary"] == 0:
        problems.append(
            Failure(
                "control",
                "a covered vocabulary miss was not counted as one — the reject "
                "clause cannot fire",
            )
        )
    return problems


def load_rows(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    connection = sqlite3.connect(db_path)
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM transcripts ORDER BY started_at ASC"
        ).fetchall()
    finally:
        connection.close()
    return [dict(row) for row in rows]


def gate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The dictations this gate is about: long ones, most recent first ten."""
    long_enough = [
        row for row in rows if (row["duration_seconds"] or 0.0) >= MIN_SECONDS
    ]
    return long_enough[-REQUIRED_DICTATIONS:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gate_phase3.py")
    parser.add_argument("--corrections", type=Path)
    parser.add_argument("--emit-corrections", type=Path, metavar="PATH")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    from amanuensis.config import load_config
    from amanuensis.postprocess.vocabulary import (
        default_vocabulary_path,
        load_vocabulary,
    )
    from amanuensis.storage.history import HistoryStore
    from amanuensis.tier import percentile

    # The control runs first and unconditionally. An instrument that has not
    # been shown to work must not be used, and must not be usable by passing a
    # flag that skips it.
    control_problems = _self_check()
    if control_problems:
        for problem in control_problems:
            print(f"CONTROL FAILED: {problem.detail}", file=sys.stderr)
        return 2

    config = load_config()
    store = HistoryStore(config.history)
    rows = gate_rows(load_rows(store.db_path))

    if args.emit_corrections is not None:
        template = {
            row["id"]: {
                "started_at": row["started_at"],
                "seconds": round(row["duration_seconds"], 1),
                "injected": row["transcript"],
                "corrected": row["transcript"],
            }
            for row in rows
        }
        args.emit_corrections.write_text(json.dumps(template, indent=2) + "\n")
        print(f"wrote {len(template)} dictation(s) to {args.emit_corrections}")
        print("Edit each 'corrected' to what you MEANT to say, then re-run with")
        print(f"  --corrections {args.emit_corrections}")
        return 0

    failures: list[Failure] = []

    if len(rows) < REQUIRED_DICTATIONS:
        failures.append(
            Failure(
                "corpus",
                f"{len(rows)} dictation(s) of >= {MIN_SECONDS:.0f}s, "
                f"need {REQUIRED_DICTATIONS}",
            )
        )

    # -- the instrument -----------------------------------------------------
    vocabulary_path = default_vocabulary_path()
    vocabulary = load_vocabulary(vocabulary_path)
    digest = (
        hashlib.sha256(vocabulary_path.read_bytes()).hexdigest()
        if vocabulary_path.exists()
        else None
    )
    if vocabulary.entry_count == 0:
        failures.append(
            Failure(
                "instrument",
                "vocabulary.toml has no [replace] entries — a frozen empty "
                "dictionary satisfies a digest and measures nothing (O4)",
            )
        )
    if "vocabulary" not in config.postprocess.chain:
        failures.append(
            Failure(
                "instrument",
                f"[postprocess] chain is {list(config.postprocess.chain)} — the "
                "gate measures the dictionary and this run did not load it",
            )
        )

    fired_any = any((row.get("fired_entries") or "").strip() for row in rows)
    if rows and not fired_any:
        failures.append(
            Failure(
                "instrument",
                "no [replace] entry fired across the set — the dictionary was "
                "loaded and measured nothing",
            )
        )

    # -- the freeze (dictionary objection O6) --------------------------------
    if rows and vocabulary_path.exists():
        edited_at = vocabulary_path.stat().st_mtime
        first = rows[0]["started_at"]
        from datetime import datetime

        try:
            first_at = datetime.fromisoformat(first).timestamp()
        except ValueError:
            first_at = 0.0
        if edited_at > first_at:
            failures.append(
                Failure(
                    "freeze",
                    "vocabulary.toml was modified after the first gate "
                    "dictation — entries written against the test set measure "
                    "nothing (dictionary O6)",
                )
            )

    # -- store_audio ---------------------------------------------------------
    if rows and not list(store.audio_dir.glob("*.wav")):
        failures.append(
            Failure(
                "reproducibility",
                "no stored audio — set [history] store_audio = true before the "
                "gate, or a collapse in this set is unreproducible",
            )
        )

    # -- latency -------------------------------------------------------------
    def series(column: str) -> list[float]:
        return [float(row[column] or 0.0) for row in rows]

    latency: dict[str, float] = {}
    for column in ("postprocess_ms", "vocab_ms", "g1_ms_computed", "transcribe_ms"):
        if column == "g1_ms_computed":
            values = [
                sum(
                    float(row[name] or 0.0)
                    for name in (
                        "vad_ms",
                        "vocab_ms",
                        "transcribe_ms",
                        "guard_ms",
                        "postprocess_ms",
                        "persist_ms",
                        "inject_ms",
                    )
                )
                for row in rows
            ]
        else:
            values = series(column)
        if values:
            latency[f"{column}_p50"] = percentile(values, 50)
            latency[f"{column}_p95"] = percentile(values, 95)

    if latency.get("postprocess_ms_p95", 0.0) > POSTPROCESS_P95_CEILING_MS:
        failures.append(
            Failure(
                "latency",
                f"postprocess_ms p95 {latency['postprocess_ms_p95']:.2f} ms over "
                f"the {POSTPROCESS_P95_CEILING_MS} ms ceiling",
            )
        )
    if latency.get("vocab_ms_p95", 0.0) > VOCAB_P95_CEILING_MS:
        failures.append(
            Failure(
                "latency",
                f"vocab_ms p95 {latency['vocab_ms_p95']:.2f} ms over the "
                f"{VOCAB_P95_CEILING_MS} ms ceiling",
            )
        )

    # -- edit rate -----------------------------------------------------------
    edit: EditResult | None = None
    if args.corrections is not None:
        payload = json.loads(args.corrections.read_text())
        terms = {_bare(value) for value in vocabulary.replacements.values()}
        terms |= {_bare(term) for term in vocabulary.boost_terms}
        for by_app in vocabulary.boost_by_app.values():
            terms |= {_bare(term) for term in by_app}

        totals = EditResult(
            0,
            0,
            {k: 0 for k in ("punctuation", "capitalisation", "vocabulary", "other")},
        )
        for row in rows:
            entry = payload.get(row["id"])
            if entry is None:
                continue
            result = classify_edits(entry["injected"], entry["corrected"], terms)
            totals.reference_words += result.reference_words
            totals.edits += result.edits
            for key, value in result.classes.items():
                totals.classes[key] += value
        edit = totals

        rules_classes = edit.classes["punctuation"] + edit.classes["capitalisation"]
        # §9's amended reject clause. `vocabulary` counts only terms the FROZEN
        # dictionary covers — un-excusing proper nouns wholesale would fail the
        # gate on the corpus's scope rather than the dictionary's misses, and
        # would hand Phase 5 a clause counting the 87.2% of errors no
        # downstream pass can recover (choice-story #8).
        dominant = rules_classes + edit.classes["vocabulary"] > edit.classes["other"]
        if edit.rate > G2_EDIT_RATE and dominant:
            failures.append(
                Failure(
                    "edit-rate",
                    f"edit rate {edit.rate:.1%} over G2's {G2_EDIT_RATE:.0%} and "
                    "dominated by classes this phase ships the fix for "
                    f"(punctuation/capitalisation {rules_classes}, covered "
                    f"vocabulary {edit.classes['vocabulary']}, other "
                    f"{edit.classes['other']})",
                )
            )
    else:
        failures.append(
            Failure(
                "edit-rate",
                "no --corrections file; edit rate is the gate's headline number "
                "and cannot be inferred from history alone",
            )
        )

    report: dict[str, Any] = {
        "dictations": len(rows),
        "vocabulary": {
            "path": str(vocabulary_path),
            "sha256": digest,
            "entries": vocabulary.entry_count,
            "boost_terms": len(vocabulary.boost_terms),
        },
        "chain": list(config.postprocess.chain),
        "latency": {k: round(v, 3) for k, v in latency.items()},
        "guard": [
            {
                "id": row["id"],
                "coverage": row["guard_coverage"],
                "retained_seconds": row["guard_retained_seconds"],
                "outcome": row["guard_outcome"],
            }
            for row in rows
        ],
        "edit_rate": (
            None
            if edit is None
            else {
                "rate": round(edit.rate, 4),
                "edits": edit.edits,
                "reference_words": edit.reference_words,
                "classes": edit.classes,
            }
        ),
        "failures": [{"code": f.code, "detail": f.detail} for f in failures],
        "verdict": "PASS" if not failures else "REJECT",
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"dictations >= {MIN_SECONDS:.0f}s : {len(rows)}")
        print(
            f"vocabulary          : {vocabulary.entry_count} entries  "
            f"sha256 {(digest or '(none)')[:16]}"
        )
        print(f"chain               : {list(config.postprocess.chain)}")
        for key in sorted(latency):
            print(f"  {key:26s} {latency[key]:9.3f} ms")
        print()
        print("guard, every dictation (fired or not — objection O8):")
        for item in report["guard"]:
            coverage = item["coverage"]
            shown = f"{coverage:.1%}" if coverage is not None else "(none)"
            print(
                f"  {item['id'][:12]}  coverage {shown:>8s}  "
                f"retained {item['retained_seconds'] or 0.0:6.1f}s  "
                f"{item['outcome'] or '-'}"
            )
        if edit is not None:
            print()
            print(
                f"edit rate           : {edit.rate:.2%} "
                f"({edit.edits} edits / {edit.reference_words} words)"
            )
            for key, value in edit.classes.items():
                print(f"  {key:18s} {value}")
        print()
        for failure in failures:
            print(f"REJECT [{failure.code}] {failure.detail}", file=sys.stderr)
        print(report["verdict"])

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
