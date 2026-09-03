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

import errno
import json
import socket
import threading
from pathlib import Path
from typing import Final, cast

from amanuensis.ipc.base import (
    ControlRequestError,
    ControlTransport,
    Handler,
    Response,
)

__all__ = ["AlreadyRunningError", "UnixSocketTransport"]


class AlreadyRunningError(Exception):
    """Something is already listening on this socket (§5.4, §7.6).

    Its own type because the situation has a specific remedy and a specific
    cost: two daemons share one hotkey, so both inject and both persist every
    dictation.
    """

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
#: A reply is a sentence for a human. This bounds a client's memory against a
#: daemon that has gone wrong, which is the same courtesy the request limit
#: extends in the other direction.
_MAX_REPLY_BYTES: Final = 65536
#: `sun_path` is 104 bytes on macOS, and the kernel's error for exceeding it is
#: a bare `OSError: AF_UNIX path too long` with no mention of what is too long.
#: The default path is nowhere near it; `$AMANUENSIS_DATA_DIR` pointed
#: somewhere deep is, and so is any temporary directory a test invents.
_MAX_PATH_BYTES: Final = 103


def _recv_line(connection: socket.socket) -> bytes:
    """Read until the newline the protocol terminates every reply with.

    A single `recv` returns whatever one read yields, which for a reply longer
    than the buffer is a truncated JSON document — reported to the user as "the
    daemon sent something this client cannot read". `status`'s detail is short
    today and is exactly the kind of string that grows.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = connection.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if chunk.endswith(b"\n") or total > _MAX_REPLY_BYTES:
            break
    return b"".join(chunks)


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

    def claim(self) -> None:
        """Bind and listen, with nothing accepting yet — §9's instance lock.

        Split out of `serve` on 2026-09-03. `serve` needs a handler, which
        needs the tray and the controller, so `cli.py` reached the bind only
        after `create_hotkey_listener`, `AudioCapture` and `TrayApp`: the
        second daemon had already taken the event tap, opened the microphone
        and put a second glyph in the menu bar before it found out it should
        not exist. §5.4 calls that state a privacy problem in its own right —
        the indicator on one daemon reads *idle* while the other records.

        The socket bound here is the one `serve` accepts on. Re-binding at
        `serve` would reopen the window this closes: two daemons started
        together would both pass a check and both bind. A lock is not a check.
        """
        if self._server is not None:
            return  # idempotent: this transport already holds it

        parent = self._path.parent
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # `mkdir(mode=...)` is ignored when the directory already exists, and
        # the data directory predates this code by three phases. §7.6's whole
        # argument is "0600 inside a 0700 directory", and a socket at 0600
        # inside a 0755 directory is not that — the mode is set explicitly
        # rather than hoped for.
        parent.chmod(0o700)
        self._unlink_stale()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self._path))
        except OSError as exc:
            server.close()
            if exc.errno == errno.EADDRINUSE:
                # `_unlink_stale` already removed a dead socket, so reaching
                # here means something is listening. Two daemons on one hotkey
                # double-inject and double-persist; the bare `Errno 48 Address
                # already in use` names none of that.
                raise AlreadyRunningError(
                    f"another Amanuensis daemon is already listening at "
                    f"{self._path}. Two daemons share one hotkey and would "
                    "both inject and both persist every dictation. Stop the "
                    "other one first — `manu status` will answer from it."
                ) from exc
            raise
        # Between bind and chmod the socket exists at the umask's mode. The
        # window is real and unavoidable with AF_UNIX; the parent directory is
        # 0700, which is what actually keeps other users out during it.
        self._path.chmod(0o600)
        server.listen(_BACKLOG)
        server.settimeout(0.25)  # so `stop` is noticed without a wakeup pipe
        self._server = server
        self._stopping.clear()

    def serve(self, handler: Handler) -> None:
        """Start accepting, on a thread of its own (§6.3).

        Its own thread rather than the worker's: serving from the worker is
        free until the worker is mid-transcription, at which point `manu
        status` blocks behind a decode — a status command that hangs precisely
        when you most want to ask.

        Claims first when the caller has not. A caller that forgets `claim` is
        still single-instance; what it loses is only the early discovery.
        """
        if self._thread is not None:
            raise RuntimeError("this transport is already serving")
        self.claim()

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
        # `object`, not `Response`, and deliberately. `Handler` promises a
        # `Response` and mypy believes it, which makes the check below
        # unreachable to the type checker and entirely reachable at runtime:
        # the handler is supplied by the daemon and Python enforces nothing.
        # Without the check the failure is a `TypeError` inside `json.dumps`,
        # after which the connection closes with nothing written and the client
        # reports the daemon unreadable — the transport describing itself as
        # broken when the caller is.
        # `cast` rather than an annotation: mypy narrows straight back to
        # `Response` from the call's own return type, which is the assumption
        # under test.
        result: object
        try:
            result = cast(object, handler(verb))
        except Exception as exc:
            result = Response(ok=False, detail=f"the daemon failed: {exc}")
        if isinstance(result, Response):
            response = result
        else:
            response = Response(
                ok=False,
                detail=f"the daemon returned {type(result).__name__}, not a Response",
            )
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
                encoded = verb.encode("utf-8")
                if len(encoded) > _MAX_REQUEST_BYTES:
                    # Refused here rather than sent. The daemon reads at most
                    # `_MAX_REQUEST_BYTES`, answers the truncation and closes,
                    # and the rest of the write then fails with EPIPE — which
                    # this method would report as "the daemon is not running",
                    # the one answer §7.6 says must never be given wrongly.
                    return Response(
                        ok=False,
                        detail=f"that verb is {len(encoded)} bytes; the limit "
                        f"is {_MAX_REQUEST_BYTES}",
                    )
                client.sendall(encoded + b"\n")
                try:
                    client.shutdown(socket.SHUT_WR)
                except OSError:
                    # ENOTCONN. The server reads, answers and closes, and on a
                    # fast answer that happens before this call — the verb is
                    # already sent, so there is nothing to salvage and nothing
                    # to report. Raising here turned every quick reply into
                    # "the daemon is not running".
                    pass
                raw = _recv_line(client)
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
