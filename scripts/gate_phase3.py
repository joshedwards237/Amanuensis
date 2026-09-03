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
from typing import Any, Final

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


#: Buckets, in report order. The split is by WHICH COMPONENT could have fixed
#: the edit, not by what the edit looks like. §9's reject clause is about
#: responsibility — "classes the rules chain should have caught" — and the
#: earlier surface-form split could not express that: it counted an interior
#: sentence break Whisper never emitted as "punctuation", identically to a
#: terminal mark `ensure_terminal_punctuation` genuinely missed.
EDIT_CLASSES: Final[tuple[str, ...]] = (
    "chain_terminal",
    "chain_capital",
    "chain_spacing",
    "vocabulary",
    "decoder_segmentation",
    "decoder_capital",
    "decoder_words",
)

#: The three the phase ships the fix for, plus `vocabulary`, are what §9 weighs.
CHAIN_CLASSES: Final[tuple[str, ...]] = (
    "chain_terminal",
    "chain_capital",
    "chain_spacing",
)

_TERMINALS = ".!?"


def _merge_floating(words: list[str]) -> tuple[list[str], int]:
    """Attach a free-standing punctuation token to the word before it.

    `normalise_punctuation_spacing` operates on the string, so its defect —
    `wait , then` — is invisible to a whitespace tokeniser: the mark arrives as
    its own token that bares to the empty string, and the aligner deletes it
    rather than reporting the mark that moved. Merging first makes the two
    streams comparable and makes the merge itself countable, which is the edit.
    """
    merged: list[str] = []
    count = 0
    for word in words:
        if merged and word and not _bare(word):
            merged[-1] += word
            count += 1
        else:
            merged.append(word)
    return merged, count


def _adds_terminal(before: str, after: str) -> bool:
    return bool((set(after) - set(before)) & set(_TERMINALS))


def classify_edits(
    injected: str,
    corrected: str,
    vocabulary_terms: set[str],
    *,
    terminal_punctuation: bool = True,
) -> EditResult:
    """Word-level edits between what landed and what the user meant, by cause.

    `difflib` rather than `jiwer`: the alignment is the same shape and it costs
    no dependency, which CLAUDE.md asks for.

    **The classes are the rules chain's actual remit, not the shape of the
    difference.** `rules.py` can do four things to punctuation and case: fix
    spacing around a mark, capitalise after an existing terminal mark, append
    the utterance's final mark, and expand spoken commands. It has **no** rule
    that inserts an interior sentence break, none that inserts a comma, and
    none that lowercases anything. So:

    - **chain_terminal** — the utterance ended on a word character and
      `ensure_terminal_punctuation` did not append. Only chargeable when the
      key is on; with `terminal_punctuation = false` the product never
      promised it, and charging it would fail the gate for a configured
      choice.
    - **chain_capital** — a word that opens a sentence *after a mark already
      present* was left lowercase. That is exactly `capitalise_sentences`'
      precondition, so it is exactly what it should have caught.
    - **chain_spacing** — the span's words are identical bare and differ only
      in how punctuation is attached, which is `normalise_punctuation_spacing`.
    - **vocabulary** — a word the FROZEN dictionary covers and still got wrong.
      §9's clause was amended (objection O4, choice-story #8) to count only
      these among proper nouns: un-excusing the class wholesale would fail the
      gate on the corpus's scope rather than the dictionary's misses.
    - **decoder_segmentation** — an interior mark the decoder did not emit. No
      rule in the chain inserts one; knowing where a sentence ends is the LLM
      pass §9 lists as UNRESOLVED.
    - **decoder_capital** — a case change with no chain rule behind it, which
      in practice is the decoder capitalising the first word of its own
      segment mid-sentence. The chain cannot lowercase.
    - **decoder_words** — mistranscription. `04-rules-only.md` measured this at
      87.2% of corpus errors, which no downstream pass can recover.

    Measured 2026-09-01 against the ten-take corpus, the surface split called
    107 of 172 edits "punctuation/capitalisation" and fired the reject clause;
    the responsibility split puts 8 of them inside the chain. Both numbers
    describe the same corrections file.
    """
    left, left_merges = _merge_floating(_words(injected))
    right, right_merges = _merge_floating(_words(corrected))
    matcher = difflib.SequenceMatcher(
        a=[_bare(w) for w in left], b=[_bare(w) for w in right], autojunk=False
    )

    classes = {name: 0 for name in EDIT_CLASSES}
    # A mark that had to be re-attached is one spacing edit, charged before the
    # alignment so the two streams below describe the same words.
    spacing = max(left_merges - right_merges, 0)
    classes["chain_spacing"] += spacing
    edits = spacing
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Same words modulo punctuation and case, so every difference here
            # is a mark or a capital — the question is only whose it was.
            for offset in range(i2 - i1):
                index_l, index_r = i1 + offset, j1 + offset
                before, after = left[index_l], right[index_r]
                if before == after:
                    continue
                edits += 1

                if before.lower() == after.lower():
                    previous = right[index_r - 1] if index_r else ""
                    opens_sentence = index_r == 0 or (
                        bool(previous) and previous[-1] in _TERMINALS
                    )
                    if opens_sentence and after[:1].isupper():
                        classes["chain_capital"] += 1
                    else:
                        classes["decoder_capital"] += 1
                    continue

                if (
                    index_l == len(left) - 1
                    and _adds_terminal(before, after)
                    and terminal_punctuation
                ):
                    classes["chain_terminal"] += 1
                else:
                    classes["decoder_segmentation"] += 1
            continue

        span = max(i2 - i1, j2 - j1)
        edits += span

        # A span whose bare text matches on both sides was NOT a spacing defect,
        # tempting as it looks: measured on the 2026-09-01 corpus it caught
        # `off boarded -> offboarded`, `code base. -> codebase.` and
        # `a K a -> AKA` — word-joining by the decoder, which
        # `normalise_punctuation_spacing` cannot do and never claimed. Charging
        # them to the chain over-counted its misses by 9 of 17. Real spacing
        # defects are free-standing marks and are handled by `_merge_floating`
        # before the alignment; there is nothing left for a span rule to catch.

        for offset in range(j2 - j1):
            wanted = _bare(right[j1 + offset])
            if wanted in vocabulary_terms:
                classes["vocabulary"] += 1
            else:
                classes["decoder_words"] += 1
        # A deletion has no right-hand word to classify; charge the remainder
        # rather than dropping it, or the class counts stop summing to the edit
        # count and the report quietly under-states.
        classes["decoder_words"] += max(0, (i2 - i1) - (j2 - j1))

    return EditResult(reference_words=len(right), edits=edits, classes=classes)


#: `Vocabulary.apply` tags what it fired `replace:<key>`
#: (`postprocess/vocabulary.py`); the rules pass tags its rules bare; and
#: `HistorySession.to_row` joins the two with ", " into one column. The prefix
#: is therefore the only thing in the record that distinguishes the dictionary
#: from everything else in the chain.
REPLACE_PREFIX = "replace:"


def replace_entries_fired(rows: list[dict[str, Any]]) -> bool:
    """Did the *dictionary* act — as opposed to the rules pass acting near it?

    This was `any((row["fired_entries"] or "").strip() for row in rows)` until
    2026-08-18, which is to say it was satisfied by `collapse_whitespace`.
    That rule fires on every transcript faster-whisper has ever produced,
    because the decoder prepends a leading space to all of them. Measured on
    this machine's own `history.db`: `collapse_whitespace` fired on 10 of 10
    recorded dictations and `replace:` fired on none, and the check whose
    failure message reads "the dictionary was loaded and measured nothing"
    reported nothing on all ten.

    So the old predicate could not fail — not "had not failed yet". It was
    true for any completed dictation whether `vocabulary.toml` held eight
    entries or did not exist. This is the eighth check of that shape found in
    this project, and the first one written expressly to be the guard against
    a hollow instrument.

    Split on "," and stripped rather than on ", " exactly: a `[replace]` key
    containing a comma splits into fragments, and the fragment that opens the
    entry still carries the prefix. The discriminator must not depend on the
    user's vocabulary being unimaginative.
    """
    return any(
        entry.strip().startswith(REPLACE_PREFIX)
        for row in rows
        for entry in (row.get("fired_entries") or "").split(",")
    )


def _self_check() -> list[Failure]:
    """The controls, and it exits non-zero when any of them catches nothing.

    A check that has never failed has not been tested, and a control that
    reproduces nothing measures the other control twice. Since 2026-09-01 the
    classes are attributions rather than shapes, so one control per class is not
    enough: an attribution can be wrong by charging the chain for the decoder's
    work, which no positive control detects. Every chain class therefore carries
    a **negative** control — the adjacent decoder-side edit that must NOT land
    in it.
    """
    problems: list[Failure] = []

    def check(
        label: str,
        injected: str,
        corrected: str,
        terms: set[str],
        expected: str,
        forbidden: tuple[str, ...] = (),
    ) -> None:
        result = classify_edits(injected, corrected, terms)
        if result.edits == 0:
            problems.append(Failure("control", f"{label}: produced no edit at all"))
            return
        if result.classes[expected] == 0:
            problems.append(
                Failure("control", f"{label}: nothing landed in {expected}")
            )
        for name in forbidden:
            if result.classes[name]:
                problems.append(
                    Failure(
                        "control",
                        f"{label}: {result.classes[name]} edit(s) wrongly "
                        f"charged to {name}",
                    )
                )

    identical = classify_edits("the same words", "the same words", set())
    if identical.edits != 0:
        problems.append(
            Failure("control", f"identical text reported {identical.edits} edits")
        )

    # POSITIVE — each chain class must be reachable.
    check("terminal mark", "hello there", "hello there.", set(), "chain_terminal")
    check(
        "sentence capital", "one. two things", "one. Two things", set(), "chain_capital"
    )
    check(
        "punctuation spacing", "wait , then go", "wait, then go", set(), "chain_spacing"
    )
    check(
        "covered vocabulary",
        "open the breadshoe",
        "open the spreadsheet",
        {"spreadsheet"},
        "vocabulary",
    )

    # NEGATIVE — the decoder's own misses must not be charged to the chain.
    # Without these the attribution can be uniformly wrong and every positive
    # control still passes, which is the defect this split exists to fix.
    check(
        "interior break is not the chain's",
        "i went home it was late",
        "i went home. It was late",
        set(),
        "decoder_segmentation",
        forbidden=("chain_terminal", "chain_spacing"),
    )
    check(
        "interior comma is not the chain's",
        "first this then that",
        "first this, then that",
        set(),
        "decoder_segmentation",
        forbidden=("chain_terminal", "chain_capital", "chain_spacing"),
    )
    check(
        "mid-sentence capital is not the chain's",
        "the Habitat is ready",
        "the habitat is ready",
        set(),
        "decoder_capital",
        forbidden=("chain_capital",),
    )
    check(
        "mid-sentence proper noun is not the chain's",
        "we use firebase today",
        "we use Firebase today",
        set(),
        "decoder_capital",
        forbidden=("chain_capital",),
    )
    check(
        "word-joining is not the chain's",
        "the code base is old",
        "the codebase is old",
        set(),
        "decoder_words",
        forbidden=("chain_spacing",),
    )
    check(
        "mistranscription is not the chain's",
        "run the demon now",
        "run the daemon now",
        set(),
        "decoder_words",
        forbidden=("chain_terminal", "chain_capital", "chain_spacing", "vocabulary"),
    )

    # And the key that gates the terminal rule must actually gate it: with
    # `terminal_punctuation = false` the product never promised the mark.
    off = classify_edits(
        "hello there", "hello there.", set(), terminal_punctuation=False
    )
    if off.classes["chain_terminal"]:
        problems.append(
            Failure(
                "control",
                "a missing terminal mark was charged to the chain with "
                "terminal_punctuation = false",
            )
        )

    # The two halves of `replace_entries_fired`, because one half alone is
    # passed by a constant: `return False` satisfies the rules-only case and
    # `return True` satisfies the dictionary case. Only the pair pins it.
    #
    # This is the control the 2026-08-18 fix carried and the 2026-09-01
    # re-implementation did not. The predicate was corrected inline, correctly,
    # and left with nothing asserting it stays correct — which is how the
    # original defect got in.
    rules_only = [{"fired_entries": "collapse_whitespace, capitalise_sentences"}]
    if replace_entries_fired(rules_only):
        problems.append(
            Failure(
                "control",
                "the rules pass alone was read as the dictionary firing — the "
                "instrument check is hollow again",
            )
        )

    with_dictionary = [{"fired_entries": "collapse_whitespace, replace:Cloud Code"}]
    if not replace_entries_fired(with_dictionary):
        problems.append(
            Failure(
                "control",
                "a real replace: entry was not seen — the instrument check now "
                "rejects good runs",
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

    if rows and not replace_entries_fired(rows):
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
    # Per gate row, not "any .wav anywhere". Until 2026-08-18 this asked
    # `not list(audio_dir.glob("*.wav"))`, which any single file satisfied —
    # including leftovers from a corpus being discarded, which is precisely the
    # state the disk is in when a gate is re-recorded after a config change.
    # `_sweep_audio` also expires audio on `retain_days` while the rows persist
    # (storage/history.py), so rows-without-audio is the *normal* steady state
    # of a long-lived daemon, not an edge case. Ninth check of that shape found
    # in this project, and the second in this file in one day.
    if rows:
        missing = [
            str(row["id"])[:12]
            for row in rows
            if not (store.audio_dir / f"{row['id']}.wav").exists()
        ]
        if missing:
            failures.append(
                Failure(
                    "reproducibility",
                    f"{len(missing)} of {len(rows)} gate dictations have no "
                    f"stored audio ({', '.join(missing[:4])}"
                    f"{', ...' if len(missing) > 4 else ''}) — set [history] "
                    "store_audio = true before the gate, or a collapse in this "
                    "set is unreproducible",
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

        totals = EditResult(0, 0, {k: 0 for k in EDIT_CLASSES})
        missing: list[str] = []
        for row in rows:
            entry = payload.get(row["id"])
            if entry is None:
                # Silently skipping is how a stale corrections file scores
                # 0 edits over 0 words and prints PASS. Found 2026-09-01 by
                # running the August file against the September takes: every
                # id missed, every class zero, verdict PASS.
                missing.append(str(row["id"])[:12])
                continue
            result = classify_edits(
                entry["injected"],
                entry["corrected"],
                terms,
                terminal_punctuation=config.postprocess.terminal_punctuation,
            )
            totals.reference_words += result.reference_words
            totals.edits += result.edits
            for key, value in result.classes.items():
                totals.classes[key] += value
        edit = totals

        if missing:
            failures.append(
                Failure(
                    "corrections",
                    f"{len(missing)} of {len(rows)} dictations have no entry in "
                    f"{args.corrections.name} ({', '.join(missing[:3])}"
                    f"{', ...' if len(missing) > 3 else ''}) — re-emit it with "
                    "--emit-corrections against the current set",
                )
            )

        chain_classes = sum(edit.classes[name] for name in CHAIN_CLASSES)
        decoder_classes = edit.edits - chain_classes - edit.classes["vocabulary"]
        # §9's amended reject clause, weighed by attribution rather than by the
        # shape of the difference. `vocabulary` counts only terms the FROZEN
        # dictionary covers — un-excusing proper nouns wholesale would fail the
        # gate on the corpus's scope rather than the dictionary's misses, and
        # would hand Phase 5 a clause counting the 87.2% of errors no
        # downstream pass can recover (choice-story #8).
        #
        # The rate condition is unchanged and still stands alone in the report:
        # an edit rate over G2 is stated whether or not the clause fires, so
        # re-attributing edits can never hide it.
        dominant = chain_classes + edit.classes["vocabulary"] > decoder_classes
        if edit.rate > G2_EDIT_RATE and dominant:
            failures.append(
                Failure(
                    "edit-rate",
                    f"edit rate {edit.rate:.1%} over G2's {G2_EDIT_RATE:.0%} and "
                    "dominated by classes this phase ships the fix for "
                    f"(rules chain {chain_classes}, covered vocabulary "
                    f"{edit.classes['vocabulary']}, decoder {decoder_classes})",
                )
            )
        elif edit.rate > G2_EDIT_RATE:
            # Not a failure by §9, and not silent either: G2 is missed and the
            # gate record has to say so and say why it did not reject.
            print(
                f"NOTE: edit rate {edit.rate:.2%} is over G2's "
                f"{G2_EDIT_RATE:.0%}, but {decoder_classes} of {edit.edits} "
                f"edits are decoder-side and outside this phase's remit "
                f"(rules chain {chain_classes}, covered vocabulary "
                f"{edit.classes['vocabulary']}). §9 requires the gate record "
                f"to state this and to confirm or move G2 explicitly.",
                file=sys.stderr,
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
        # objection O11. Nothing in `history.db` records which decode produced
        # a row — `session.engine` is "backend:model" and nothing else — so two
        # corpora recorded either side of a configuration change are
        # indistinguishable in the record, and the operator's memory is the only
        # artefact separating them. That is verbatim the `verify_guard.py`
        # failure §9 already documents: the prompt that collapsed a transcript
        # was described in prose and never written down, so the control
        # reproduced nothing and printed PASS.
        #
        # The prompt is recorded by SHA-256 *and* length rather than verbatim:
        # it is user-authored text that can name people and clients, the gate
        # record is committed, and length is the variable this project measured
        # as load-bearing. `initial_prompt_chars = 0` is the disabling itself.
        "engine": {
            "backend": config.engine.backend,
            "model": config.engine.model,
            "language": config.engine.language,
            "initial_prompt_sha256": hashlib.sha256(
                config.engine.initial_prompt.encode("utf-8")
            ).hexdigest()[:16],
            "initial_prompt_chars": len(config.engine.initial_prompt),
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
        print(
            f"engine              : {config.engine.backend}:"
            f"{config.engine.model}  initial_prompt "
            f"{len(config.engine.initial_prompt)} chars sha "
            f"{hashlib.sha256(config.engine.initial_prompt.encode()).hexdigest()[:12]}"
        )
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
