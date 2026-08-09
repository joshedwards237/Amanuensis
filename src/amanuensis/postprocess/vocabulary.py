"""`vocabulary.toml` — the user's own words, and the two ways they are applied.

PRD §5.6 names two mechanisms and says "they fail in different places" without
saying where. Both halves live here because they read one file, and splitting
them would put the dictionary in two modules for the sake of a package boundary
(objection O2 named that as the wrong trade).

- **`[replace]`** is deterministic and local. It runs after the rules pass and
  fails by firing on a homonym, invisibly — which is why every firing is
  recorded (`process_traced`, dictionary objection O5).
- **`[boost]`** is probabilistic and global. It biases the decoder *before* it
  commits, and fails by **degrading unrelated speech**: measured at +3.2 and
  +5.2 WER on two of six samples for a net macro gain of 1.1. That is a trade,
  not a win, which is why it is scoped per application and why the global list
  defaults to empty.

Three things this file is not
-----------------------------
**Not a regex engine.** §5.5's non-goals: a user debugging a regex against their
own speech is worse off than one adding three literal entries. Every key is
`re.escape`d.

**Not a casing heuristic.** Replacement is literal. Dictionary objection O4
rejected the "preserve the casing of what was matched" design as PRD §7.3's
hazard re-committed by the one mechanism whose selling point is determinism —
§7.3 measured macOS text substitution silently rewriting five things in one
sentence and called it unacceptable. What the user writes on the right-hand side
is what lands.

**Not a loop of `re.sub`.** One compiled alternation, keys sorted longest-first.
Measured **70x at 1000 entries** (0.35 ms vs 12.01 ms p50), and the sort is what
implements longest-key-wins rather than a comparison after the fact.

Two contracts, deliberately different from `config.py`
------------------------------------------------------
`config.toml` is loaded once, frozen, and a malformed file is an error at
startup. This file is **re-read when its mtime changes** (operator decision
2026-08-04) because a dictionary's use pattern is notice, edit, retry — and a
restart between noticing and retrying is the friction the feature exists to
remove.

That forces a second difference. At startup a malformed file is an error, as
`config.py` does. **At reload it is not**: the daemon is holding a transcript,
and §5.3's degrade-rather-than-stall rule says losing the user's words to a
half-saved TOML file is the wrong failure. The last good map stays live and the
error is reported — three ways, because a silent keep is the original complaint
one layer down (choice-story #5): the daemon prints it once, the session records
it, and `manu vocab check` re-reads the file directly so the real parse error is
legible where a user goes to debug.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from amanuensis.config import ConfigError, PostprocessConfig, default_config_path
from amanuensis.models.session import DictationSession
from amanuensis.postprocess.base import TextPostProcessor

__all__ = [
    "Vocabulary",
    "VocabularyLoader",
    "VocabularyPostProcessor",
    "default_vocabulary_path",
    "load_vocabulary",
]

#: The prompt window is finite and silently drops overflow, which would present
#: as "my term does not work" rather than "the list is too long".
MAX_BOOST_TERMS: Final = 100

_TABLES: Final = ("replace", "boost")


def default_vocabulary_path() -> Path:
    """Beside `config.toml`, per §5.6. Resolved through the same override."""
    return default_config_path().parent / "vocabulary.toml"


def _escape_key(key: str) -> str:
    """One alternation branch for a key, with boundaries only where they mean something.

    A zero-width assertion is applied to an edge **only when that edge is a word
    character**. `breadshoe` must not match inside `breadshoes`, but `c++` ends
    in punctuation and a trailing `\\b` there would demand a following word
    character — which would make the entry match `c++x` and nothing else.

    Internal whitespace becomes `\\s+`, so a phrase key matches across a run of
    spaces or a newline the decoder emitted at a segment join.
    """
    parts = [re.escape(part) for part in key.split()]
    body = r"\s+".join(parts)
    prefix = r"(?<!\w)" if key[:1].isalnum() or key[:1] == "_" else ""
    suffix = r"(?!\w)" if key[-1:].isalnum() or key[-1:] == "_" else ""
    return f"{prefix}{body}{suffix}"


@dataclass(frozen=True, slots=True)
class Vocabulary:
    """One parsed `vocabulary.toml`, compiled and ready.

    Frozen: it is a snapshot of a file at an mtime, and a caller that could edit
    it would be editing something the loader believes it knows the stamp of.
    """

    #: Lowercased key -> literal replacement. Lowercased because matching is
    #: case-insensitive; the *value* is untouched (B4 rejected).
    replacements: dict[str, str] = field(default_factory=dict)
    boost_terms: tuple[str, ...] = ()
    boost_by_app: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: Non-fatal problems worth telling the user about, e.g. a truncated list.
    warnings: tuple[str, ...] = ()
    #: `(st_mtime_ns, st_size)` of the file this came from. `None` when the file
    #: did not exist — which is not an error and must be distinguishable from
    #: "not yet read".
    stamp: tuple[int, int] | None = None
    _pattern: re.Pattern[str] | None = None

    @property
    def entry_count(self) -> int:
        """`[replace]` entries. The Phase 3 gate records this beside the digest.

        A frozen *empty* dictionary satisfies a SHA-256 and measures nothing
        (objection O4), so the gate needs a count rather than a hash alone.
        """
        return len(self.replacements)

    def terms_for(self, bundle_id: str | None) -> tuple[str, ...]:
        """Boost terms for the focused application.

        A per-application list **replaces** the global one rather than adding to
        it. Union would make the measured degradation unavoidable and the
        scoping pointless — the whole reason to scope is that boosting an
        irrelevant term list is the configuration that produced the collapse.
        """
        if bundle_id is not None and bundle_id in self.boost_by_app:
            return self.boost_by_app[bundle_id]
        return self.boost_terms

    def apply(self, text: str) -> tuple[str, tuple[str, ...]]:
        """Replace, and report which keys fired. One pass, no cascading.

        `re.sub` with a callback gives B5, B6 and B7 together: the alternation
        is ordered longest-first so the longest key wins; each match is consumed
        so a shorter key cannot re-fire inside it; and the callback's output is
        never re-scanned, so `a -> b`, `b -> c` yields `b` rather than `c`.
        """
        if self._pattern is None or not self.replacements:
            return text, ()

        fired: list[str] = []

        def _swap(match: re.Match[str]) -> str:
            # Collapse internal whitespace so a phrase key matched across a
            # newline resolves to the same map entry it was written as.
            key = " ".join(match.group(0).split()).lower()
            # `.get`, not `[]`. `re.IGNORECASE` uses simple case folding and
            # `str.lower()` uses full folding, so the two disagree on a handful
            # of characters: `İ` matches an `i` key and lowers to TWO code
            # points, and dotless `ı` matches and lowers to itself. Verified
            # both raise `KeyError` under `[]`. The lookup was asserting an
            # invariant the regex engine does not promise, on user data
            # (objection C9). A miss leaves the text alone, which is the
            # behaviour a user reading their own file would predict.
            replacement = self.replacements.get(key)
            if replacement is None:
                return match.group(0)
            if key not in fired:
                fired.append(key)
            return replacement

        return self._pattern.sub(_swap, text), tuple(f"replace:{key}" for key in fired)


def _compile(replacements: dict[str, str]) -> re.Pattern[str] | None:
    """One alternation, longest key first. The sort *is* the longest-wins rule.

    Python's `|` is first-match-wins rather than longest-match-wins, so an
    unsorted alternation would let `spread` win over `spread sheet` purely by
    declaration order — which is not something a user could predict from reading
    their file.
    """
    if not replacements:
        return None
    ordered = sorted(replacements, key=lambda key: (-len(key), key))
    return re.compile(
        "|".join(_escape_key(key) for key in ordered),
        re.IGNORECASE | re.UNICODE,
    )


def _read_replace(raw: Any, path: Path) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ConfigError(f'{path}: [replace] must be a table of key = "value" pairs')
    out: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(value, str):
            raise ConfigError(
                f'{path}: [replace] "{key}" must be a string, got '
                f"{type(value).__name__} ({value!r})"
            )
        stripped = key.strip()
        if not stripped:
            # An empty key matches at every position in the alternation and
            # would replace the gaps between words.
            raise ConfigError(f"{path}: [replace] has an empty key")
        # B6, one replacement per key: TOML already rejects a duplicate literal
        # key, but two keys differing only in case are one key here.
        lowered = " ".join(stripped.split()).lower()
        if lowered in out:
            raise ConfigError(
                f'{path}: [replace] "{key}" duplicates an earlier entry '
                "(matching is case-insensitive, so these are one key)"
            )
        out[lowered] = value
    return out


def _read_boost(
    raw: Any, path: Path
) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]], list[str]]:
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: [boost] must be a table")
    warnings: list[str] = []

    def _terms(value: Any, where: str) -> tuple[str, ...]:
        if not isinstance(value, list):
            raise ConfigError(f"{path}: {where} must be a list of strings")
        for item in value:
            if not isinstance(item, str):
                raise ConfigError(
                    f"{path}: {where} must contain only strings, found "
                    f"{type(item).__name__} ({item!r})"
                )
        if len(value) > MAX_BOOST_TERMS:
            warnings.append(
                f"{where}: {len(value)} terms is over the {MAX_BOOST_TERMS} the "
                "prompt window holds — the rest are dropped rather than "
                "silently truncated by the decoder"
            )
            return tuple(value[:MAX_BOOST_TERMS])
        return tuple(value)

    apps_raw = raw.get("apps", {})
    if not isinstance(apps_raw, dict):
        raise ConfigError(f"{path}: [boost.apps] must be a table of bundle identifiers")

    unknown = set(raw) - {"terms", "apps"}
    if unknown:
        raise ConfigError(
            f"{path}: [boost] has unknown key(s): {', '.join(sorted(unknown))}. "
            "Known: terms, apps"
        )

    global_terms = _terms(raw.get("terms", []), "[boost] terms")
    by_app = {
        bundle: _terms(value, f'[boost.apps] "{bundle}"')
        for bundle, value in apps_raw.items()
    }
    return global_terms, by_app, warnings


def load_vocabulary(path: Path | None = None) -> Vocabulary:
    """Read and compile `vocabulary.toml`. A missing file is not an error (B8).

    Errors name the file and the key, on `config.py`'s contract: the reader is
    looking at a TOML file they just edited, not at a stack trace.
    """
    resolved = path if path is not None else default_vocabulary_path()
    try:
        stat = resolved.stat()
    except OSError:
        return Vocabulary()

    try:
        with resolved.open("rb") as handle:
            raw: dict[str, Any] = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{resolved}: not valid TOML — {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"{resolved}: could not be read — {exc}") from exc

    unknown = set(raw) - set(_TABLES)
    if unknown:
        raise ConfigError(
            f"{resolved}: unknown table(s): {', '.join(sorted(unknown))}. "
            f"Known tables: {', '.join(_TABLES)}"
        )

    replacements = _read_replace(raw.get("replace", {}), resolved)
    boost_terms, by_app, warnings = _read_boost(raw.get("boost", {}), resolved)

    return Vocabulary(
        replacements=replacements,
        boost_terms=boost_terms,
        boost_by_app=by_app,
        warnings=tuple(warnings),
        stamp=(stat.st_mtime_ns, stat.st_size),
        _pattern=_compile(replacements),
    )


class VocabularyLoader:
    """Holds the current `Vocabulary` and re-reads it when the file changes.

    **One read point, at the top of the worker's `_process`** (objection O10).
    `[boost]` needs its terms *before* the decode and `[replace]` does not care,
    so the earlier point serves both and there is no second schedule for one
    file. An earlier draft said "before the chain runs", which is after the
    decode and would have left the two halves reading different snapshots.

    The cost is one `stat()` per dictation. The `re.compile` is paid only when
    the stamp changes — on the dictation immediately after the user edits their
    file, which is also the dictation they are testing their new entry on, which
    is why `vocab_ms` exists and has a gate ceiling.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path if path is not None else default_vocabulary_path()
        self._current = Vocabulary()
        self._error: str | None = None
        self._loaded = False

    @property
    def path(self) -> Path:
        return self._path

    @property
    def error(self) -> str | None:
        """The last reload failure, or `None`. Cleared when the file parses.

        Read by the daemon (printed once), by the controller (recorded on the
        session) and by `manu vocab check`. A reload that fails silently is
        C3's original complaint one layer down: the user edits the file, nothing
        changes, and nothing says why.
        """
        return self._error

    def current(self) -> Vocabulary:
        """The live vocabulary.

        Reads the file exactly once if nothing has yet — a first-use load rather
        than a re-read, so the steady state is still "the worker refreshes, the
        processor reads". Without it a caller that never calls `refresh` (a test,
        `manu vocab check`, any future direct user) silently gets an empty map,
        which is the failure mode hardest to notice: the dictionary appears to
        be configured and does nothing.
        """
        if not self._loaded:
            self.refresh()
        return self._current

    def refresh(self) -> Vocabulary:
        """Re-read if the file changed. Returns the live vocabulary either way.

        Returns the *same object* when nothing changed, which is what makes the
        no-op cheap enough to run on every dictation.
        """
        try:
            stat = self._path.stat()
            stamp: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            stamp = None

        if self._loaded and stamp == self._current.stamp:
            return self._current

        try:
            self._current = load_vocabulary(self._path)
            self._error = None
        except ConfigError as exc:
            # The last good map stays live. §5.3's degrade-rather-than-stall
            # rule: at startup a malformed file is an error, but here the daemon
            # is mid-dictation and refusing would cost the user their words for
            # a file they are halfway through saving.
            self._error = str(exc)
        self._loaded = True
        return self._current


class VocabularyPostProcessor(TextPostProcessor):
    """The `vocabulary` entry in `[postprocess] chain`.

    **Runs after `rules`** (B2): the rules pass changes capitalisation and
    punctuation, and running it second would rewrite the map's output — which is
    the one thing the deterministic half must not do.

    Reads the loader rather than the file. The reload is the worker's business
    because `[boost]` needs the same snapshot before the decode, and a processor
    that stat'd the file itself would give the two halves different views of one
    edit.
    """

    def __init__(
        self,
        config: PostprocessConfig | None = None,
        loader: VocabularyLoader | None = None,
    ) -> None:
        self._config = config if config is not None else PostprocessConfig()
        self._loader = loader if loader is not None else VocabularyLoader()

    @property
    def name(self) -> str:
        return "vocabulary"

    def process(self, text: str, session: DictationSession) -> str:
        return self.process_traced(text, session)[0]

    def process_traced(
        self, text: str, session: DictationSession
    ) -> tuple[str, tuple[str, ...]]:
        """Apply the map, and name every entry that fired.

        Naming them is the answer to dictionary objection O5: a rule firing
        where it should not — `sheet -> worksheet` rewriting a sentence about
        bedding — presents to the user as an ASR error, which is the one
        explanation that sends them to the wrong fix.
        """
        return self._loader.current().apply(text)
