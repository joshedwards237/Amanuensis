"""The Desktop launcher `manu install` writes (§9 Phase 4, README step 5b).

Why this exists at all: the product is a terminal command, and the people §4
describes are not all people who will open a terminal to start a dictation
daemon every morning. A double-clickable entry is the smallest thing that
removes that step without pretending to be an application.

**Why a generated copy rather than a symlink.** A source checkout can symlink
its Desktop entry back into the tree — `start-amanuensis.command --link` does
exactly that, and the entry then follows the checkout. An installed copy has no
tree to point at: `pip install` puts a package in `site-packages` and a console
script in a `bin` directory, and a Finder launch inherits no shell profile, so
`manu` is not on `PATH` and cannot be found by looking. The launcher has to be
*told*. So `manu install` writes a copy with `MANU_HINT` set to the absolute
path of the `manu` that wrote it.

**That is a recorded path, and the difference from the 2026-09-04 bug matters.**
That one was a path a person typed, naming a git worktree — an object routine
merges delete, which is what happened. This one is written by the program that
knows the answer, names the environment it was installed into, is rewritten by
re-running the same command, and when it does go stale the launcher says which
command repairs it instead of printing `cannot find`. A launcher that must find
a `bin` directory nobody told it about has no honest way to do so.

What this module deliberately does not do: decide. `cli.py` owns whether a
launcher is wanted; this owns what one is and how it is written safely.
"""

from __future__ import annotations

import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "LAUNCHER_MARKER",
    "LauncherResult",
    "desktop_launcher_path",
    "packaged_launcher",
    "resolve_manu",
    "write_desktop_launcher",
]

#: Identifies a file this project wrote, as against a file someone else happens
#: to have named the same. Checked before anything is overwritten. Versioned so
#: that a future format change can recognise — and refuse — an older one rather
#: than assuming.
LAUNCHER_MARKER = "# amanuensis-launcher:"

#: How far in to look for it. It cannot be the first line, because the first
#: line of an executable script is the shebang; reading only line one made
#: `manu install` refuse to replace **its own** launcher, which is the
#: idempotence the documented repair depends on. Found by the test for that.
_MARKER_WINDOW = 3

#: The line the packaged script carries, and the one substituted on write.
_HINT_LINE = 'MANU_HINT=""'

_LAUNCHER_NAME = "Start Amanuensis.command"

#: rwxr-xr-x. Finder opens a `.command` without the execute bit in a text
#: editor rather than running it, which reads to a user as "nothing happened".
_MODE = 0o755


@dataclass(frozen=True, slots=True)
class LauncherResult:
    """What happened, in enough detail for the CLI to say so honestly."""

    path: Path
    #: written | replaced | kept-symlink | refused
    action: str
    detail: str

    @property
    def ok(self) -> bool:
        return self.action != "refused"


def packaged_launcher() -> Path:
    """The template, inside the package so that it ships in the wheel.

    Same mechanism as `tier.py`'s reference clip. Verified rather than assumed:
    hatchling includes non-Python files under `packages = ["src/amanuensis"]`,
    and `tests/test_launcher.py` asserts this path exists.
    """
    return Path(__file__).parent / "assets" / "start-amanuensis.command"


def desktop_launcher_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / "Desktop" / _LAUNCHER_NAME


def resolve_manu() -> Path | None:
    """The absolute path of the `manu` this process is running as.

    `sys.executable`'s directory first: in a virtualenv or a `pipx` install the
    console script sits beside the interpreter, and that is true whether or not
    the environment is activated — which is the case that matters, because the
    launcher runs from Finder with no profile and no activation. `PATH` is the
    fallback for a global install, and it is checked second rather than first
    precisely because an activated venv makes `PATH` agree for the wrong
    reason: it would find the right file today and record a path that depends
    on the shell that ran the install.
    """
    beside = Path(sys.executable).parent / "manu"
    if beside.is_file():
        return beside.resolve()
    found = shutil.which("manu")
    return Path(found).resolve() if found else None


def render(manu: Path, template: str | None = None) -> str:
    """The template with `MANU_HINT` filled in.

    Raises rather than writing an unsubstituted script: a launcher whose hint
    is empty has nowhere to look when it runs from a Desktop, and would fail at
    double-click time for a reason nothing observed at install time.
    """
    body = packaged_launcher().read_text() if template is None else template
    if body.count(_HINT_LINE) != 1:
        raise ValueError(
            f"the packaged launcher does not carry exactly one {_HINT_LINE!r} "
            "line to substitute — it cannot be rendered"
        )
    return body.replace(_HINT_LINE, f'MANU_HINT="{manu}"', 1)


def write_desktop_launcher(
    manu: Path, *, home: Path | None = None
) -> LauncherResult:
    """Write the launcher to the Desktop. Idempotent, and never clobbering.

    Three things it refuses, each because the alternative is worse than not
    having a launcher:

    * **A file that is not ours.** Recognised by `LAUNCHER_MARKER` on the first
      line. `manu install` writing into `$HOME` is a side effect on somebody's
      own space, and deleting a file they made because it shares a name is not
      a trade this feature is worth.
    * **A symlink.** That is `--link`'s work, and it points into a checkout that
      the entry then follows. Replacing it with a copy would silently downgrade
      a developer's setup from "tracks the tree" to "snapshot of the tree",
      which is the exact property this whole area exists to preserve.
    * **A missing Desktop.** Created directories in `$HOME` are not this
      command's business.
    """
    target = desktop_launcher_path(home)
    desktop = target.parent

    if not desktop.is_dir():
        return LauncherResult(
            target, "refused", f"no Desktop directory at {desktop}"
        )

    if target.is_symlink():
        return LauncherResult(
            target,
            "kept-symlink",
            "left the existing symlink alone — it follows a source checkout "
            "(start-amanuensis.command --link)",
        )

    if target.exists():
        try:
            head = target.read_text().splitlines()[:_MARKER_WINDOW]
        except (OSError, UnicodeDecodeError):
            head = []
        if not any(line.startswith(LAUNCHER_MARKER) for line in head):
            return LauncherResult(
                target,
                "refused",
                f"{target} already exists and was not written by Amanuensis — "
                "move it aside if you want one here",
            )

    body = render(manu)
    # Written beside the target and moved into place, so an interrupted write
    # cannot leave a half-file that Finder will happily try to execute.
    scratch = target.with_name(target.name + ".new")
    scratch.write_text(body)
    scratch.chmod(_MODE)
    action = "replaced" if target.exists() else "written"
    scratch.replace(target)

    return LauncherResult(target, action, f"points at {manu}")


def is_executable(path: Path) -> bool:
    """Finder runs a `.command` only if this is true; otherwise it opens it."""
    return bool(path.stat().st_mode & stat.S_IXUSR)
