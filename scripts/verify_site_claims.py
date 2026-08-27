#!/usr/bin/env python3
"""Prove the landing page's numbers still come from the database (SITE_PRD §7.3).

What this replaced, and why
---------------------------
An earlier revision defended the page's figures with a CI grep for
`\\d+\\s*ms` in the component tree. It could not fail for the reason it
claimed, on four counts: it fired on the spec's own mandated motion durations
(`150 ms` crossfade, `120 ms` hover), it was escaped by spelling the number
out, by detaching it from its unit (`{P95}ms`), and by splitting the unit
across two elements — and, decisively, **it never inspected a value**. A
`claims.json` typed by hand passed it. The property the page needs is "this
number came from `history.db` via the export"; the property the grep tested was
"this substring is absent from these files".

This check discriminates on the token the product itself writes. It runs the
export against a committed fixture database and compares the output, byte for
byte, with committed golden files. That catches a hand-edited value, a
component reading a stale one, *and* the export silently changing behaviour —
none of which the grep could see.

Two controls, because one control is passed by a constant
----------------------------------------------------------
`CLAUDE.md`'s rule is a negative and a positive, and either alone is satisfied
by an instrument that reads nothing:

- **Negative control.** One row's `transcribe_ms` is perturbed in a scratch
  copy of the fixture. The export MUST produce output that differs from the
  golden. If it does not, this check is not reading the database, and its
  agreement on the clean fixture means nothing.
- **Positive control.** The clean fixture MUST reproduce the golden exactly.
  If it does not, either the export is non-deterministic or the golden is
  stale.

A check that has only ever seen agreement is indistinguishable from a check
that reads nothing. This one is required to see a disagreement it created on
purpose, every single run.
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Final

REPO: Final = Path(__file__).resolve().parent.parent
EXPORT: Final = REPO / "scripts" / "export_site_session.py"
FIXTURE: Final = REPO / "tests" / "fixtures" / "site" / "history-fixture.db"
ALLOWLIST: Final = REPO / "site" / "src" / "data" / "sessions.allowlist.fixture.json"
GOLDEN: Final = REPO / "tests" / "fixtures" / "site" / "golden"


def run_export(db: Path, out: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(EXPORT),
            "--db",
            str(db),
            "--allowlist",
            str(ALLOWLIST),
            "--out",
            str(out),
            "--quiet",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"export failed:\n{result.stderr}")


def tree(root: Path) -> list[Path]:
    return sorted(p.relative_to(root) for p in root.rglob("*.json"))


def differs(a: Path, b: Path) -> list[str]:
    """Every relative path where the two trees disagree, including absences."""
    names = set(tree(a)) | set(tree(b))
    out: list[str] = []
    for name in sorted(names):
        left, right = a / name, b / name
        if not left.exists() or not right.exists():
            out.append(f"{name}: present in only one tree")
        elif not filecmp.cmp(left, right, shallow=False):
            out.append(f"{name}: content differs")
    return out


def perturb(source: Path, destination: Path) -> str:
    """Copy the fixture and change one measurement. Returns the row id."""
    shutil.copy2(source, destination)
    connection = sqlite3.connect(destination)
    try:
        row = connection.execute(
            "SELECT id, transcribe_ms FROM transcripts "
            "WHERE error IS NULL AND injected = 1 AND duration_seconds <= 10 "
            "ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            raise RuntimeError("fixture has no eligible row to perturb")
        row_id, value = str(row[0]), float(row[1])
        connection.execute(
            "UPDATE transcripts SET transcribe_ms = ? WHERE id = ?",
            (value + 500.0, row_id),
        )
        connection.commit()
    finally:
        connection.close()
    return row_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="regenerate the golden files. Review the diff before committing.",
    )
    args = parser.parse_args(argv)

    if not FIXTURE.exists():
        print(
            f"no fixture at {FIXTURE}. Generate it:\n"
            "  python tests/fixtures/site/make_fixture.py",
            file=sys.stderr,
        )
        return 1

    if args.update:
        if GOLDEN.exists():
            shutil.rmtree(GOLDEN)
        run_export(FIXTURE, GOLDEN)
        print(
            f"golden regenerated at {GOLDEN.relative_to(REPO)}"
            " — review the diff before committing"
        )
        return 0

    if not GOLDEN.exists():
        print(f"no golden at {GOLDEN}. Create it with --update.", file=sys.stderr)
        return 1

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)

        # Positive control — the clean fixture must reproduce the golden.
        clean_out = scratch / "clean"
        run_export(FIXTURE, clean_out)
        drift = differs(GOLDEN, clean_out)
        if drift:
            failures.append(
                "POSITIVE CONTROL FAILED — the clean fixture no longer reproduces "
                "the golden. Either the export changed behaviour or the golden is "
                "stale. Files:\n    " + "\n    ".join(drift)
            )
        else:
            print("positive control: clean fixture reproduces the golden")

        # Negative control — a perturbed row must show up as a difference.
        perturbed_db = scratch / "perturbed.db"
        row_id = perturb(FIXTURE, perturbed_db)
        perturbed_out = scratch / "perturbed"
        run_export(perturbed_db, perturbed_out)
        seen = differs(GOLDEN, perturbed_out)
        if not seen:
            failures.append(
                f"NEGATIVE CONTROL FAILED — transcribe_ms was raised by 500 ms on "
                f"row {row_id!r} and the export produced byte-identical output. "
                "This check is not reading the database, so its agreement on the "
                "clean fixture proves nothing."
            )
        else:
            print(
                f"negative control: perturbing {row_id!r} moved "
                f"{len(seen)} file(s), as required"
            )

    if failures:
        print("\n" + "\n\n".join(failures), file=sys.stderr)
        return 1
    print("claims verified: the page's numbers are the database's numbers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
