"""The §8 persist-before-inject write, and the two paths it takes.

This is the smallest `HistoryStore` that can honour PRD §8: *never lose a
transcript — write to history before injection*. Retention, purge and
`manu history` are Phase 3. What lands here is the write, because Phase 2a is
the first phase in which there is a transcript that could be lost.

Four properties get tests, and each one is a place the PRD argues at length
because getting it wrong is silent:

**The write is unconditional; `retain` governs only what happens afterwards**
(§5.5, objection O10). A guarantee whose mechanism a user can switch off
without being told is not a guarantee. `retain = false` must still persist
before injection — it just persists somewhere it can erase.

**`retain = false` never touches `history.db`** (§5.5, choice-story #5). The
transcript goes to a `0600` file under `pending/` and is unlinked once
injection succeeds. The earlier design was write-then-`DELETE` in SQLite,
which makes "nothing persists" rest on a statement that marks pages free for
reuse. Not writing it to the shared file at all is the weaker claim that is
actually true.

**A failed injection leaves the transcript behind.** That is the entire point
of the ordering, and it is the Phase 2a gate's reject condition. Both paths
are tested for it, because they fail differently: one leaves a row, one leaves
a file.

**A session that never reaches injection leaves nothing** (choice-story #7).
§8's guarantee protects words the user committed to. An empty transcript has
no such claim, and writing one would mean every misfired session lands on disk
before the user has seen it — retained for thirty days by default.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from amanuensis.config import HistoryConfig
from amanuensis.models.session import DictationSession, LatencyBreakdown
from amanuensis.storage.history import HistoryStore


def _session(**overrides: Any) -> DictationSession:
    defaults: dict[str, Any] = {
        "id": "01J0000000000000000000",
        "started_at": datetime(2026, 8, 2, 9, 0, tzinfo=UTC),
        "audio": None,
        "sample_rate": 16000,
        "raw_transcript": "the small conference room",
        "engine": "faster_whisper:tiny.en",
    }
    defaults.update(overrides)
    return DictationSession(**defaults)


def _store(tmp_path: Path, *, retain: bool = True) -> HistoryStore:
    return HistoryStore(HistoryConfig(retain=retain), data_dir=tmp_path)


def _rows(db: Path) -> list[sqlite3.Row]:
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    try:
        return list(connection.execute("SELECT * FROM transcripts"))
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# retain = true — the row lands in history.db
# ---------------------------------------------------------------------------


def test_the_transcript_is_on_disk_before_injection_is_attempted(
    tmp_path: Path,
) -> None:
    """§8's ordering, stated as a test: after `write_pending` returns and
    before anything has injected, the words are recoverable."""
    store = _store(tmp_path)

    store.write_pending(_session())

    rows = _rows(store.db_path)
    assert len(rows) == 1
    assert rows[0]["transcript"] == "the small conference room"
    assert rows[0]["injected"] == 0


def test_the_row_carries_the_engine_that_produced_it(tmp_path: Path) -> None:
    """§5.5 lists engine among what history stores. A transcript whose engine
    is unknown cannot be re-judged when the engine changes."""
    store = _store(tmp_path)

    store.write_pending(_session(engine="faster_whisper:tiny.en"))

    assert _rows(store.db_path)[0]["engine"] == "faster_whisper:tiny.en"


def test_post_processed_text_wins_over_the_raw_transcript(tmp_path: Path) -> None:
    """Both are persisted paths in §6.3: the write runs before post-processing
    on the crash path and after it on the normal one. Whichever exists."""
    store = _store(tmp_path)

    store.write_pending(
        _session(raw_transcript="the small big room", final_text="the big room")
    )

    assert _rows(store.db_path)[0]["transcript"] == "the big room"


def test_the_raw_transcript_is_used_when_post_processing_has_not_run(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)

    store.write_pending(_session(raw_transcript="raw words", final_text=None))

    assert _rows(store.db_path)[0]["transcript"] == "raw words"


def test_a_failed_injection_leaves_the_row_behind(tmp_path: Path) -> None:
    """The Phase 2a gate rejects if a transcript is lost when injection fails.
    Failure is modelled as `mark_injected` never being called."""
    store = _store(tmp_path)
    session = _session()

    store.write_pending(session)
    # injection raises, returns succeeded=False, or the process dies here

    rows = _rows(store.db_path)
    assert len(rows) == 1
    assert rows[0]["injected"] == 0


def test_marking_injected_records_the_stages_the_row_could_not_contain(
    tmp_path: Path,
) -> None:
    """The row is written *before* injection, so `inject_ms` is structurally
    zero at write time — and so is `persist_ms`, which is the duration of the
    write itself. §5.5 says history stores the latency breakdown, which means
    the row has to be completed after the fact rather than left half-empty."""
    store = _store(tmp_path)
    session = _session(timings=LatencyBreakdown(vad_ms=30.0, transcribe_ms=248.0))

    store.write_pending(session)
    session.timings.persist_ms = 1.4
    session.timings.inject_ms = 22.0
    store.mark_injected(session)

    row = _rows(store.db_path)[0]
    assert row["injected"] == 1
    assert row["inject_ms"] == pytest.approx(22.0)
    assert row["persist_ms"] == pytest.approx(1.4)
    assert row["vad_ms"] == pytest.approx(30.0)


def test_writing_the_same_session_twice_leaves_one_row(tmp_path: Path) -> None:
    """A retried injection must not duplicate the user's words in history."""
    store = _store(tmp_path)
    session = _session()

    store.write_pending(session)
    store.write_pending(session)

    assert len(_rows(store.db_path)) == 1


def test_the_database_is_not_readable_by_other_users(tmp_path: Path) -> None:
    """It holds transcripts. §7.6 treats those as the sensitive artefact, and
    the default umask on a shared machine does not."""
    store = _store(tmp_path)

    store.write_pending(_session())

    assert store.db_path.stat().st_mode & 0o077 == 0


# ---------------------------------------------------------------------------
# retain = false — the transcript never enters history.db
# ---------------------------------------------------------------------------


def test_not_retaining_still_persists_before_injection(tmp_path: Path) -> None:
    """§8 is not conditional on `[history] retain` (§5.5, objection O10)."""
    store = _store(tmp_path, retain=False)

    store.write_pending(_session())

    pending = list(store.pending_dir.glob("*.json"))
    assert len(pending) == 1
    assert json.loads(pending[0].read_text())["transcript"] == (
        "the small conference room"
    )


def test_not_retaining_never_creates_the_database(tmp_path: Path) -> None:
    """choice-story #5: a long-lived shared database stops being load-bearing
    for a privacy promise. The claim is only true if the file is never made."""
    store = _store(tmp_path, retain=False)

    store.write_pending(_session())

    assert not store.db_path.exists()


def test_the_pending_transcript_is_not_readable_by_other_users(
    tmp_path: Path,
) -> None:
    """§5.5 specifies 0600 explicitly. A world-readable file under `pending/`
    would be a worse exposure than the database it exists to avoid."""
    store = _store(tmp_path, retain=False)

    store.write_pending(_session())

    pending = next(iter(store.pending_dir.glob("*.json")))
    assert pending.stat().st_mode & 0o077 == 0
    assert store.pending_dir.stat().st_mode & 0o077 == 0


def test_a_successful_injection_unlinks_the_pending_transcript(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path, retain=False)
    session = _session()

    store.write_pending(session)
    store.mark_injected(session)

    assert list(store.pending_dir.glob("*.json")) == []


def test_a_failed_injection_leaves_the_pending_transcript_behind(
    tmp_path: Path,
) -> None:
    """The other half of the gate's reject condition. §5.5 gap 2 names this as
    how orphans accumulate — which is why they get swept, not why they are
    avoided."""
    store = _store(tmp_path, retain=False)

    store.write_pending(_session())

    assert len(list(store.pending_dir.glob("*.json"))) == 1


def test_the_pending_record_carries_enough_to_recover_from(tmp_path: Path) -> None:
    """§5.5 gap 3: `manu history` must be able to surface these in Phase 3.
    A bare transcript with no timestamp is not something a user can act on."""
    store = _store(tmp_path, retain=False)

    store.write_pending(_session())

    record = json.loads(next(iter(store.pending_dir.glob("*.json"))).read_text())
    assert record["id"] == "01J0000000000000000000"
    assert record["started_at"] == "2026-08-02T09:00:00+00:00"
    assert record["engine"] == "faster_whisper:tiny.en"


# ---------------------------------------------------------------------------
# Sessions with no claim on §8
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("transcript", [None, "", "   "])
def test_a_session_with_nothing_to_say_leaves_nothing_on_disk(
    tmp_path: Path, transcript: str | None
) -> None:
    """choice-story #7. §8 protects words the user committed to; an empty
    transcript is a misfire, and writing it means every misfire lands on disk
    before the user has seen it, retained for thirty days by default."""
    store = _store(tmp_path)

    persisted = store.write_pending(
        _session(raw_transcript=transcript, final_text=None)
    )

    assert persisted is False
    assert not store.db_path.exists()


def test_marking_a_session_that_was_never_written_is_not_an_error(
    tmp_path: Path,
) -> None:
    """The caller injects whatever it has and marks unconditionally. Making the
    no-op path raise would push the branch into every call site."""
    store = _store(tmp_path, retain=False)

    store.mark_injected(_session(raw_transcript=""))


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------


def test_the_store_resolves_its_own_directory_when_not_given_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Portability floor item 2 (§7.3): paths resolve through `platformdirs`
    and the `$AMANUENSIS_DATA_DIR` override, never through a literal."""
    monkeypatch.setenv("AMANUENSIS_DATA_DIR", str(tmp_path / "elsewhere"))

    store = HistoryStore(HistoryConfig())

    assert store.db_path == tmp_path / "elsewhere" / "history.db"


# ---------------------------------------------------------------------------
# Phase 2b — the orphan sweep §5.5 gap 2 asks for at daemon start
# ---------------------------------------------------------------------------


def _orphan(store: HistoryStore, session_id: str, age_days: float) -> Path:
    """A pending file left behind by a failed injection, aged by its mtime."""
    store.pending_dir.mkdir(parents=True, exist_ok=True)
    path = store.pending_dir / f"{session_id}.json"
    path.write_text(f'{{"id": "{session_id}", "transcript": "words"}}')
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))
    return path


def test_the_sweep_does_not_delete_a_recoverable_transcript(tmp_path: Path) -> None:
    """The single most important property of this method.

    §5.5 gap 2 asks for a sweep because failed injections accumulate plaintext.
    §8 says the words must survive a failed injection. A sweep that deleted on
    sight would resolve the first by breaking the second — and it would break
    it precisely for the user who set `retain = false`, who has no `history.db`
    row to fall back on.
    """
    store = HistoryStore(HistoryConfig(retain=False), data_dir=tmp_path)
    fresh = _orphan(store, "recent", age_days=1)

    result = store.sweep_pending()

    assert fresh.exists()
    assert result.removed == 0
    assert result.remaining == 1


def test_the_sweep_applies_retain_days(tmp_path: Path) -> None:
    """`retain_days` is the spec's existing expiry knob and there is no reason
    for the pending path to invent a second one."""
    store = HistoryStore(HistoryConfig(retain=False, retain_days=30), data_dir=tmp_path)
    stale = _orphan(store, "old", age_days=31)
    fresh = _orphan(store, "new", age_days=29)

    result = store.sweep_pending()

    assert not stale.exists()
    assert fresh.exists()
    assert result.removed == 1
    assert result.remaining == 1


def test_retain_days_zero_sweeps_everything(tmp_path: Path) -> None:
    """§5.3 admits 0, and the only coherent reading of "retain for zero days"
    is that nothing is kept."""
    store = HistoryStore(HistoryConfig(retain=False, retain_days=0), data_dir=tmp_path)
    _orphan(store, "old", age_days=31)
    _orphan(store, "new", age_days=0)

    result = store.sweep_pending()

    assert result.removed == 2
    assert result.remaining == 0


def test_a_missing_pending_directory_is_not_an_error(tmp_path: Path) -> None:
    """The overwhelmingly common case: `retain = true`, or a daemon that has
    never had an injection fail. Daemon start must not care."""
    store = HistoryStore(HistoryConfig(), data_dir=tmp_path)

    result = store.sweep_pending()

    assert result.removed == 0
    assert result.remaining == 0


def test_the_sweep_ignores_files_it_did_not_write(tmp_path: Path) -> None:
    """A sweep that unlinked by directory rather than by pattern is a sweep
    that deletes whatever a user or another tool put there."""
    store = HistoryStore(HistoryConfig(retain=False, retain_days=0), data_dir=tmp_path)
    _orphan(store, "old", age_days=31)
    stranger = store.pending_dir / "notes.txt"
    stranger.write_text("not ours")

    result = store.sweep_pending()

    assert stranger.exists()
    assert result.removed == 1


def test_every_latency_field_has_a_column(tmp_path: Path) -> None:
    """§5.5 says history stores the latency breakdown. All of it.

    Found by reading a real row at the Phase 2b gate: `restore_ms` was added to
    `LatencyBreakdown` in Phase 2a — as that phase's headline finding — and the
    schema never grew a column for it, so `to_history_row()` emitted it and
    `_insert` silently dropped it. Asserted structurally rather than by naming
    the field, because the failure was a list that stopped being checked
    against the dataclass, and naming one more field would not fix that.

    This is the second instance of AGENTS.md's "an amendment must reach the
    tooling that can regenerate it".
    """
    store = _store(tmp_path)
    store.write_pending(_session())

    columns = set(_rows(store.db_path)[0].keys())
    for field in dataclasses.fields(LatencyBreakdown):
        assert field.name in columns, f"LatencyBreakdown.{field.name} has no column"


def test_the_restore_is_persisted_so_the_exposure_window_can_be_read(
    tmp_path: Path,
) -> None:
    """`restore_ms` is outside G1 and still worth storing: it is how long the
    transcript sat on the system clipboard, which §7.3 argues about at length
    and Phase 2a measured against a real clipboard manager."""
    store = _store(tmp_path)
    session = _session(timings=LatencyBreakdown(restore_ms=155.1))

    store.write_pending(session)

    assert _rows(store.db_path)[0]["restore_ms"] == pytest.approx(155.1)


def test_an_older_database_gains_the_missing_column(tmp_path: Path) -> None:
    """A schema that only ever runs `CREATE TABLE IF NOT EXISTS` cannot add a
    column to a database that already exists — which is every database
    belonging to anyone who used the previous version."""
    store = _store(tmp_path)
    store.write_pending(_session())
    connection = sqlite3.connect(store.db_path)
    connection.execute("ALTER TABLE transcripts DROP COLUMN restore_ms")
    connection.commit()
    connection.close()

    store.write_pending(_session(id="second"))

    assert "restore_ms" in _rows(store.db_path)[0].keys()


def test_marking_injected_records_the_restore_as_well(tmp_path: Path) -> None:
    """`restore_ms` is zero at write time for the same structural reason
    `inject_ms` is — the restore has not happened yet. Completing the row
    without it would store a permanent zero and make the clipboard-exposure
    window unreadable from history, which is the one thing it is stored for."""
    store = _store(tmp_path)
    session = _session()

    store.write_pending(session)
    session.timings.inject_ms = 22.0
    session.timings.restore_ms = 155.1
    store.mark_injected(session)

    assert _rows(store.db_path)[0]["restore_ms"] == pytest.approx(155.1)
