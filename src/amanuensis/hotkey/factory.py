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
from typing import TYPE_CHECKING, Final

from amanuensis.hotkey.base import HotkeyListener
from amanuensis.injection.factory import UnsupportedPlatformError

if TYPE_CHECKING:  # pragma: no cover — import-time cost, not behaviour
    from amanuensis.config import HotkeyConfig

__all__ = ["create_hotkey_listener"]

#: Platforms with a listener. A set rather than the phase table this used to
#: be: the phase table answered "when will this exist", and now it does.
_SUPPORTED: Final[frozenset[str]] = frozenset({"darwin"})


def create_hotkey_listener(
    config: HotkeyConfig, platform: str | None = None
) -> HotkeyListener:
    """Return the hotkey listener for this platform.

    `platform` defaults to `sys.platform`; it is a parameter so the dispatch
    can be tested from any machine.
    """
    target = platform if platform is not None else sys.platform

    if target not in _SUPPORTED:
        raise UnsupportedPlatformError(
            f"no hotkey listener for platform {target!r}. Amanuensis supports "
            "macOS only in v1; Windows is post-v1 intent and Linux is a "
            "non-goal (PRD §3, §7.3)."
        )

    # Imported here, not at module scope: `hotkey/macos.py` is importable off
    # macOS but nothing in it is useful there, and this module has to load on
    # any platform to raise the error above.
    from amanuensis.hotkey.macos import MacOSHotkeyListener

    return MacOSHotkeyListener(config)
