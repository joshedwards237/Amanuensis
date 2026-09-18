"""Does the pause before a segment boundary predict a sentence mark there?

The Phase 3 gate measured the obvious rule and rejected it: insert `.` at every
segment join whose preceding segment ends on an alphanumeric. 95 insertions, 29
right, **66 invented**, edit rate 9.59% -> 12.35%. Its own post-mortem names why:

> Sizing a rule on recall when it is priced on precision.

70% of the marks the operator added sat on a boundary — recall. The rule runs on
boundaries, of which there are 95, and only 31% want a mark — precision.

**This asks a narrower question that experiment did not.** It fired on every
boundary equally. A first probe (2026-09-17) found the boundaries are not one
population: of 139, **64 have a gap of exactly 0.000 s** and 66 exceed 0.5 s.
Whisper splits for its own reasons as often as it splits at a silence. If the
silent ones are disproportionately the ones that want a mark, a gap-gated rule
is priced differently from the flat one.

Three controls, and none of them is optional.

* **POSITIVE — the flat rule.** Firing on every boundary must reproduce
  something near the gate's 31% precision. If it cannot, this harness is
  measuring a different thing and its other numbers mean nothing.
* **NEGATIVE — shuffled gaps.** The same boundaries with their gaps permuted
  must collapse to the base rate. If a shuffle scores as well as the real thing,
  the gap carries no signal and any apparent result is the threshold sweep
  finding noise.
* **COVERAGE.** Boundaries that cannot be located in the corrected text are
  counted and reported, never silently dropped. A harness that quietly discards
  what it cannot align reports a precision for the easy half of the corpus.

The corpus is `scripts/make_punctuation_corpus.py`'s output. Timings come from
the file it wrote at decode time and **nothing here re-decodes**: the Phase 3
corpus was decoded twice under different configs and the first reading was of a
dead `initial_prompt` nobody had noticed.
"""

from __future__ import annotations

import argparse
import difflib
import json
import random
import re
import statistics
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = REPO / "tests/fixtures/phase3"
TERMINALS = ".!?"
#: Trailing characters that may sit after a sentence mark. `"He left."` ends a
#: sentence; stripping them first is what stops a quoted line reading as
#: unterminated.
_CLOSERS = '"\'’”)]}'


def bare(word: str) -> str:
    return re.sub(r"[^\w']", "", word).lower()


def ends_sentence(word: str) -> bool:
    return word.rstrip(_CLOSERS).endswith(tuple(TERMINALS))


def align(source: list[str], target: list[str]) -> dict[int, int]:
    """Index in `source` -> index in `target`, for words that survived.

    Compared **bare**, so a punctuation or case edit reads as `equal` and the
    pair is aligned rather than showing up as a replacement. That is the whole
    point: the edits being measured are exactly the ones that must not break
    the alignment that finds them.
    """
    matcher = difflib.SequenceMatcher(
        a=[bare(w) for w in source], b=[bare(w) for w in target], autojunk=False
    )
    mapping: dict[int, int] = {}
    for a_start, b_start, size in matcher.get_matching_blocks():
        for offset in range(size):
            mapping[a_start + offset] = b_start + offset
    return mapping


def boundary_rows(
    take: dict[str, Any], corrected: str
) -> tuple[list[dict], int, int]:
    """One row per *insertable* segment boundary: its gap, and whether a mark
    belongs there.

    Returns the rows, the boundaries that could not be located, and the ones
    the decoder had already punctuated — which are excluded rather than scored.
    """
    segments = take["segments"]
    raw_words = take["raw"].split()
    corrected_words = corrected.split()
    mapping = align(raw_words, corrected_words)

    rows: list[dict] = []
    uncovered = 0
    already_marked = 0
    # Where each segment ends, as an index into the raw word list. Counted by
    # walking the segments in order rather than by searching for their text: a
    # segment's text can repeat, and a search would bind the boundary to the
    # wrong instance of it.
    cursor = 0
    ends: list[int] = []
    for segment in segments:
        cursor += len(segment["text"].split())
        ends.append(cursor - 1)

    for index in range(len(segments) - 1):
        raw_index = ends[index]
        gap = segments[index + 1]["start"] - segments[index]["end"]
        target = mapping.get(raw_index)
        if target is None:
            uncovered += 1
            continue
        if ends_sentence(raw_words[raw_index]):
            # **Excluded, matching the gate's own predicate.** Its rule fired
            # only where the preceding segment ended on an alphanumeric — a
            # boundary the decoder already punctuated is a no-op, and counting
            # it as a hit credits the rule for a mark it did not insert. Left
            # in, it inflates precision by a constant that nothing in the
            # output would show.
            already_marked += 1
            continue
        rows.append(
            {"gap": gap, "wants_mark": ends_sentence(corrected_words[target])}
        )
    return rows, uncovered, already_marked


def precision(rows: list[dict], threshold: float) -> tuple[int, int, float]:
    fired = [r for r in rows if r["gap"] >= threshold]
    if not fired:
        return 0, 0, float("nan")
    right = sum(1 for r in fired if r["wants_mark"])
    return len(fired), right, right / len(fired)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    args = parser.parse_args(argv)

    out = args.corpus.expanduser().resolve() / "corpus"
    decode_path = out / "decode.json"
    if not decode_path.exists():
        raise SystemExit(f"no {decode_path} — run make_punctuation_corpus.py first")
    record = json.loads(decode_path.read_text())

    print("config that produced these transcripts:")
    for key, value in record["config"].items():
        print(f"  {key:22} {value}")
    print()

    rows: list[dict] = []
    uncovered = 0
    already_marked = 0
    unedited: list[str] = []
    for slug, take in sorted(record["takes"].items()):
        path = out / f"{slug}.txt"
        if not path.exists():
            raise SystemExit(f"missing {path}")
        corrected = path.read_text().strip()
        if corrected == take["injected"].strip():
            unedited.append(slug)
        take_rows, take_uncovered, take_marked = boundary_rows(take, corrected)
        rows.extend(take_rows)
        uncovered += take_uncovered
        already_marked += take_marked

    if unedited:
        print(f"!! {len(unedited)} transcript(s) are unchanged from the decoder:")
        for slug in unedited:
            print(f"     {slug}")
        print(
            "   An uncorrected transcript contributes boundaries that all read\n"
            "   'no mark wanted', which drags every precision figure down. Either\n"
            "   they are genuinely perfect or they are not done.\n"
        )

    total = len(rows) + uncovered + already_marked
    if not rows:
        raise SystemExit("no boundaries could be located — the alignment failed")
    base = sum(1 for r in rows if r["wants_mark"]) / len(rows)
    print(
        f"boundaries: {total}   scored: {len(rows)}   "
        f"uncovered: {uncovered}   already punctuated: {already_marked}"
    )
    print(f"base rate (boundaries wanting a mark): {base:.1%}")
    gaps = sorted(r["gap"] for r in rows)
    zero = sum(1 for g in gaps if g <= 0.0)
    print(
        f"gaps: exactly 0.000 s {zero}/{len(gaps)}   "
        f"p50 {statistics.median(gaps):.3f}   max {gaps[-1]:.3f}\n"
    )

    print("-- POSITIVE CONTROL: the flat rule, every boundary --")
    fired, right, flat = precision(rows, -1e9)
    print(f"   fired {fired}, correct {right}, precision {flat:.1%}")
    print("   the Phase 3 gate measured 31% on its own corpus")
    if not 0.20 <= flat <= 0.45:
        print("   !! outside a plausible band — treat everything below as suspect")
    print()

    print("-- gap threshold sweep --")
    wanted = sum(1 for r in rows if r["wants_mark"])
    print(f"   {'T (s)':>7} {'fired':>6} {'right':>6} {'prec':>8} {'recall':>8}")
    thresholds = [0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 1.5]
    for t in thresholds:
        n, r, p = precision(rows, t)
        rec = r / wanted if wanted else float("nan")
        print(f"   {t:7.2f} {n:6d} {r:6d} {p:8.1%} {rec:8.1%}")
    print()

    print("-- NEGATIVE CONTROL: gaps shuffled across boundaries --")
    rng = random.Random(20260918)
    gap_values = [r["gap"] for r in rows]
    wants = [r["wants_mark"] for r in rows]
    best_real = max(precision(rows, t)[2] for t in thresholds[1:])
    shuffled: list[float] = []
    for _ in range(500):
        rng.shuffle(gap_values)
        permuted = [
            {"gap": g, "wants_mark": w}
            for g, w in zip(gap_values, wants, strict=True)
        ]
        shuffled.append(max(precision(permuted, t)[2] for t in thresholds[1:]))
    mean_shuffled = statistics.mean(shuffled)
    print(f"   best real precision:     {best_real:.1%}")
    print(f"   mean shuffled precision: {mean_shuffled:.1%}  (500 permutations)")
    ceiling = sorted(shuffled)[int(0.95 * len(shuffled))]
    print(f"   95th pct shuffled:       {ceiling:.1%}")
    verdict = "SIGNAL" if best_real > ceiling else "NO SIGNAL"
    print(f"   VERDICT: {verdict}")
    print(
        "\n   A threshold sweep finds its own best number, so the shuffle is\n"
        "   swept too. Comparing a swept real figure against an unswept\n"
        "   shuffled one would credit the sweep's own optimism to the signal."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
