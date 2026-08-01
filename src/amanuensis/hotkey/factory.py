"""Platform detection to hotkey listener. Mirrors `injection/factory.py`.

Deliberately the same shape as the injector factory, down to the error
wording. Two platform-selection boundaries that dispatch differently would be
two things to learn instead of one, and the second one is always the one
someone gets wrong.

Portability floor item 4 (PRD §7.3): none of this builds Windows support. It
is the difference between a port and a rewrite.
"""

from __future__ import annotations

import sys
from typing import Final

from amanuensis.hotkey.base import HotkeyListener
from amanuensis.injection.factory import UnsupportedPlatformError

__all__ = ["create_hotkey_listener"]

#: `sys.platform` value -> the phase that builds its listener.
_LISTENERS: Final[dict[str, str]] = {"darwin": "Phase 2b"}


def create_hotkey_listener(platform: str | None = None) -> HotkeyListener:
    """Return the hotkey listener for this platform.

    `platform` defaults to `sys.platform`; it is a parameter so the dispatch
    can be tested from any machine.
    """
    target = platform if platform is not None else sys.platform

    if target not in _LISTENERS:
        raise UnsupportedPlatformError(
            f"no hotkey listener for platform {target!r}. Amanuensis supports "
            "macOS only in v1; Windows is post-v1 intent and Linux is a "
            "non-goal (PRD §3, §7.3)."
        )

    raise NotImplementedError(
        f"the {target!r} hotkey listener is not implemented yet — it is built "
        f"in {_LISTENERS[target]}. Phase 0 defines the contract only."
    )
