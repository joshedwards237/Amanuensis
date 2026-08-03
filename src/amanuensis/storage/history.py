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
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from amanuensis.config import HistoryConfig, default_data_dir
from amanuensis.models.session import DictationSession

__all__ = ["HistoryStore", "SweepResult"]

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
    "duration_seconds",
    "engine",
    "error",
    "capture_ms",
    "vad_ms",
    "transcribe_ms",
    "postprocess_ms",
    "persist_ms",
    "inject_ms",
)

_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS transcripts (
    id               TEXT PRIMARY KEY,
    started_at       TEXT    NOT NULL,
    transcript       TEXT    NOT NULL,
    duration_seconds REAL    NOT NULL,
    engine           TEXT    NOT NULL DEFAULT '',
    error            TEXT,
    capture_ms       REAL    NOT NULL DEFAULT 0,
    vad_ms           REAL    NOT NULL DEFAULT 0,
    transcribe_ms    REAL    NOT NULL DEFAULT 0,
    postprocess_ms   REAL    NOT NULL DEFAULT 0,
    persist_ms       REAL    NOT NULL DEFAULT 0,
    inject_ms        REAL    NOT NULL DEFAULT 0,
    injected         INTEGER NOT NULL DEFAULT 0
)
"""


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
        else:
            self._write_pending_file(row)
        return True

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
        if not self.pending_dir.exists():
            return SweepResult(removed=0, remaining=0, failed=0)

        cutoff = time.time() - self._config.retain_days * _SECONDS_PER_DAY
        removed = remaining = failed = 0
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
                "inject_ms = ?, postprocess_ms = ? WHERE id = ?",
                (
                    timings.persist_ms,
                    timings.inject_ms,
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
        return connection

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
