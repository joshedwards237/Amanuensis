"""The double-clickable launcher, and the path that must not be written into it.

`scripts/start-amanuensis.command` is the one artefact that outlives the tree it
was written in: it gets copied — or, since 2026-09-04, symlinked — somewhere a
person can double-click, and then it stays there while the repository moves
underneath it.

It hard-coded its checkout until 2026-09-04. That checkout was a worktree, the
worktree was removed when its pull request merged, and the copy on the
operator's Desktop started answering `cannot find`. Nothing caught it, because
nothing was looking: the script is not imported, not linted as source, and not
run by any other test.

So these are the tests the file could not have. One asserts the *shape* — no
absolute path, ever — and one drives the real resolution through a real symlink
in a temporary directory, because a script that merely looks self-locating and
resolves to the wrong place is the failure being prevented.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = REPO_ROOT / "scripts" / "start-amanuensis.command"
#: The canonical file. `scripts/` is a symlink to it so a checkout keeps the
#: familiar path while the wheel gets the same bytes.
PACKAGED = REPO_ROOT / "src" / "amanuensis" / "assets" / "start-amanuensis.command"

#: Any absolute path into a user's home or a checkout. Deliberately broad: the
#: 2026-09-04 regression was `/Users/<name>/…/worktrees/<branch>`, and a rule
#: written to catch exactly that string would be a rule that catches exactly
#: that string.
ABSOLUTE_PATH = re.compile(r"(?<![\w$])/(Users|home|opt|private/var)/", re.MULTILINE)


def _code_lines(text: str) -> list[tuple[int, str]]:
    """Non-comment, non-blank lines, numbered from 1.

    The preamble *describes* the path that used to be here, and describing the
    bug is how the file explains itself. Only executable lines are the subject.
    """
    out: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append((number, line))
    return out


def test_the_launcher_exists_and_is_executable() -> None:
    """Double-clicking a file without the execute bit opens it in an editor."""
    assert LAUNCHER.is_file()
    assert LAUNCHER.stat().st_mode & stat.S_IXUSR, "Finder needs the execute bit"


def test_the_launcher_contains_no_absolute_paths() -> None:
    """The regression, as a rule about the text.

    A path baked in here is a path that outlives its target: this file is meant
    to be reachable from a Desktop, and the tree it names can be deleted by a
    routine merge without anything noticing.
    """
    offenders = [
        (number, line.strip())
        for number, line in _code_lines(LAUNCHER.read_text())
        if ABSOLUTE_PATH.search(line)
    ]
    assert not offenders, (
        "absolute paths in the launcher — it must resolve its own location:\n"
        + "\n".join(f"  line {n}: {text}" for n, text in offenders)
    )


def test_the_absolute_path_rule_matches_the_path_that_actually_broke() -> None:
    """The positive control, and it is not decorative.

    A regex that matches nothing passes the test above forever. This pins it to
    the literal line that shipped and broke, so a future loosening that stops
    catching it fails here rather than silently.
    """
    broke = 'REPO="/Users/someone/Development/personal/worktrees/phase-4-tray-modes"'
    assert ABSOLUTE_PATH.search(broke), "the rule no longer catches the 2026-09-04 line"
    assert not ABSOLUTE_PATH.search('REPO="$(cd -- "$HERE/.." && pwd -P)"'), (
        "the rule rejects the correct form — it would have to be worked around"
    )


def test_the_launcher_resolves_its_repository_through_a_symlink() -> None:
    """The behaviour, not the shape.

    The Desktop entry is a **symlink** into the checkout, which is what makes it
    follow the repository instead of snapshotting it. That only works if the
    script resolves the link rather than trusting `dirname $0` — so this runs
    the real thing from a real symlink in a temporary directory and asks it
    where it thinks it is.

    `--check` exits before the daemon is started. Nothing here opens a
    microphone, loads a model, or binds a socket.
    """
    with tempfile.TemporaryDirectory() as directory:
        link = Path(directory) / "Start Amanuensis.command"
        link.symlink_to(LAUNCHER)

        result = subprocess.run(
            ["bash", str(link), "--check"],
            capture_output=True,
            text=True,
            timeout=30,
            # A Finder double-click inherits no shell profile. Reproduce that
            # rather than the developer's PATH, or the test passes for a reason
            # the real launch does not have.
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": directory},
        )

    reported = dict(
        line.split(":", 1) for line in result.stdout.splitlines() if ":" in line
    )
    assert reported.get("repo", "").strip() == str(REPO_ROOT), (
        f"resolved to {reported.get('repo')!r}, expected {str(REPO_ROOT)!r}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_a_symlink_chain_resolves_to_the_same_repository() -> None:
    """One hop is the case that exists; a chain is the case macOS creates when
    a Desktop entry is moved and re-linked. The loop handles both or neither."""
    with tempfile.TemporaryDirectory() as directory:
        first = Path(directory) / "first.command"
        second = Path(directory) / "second.command"
        first.symlink_to(LAUNCHER)
        second.symlink_to(first)

        result = subprocess.run(
            ["bash", str(second), "--check"],
            capture_output=True,
            text=True,
            timeout=30,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": directory},
        )

    assert f"repo:     {REPO_ROOT}" in result.stdout, result.stdout


@pytest.mark.skipif(
    not (REPO_ROOT / ".venv" / "bin" / "manu").exists(),
    reason="no .venv beside this checkout — the worktree case, which is fine",
)
def test_the_launcher_prefers_the_checkouts_own_venv() -> None:
    """A Finder launch has the bare system PATH, so an activated virtualenv is
    not in it. Resolving `manu` explicitly is the case that actually works when
    the file is double-clicked, and the fallback to PATH is for a global
    install."""
    with tempfile.TemporaryDirectory() as directory:
        result = subprocess.run(
            ["bash", str(LAUNCHER), "--check"],
            capture_output=True,
            text=True,
            timeout=30,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": directory},
        )

    assert result.returncode == 0, result.stdout + result.stderr
    assert str(REPO_ROOT / ".venv" / "bin" / "manu") in result.stdout


# ---------------------------------------------------------------------------
# `--link` — the reproducible way to put it on a Desktop
# ---------------------------------------------------------------------------
#
# The Desktop entry was a hand-made copy, which is why nobody updated it when
# the tree moved. `--link` makes it a symlink and makes creating it a command
# rather than a memory.


def _link(
    home: Path, *, invoke_relatively: bool = False
) -> subprocess.CompletedProcess[str]:
    argument = (
        os.path.relpath(LAUNCHER, REPO_ROOT) if invoke_relatively else str(LAUNCHER)
    )
    return subprocess.run(
        ["bash", argument, "--link"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO_ROOT) if invoke_relatively else None,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(home)},
    )


def test_link_creates_a_symlink_not_a_copy(tmp_path: Path) -> None:
    """A copy is a snapshot of the checkout at the moment it was made, which is
    exactly how the Desktop entry went stale. A symlink follows."""
    (tmp_path / "Desktop").mkdir()

    result = _link(tmp_path)

    entry = tmp_path / "Desktop" / "Start Amanuensis.command"
    assert result.returncode == 0, result.stdout + result.stderr
    assert entry.is_symlink(), "a copy would go stale again"
    assert entry.resolve() == LAUNCHER.resolve()


def test_link_writes_an_absolute_target_even_when_invoked_by_a_relative_path(
    tmp_path: Path,
) -> None:
    """Found by running it, not by reading it.

    The first version linked to `$SELF` — whatever was typed. Invoked as
    `bash scripts/start-amanuensis.command --link`, that is *relative*, and a
    relative symlink target resolves against the **link's** directory: the
    Desktop entry pointed at `~/Desktop/scripts/…` and found nothing. The same
    class of defect this whole change exists to remove, reproduced inside the
    fix for it.
    """
    (tmp_path / "Desktop").mkdir()

    result = _link(tmp_path, invoke_relatively=True)

    entry = tmp_path / "Desktop" / "Start Amanuensis.command"
    assert result.returncode == 0, result.stdout + result.stderr
    target = os.readlink(entry)
    assert os.path.isabs(target), f"relative symlink target {target!r}"
    assert entry.resolve() == LAUNCHER.resolve()


def test_link_refuses_to_overwrite_a_file_that_is_not_its_own(tmp_path: Path) -> None:
    """`rm -f` on a path derived from `$HOME` is worth a guard. Someone else's
    file with that name is not ours to delete."""
    (tmp_path / "Desktop").mkdir()
    theirs = tmp_path / "Desktop" / "Start Amanuensis.command"
    theirs.write_text("something a person wrote")

    result = _link(tmp_path)

    assert result.returncode != 0
    assert "not a symlink" in result.stdout
    assert theirs.read_text() == "something a person wrote", "it deleted their file"


def test_link_is_rerunnable(tmp_path: Path) -> None:
    """It replaces its own previous link rather than failing on the second run —
    which is what makes it usable after the checkout moves."""
    (tmp_path / "Desktop").mkdir()

    assert _link(tmp_path).returncode == 0
    second = _link(tmp_path)

    assert second.returncode == 0, second.stdout + second.stderr
    assert (tmp_path / "Desktop" / "Start Amanuensis.command").resolve() == (
        LAUNCHER.resolve()
    )


def test_link_reports_failure_rather_than_printing_success(tmp_path: Path) -> None:
    """It printed `linked:` after `ln` had failed. A launcher that reports
    success and does nothing is worse than one that is missing."""
    result = _link(tmp_path)  # no Desktop directory exists

    assert result.returncode != 0
    assert "linked:" not in result.stdout, "claimed success with nothing created"


# ---------------------------------------------------------------------------
# `manu install` writes one — the installed path, where there is no checkout
# ---------------------------------------------------------------------------


def test_the_launcher_is_inside_the_package_so_it_ships_in_the_wheel() -> None:
    """`pip install` gets `src/amanuensis` and nothing else. A launcher under
    `scripts/` cannot be written to a Desktop by an installed `manu`, because an
    installed `manu` has no `scripts/`."""
    assert PACKAGED.is_file()
    assert LAUNCHER.is_symlink(), "scripts/ should point at the packaged copy"
    assert LAUNCHER.resolve() == PACKAGED.resolve(), "one file, not two"


def test_the_packaged_launcher_carries_the_marker_and_an_empty_hint() -> None:
    """The marker is what stops `manu install` deleting somebody else's file,
    and an empty hint is what makes the repository copy self-locating."""
    from amanuensis.launcher import LAUNCHER_MARKER

    text = PACKAGED.read_text()
    assert text.splitlines()[1].startswith(LAUNCHER_MARKER)
    assert 'MANU_HINT=""' in text


def test_a_rendered_launcher_finds_manu_with_no_checkout_above_it(
    tmp_path: Path,
) -> None:
    """The case the whole feature is for, and the one a symlink cannot serve.

    An installed copy sits on a Desktop with no repository anywhere above it,
    and Finder gives it the bare system PATH — so `manu` is neither beside it
    nor findable. It works only because `manu install` recorded where `manu`
    was. This puts a fake `manu` somewhere arbitrary, renders against it, and
    runs the result from a directory with no checkout in sight.
    """
    from amanuensis.launcher import render

    fake_bin = tmp_path / "somewhere" / "bin"
    fake_bin.mkdir(parents=True)
    fake_manu = fake_bin / "manu"
    fake_manu.write_text("#!/bin/bash\nexit 0\n")
    fake_manu.chmod(0o755)

    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    entry = desktop / "Start Amanuensis.command"
    entry.write_text(render(fake_manu))
    entry.chmod(0o755)

    result = subprocess.run(
        ["bash", str(entry), "--check"],
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp_path)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert str(fake_manu) in result.stdout
    assert "recorded by manu install" in result.stdout, (
        "it found `manu` some other way, so this test is not exercising the hint"
    )


def test_an_unrendered_launcher_on_a_desktop_finds_nothing_and_says_why(
    tmp_path: Path,
) -> None:
    """The negative control on the test above.

    If the copy on the Desktop worked without the hint, the hint would not be
    doing anything and the test above would pass for the wrong reason. With an
    empty hint, no checkout and a bare PATH, there is genuinely nowhere to look.
    """
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    entry = desktop / "Start Amanuensis.command"
    entry.write_text(PACKAGED.read_text())
    entry.chmod(0o755)

    result = subprocess.run(
        ["bash", str(entry), "--check"],
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp_path)},
    )

    assert result.returncode != 0
    assert "NOT FOUND" in result.stdout


def test_write_desktop_launcher_produces_something_executable(tmp_path: Path) -> None:
    """Finder opens a `.command` without the execute bit in a text editor,
    which a user reads as the launcher doing nothing."""
    from amanuensis.launcher import is_executable, write_desktop_launcher

    (tmp_path / "Desktop").mkdir()
    manu = tmp_path / "bin" / "manu"
    manu.parent.mkdir()
    manu.touch()

    outcome = write_desktop_launcher(manu, home=tmp_path)

    assert outcome.action == "written"
    assert is_executable(outcome.path)
    assert f'MANU_HINT="{manu}"' in outcome.path.read_text()


def test_write_desktop_launcher_is_idempotent(tmp_path: Path) -> None:
    """Re-running `manu install` after moving an environment is the documented
    repair, so the second write has to replace the first rather than refuse."""
    from amanuensis.launcher import write_desktop_launcher

    (tmp_path / "Desktop").mkdir()
    first = tmp_path / "a" / "manu"
    second = tmp_path / "b" / "manu"
    for path in (first, second):
        path.parent.mkdir()
        path.touch()

    write_desktop_launcher(first, home=tmp_path)
    outcome = write_desktop_launcher(second, home=tmp_path)

    assert outcome.action == "replaced"
    assert f'MANU_HINT="{second}"' in outcome.path.read_text()
    assert str(first) not in outcome.path.read_text()


def test_write_desktop_launcher_refuses_a_file_it_did_not_write(
    tmp_path: Path,
) -> None:
    """`manu install` writing into `$HOME` is a side effect on somebody's own
    space. Deleting a file because it shares a name is not a trade a
    convenience feature gets to make."""
    from amanuensis.launcher import write_desktop_launcher

    (tmp_path / "Desktop").mkdir()
    theirs = tmp_path / "Desktop" / "Start Amanuensis.command"
    theirs.write_text("#!/bin/bash\n# something a person wrote\n")
    manu = tmp_path / "manu"
    manu.touch()

    outcome = write_desktop_launcher(manu, home=tmp_path)

    assert outcome.action == "refused"
    assert not outcome.ok
    assert theirs.read_text() == "#!/bin/bash\n# something a person wrote\n"


def test_write_desktop_launcher_leaves_a_developers_symlink_alone(
    tmp_path: Path,
) -> None:
    """`--link` points the entry into a checkout so it follows the tree.
    Replacing that with a copy would silently downgrade it to a snapshot --
    which is the exact property this area exists to preserve."""
    from amanuensis.launcher import write_desktop_launcher

    (tmp_path / "Desktop").mkdir()
    entry = tmp_path / "Desktop" / "Start Amanuensis.command"
    entry.symlink_to(PACKAGED)
    manu = tmp_path / "manu"
    manu.touch()

    outcome = write_desktop_launcher(manu, home=tmp_path)

    assert outcome.action == "kept-symlink"
    assert entry.is_symlink(), "a developer's link was replaced by a copy"
    assert entry.resolve() == PACKAGED.resolve()


def test_write_desktop_launcher_refuses_when_there_is_no_desktop(
    tmp_path: Path,
) -> None:
    """Creating directories in someone's home is not this command's business."""
    from amanuensis.launcher import write_desktop_launcher

    manu = tmp_path / "manu"
    manu.touch()

    outcome = write_desktop_launcher(manu, home=tmp_path)

    assert outcome.action == "refused"
    assert "Desktop" in outcome.detail


def test_render_refuses_a_template_it_cannot_substitute() -> None:
    """A launcher written with an empty hint fails at double-click time, for a
    reason nothing observed at install time. Caught where it is cheap."""
    from amanuensis.launcher import render

    with pytest.raises(ValueError, match="MANU_HINT"):
        render(Path("/x/manu"), template="#!/bin/bash\nexit 0\n")


def test_an_installed_copy_ignores_an_unrelated_checkout_above_it(
    tmp_path: Path,
) -> None:
    """Observed while testing a real wheel install, not reasoned about.

    The launcher walks up looking for a checkout, and a Desktop copy has no
    business finding one: a clone at `$HOME` makes `$HOME/Desktop` walk into
    it, and the launcher would then put that tree's `src` on `PYTHONPATH` ahead
    of the environment the user actually installed — running a stranger's code
    under the name of theirs. A recorded hint means this copy was written by
    `manu install`, which settles which situation it is in.
    """
    from amanuensis.launcher import render

    # A checkout at the fake home, exactly as a user with a clone at ~ has.
    (tmp_path / "pyproject.toml").write_text("[project]\nname='decoy'\n")
    (tmp_path / "src" / "amanuensis").mkdir(parents=True)
    desktop = tmp_path / "Desktop"
    desktop.mkdir()

    manu = tmp_path / "env" / "bin" / "manu"
    manu.parent.mkdir(parents=True)
    manu.write_text("#!/bin/bash\nexit 0\n")
    manu.chmod(0o755)

    entry = desktop / "Start Amanuensis.command"
    entry.write_text(render(manu))
    entry.chmod(0o755)

    result = subprocess.run(
        ["bash", str(entry), "--check"],
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp_path)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "not used" in result.stdout, (
        "an installed copy adopted a checkout that merely sits above it:\n"
        + result.stdout
    )
    assert str(manu) in result.stdout
