"""The control transport — `manu status` and `manu toggle` (§7.3 floor item 3).

Every test here uses a socket in `tmp_path`. Nothing starts a daemon, loads a
model, or goes near the microphone: S3's stress pass ended with two pytest
processes holding the operator's microphone for thirteen minutes, and the
lesson generalises to the slice that adds a second way to open it.

The authority model is the subject of half of these. §7.6 decided the boundary
is filesystem permissions and nothing else — which is defensible only if the
permissions are actually what the code sets, so that is asserted rather than
assumed.
"""

from __future__ import annotations

import shutil
import socket
import stat
import tempfile
import threading
from pathlib import Path

import pytest

from amanuensis.ipc.base import ControlRequestError, Response, make_handler
from amanuensis.ipc.macos import AlreadyRunningError, UnixSocketTransport


@pytest.fixture
def sock_dir() -> Path:
    """A *short* directory. `sun_path` is 104 bytes on macOS and pytest's
    `tmp_path` is nowhere near short enough — which is itself worth knowing,
    because `$AMANUENSIS_DATA_DIR` pointed somewhere deep hits the same wall."""
    made = Path(tempfile.mkdtemp(prefix="amn", dir="/tmp"))
    yield made
    shutil.rmtree(made, ignore_errors=True)


def _serve(path: Path, handler: object) -> UnixSocketTransport:
    transport = UnixSocketTransport(path)
    transport.serve(handler)  # type: ignore[arg-type]
    return transport


@pytest.fixture
def transport(sock_dir: Path) -> UnixSocketTransport:
    made = _serve(sock_dir / "daemon.sock", lambda verb: Response(ok=True, detail=verb))
    yield made
    made.stop()


# ---------------------------------------------------------------------------
# It works at all
# ---------------------------------------------------------------------------


def test_a_verb_reaches_the_handler_and_the_answer_comes_back(
    transport: UnixSocketTransport,
) -> None:
    reply = UnixSocketTransport(transport.path).request("status")
    assert reply.ok
    assert reply.detail == "status"


def test_two_requests_on_one_socket_file(transport: UnixSocketTransport) -> None:
    """One connection per request. A transport that only worked once would
    pass a single-call test and fail the second time a user asked."""
    client = UnixSocketTransport(transport.path)
    assert client.request("status").ok
    assert client.request("toggle").ok


def test_concurrent_clients_do_not_interleave(
    transport: UnixSocketTransport,
) -> None:
    """Two `manu status` invocations at once is ordinary — a shell loop does
    it. Interleaved replies would hand one client the other's answer."""
    results: list[str] = []
    lock = threading.Lock()

    def ask(verb: str) -> None:
        reply = UnixSocketTransport(transport.path).request(verb)
        with lock:
            results.append(f"{verb}:{reply.detail}")

    threads = [
        threading.Thread(target=ask, args=(v,))
        for v in ["status", "toggle"] * 6
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)

    assert len(results) == 12
    assert all(r.split(":")[0] == r.split(":")[1] for r in results), results


# ---------------------------------------------------------------------------
# Authority — §7.6's boundary is the permissions, so assert the permissions
# ---------------------------------------------------------------------------


def test_the_socket_is_not_readable_by_other_users(
    transport: UnixSocketTransport,
) -> None:
    """This is the whole security boundary. §7.6 argues the socket grants no
    authority a same-user process does not already have — an argument that
    says nothing about *other* users, and only holds if the mode is 0600."""
    mode = stat.S_IMODE(Path(transport.path).stat().st_mode)
    assert mode == 0o600, f"socket mode is {mode:o}"


def test_it_is_not_a_network_socket(transport: UnixSocketTransport) -> None:
    """A TCP transport would be reachable from off the machine, which is a G3
    question and not a convenience one."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
        probe.settimeout(5)
        probe.connect(str(transport.path))  # AF_UNIX or it would not connect


def test_an_unknown_verb_is_refused_and_names_the_known_ones(
    sock_dir: Path,
) -> None:
    """§7.6: unknown verbs are refused, not ignored. A daemon that silently
    dropped one would leave a caller waiting for something that never happens,
    and the refusal names what does work because the caller is a person at a
    terminal.

    This is the handler's requirement, not the transport's — the transport
    carries whatever string it is given, which is why `make_handler` exists in
    one place rather than in each caller that remembers to check.
    """
    handler = make_handler({"status": lambda: Response(ok=True, detail="idle")})
    transport = _serve(sock_dir / "d.sock", handler)
    try:
        reply = UnixSocketTransport(transport.path).request("rm -rf")
        assert not reply.ok
        assert "rm -rf" in reply.detail
        assert "status" in reply.detail, "the refusal must name what works"
    finally:
        transport.stop()


# ---------------------------------------------------------------------------
# Nothing listening, and stale files
# ---------------------------------------------------------------------------


def test_no_daemon_is_distinguishable_from_an_idle_one(sock_dir: Path) -> None:
    """§7.6's third requirement. Reporting "nothing is listening" as "the
    daemon says it is idle" is a claim about the microphone nobody checked."""
    client = UnixSocketTransport(sock_dir / "absent.sock")
    with pytest.raises(ControlRequestError) as exc:
        client.request("status")
    assert "not running" in str(exc.value).lower()


def test_a_stale_socket_file_is_not_a_running_daemon(sock_dir: Path) -> None:
    """The file outlives a crash. Connecting to it fails with ECONNREFUSED
    rather than hanging, and that must read as "not running"."""
    path = sock_dir / "stale.sock"
    dead = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    dead.bind(str(path))
    dead.close()  # the file remains, nothing is accepting

    with pytest.raises(ControlRequestError):
        UnixSocketTransport(path).request("status")


def test_serving_over_a_stale_file_succeeds(sock_dir: Path) -> None:
    """A daemon that could not restart after a crash would need the user to
    delete a file they have never heard of."""
    path = sock_dir / "stale.sock"
    dead = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    dead.bind(str(path))
    dead.close()

    transport = _serve(path, lambda verb: Response(ok=True, detail=verb))
    try:
        assert UnixSocketTransport(path).request("status").ok
    finally:
        transport.stop()


def test_stop_removes_the_socket_file(sock_dir: Path) -> None:
    path = sock_dir / "daemon.sock"
    transport = _serve(path, lambda verb: Response(ok=True, detail=verb))
    assert path.exists()
    transport.stop()
    assert not path.exists(), "a socket left behind is the next start's stale file"


def test_stop_is_idempotent(sock_dir: Path) -> None:
    transport = _serve(sock_dir / "d.sock", lambda verb: Response(ok=True, detail=verb))
    transport.stop()
    transport.stop()


# ---------------------------------------------------------------------------
# A handler that misbehaves must not take the daemon with it
# ---------------------------------------------------------------------------


def test_a_raising_handler_answers_rather_than_killing_the_acceptor(
    sock_dir: Path,
) -> None:
    """The handler calls into the controller. A controller that raises must
    cost its own request and nothing else — the daemon holds the microphone."""

    def boom(verb: str) -> Response:
        raise RuntimeError("controller exploded")

    transport = _serve(sock_dir / "d.sock", boom)
    try:
        client = UnixSocketTransport(transport.path)
        reply = client.request("toggle")
        assert not reply.ok
        assert client.request("status") is not None, "the acceptor died"
    finally:
        transport.stop()


def test_garbage_on_the_socket_does_not_kill_the_acceptor(
    transport: UnixSocketTransport,
) -> None:
    """Anything running as this user can write to it. Most of what a confused
    process writes is not a verb."""
    for payload in (b"\x00\xff\xfe", b"{", b"x" * 100_000, b""):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.settimeout(5)
            probe.connect(str(transport.path))
            try:
                probe.sendall(payload)
                probe.shutdown(socket.SHUT_WR)
                probe.recv(4096)
            except OSError:
                # The server answers and closes; on a fast reply the probe's
                # own half-close loses the race. That is the server behaving,
                # and this test is about the *next* line — whether it survived.
                pass

    assert UnixSocketTransport(transport.path).request("status").ok


def test_an_overlong_socket_path_is_refused_with_a_reason() -> None:
    """`sun_path` is 104 bytes and the kernel says only "AF_UNIX path too
    long", naming nothing. Found by writing these tests: pytest's own
    `tmp_path` exceeds it, which means `$AMANUENSIS_DATA_DIR` can too.
    """
    deep = Path("/tmp") / ("x" * 120) / "daemon.sock"
    with pytest.raises(ValueError) as exc:
        UnixSocketTransport(deep)
    assert "AMANUENSIS_DATA_DIR" in str(exc.value)


# ---------------------------------------------------------------------------
# Found by the stress pass
# ---------------------------------------------------------------------------


def test_a_second_daemon_is_refused_by_name(sock_dir: Path) -> None:
    """The operator hit the two-daemon problem on 2026-09-02 — two status
    items in his menu bar, both holding the microphone.

    `bind` reports `[Errno 48] Address already in use`, which names neither
    the product nor the consequence. Two daemons share one hotkey: both inject
    and both persist every dictation.
    """
    ok = make_handler({"status": lambda: Response(ok=True)})
    first = _serve(sock_dir / "d.sock", ok)
    try:
        second = UnixSocketTransport(first.path)
        with pytest.raises(AlreadyRunningError) as exc:
            second.serve(ok)
        assert "already listening" in str(exc.value)
        assert "manu status" in str(exc.value), "the error must name a next step"
    finally:
        first.stop()


def test_the_socket_directory_is_tightened_even_when_it_already_exists(
    sock_dir: Path,
) -> None:
    """§7.6's argument is "0600 inside a 0700 directory", and `mkdir(mode=...)`
    is ignored when the directory already exists — which the data directory
    does, by three phases. A 0600 socket inside a 0755 directory is not the
    thing §7.6 argued for.
    """
    loose = sock_dir / "loose"
    loose.mkdir(mode=0o755)
    assert stat.S_IMODE(loose.stat().st_mode) == 0o755

    ok = make_handler({"status": lambda: Response(ok=True)})
    transport = _serve(loose / "d.sock", ok)
    try:
        assert stat.S_IMODE(loose.stat().st_mode) == 0o700
    finally:
        transport.stop()


def test_a_reply_longer_than_one_read_arrives_whole(sock_dir: Path) -> None:
    """A single `recv` truncates, and the client reports that as "the daemon
    sent something this client cannot read" — the transport describing itself
    as broken. `status`'s detail is short today and is exactly the kind of
    string that grows."""
    long_detail = "detail " * 2000
    transport = _serve(
        sock_dir / "d.sock",
        make_handler({"status": lambda: Response(ok=True, detail=long_detail)}),
    )
    try:
        reply = UnixSocketTransport(transport.path).request("status")
        assert reply.detail == long_detail
    finally:
        transport.stop()


def test_an_oversized_verb_is_refused_locally_not_reported_as_no_daemon(
    transport: UnixSocketTransport,
) -> None:
    """The daemon reads a bounded amount, answers and closes; the rest of the
    write then fails with EPIPE, which `request` reported as "the daemon is not
    running" — the one answer §7.6 says must never be given wrongly."""
    reply = UnixSocketTransport(transport.path).request("x" * 8192)
    assert not reply.ok
    assert "limit" in reply.detail


def test_a_handler_returning_the_wrong_type_is_answered(sock_dir: Path) -> None:
    """Without this the failure is a `TypeError` inside `json.dumps`, the
    connection closes with nothing written, and the client calls the daemon
    unreadable — describing the transport as broken when the caller is."""
    transport = _serve(sock_dir / "d.sock", lambda verb: "not a Response")
    try:
        reply = UnixSocketTransport(transport.path).request("status")
        assert not reply.ok
        assert "not a Response" in reply.detail
    finally:
        transport.stop()
