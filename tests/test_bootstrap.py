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

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from amanuensis import tier

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
