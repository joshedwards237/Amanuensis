"""Config string to engine class. The replacement dispatch (PRD §6.3).

Backends are declared as module paths and imported lazily, for one reason
that matters: importing this module must not import CTranslate2. `manu
--help` and `manu status` have no business paying a multi-second import for a
model runtime they will not use, and a broken wheel for one backend must not
prevent the CLI from starting and telling the user so.

`resolve_engine` has two distinct failure modes and keeping them distinct is
the point: an unknown name is the *user's* typo and lists the valid names; a
known name with no implementation is *our* gap and names the phase that closes
it. Collapsing both into "not found" would tell a user their config was wrong
when it was right.

**Wired up 2026-09-02, four phases late, and what it cost.** Phase 0 registered
the names and implemented none, so this function raised `NotImplementedError`
for *every* backend — including `faster_whisper`, which ships. The daemon
worked because `cli.py` imported `FasterWhisperEngine` by name and never asked,
which is what let dead dispatch sit behind a §6.4 entry describing it as
"backend string → class, per config".

The cost was not inertness. `[engine] backend` was read in exactly one place —
to build the `engine` label on a history row — so `backend = "moonshine"` was
accepted, the daemon ran faster-whisper anyway, and `history.db` recorded
`moonshine:tiny.en`. A key that does nothing is inert; a key that mislabels the
measurement record makes every figure derived from those rows a claim about the
wrong engine. `_check_coherence` now refuses a backend that cannot be
constructed, so the label and the engine cannot disagree.
"""

from __future__ import annotations

from typing import Final

__all__ = ["UnknownBackendError", "available_backends", "resolve_engine"]


class UnknownBackendError(Exception):
    """`[engine] backend` names something that does not exist."""


#: Backend name -> `(module, class)`, or `(None, phase)` for one that is
#: declared and unbuilt. Imported lazily: importing this module must not import
#: CTranslate2, and a broken wheel for one backend must not stop the CLI from
#: starting and saying so.
_BACKENDS: Final[dict[str, tuple[str | None, str]]] = {
    "faster_whisper": ("amanuensis.engines.faster_whisper", "FasterWhisperEngine"),
    "moonshine": ("amanuensis.engines.moonshine", "MoonshineEngine"),
    #: ADR 0001 named it; nothing has ever benchmarked it, and the Phase 4 gate
    #: records that as a gap rather than closing it. NVIDIA NeMo has no
    #: CoreML/Metal path on macOS.
    "parakeet": (None, "unscheduled — see §7.2 and the Phase 4 gate record"),
}


def available_backends() -> tuple[str, ...]:
    """Backend names accepted by `[engine] backend`, in declaration order."""
    return tuple(_BACKENDS)


def resolve_engine(backend: str) -> type:
    """Return the engine class for a config backend string.

    Raises `UnknownBackendError` for a name that is not a backend, and
    `NotImplementedError` for one that is but has not been built yet.
    """
    if backend not in _BACKENDS:
        known = ", ".join(available_backends())
        raise UnknownBackendError(
            f"unknown engine backend {backend!r}. Known backends: {known}"
        )

    module_path, name = _BACKENDS[backend]
    if module_path is None:
        raise NotImplementedError(
            f"the {backend!r} engine is declared and not built: {name}."
        )

    import importlib

    module = importlib.import_module(module_path)
    engine: type = getattr(module, name)
    return engine
