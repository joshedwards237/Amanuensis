"""The short-band corrections emitter (Phase 4 runbook, lane 4).

Lane 4 asks for ten ordinary short dictations judged on punctuation, and until
2026-09-10 there was no way to start it: `gate_phase3.py --emit-corrections`
exists but its `gate_rows` selects the **long** corpus — ten most recent takes
of 60 s or more, which is the Phase 3 gate's own criterion and the opposite band
by construction. The operator had the dictations and no template, and the only
route was hand-writing JSON out of `manu history` output.

Nothing here touches the operator's real database. Every test builds its own
sqlite file, because the rows in the real one are the verbatim text of somebody's
dictation and a test that reads them is a test that can print them.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from bench_punctuation import (  # noqa: E402
    SHORT_BAND_SECONDS,
    emit_corrections,
)

sys.path.remove(str(ROOT / "scripts"))


def _database(tmp_path: Path, rows: list[tuple[str, str, float, str]]) -> Path:
    path = tmp_path / "history.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE transcripts (id TEXT, started_at TEXT, "
        "duration_seconds REAL, transcript TEXT)"
    )
    connection.executemany("INSERT INTO transcripts VALUES (?, ?, ?, ?)", rows)
    connection.commit()
    connection.close()
    return path


def test_only_the_short_band_is_emitted(tmp_path: Path) -> None:
    """The band is the point. A 74-second take is the long-form case §7.2
    already settled, and mixing one in answers a different question."""
    db = _database(
        tmp_path,
        [
            ("short", "2026-09-10T10:00:00", 9.0, "a short one"),
            ("tooshort", "2026-09-10T10:01:00", 2.0, "hi"),
            ("toolong", "2026-09-10T10:02:00", 74.0, "a long one"),
            ("edgelow", "2026-09-10T10:03:00", 6.0, "at the floor"),
            ("edgehigh", "2026-09-10T10:04:00", 12.0, "at the ceiling"),
        ],
    )
    out = tmp_path / "corrections.json"

    written = emit_corrections(db, out, SHORT_BAND_SECONDS)

    assert written == 3
    assert set(json.loads(out.read_text())) == {"short", "edgelow", "edgehigh"}


def test_since_scopes_the_set_to_one_configuration(tmp_path: Path) -> None:
    """Not convenience. The Phase 3 gate recorded a whole corpus under an
    `initial_prompt` removed from `config.toml` eight minutes after the last
    take, and every take had to be re-recorded. `history.db` carries no config
    digest, so nothing can *detect* the change — scoping the window is the only
    defence there is."""
    db = _database(
        tmp_path,
        [
            ("old", "2026-09-02T10:00:00", 9.0, "before the change"),
            ("new", "2026-09-10T10:00:00", 9.0, "after the change"),
        ],
    )
    out = tmp_path / "corrections.json"

    assert emit_corrections(db, out, SHORT_BAND_SECONDS, since="2026-09-10") == 1
    assert set(json.loads(out.read_text())) == {"new"}


def test_without_since_everything_in_band_is_emitted(tmp_path: Path) -> None:
    """The negative control on the test above. A filter that excluded rows
    unconditionally would pass it while making the tool useless."""
    db = _database(
        tmp_path,
        [
            ("old", "2026-09-02T10:00:00", 9.0, "before"),
            ("new", "2026-09-10T10:00:00", 9.0, "after"),
        ],
    )
    out = tmp_path / "corrections.json"

    assert emit_corrections(db, out, SHORT_BAND_SECONDS) == 2


def test_empty_transcripts_are_not_offered_for_correction(tmp_path: Path) -> None:
    """A guard refusal stores a row with no text. There is nothing to correct
    and offering one invites the operator to type a reference from memory,
    which is the read-aloud failure in a different costume."""
    db = _database(
        tmp_path,
        [
            ("real", "2026-09-10T10:00:00", 9.0, "words"),
            ("refused", "2026-09-10T10:01:00", 9.0, ""),
        ],
    )
    out = tmp_path / "corrections.json"

    assert emit_corrections(db, out, SHORT_BAND_SECONDS) == 1


def test_corrected_is_seeded_with_injected(tmp_path: Path) -> None:
    """The operator is correcting a transcript, not transcribing from scratch,
    and most takes need no edit. An empty field invites retyping the whole
    thing, which introduces differences that are the typist's rather than the
    decoder's — measured at 54.09% against a real 8.59% on 2026-09-02."""
    db = _database(
        tmp_path, [("one", "2026-09-10T10:00:00", 9.0, "what the model heard")]
    )
    out = tmp_path / "corrections.json"

    emit_corrections(db, out, SHORT_BAND_SECONDS)

    entry = json.loads(out.read_text())["one"]
    assert entry["injected"] == "what the model heard"
    assert entry["corrected"] == entry["injected"]
    assert entry["seconds"] == 9.0
    assert entry["started_at"] == "2026-09-10T10:00:00"


def test_the_emitted_shape_is_the_one_the_consumer_reads(tmp_path: Path) -> None:
    """Both ends of the file, in one test. `--corrections` reads `injected` and
    `corrected`; an emitter that wrote `text`/`fixed` would be self-consistent
    and useless, and nothing else here would notice."""
    db = _database(tmp_path, [("one", "2026-09-10T10:00:00", 9.0, "words")])
    out = tmp_path / "corrections.json"

    emit_corrections(db, out, SHORT_BAND_SECONDS)
    entry = json.loads(out.read_text())["one"]

    reference = json.loads(
        (ROOT / "tests" / "fixtures" / "corrections-shape.json").read_text()
    )
    assert set(entry) == set(next(iter(reference.values())))


@pytest.mark.parametrize("band", [SHORT_BAND_SECONDS])
def test_the_band_matches_what_the_runbook_asks_for(
    band: tuple[float, float]
) -> None:
    """The runbook says 8-12 s. The floor is 6 because real dictation does not
    land where a runbook says it will and a 6.1 s take asks the same question;
    the ceiling is the one that carries meaning."""
    assert band[1] == 12.0
    assert band[0] <= 8.0
