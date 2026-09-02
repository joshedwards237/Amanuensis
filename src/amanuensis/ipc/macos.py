"""A unix domain socket. The macOS half of §7.3's floor item 3.

**The security boundary is the filesystem and nothing else** (§7.6). The socket
is `0600` inside a `0700` directory: any process running as this user can send
a verb, no process running as another user can reach it, and nothing on the
network can reach it at all because it is not a network socket.

That is the right level rather than a shortcut, and the argument is that it
grants no authority a same-user process does not already have — such a process
can synthesise the hotkey through `CGEvent`, open the microphone itself, read
the clipboard the transcript transits, and read `history.db` directly. A token
would move the secret into a file with the same permissions as the socket.

**A stale socket file is not a running daemon.** The file outlives a crash, so
`serve` unlinks a dead one before binding and `request` reports a refused
connection as "not running" rather than hanging. §7.6 makes that a requirement:
the two states must never be conflated.

Protocol: one line of UTF-8 in, one line of JSON out, then the connection
closes. Chosen over anything framed because the entire vocabulary is two verbs
and a framing bug would be the only interesting failure mode available.
"""

from __future__ import annotations

import json
import socket
import threading
from pathlib import Path
from typing import Final

from amanuensis.ipc.base import (
    ControlRequestError,
    ControlTransport,
    Handler,
    Response,
)

__all__ = ["UnixSocketTransport"]

#: A verb is a short word. Anything longer is a confused process, and reading
#: it into memory before deciding that is how a local socket becomes a way to
#: exhaust a daemon that holds the microphone.
_MAX_REQUEST_BYTES: Final = 4096
#: How long a *client* waits for the daemon to answer.
_TIMEOUT_S: Final = 5.0
#: How long the **acceptor** waits for a connected client to say something.
#: Much shorter, and for a different reason: connections are handled one at a
#: time, so a client that connects and then says nothing occupies the acceptor
#: for exactly this long and `manu status` hangs behind it. Any process running
#: as this user can do that (§7.6), which makes it a robustness bound rather
#: than a security one — but a wedged status command on a daemon that holds the
#: microphone is precisely the moment you want an answer.
_READ_TIMEOUT_S: Final = 1.0
#: Connection backlog. Was 8, which is the number everyone writes and which a
#: shell loop asking twelve times at once exceeds — two requests were refused
#: outright and reported as "the daemon is not running", which is the one
#: answer §7.6 says must never be given wrongly.
_BACKLOG: Final = 64
#: `sun_path` is 104 bytes on macOS, and the kernel's error for exceeding it is
#: a bare `OSError: AF_UNIX path too long` with no mention of what is too long.
#: The default path is nowhere near it; `$AMANUENSIS_DATA_DIR` pointed
#: somewhere deep is, and so is any temporary directory a test invents.
_MAX_PATH_BYTES: Final = 103


class UnixSocketTransport(ControlTransport):
    """Server and client in one class — they must agree, so they live together."""

    def __init__(self, path: Path) -> None:
        encoded = str(path).encode("utf-8")
        if len(encoded) > _MAX_PATH_BYTES:
            raise ValueError(
                f"the socket path is {len(encoded)} bytes and the kernel "
                f"allows {_MAX_PATH_BYTES}: {path}. Set $AMANUENSIS_DATA_DIR "
                "to something shorter."
            )
        self._path = Path(path)
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()

    @property
    def path(self) -> Path:
        return self._path

    # -- server ------------------------------------------------------------

    def serve(self, handler: Handler) -> None:
        """Bind, listen, and accept on a thread of its own (§6.3).

        Its own thread rather than the worker's: serving from the worker is
        free until the worker is mid-transcription, at which point `manu
        status` blocks behind a decode — a status command that hangs precisely
        when you most want to ask.
        """
        if self._server is not None:
            raise RuntimeError("this transport is already serving")

        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._unlink_stale()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self._path))
        # Between bind and chmod the socket exists at the umask's mode. The
        # window is real and unavoidable with AF_UNIX; the parent directory is
        # 0700, which is what actually keeps other users out during it.
        self._path.chmod(0o600)
        server.listen(_BACKLOG)
        server.settimeout(0.25)  # so `stop` is noticed without a wakeup pipe
        self._server = server
        self._stopping.clear()

        thread = threading.Thread(
            target=self._accept_loop, args=(handler,),
            name="amanuensis-ipc", daemon=True,
        )
        self._thread = thread
        thread.start()

    def stop(self) -> None:
        """Idempotent. A socket left behind is the next start's stale file."""
        self._stopping.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2.0)
        server, self._server = self._server, None
        if server is not None:
            server.close()
        self._path.unlink(missing_ok=True)

    def _accept_loop(self, handler: Handler) -> None:
        server = self._server
        if server is None:  # pragma: no cover — stopped between start and run
            return
        while not self._stopping.is_set():
            try:
                connection, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                return  # the socket was closed under us; that is `stop`
            with connection:
                try:
                    self._handle(connection, handler)
                except Exception:
                    # One bad request costs its own connection. This daemon
                    # holds the microphone; an acceptor that died on malformed
                    # input would leave it held with no way to ask it to stop.
                    pass

    def _handle(self, connection: socket.socket, handler: Handler) -> None:
        connection.settimeout(_READ_TIMEOUT_S)
        raw = connection.recv(_MAX_REQUEST_BYTES)
        verb = raw.decode("utf-8", errors="replace").strip()
        try:
            response = handler(verb)
        except Exception as exc:
            response = Response(ok=False, detail=f"the daemon failed: {exc}")
        payload = json.dumps({"ok": response.ok, "detail": response.detail})
        connection.sendall(payload.encode("utf-8") + b"\n")

    def _unlink_stale(self) -> None:
        """Remove a socket file nothing is listening on.

        A daemon that could not restart after a crash would need the user to
        delete a file they have never heard of. Only a *dead* one is removed:
        if something answers, the bind below fails and says so.
        """
        if not self._path.exists():
            return
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.settimeout(_TIMEOUT_S)
            try:
                probe.connect(str(self._path))
            except OSError:
                self._path.unlink(missing_ok=True)

    # -- client ------------------------------------------------------------

    def request(self, verb: str) -> Response:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(_TIMEOUT_S)
                client.connect(str(self._path))
                client.sendall(verb.encode("utf-8") + b"\n")
                try:
                    client.shutdown(socket.SHUT_WR)
                except OSError:
                    # ENOTCONN. The server reads, answers and closes, and on a
                    # fast answer that happens before this call — the verb is
                    # already sent, so there is nothing to salvage and nothing
                    # to report. Raising here turned every quick reply into
                    # "the daemon is not running".
                    pass
                raw = client.recv(_MAX_REQUEST_BYTES)
        except OSError as exc:
            # ENOENT (no file) and ECONNREFUSED (stale file) are the same fact
            # to a user: the daemon is not running. §7.6 requires this be
            # distinguishable from a daemon answering "idle".
            raise ControlRequestError(
                f"the daemon is not running (no socket at {self._path}): {exc}"
            ) from exc

        try:
            parsed = json.loads(raw.decode("utf-8"))
            return Response(ok=bool(parsed["ok"]), detail=str(parsed["detail"]))
        except (ValueError, KeyError, TypeError) as exc:
            raise ControlRequestError(
                f"the daemon sent something this client cannot read: {raw!r}"
            ) from exc
