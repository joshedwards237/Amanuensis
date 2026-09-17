"""The install script, checked against the product it installs.

`scripts/bootstrap.sh` shipped untested on 2026-09-16 and a tester's install
died at step 5 on three defects at once: it guarded a path nothing writes, it
generated the reference clip *after* a non-editable `pip install .` had already
copied the package to site-packages, and it swallowed the generator's errors.

None of the three is reachable by running the script here — it wants the
network, a fresh machine and several minutes — so these are static checks
against the text. That is a real limit and it is stated rather than papered
over: this file can prove the script *says* the right thing, not that a clean
machine gets through it. The end-to-end reading is lane 6's.

The load-bearing assertion is the first one. It re-derives the clip path from
`tier.default_clip_path()` — the function the product actually calls — rather
than restating the literal, because a test that hardcodes the same string
twice agrees with itself for free.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from amanuensis import launcher, tier

REPO = Path(__file__).resolve().parent.parent
BOOTSTRAP = REPO / "scripts/bootstrap.sh"


@pytest.fixture(scope="module")
def script() -> str:
    return BOOTSTRAP.read_text()


def _clip_assignment(script: str) -> str:
    match = re.search(r'^CLIP="([^"]+)"', script, re.MULTILINE)
    assert match, "bootstrap.sh no longer assigns CLIP"
    return match.group(1)


def test_the_clip_path_is_where_the_product_looks_for_it(script: str) -> None:
    """The defect that cost the install, stated as an invariant.

    `tier.default_clip_path()` resolves inside the *installed* package. The
    script generates into the *checkout*. Those are different directories under
    a non-editable install, which is what step 4 performs — so the script must
    pass the path explicitly, and the path it passes must be the checkout's
    copy of the same relative location.
    """
    relative = tier.default_clip_path().relative_to(
        Path(tier.__file__).resolve().parent
    )
    assert _clip_assignment(script).endswith(f"src/amanuensis/{relative}")


def test_manu_install_is_given_the_clip_explicitly(script: str) -> None:
    """Without `--clip`, `manu install` reads the site-packages copy, which a
    fresh clone never has: the file is gitignored, so only machines that have
    already generated one are unaffected. Every development machine has one.
    """
    assert '"$MANU" install --clip "$CLIP"' in script


def test_clip_generation_failures_are_not_swallowed(script: str) -> None:
    """`>/dev/null 2>&1 || true` made a failed generation indistinguishable
    from a successful one, and the script continued to a step that could only
    fail because of it. stdout may be quiet; stderr and the exit status may
    not.
    """
    line = next(
        line
        for line in script.splitlines()
        if "make_tier_clip.sh" in line and "./" in line
    )
    assert "|| true" not in line, "a failed generation must stop the script"
    assert "2>&1" not in line, "stderr must survive"


def test_the_script_is_valid_bash() -> None:
    """A syntax error here is only discoverable on a stranger's machine."""
    bash = shutil.which("bash")
    assert bash, "bash is required to check the install script"
    result = subprocess.run(
        [bash, "-n", str(BOOTSTRAP)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# What the script tells the user to do when it is finished (2026-09-17)
# ---------------------------------------------------------------------------


def _closing_message(script: str) -> str:
    """Everything after the script declares success."""
    marker = "Installed."
    assert marker in script, "the script no longer announces success"
    return script[script.index(marker) :]


def _launcher_probe(script: str) -> str:
    """The Python the script runs to decide whether the launcher is there."""
    marker = "<<'PYLAUNCHER'"
    assert marker in script, "the launcher probe is gone"
    body = script[script.index(marker) + len(marker) :]
    # The heredoc opener carries a redirect after it; the script starts at the
    # newline, not at the marker.
    body = body[body.index("\n") + 1 :]
    return body[: body.index("PYLAUNCHER")]


def test_the_launcher_probe_finds_a_real_launcher(
    script: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive control, run rather than matched.

    The name carries a space and a `.command` extension, and a user told to
    look for the wrong one finds nothing on a Desktop that has the right one.
    Asserting the script contains the literal would have agreed with itself —
    the script builds the name with `basename` on the path this probe prints,
    so the only thing worth checking is what the probe prints.
    """
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    target = desktop / launcher.desktop_launcher_path().name
    target.write_text("#!/bin/sh\n")
    target.chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path))

    result = subprocess.run(
        [sys.executable, "-c", _launcher_probe(script)],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(tmp_path), "PYTHONPATH": str(REPO / "src")},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(target)


def test_the_launcher_probe_stays_silent_when_there_is_nothing_to_click(
    script: str, tmp_path: Path
) -> None:
    """Negative control. Without it the positive one is passed by `print(path)`.

    Two ways to have nothing worth announcing: no file at all, and a file
    without the execute bit — Finder opens that one in a text editor, which
    looks to the user exactly like the product being broken. Both must print
    nothing, and the second is the one a bare existence check gets wrong.
    """
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    probe = _launcher_probe(script)
    env = {**os.environ, "HOME": str(tmp_path), "PYTHONPATH": str(REPO / "src")}

    absent = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, env=env
    )
    assert absent.stdout.strip() == "", "announced a launcher that is not there"

    target = desktop / launcher.desktop_launcher_path().name
    target.write_text("#!/bin/sh\n")
    target.chmod(0o644)
    not_executable = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, env=env
    )
    assert (
        not_executable.stdout.strip() == ""
    ), "announced a launcher Finder will open in a text editor"


def test_the_launcher_is_offered_before_the_daemon_command(script: str) -> None:
    """Double-clicking is the primary route; `manu daemon` is the fallback.

    A terminal command as the headline instruction asks someone who has just
    been walked through their first `curl` to keep a terminal habit in order to
    dictate. The launcher exists precisely so they do not have to, and a
    closing message that leads with the command buries it.
    """
    closing = _closing_message(script)
    assert closing.index("LAUNCHER_PATH") < closing.index(
        "daemon"
    ), "the daemon command is offered before the Desktop launcher"


def test_the_launcher_is_only_promised_when_it_exists(script: str) -> None:
    """`write_desktop_launcher` refuses when there is no Desktop directory, so
    the file is not guaranteed and the script must not assume it.

    This is the defect that killed the last install in a different costume:
    announcing a path without checking it. A missing launcher is not fatal —
    `manu daemon` still works — so the script branches rather than dying.
    """
    closing = _closing_message(script)
    assert "LAUNCHER_PRESENT" in script, "no check guards the launcher message"
    assert "if [[ $LAUNCHER_PRESENT -eq 1 ]]" in closing


def test_the_launcher_check_asks_the_product_for_the_path(script: str) -> None:
    """`desktop_launcher_path()` and `is_executable()`, not a hand-built path.

    Finder runs a `.command` only if the execute bit is set and silently opens
    it in a text editor otherwise, which looks to the user exactly like the
    product being broken. Both facts belong to `launcher.py`; a second
    implementation here can disagree with the one that matters.
    """
    assert "desktop_launcher_path()" in script
    assert "is_executable" in script
