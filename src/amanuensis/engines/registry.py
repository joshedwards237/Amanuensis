"""Config string to engine class. The replacement dispatch (PRD §6.3).

Backends are declared as module paths and imported lazily, for one reason
that matters: importing this module must not import CTranslate2. `manu
--help` and `manu status` have no business paying a multi-second import for a
model runtime they will not use, and a broken wheel for one backend must not
prevent the CLI from starting and telling the user so.

Phase 0 registers the names and implements none of them. `resolve_engine`
therefore has two distinct failure modes, and keeping them distinct is the
point: an unknown name is the *user's* typo and lists the valid names; a known
name with no implementation is *our* gap and names the phase that closes it.
Collapsing both into "not found" would tell a user their config was wrong when
it was right.
"""

from __future__ import annotations

from typing import Final

__all__ = ["UnknownBackendError", "available_backends", "resolve_engine"]


class UnknownBackendError(Exception):
    """`[engine] backend` names something that does not exist."""


#: Backend name -> the phase that builds it. Becomes name -> module path once
#: there is a module to point at.
_BACKENDS: Final[dict[str, str]] = {
    "faster_whisper": "Phase 1",
    "moonshine": "Phase 1",
    "parakeet": "Phase 1",
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

    raise NotImplementedError(
        f"the {backend!r} engine is not implemented yet — it is built in "
        f"{_BACKENDS[backend]}. Phase 0 defines the contract only."
    )
