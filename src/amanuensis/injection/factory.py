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
from typing import Final

from amanuensis.injection.base import TextInjector

__all__ = ["UnsupportedPlatformError", "create_injector"]


class UnsupportedPlatformError(Exception):
    """No injector exists for the platform this is running on."""


#: `sys.platform` value -> the phase that builds its injector.
_INJECTORS: Final[dict[str, str]] = {"darwin": "Phase 2a"}


def create_injector(platform: str | None = None) -> TextInjector:
    """Return the injector for this platform.

    `platform` defaults to `sys.platform` so that no production caller has to
    pass one; it is a parameter at all so the dispatch can be tested from any
    machine.
    """
    target = platform if platform is not None else sys.platform

    if target not in _INJECTORS:
        raise UnsupportedPlatformError(
            f"no text injector for platform {target!r}. Amanuensis supports "
            "macOS only in v1; Windows is post-v1 intent and Linux is a "
            "non-goal (PRD §3, §7.3)."
        )

    raise NotImplementedError(
        f"the {target!r} text injector is not implemented yet — it is built "
        f"in {_INJECTORS[target]}. Phase 0 defines the contract only."
    )
