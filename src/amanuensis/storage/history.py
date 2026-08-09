"""The §8 write that has to happen before anything is injected.

PRD §8 states the guarantee in six words — *never lose a transcript* — and
then states the mechanism, which is an ordering: persist first, inject second.
This module is the persist half. It arrives in Phase 2a rather than Phase 3
with the rest of history because Phase 2a is the first phase in which there is
a transcript that can be lost, and an injection path that structurally cannot
honour §8 is not a scheduling detail (PRD §9, slicing record S4).

What is deliberately *not* here: retention sweeps, `retain_days`, `manu
history`, purge, search. Those are Phase 3. This is `write_pending` and
`mark_injected`, which is the smallest surface that makes the guarantee true.

**Two storage paths, and `retain` picks between them — it never disables the
write.** §5.5 is emphatic about this and the reasoning is worth restating: a
guarantee whose mechanism a user can switch off without being told is not a
guarantee, and the user most likely to set `retain = false` is §4's
privacy-motivated primary user, while the user who most needs the recovery
path is §4's secondary user with a motor impairment. Neither would have been
told the trade existed.

- `retain = true` writes a row to `history.db` and leaves it there.
- `retain = false` writes a `0600` JSON file under `pending/` and unlinks it
  once injection succeeds. It never opens `history.db` at all.

The second path exists because of choice-story #5. The earlier design was
write-then-`DELETE` in SQLite, which makes "nothing persists" a privacy claim
resting on a statement that marks pages free for reuse — `secure_delete`,
`VACUUM` and WAL checkpointing all bear on whether the bytes are actually
gone, and specifying three of those correctly is more work than not writing to
the shared file in the first place. What the temp file buys is narrower than
erasure and still worth having: a long-lived shared database stops being
load-bearing for a privacy promise. §5.5 says plainly that Amanuensis does not
claim secure erasure, and this module does not either.

**Both paths leave the transcript behind when injection fails.** That is the
entire point of the ordering and it is the Phase 2a gate's reject condition.
`mark_injected` is called only on success, so failure is the absence of a call
rather than a branch — the case the guarantee protects is the one that needs
no code.

**The row is completed after the fact, not written half-empty.** A row written
before injection cannot contain `inject_ms`, and cannot contain `persist_ms`
either, since that is the duration of the write producing the row. §5.5 says
history stores the latency breakdown, so `mark_injected` fills them in. The
alternative — persisting the timings only after injection — would put the
transcript on disk twice or not at all, which is the ordering §8 forbids.

**Nothing with an empty transcript is written** (choice-story #7). §8 protects
words the user committed to; a misfire has no such claim, and writing one
would mean every aborted session lands on disk before the user has seen it,
retained for thirty days by default.

**Orphans expire; they are not deleted on sight** (Phase 2b, §5.5 gap 2).
Every failed injection under `retain = false` leaves a plaintext file behind,
and §5.5 asks for a sweep at daemon start. What §5.5 does *not* say is what
sweeping means, and the two readings point opposite ways: unlinking every
pending file at start would close the accumulation gap by deleting the exact
transcript §8 wrote to survive a failed injection — for the one user who has no
`history.db` row to fall back on. So `sweep_pending` applies `retain_days`,
which is §5.3's existing expiry knob and needs no second one invented beside
it. `retain_days = 0` still means nothing is kept.

`manu history` surfaces these files in Phase 3 (§5.5 gap 3). Until then a user
whose injection failed is told the path on stderr and nothing enumerates them,
which is stated in the gate record rather than left for someone to find.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import wave
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np

from amanuensis.config import HistoryConfig, default_data_dir
from amanuensis.models.session import DictationSession

__all__ = ["HistoryStore", "StoredTranscript", "SweepResult"]

_SECONDS_PER_DAY: Final = 86400.0


@dataclass(frozen=True, slots=True)
class SweepResult:
    """What the daemon-start sweep did, so the daemon can say so.

    `remaining` is the interesting number and the reason this is not a bare
    count of deletions: it is how many transcripts the user still has waiting
    from failed injections, and until `manu history` surfaces them (Phase 3)
    the daemon's start-up line is the only thing that mentions they exist.
    """

    removed: int
    remaining: int
    failed: int = 0


@dataclass(frozen=True, slots=True)
class StoredTranscript:
    """One transcript, read back. The smallest thing `manu history --last` needs.

    Deliberately not the whole row. This exists so a user can retrieve words
    the §5.7 guard refused to inject, and the read surface a Phase 2b follow-up
    is entitled to open is the one that discharges that — search, filtering and
    purge remain Phase 3.
    """

    id: str
    started_at: str
    transcript: str
    injected: bool
    guard_outcome: str | None = None
    guard_reason: str | None = None


#: Owner-only. The database and the pending files both hold transcripts, which
#: §7.6 treats as the sensitive artefact and the default umask does not.
_FILE_MODE: Final = 0o600
_DIR_MODE: Final = 0o700

#: Enumerated rather than derived from the row dict. The row's shape is a
#: model concern and the table's is a storage concern; letting one drive the
#: other means a field added to `LatencyBreakdown` silently breaks the INSERT
#: at runtime instead of loudly at review time.
_COLUMNS: Final = (
    "id",
    "started_at",
    "transcript",
    "raw_transcript",
    "duration_seconds",
    "engine",
    "error",
    "guard_outcome",
    "guard_coverage",
    "guard_retained_seconds",
    "fired_entries",
    "capture_ms",
    "vad_ms",
    "vocab_ms",
    "transcribe_ms",
    "guard_ms",
    "postprocess_ms",
    "persist_ms",
    "inject_ms",
    "restore_ms",
)

_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS transcripts (
    id               TEXT PRIMARY KEY,
    started_at       TEXT    NOT NULL,
    transcript       TEXT    NOT NULL,
    raw_transcript   TEXT,
    duration_seconds REAL    NOT NULL,
    engine           TEXT    NOT NULL DEFAULT '',
    error            TEXT,
    guard_outcome    TEXT,
    guard_coverage   REAL,
    guard_retained_seconds REAL,
    fired_entries   TEXT,
    capture_ms       REAL    NOT NULL DEFAULT 0,
    vad_ms           REAL    NOT NULL DEFAULT 0,
    vocab_ms         REAL    NOT NULL DEFAULT 0,
    transcribe_ms    REAL    NOT NULL DEFAULT 0,
    guard_ms         REAL    NOT NULL DEFAULT 0,
    postprocess_ms   REAL    NOT NULL DEFAULT 0,
    persist_ms       REAL    NOT NULL DEFAULT 0,
    inject_ms        REAL    NOT NULL DEFAULT 0,
    restore_ms       REAL    NOT NULL DEFAULT 0,
    injected         INTEGER NOT NULL DEFAULT 0
)
"""


#: Columns added after the first release of the schema, with the DDL that adds
#: them. `CREATE TABLE IF NOT EXISTS` cannot widen a table that already exists,
#: which is every table belonging to anyone who has already used the product —
#: so a new field in `LatencyBreakdown` needs a row here as well as a line in
#: `_SCHEMA`, or it lands only for users with no history.
#:
#: `restore_ms` is the first entry and is here because it was missed: Phase 2a
#: added the field as that phase's headline finding and the schema never grew
#: the column, so `to_history_row()` emitted the value and `_insert` dropped
#: it. Found by reading a real row at the Phase 2b gate.
#: The §5.7 columns are nullable with no default, deliberately. A row written
#: before the guard existed has no verdict, and `NULL` says so; a `0` would
#: claim the decoder covered none of the audio, which is the catastrophe the
#: guard exists to report.
_MIGRATIONS: Final[tuple[tuple[str, str], ...]] = (
    (
        "restore_ms",
        "ALTER TABLE transcripts ADD COLUMN restore_ms REAL NOT NULL DEFAULT 0",
    ),
    (
        "guard_ms",
        "ALTER TABLE transcripts ADD COLUMN guard_ms REAL NOT NULL DEFAULT 0",
    ),
    (
        "guard_outcome",
        "ALTER TABLE transcripts ADD COLUMN guard_outcome TEXT",
    ),
    (
        "guard_coverage",
        "ALTER TABLE transcripts ADD COLUMN guard_coverage REAL",
    ),
    (
        "guard_retained_seconds",
        "ALTER TABLE transcripts ADD COLUMN guard_retained_seconds REAL",
    ),
    # Nullable with no default, like the guard columns and for the same reason:
    # a row written before Phase 3 has no separate raw text, and `NULL` says so
    # where `''` would claim the decoder produced nothing.
    (
        "raw_transcript",
        "ALTER TABLE transcripts ADD COLUMN raw_transcript TEXT",
    ),
    (
        "fired_entries",
        "ALTER TABLE transcripts ADD COLUMN fired_entries TEXT",
    ),
    (
        "vocab_ms",
        "ALTER TABLE transcripts ADD COLUMN vocab_ms REAL NOT NULL DEFAULT 0",
    ),
)


def _add_missing_columns(connection: sqlite3.Connection) -> None:
    """Widen an existing table to the current schema. Idempotent."""
    present = {row[1] for row in connection.execute("PRAGMA table_info(transcripts)")}
    for column, statement in _MIGRATIONS:
        if column not in present:
            connection.execute(statement)


class HistoryStore:
    """Persist a transcript before it is injected, and complete it after.

    Takes the `[history]` slice of the config rather than the whole thing
    (§6.3, choice-story #3), so it structurally cannot read `[injection]` —
    which matters here more than most places, because the two are adjacent in
    the one ordering §8 cares about.
    """

    def __init__(self, config: HistoryConfig, data_dir: Path | None = None) -> None:
        self._config = config
        # Resolved once at construction rather than per call: `$AMANUENSIS_
        # DATA_DIR` changing mid-process would split one session's write from
        # its own unlink.
        self._data_dir = data_dir if data_dir is not None else default_data_dir()

    @property
    def db_path(self) -> Path:
        return self._data_dir / "history.db"

    @property
    def pending_dir(self) -> Path:
        return self._data_dir / "pending"

    @property
    def audio_dir(self) -> Path:
        """Where `store_audio` puts WAVs. Empty and absent unless enabled."""
        return self._data_dir / "audio"

    # -- the two operations ------------------------------------------------

    def write_pending(self, session: DictationSession) -> bool:
        """Put the transcript somewhere recoverable. Call before injecting.

        Returns False when the session had nothing worth keeping, so a caller
        can say "nothing was captured" rather than reporting a successful
        write of an empty string.
        """
        row = session.to_history_row()
        transcript = row.get("transcript")
        if not isinstance(transcript, str) or not transcript.strip():
            return False

        if self._config.retain:
            self._insert(row)
            self._write_audio(session)
        else:
            self._write_pending_file(row)
        return True

    def latest(self) -> StoredTranscript | None:
        """The most recently started transcript, on whichever path is in use.

        Exists because of objection O2. §5.7 refuses to inject a transcript the
        decoder destroyed, and §8's write makes the words *present* rather than
        *reachable* — `manu history` is Phase 3, so before this the refused
        transcript went somewhere no shipped command could show it. A guarantee
        mechanically preserved and practically unreachable is the failure §5.5
        already documented once.

        Both paths are searched rather than the configured one, because a user
        who has just changed `retain` is precisely the user who cannot find
        their last transcript.
        """
        return max(
            (
                candidate
                for candidate in (self._latest_row(), self._latest_pending())
                if candidate is not None
            ),
            key=lambda found: found.started_at,
            default=None,
        )

    def _latest_row(self) -> StoredTranscript | None:
        if not self.db_path.exists():
            return None
        with self._transaction() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT id, started_at, transcript, injected, guard_outcome "
                "FROM transcripts ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return StoredTranscript(
            id=row["id"],
            started_at=row["started_at"],
            transcript=row["transcript"],
            injected=bool(row["injected"]),
            guard_outcome=row["guard_outcome"],
        )

    def _latest_pending(self) -> StoredTranscript | None:
        """The newest orphan under `pending/`, which is by definition uninjected.

        A pending file exists only until injection succeeds, so anything found
        here is a transcript the user did not receive — the case this method
        exists for.
        """
        if not self.pending_dir.exists():
            return None
        newest: StoredTranscript | None = None
        for path in self.pending_dir.glob("*.json"):
            try:
                row = json.loads(path.read_text())
            except (OSError, ValueError):
                # A half-written or hand-edited file must not stop the user
                # reading the transcripts that are intact.
                continue
            found = StoredTranscript(
                id=str(row.get("id", path.stem)),
                started_at=str(row.get("started_at", "")),
                transcript=str(row.get("transcript", "")),
                injected=False,
                guard_outcome=row.get("guard_outcome"),
            )
            if newest is None or found.started_at > newest.started_at:
                newest = found
        return newest

    def mark_injected(self, session: DictationSession) -> None:
        """The user has their words. Complete the row, or erase the file.

        Safe to call for a session that was never written — the caller injects
        whatever it has and marks unconditionally, and pushing the branch out
        to every call site is how one call site forgets it.
        """
        if self._config.retain:
            self._complete(session)
        else:
            self._pending_path(session.id).unlink(missing_ok=True)

    def sweep_pending(self) -> SweepResult:
        """Expire orphaned pending files. Call at daemon start (§5.5 gap 2).

        An orphan is a transcript that was written before injection and never
        unlinked, because the injection failed or the process died between the
        two. They are plaintext, they are `0600`, and under `retain = false`
        they accumulate — which is the gap §5.5 asks to close.

        **It closes by expiry, not by deletion.** Unlinking on sight would
        delete the words §8 wrote precisely so a failed injection would not
        cost them, and it would do it to the user who has no `history.db` row
        to recover from. `retain_days` is what §5.3 already means by "how long
        transcripts are kept", so it governs here too.

        Errors are counted, not raised. This runs at daemon start, and a file
        another process holds open must not stop the microphone coming up.
        """
        cutoff = time.time() - self._config.retain_days * _SECONDS_PER_DAY
        # Audio seeds the totals so the two artefacts expire on one clock and
        # are reported as one number. They are swept together because a caller
        # who has to remember a second sweep will eventually not.
        removed, remaining, failed = self._sweep_audio(cutoff)

        if not self.pending_dir.exists():
            return SweepResult(removed=removed, remaining=remaining, failed=failed)

        # Globbed by the pattern this module writes, never by directory. A
        # sweep that unlinked everything under `pending/` would delete whatever
        # a user or another tool had put there.
        for path in self.pending_dir.glob("*.json"):
            try:
                if path.stat().st_mtime > cutoff:
                    remaining += 1
                    continue
                path.unlink()
                removed += 1
            except OSError:
                failed += 1
        return SweepResult(removed=removed, remaining=remaining, failed=failed)

    def _sweep_audio(self, cutoff: float) -> tuple[int, int, int]:
        """Expire stored audio on the same clock as pending transcripts.

        Audio is the sensitive artefact (§7.6) and `manu history --purge` is
        Phase 3, so a writer without a reaper would leave a directory that
        grows without bound and that nothing reaches. `retain_days` is what
        §5.3 already means by how long things are kept, so it governs here too.
        """
        if not self.audio_dir.exists():
            return 0, 0, 0
        removed = remaining = failed = 0
        for path in self.audio_dir.glob("*.wav"):
            try:
                if path.stat().st_mtime > cutoff:
                    remaining += 1
                    continue
                path.unlink()
                removed += 1
            except OSError:
                failed += 1
        return removed, remaining, failed

    # -- retain = true -----------------------------------------------------

    def _insert(self, row: dict[str, Any]) -> None:
        placeholders = ", ".join("?" for _ in _COLUMNS)
        columns = ", ".join(_COLUMNS)
        # REPLACE rather than IGNORE: a session written twice has been written
        # twice *before* injection, so the second write's timings are the live
        # ones and `injected` correctly returns to its default of 0.
        statement = (
            f"INSERT OR REPLACE INTO transcripts ({columns}) "
            f"VALUES ({placeholders})"
        )
        with self._transaction() as connection:
            connection.execute(statement, [row.get(name) for name in _COLUMNS])

    def _complete(self, session: DictationSession) -> None:
        timings = session.timings
        with self._transaction() as connection:
            connection.execute(
                "UPDATE transcripts SET injected = 1, persist_ms = ?, "
                "inject_ms = ?, restore_ms = ?, postprocess_ms = ? WHERE id = ?",
                (
                    timings.persist_ms,
                    timings.inject_ms,
                    # Zero at write time for the same structural reason
                    # `inject_ms` is: the restore has not happened yet. It is
                    # outside G1 and still stored, because it is how long the
                    # transcript sat on the system clipboard — the exposure
                    # §7.3 argues about and Phase 2a measured.
                    timings.restore_ms,
                    timings.postprocess_ms,
                    session.id,
                ),
            )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """Connect, run, commit, close.

        `with sqlite3.connect(...)` commits but does *not* close — a detail
        that reads like a bug report waiting to happen in a process that will
        eventually run for days holding a microphone.
        """
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        """Open the database, creating it owner-only if it does not exist.

        The file is created here rather than left to sqlite because sqlite
        applies the process umask, and the default umask on a shared machine
        produces a group-readable file full of transcripts. Creating it at
        0600 first closes the window; umask can only clear bits, and 0600 has
        none to clear.

        The schema is applied on every connect rather than once at startup.
        `CREATE TABLE IF NOT EXISTS` is cheap and idempotent, and the
        alternative — an `initialise()` the caller must remember — is a step
        that gets skipped exactly once, on the path where a transcript is
        being written before injection.
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        if not self.db_path.exists():
            self.db_path.touch(mode=_FILE_MODE)
        connection = sqlite3.connect(self.db_path)
        connection.execute(_SCHEMA)
        _add_missing_columns(connection)
        return connection

    # -- store_audio -------------------------------------------------------

    def _write_audio(self, session: DictationSession) -> None:
        """Keep the recording, when `[history] store_audio` says to.

        This key validated and did nothing for three phases — it parsed, it had
        a rule, `test_config.py` asserted its default, and no code anywhere
        read it. The cost came due when a live transcript collapse turned out
        to be unreproducible: the one setting that would have preserved the
        evidence was the one that did nothing.

        Written under `retain = true` only. The `retain = false` path exists so
        a transcript survives a crash; audio is not needed for that, and it is
        the artefact §7.6 cares most about. `0600` for the same reason the
        database is.
        """
        if not self._config.store_audio or session.audio is None:
            return
        if len(session.audio) == 0:
            return

        self.audio_dir.mkdir(parents=True, exist_ok=True, mode=_DIR_MODE)
        path = self.audio_dir / f"{session.id}.wav"
        # Created before opening, for the same reason the database is: the
        # umask can only clear bits, and 0600 has none to clear.
        path.touch(mode=_FILE_MODE)
        # float32 in [-1, 1] out to 16-bit PCM, which is what `read_wav` in the
        # test suite and every audio tool expects. Clipped rather than scaled:
        # a sample above 1.0 is already distorted, and rescaling the whole clip
        # to accommodate it would quietly change every other sample too.
        samples = np.clip(session.audio, -1.0, 1.0)
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(session.sample_rate)
            handle.writeframes((samples * 32767.0).astype("<i2").tobytes())

    # -- retain = false ----------------------------------------------------

    def _pending_path(self, session_id: str) -> Path:
        return self.pending_dir / f"{session_id}.json"

    def _write_pending_file(self, row: dict[str, Any]) -> None:
        """Write the whole row, not just the transcript.

        §5.5 gap 3 makes `manu history` responsible for surfacing these in
        Phase 3, and a bare transcript with no timestamp is not something a
        user can act on. The cost is that the file is a superset of what the
        transcript alone would expose — accepted, because everything in the
        row is derived from a transcript that is already in the file.
        """
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.pending_dir.chmod(_DIR_MODE)

        path = self._pending_path(str(row["id"]))
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(row, handle, indent=2)
