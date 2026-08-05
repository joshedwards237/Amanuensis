#!/usr/bin/env python3
"""Regenerate the sentinel-record table in AMANUENSIS_PRD.md §14.

Why this exists. §14 indexes the four sentinel records and reports how many
entries each holds and how they are disposed. Those counts were hand-maintained
for one day and went stale three times in that day — every disposition batch
invalidated them, and a stale count is worse than no count because it reads as
current. Choice-story #13 named the fix: generate what is computable.

The counts are computed from each record's YAML frontmatter, not from prose.
This matters: `disposition: pending` appears in objection and story records in
two places, and only one is a real disposition. Frontmatter list-item fields are
indented exactly four spaces; the same token inside an `evidence:` or `claim:`
string is part of a quoted value. A naive grep over the whole file counts both.
In 2026-05 that trap made a fully-resolved record report three pending items.
So: parse the first `---`...`---` block, count lines matching exactly four
leading spaces, and ignore everything else.

Idempotent — running it twice produces the same file. It rewrites only the rows
between the table markers and leaves the surrounding prose alone.

Usage:  python3 scripts/regenerate-sentinel-index.py [--check]
        --check exits 1 if the file would change, for use as a CI constraint.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRD = ROOT / "AMANUENSIS_PRD.md"

BEGIN = "<!-- BEGIN sentinel-index (generated) -->"
END = "<!-- END sentinel-index (generated) -->"

# label, directory, the frontmatter key holding the list
#
# Directories, not filenames. The first version named three exact files, which
# meant a *new* record was invisible to both the table and the --check
# constraint: adding nine pending objections in a second file left the script
# reporting "up to date". A staleness check that cannot see new records is the
# same failure as `sentinel-integrity-check.sh` passing on zero agents — green
# because it looked at nothing. Found 2026-07-31.
RECORD_DIRS = [
    ("Slicing", "docs/superpowers/slices", "slices"),
    ("Objections", "docs/superpowers/objections", "objections"),
    ("Choice stories", "docs/superpowers/stories", "stories"),
]

ESTIMATE = ("Cost estimate", "cost-estimates/2026-07-30-amanuensis-prd-estimate.md")

# Order matters only for display; unknown values are appended as found.
KNOWN_DISPOSITIONS = ["accepted", "merged", "deferred", "revised", "rejected", "pending"]


def frontmatter(path: Path) -> list[str]:
    """Return the lines of the file's first --- ... --- block."""
    lines = path.read_text().splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    out: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        out.append(line)
    return out  # unterminated frontmatter; caller sees what there was


def tally(path: Path) -> tuple[int, dict[str, int]]:
    """Count list items and their dispositions, frontmatter only."""
    entries = 0
    counts: dict[str, int] = {}
    for line in frontmatter(path):
        if re.match(r"^  - id:", line):
            entries += 1
            continue
        # Exactly four leading spaces — deeper indentation is block-scalar
        # content, shallower is a top-level key. Neither is a list-item field.
        m = re.match(r"^ {4}disposition:\s*(\S+)\s*$", line)
        if m:
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    return entries, counts


def is_uncountable(path: Path, entries: int) -> bool:
    """True when the record clearly holds entries the frontmatter does not list.

    A record whose frontmatter carries `objections: 11` as a scalar instead of a
    list parses to zero entries, and the table then reports "0 objections" for a
    file containing eleven. That reads as a feature reviewed and found clean —
    the opposite of what happened.

    This is the same failure the directory scan above was written to fix, one
    layer down: that version could not see new *records*, this one could not see
    entries *inside* a record it could see. Both were green because they looked
    at nothing. Found 2026-08-05, when four self-authored dictionary records all
    reported zero.

    The tell is a scalar `<noun>: <digits>` key in the frontmatter, which is what
    a hand-written record naturally produces. Nothing else is guessed at: a
    record with genuinely no entries has no such key and still reports zero,
    honestly.
    """
    if entries:
        return False
    return any(re.match(r"^\w+:\s*\d+\s*$", line) for line in frontmatter(path))


def describe(entries: int, counts: dict[str, int], noun: str) -> str:
    if not counts:
        return f"{entries} {noun}"
    ordered = [d for d in KNOWN_DISPOSITIONS if d in counts]
    ordered += [d for d in sorted(counts) if d not in KNOWN_DISPOSITIONS]
    if len(ordered) == 1 and ordered[0] != "pending":
        return f"{entries} {noun} — **all {ordered[0]}**"
    parts = ", ".join(f"{counts[d]} {d}" for d in ordered)
    return f"{entries} {noun} — {parts}"


def records_in(directory: Path) -> list[Path]:
    """Every record in a sentinel directory, sorted. `.gitkeep` is not a record."""
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.md") if p.name != ".gitkeep")


def build_table() -> tuple[str, list[str]]:
    """The table, and the records whose entries could not be counted."""
    rows = ["| Record | Path | State |", "|---|---|---|"]
    uncountable: list[str] = []
    for label, reldir, key in RECORD_DIRS:
        found = records_in(ROOT / reldir)
        if not found:
            rows.append(f"| {label} | `{reldir}/` | *missing* |")
            continue
        for path in found:
            rel = path.relative_to(ROOT).as_posix()
            # Disambiguate only when a directory holds more than one record, so
            # the common single-record case reads exactly as it did before.
            name = label if len(found) == 1 else f"{label} — `{path.stem}`"
            entries, counts = tally(path)
            if is_uncountable(path, entries):
                uncountable.append(rel)
                state = f"**UNCOUNTABLE** — {key} not listed in frontmatter"
            else:
                state = describe(entries, counts, key)
            rows.append(f"| {name} | `{rel}` | {state} |")
    label, rel = ESTIMATE
    state = "not adjudicable" if (ROOT / rel).exists() else "*missing*"
    rows.append(f"| {label} | `{rel}` | {state} |")
    return "\n".join(rows), uncountable


def main() -> int:
    check = "--check" in sys.argv
    text = PRD.read_text()
    if BEGIN not in text or END not in text:
        print(f"error: markers not found in {PRD.name}", file=sys.stderr)
        return 2
    table, uncountable = build_table()
    new = re.sub(
        re.escape(BEGIN) + r".*?" + re.escape(END),
        BEGIN + "\n" + table + "\n" + END,
        text,
        flags=re.DOTALL,
    )
    if new != text:
        if check:
            print(
                "sentinel index: STALE — run scripts/regenerate-sentinel-index.py",
                file=sys.stderr,
            )
            return 1
        PRD.write_text(new)
        print("sentinel index: regenerated")
    else:
        print("sentinel index: up to date")

    # Written last and separately from staleness: an uncountable record makes the
    # table *wrong*, not out of date, and regenerating does not fix it. Failing
    # here rather than only under --check means the person who runs the script by
    # hand is told too, instead of finding out from CI.
    if uncountable:
        for rel in uncountable:
            print(
                f"sentinel index: UNCOUNTABLE — {rel} has a scalar count in its "
                "frontmatter, not a list of entries; the table cannot report it",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
