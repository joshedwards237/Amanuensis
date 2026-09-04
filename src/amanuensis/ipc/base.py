"""The contract for `manu status` and `manu toggle` (§7.3 floor item 3).

The transport is an ABC for one stated reason: §7.3's portability floor says
"`manu toggle` uses a unix socket on macOS; that is a POSIX assumption and must
not appear in the CLI contract as though it were the interface." Windows has
named pipes and no unix sockets, and the floor exists so that a port is a
scheduling decision rather than a redesign. A floor item with no phase is a
floor item that does not exist, and this one spent two phases in that state.

What crosses this boundary is deliberately small: a **verb** goes in, a
`Response` comes back. No transcript content ever moves through here — §7.6
makes that a requirement rather than a convention, because a `status` that
returned the last transcript would open an egress path G3's packet capture
cannot see.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ControlRequestError",
    "ControlTransport",
    "Handler",
    "Response",
    "make_handler",
]


class ControlRequestError(Exception):
    """The request never reached a daemon.

    Distinct from a `Response` with `ok=False`, which means the daemon answered
    and said no. §7.6's third requirement is that these two are never conflated:
    reporting "nothing is listening" as "the daemon says it is idle" is a claim
    about the microphone that nobody checked.
    """


@dataclass(frozen=True, slots=True)
class Response:
    """What a verb produced. `detail` is for a human, not for parsing."""

    ok: bool
    detail: str = ""


#: A verb in, a `Response` out. Implemented by the daemon; called on the
#: acceptor thread, so it must not block — §6.3's rule for every producer.
Handler = Callable[[str], Response]


class ControlTransport(ABC):
    """One socket, one verb per connection, both ends of it."""

    @property
    @abstractmethod
    def path(self) -> Path:
        """Where the rendezvous point lives."""

    @abstractmethod
    def claim(self) -> None:
        """Acquire the rendezvous point without accepting on it yet.

        This is §9's single-instance guard, separated from `serve` because of
        *when* it has to run. `serve` needs a handler, the handler needs the
        tray and the controller, and building those means opening the
        microphone and adding a status item — so a daemon that discovered it
        was the second one at `serve` had already taken both. `claim` is the
        same acquisition with nothing listening, so the discovery happens
        before anything is taken.

        Raises the platform's already-running error when another daemon holds
        it. Idempotent for the same transport; released by `stop`.
        """

    @abstractmethod
    def serve(self, handler: Handler) -> None:
        """Start accepting. Returns once the transport is listening.

        Claims the rendezvous point first if `claim` has not already been
        called, so a caller that never claims is still single-instance.
        """

    @abstractmethod
    def stop(self) -> None:
        """Stop accepting and remove the rendezvous point. Idempotent."""

    @abstractmethod
    def request(self, verb: str) -> Response:
        """Send one verb to a running daemon.

        Raises `ControlRequestError` when nothing is listening.
        """


def make_handler(verbs: dict[str, Callable[[], Response]]) -> Handler:
    """Turn a verb table into a `Handler` that refuses everything else.

    §7.6 requires that unknown verbs are **refused, not ignored** — a daemon
    that silently dropped one would leave a caller waiting for something that
    never happens — and that the refusal names the verbs that do work, because
    the caller is a person at a terminal or a script someone is writing.

    It lives here rather than in the CLI so there is one implementation of that
    requirement instead of one per caller that remembers it.
    """

    def handle(verb: str) -> Response:
        action = verbs.get(verb)
        if action is None:
            known = ", ".join(sorted(verbs))
            return Response(
                ok=False, detail=f"unknown verb {verb!r}. This daemon answers: {known}"
            )
        return action()

    return handle
