"""Platform detection → transport, mirroring `hotkey/factory.py` (§7.3)."""

from __future__ import annotations

import sys
from pathlib import Path

from amanuensis.ipc.base import ControlTransport

__all__ = ["UnsupportedPlatformError", "create_transport", "default_socket_path"]


class UnsupportedPlatformError(Exception):
    """No transport for this platform. Windows means a named pipe (§7.3)."""


def default_socket_path() -> Path:
    """Where the rendezvous point lives.

    In the **data directory**, beside `history.db`, rather than
    `platformdirs.user_runtime_dir` (choice-story #2). The runtime directory
    has the better lifetime — it is cleared on reboot — but the data directory
    is the one with an override (`$AMANUENSIS_DATA_DIR`), and without that a
    user running two daemons under two config directories gets one socket.
    Sharing a rendezvous point between two daemons is a worse failure than a
    file surviving a reboot, and surviving a reboot is handled: a stale socket
    is unlinked before binding, because a crash leaves one within a session
    anyway and that case has to work regardless.
    """
    from amanuensis.config import default_data_dir

    path: Path = default_data_dir() / "daemon.sock"
    return path


def create_transport(path: Path | None = None) -> ControlTransport:
    if sys.platform != "darwin":
        raise UnsupportedPlatformError(
            f"no control transport for {sys.platform!r}. macOS is the only v1 "
            "platform (PRD §3); Windows means a named pipe behind this same "
            "ABC (§7.3 portability floor item 3)."
        )
    from amanuensis.ipc.macos import UnixSocketTransport

    return UnixSocketTransport(path if path is not None else default_socket_path())
