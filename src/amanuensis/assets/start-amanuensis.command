#!/bin/bash
# amanuensis-launcher: v1
#
# Double-clickable launcher for the Amanuensis daemon.
#
# A `.command` file rather than an `.app` bundle, deliberately. The bundle is
# held in reserve by PRD §5.4 — it ships only if the recording panel fails its
# confidence test — and it changes the *permission identity*: macOS attaches
# Accessibility and Input Monitoring to whatever launches the process.
# Double-clicking this launches it from **Terminal.app**, so Terminal is the app
# that needs both grants — not "Amanuensis", and not whatever terminal you
# usually type in.
#
# The window it opens is also the second way to stop the daemon. The tray's
# "Quit Amanuensis" item is the first; Ctrl-C here is the fallback, and §5.4's
# recorded failure is a daemon that cannot be stopped at all.
#
# ---------------------------------------------------------------------------
# ONE FILE, TWO HOMES, AND NO ABSOLUTE PATH WRITTEN BY HAND.
#
# It lives in the package (`amanuensis/assets/`) so that it ships in the wheel,
# and `scripts/start-amanuensis.command` is a symlink to it so a source checkout
# keeps the familiar path. `manu install` writes a third copy to the Desktop.
#
# It hard-coded its checkout until 2026-09-04. That checkout was a worktree, the
# worktree was removed when its pull request merged, and the copy on the
# operator's Desktop answered `cannot find` for four days. The launcher is the
# one artefact that outlives the tree it was written in, so a path baked into it
# is a path that outlives its target.
#
# It therefore finds things rather than remembering them: it resolves its own
# location through any chain of symlinks, then walks *up* looking for a checkout
# — a directory holding both `pyproject.toml` and `src/amanuensis`. Walking up
# rather than assuming a depth is what lets the same bytes work from
# `scripts/`, from `src/amanuensis/assets/`, and from a Desktop where there is
# no checkout above it at all.
#
# `MANU_HINT` is the one exception and it is written by a program, never by a
# person. A copy on the Desktop has no checkout above it, and a Finder launch
# inherits no shell profile — so `manu` is not on PATH and cannot be found by
# looking. `manu install` therefore records where it put itself. If that path
# later goes stale the script says so and names the command that fixes it,
# rather than failing the way its predecessor did.
#
# `tests/test_launcher.py` fails if a hand-written absolute path reappears, and
# drives `--check` through real symlinks to prove the resolution still works
# rather than merely that the text looks right.
# ---------------------------------------------------------------------------

set -u

# Written by `manu install`. Left empty in the repository and in the wheel.
MANU_HINT=""

# Resolve this script's real location, following a chain of symlinks. `readlink
# -f` would be one line and is not portable to the bash 3.2 that macOS ships
# with; this loop is.
SELF="${BASH_SOURCE[0]}"
while [ -L "$SELF" ]; do
    LINK="$(readlink "$SELF")"
    case "$LINK" in
        /*) SELF="$LINK" ;;
        *)  SELF="$(dirname "$SELF")/$LINK" ;;
    esac
done
HERE="$(cd -- "$(dirname "$SELF")" && pwd -P)"

# Walk up for a checkout rather than assuming how deep this file sits. From
# `scripts/` that is one level; from `src/amanuensis/assets/` it is three; from
# a Desktop it is nowhere, which is a valid answer and not an error.
REPO=""
PROBE="$HERE"
for _ in 1 2 3 4 5 6; do
    if [ -f "$PROBE/pyproject.toml" ] && [ -d "$PROBE/src/amanuensis" ]; then
        REPO="$PROBE"
        break
    fi
    PARENT="$(dirname "$PROBE")"
    [ "$PARENT" = "$PROBE" ] && break
    PROBE="$PARENT"
done

# In order: what `manu install` recorded, the checkout's own virtualenv, then
# PATH. A Finder launch has the bare system PATH and no activated virtualenv,
# so the first two are the cases that actually work when this is double-clicked
# and the third is for a global install.
MANU=""
MANU_SOURCE=""
if [ -n "$MANU_HINT" ] && [ -x "$MANU_HINT" ]; then
    MANU="$MANU_HINT"
    MANU_SOURCE="recorded by manu install"
elif [ -n "$REPO" ] && [ -x "$REPO/.venv/bin/manu" ]; then
    MANU="$REPO/.venv/bin/manu"
    MANU_SOURCE="the checkout's .venv"
elif command -v manu >/dev/null 2>&1; then
    MANU="$(command -v manu)"
    MANU_SOURCE="PATH"
fi

# Run the source next to this launcher rather than whatever a stale install
# resolves to — but only when this file *lives in* that checkout.
#
# A hint means `manu install` wrote this copy, which means it sits on a Desktop
# and any checkout found above it is a coincidence of where the user keeps
# things. Observed: a clone at `$HOME` makes `$HOME/Desktop` walk up into it,
# and this would then put a stranger's `src` ahead of the environment the user
# actually installed. The hint says which situation this is, so it decides.
if [ -n "$REPO" ] && [ -z "$MANU_HINT" ]; then
    export PYTHONPATH="$REPO/src${PYTHONPATH:+:$PYTHONPATH}"
fi

# `--check` reports what was resolved and exits without starting anything. For
# the tests, and for a human working out why a launch went to the wrong tree.
if [ "${1:-}" = "--check" ]; then
    if [ -n "$MANU_HINT" ]; then
        echo "repo:     (not used — an installed copy resolves through its hint)"
    else
        echo "repo:     ${REPO:-(none — an installed copy, which is expected)}"
    fi
    echo "manu:     ${MANU:-NOT FOUND}${MANU:+  ($MANU_SOURCE)}"
    echo "hint:     ${MANU_HINT:-(empty — set by manu install)}"
    [ -n "$MANU" ] || exit 1
    exit 0
fi

# `--link` puts a symlink on the Desktop pointing back into a checkout, so the
# entry follows the checkout instead of snapshotting it. For developers. The
# installed path is `manu install`, which writes a copy with `MANU_HINT` set
# because there is no checkout for it to point at.
if [ "${1:-}" = "--link" ]; then
    if [ -z "$REPO" ]; then
        echo "--link needs a checkout above this file, and there is none."
        echo "This looks like an installed copy. Re-run 'manu install' instead."
        exit 1
    fi
    # `$HERE` and not `$SELF`: `$SELF` is whatever was typed, and
    # `bash scripts/start-amanuensis.command --link` makes that *relative*. A
    # relative symlink target resolves against the link's own directory, so the
    # Desktop entry would have pointed at ~/Desktop/scripts/… and found nothing.
    # Caught by running it. `$HERE` is `pwd -P`, so it is absolute and resolved.
    SOURCE="$HERE/$(basename "$SELF")"
    DESKTOP="$HOME/Desktop"
    TARGET="$DESKTOP/Start Amanuensis.command"

    if [ ! -d "$DESKTOP" ]; then
        echo "No Desktop directory at $DESKTOP."
        exit 1
    fi
    if [ -e "$TARGET" ] && [ ! -L "$TARGET" ]; then
        echo "$TARGET exists and is not a symlink."
        echo "Move it aside first — refusing to overwrite a real file."
        exit 1
    fi

    rm -f "$TARGET"
    # Checked, because `ln` failing while the script prints "linked" is a
    # launcher that reports success and does nothing. It did exactly that once.
    if ! ln -s "$SOURCE" "$TARGET"; then
        echo "could not create $TARGET"
        exit 1
    fi
    echo "linked: $TARGET"
    echo "     -> $SOURCE"
    echo
    echo "It follows this checkout from now on. Nothing to re-copy when the"
    echo "repository changes."
    exit 0
fi

if [ -z "$MANU" ]; then
    echo "Cannot find the 'manu' command."
    echo
    if [ -n "$MANU_HINT" ]; then
        echo "This launcher was written by 'manu install' and points at"
        echo "    $MANU_HINT"
        echo "which is no longer there — the environment it was installed into"
        echo "has moved or been deleted."
        echo
        echo "Re-run 'manu install' to rewrite this file."
    else
        [ -n "$REPO" ] && echo "Looked in $REPO/.venv/bin and then on PATH." \
                       || echo "Looked on PATH, and found no checkout above this file."
        echo
        echo "Install it first — see the README:"
        echo
        echo "    python3.12 -m venv .venv && source .venv/bin/activate"
        echo "    pip install ."
        echo "    manu install"
    fi
    echo
    read -r -p "Press return to close."
    exit 1
fi

[ -n "$REPO" ] && cd "$REPO"

# Two daemons share one hotkey and would both inject and both persist every
# dictation. The socket guard in the daemon is the real lock; this is the
# friendlier message, and `manu status` answers from a running one.
if "$MANU" status >/dev/null 2>&1; then
    echo "A daemon is already running:"
    echo
    "$MANU" status
    echo
    echo "Two daemons share one hotkey — both would type your words twice and"
    echo "store them twice. Quit the other one from its menu-bar icon first."
    echo
    read -r -p "Press return to close."
    exit 1
fi

echo "Amanuensis — hold RIGHT OPTION to dictate."
echo
echo "  Stop it from the menu-bar icon: click it, then 'Quit Amanuensis'."
echo "  Or press Ctrl-C in this window."
echo
echo "  While recording you should see a panel near the bottom of the screen."
echo

exec "$MANU" daemon
