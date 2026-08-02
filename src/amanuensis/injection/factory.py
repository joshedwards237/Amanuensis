"""Platform detection to injector. One per process.

macOS only for v1 (PRD §7.3). Windows is post-v1 *intent* — it ships no code
and gates nothing — and Linux is a plain non-goal. This factory is what keeps
that a scheduling decision rather than an architectural one: adding Windows
means adding a row here and a module beside `macos.py`, not restructuring
anything that already works.

The unsupported-platform error is written for a human who has just run the
tool on the wrong OS, so it says what is supported and where that is recorded.
"Unsupported platform: linux" would be technically complete and practically
useless.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Final

from amanuensis.injection.base import TextInjector

if TYPE_CHECKING:  # pragma: no cover — import-time cost, not behaviour
    from amanuensis.config import InjectionConfig

__all__ = ["UnsupportedPlatformError", "create_injector"]

#: Platforms with an injector. A set rather than a phase table now that the
#: one entry is built — a row here saying "Phase 2a" outlived its truth the
#: moment Phase 2a shipped, which is how `engines/registry.py` came to
#: promise a Moonshine engine that ADR 0001 had already declined.
_SUPPORTED: Final[frozenset[str]] = frozenset({"darwin"})


class UnsupportedPlatformError(Exception):
    """No injector exists for the platform this is running on."""


def create_injector(
    config: InjectionConfig, platform: str | None = None
) -> TextInjector:
    """Return the injector for this platform.

    `platform` defaults to `sys.platform` so that no production caller has to
    pass one; it is a parameter at all so the dispatch can be tested from any
    machine — including the check that a Linux user gets a sentence rather
    than an ImportError from a pyobjc that was never installed there.

    The import is inside the function for that reason: `injection.macos` pulls
    in bridges that do not exist off macOS, and a module-level import would
    make this file unloadable on the platform it exists to give a good error
    on.
    """
    target = platform if platform is not None else sys.platform

    if target not in _SUPPORTED:
        raise UnsupportedPlatformError(
            f"no text injector for platform {target!r}. Amanuensis supports "
            "macOS only in v1; Windows is post-v1 intent and Linux is a "
            "non-goal (PRD §3, §7.3)."
        )

    from amanuensis.injection.macos import MacOSInjector

    return MacOSInjector(config)
