#!/bin/bash
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
# THIS FILE CONTAINS NO ABSOLUTE PATHS, AND THAT IS THE POINT.
#
# It used to hard-code the checkout it was written against. On 2026-09-04 that
# checkout was a worktree, the worktree was removed when its PR merged, and the
# copy sitting on the operator's Desktop began failing with `cannot find`. The
# launcher is the one artefact that survives the tree it was built in, so a path
# baked into it is a path that outlives its target.
#
# It now finds the repository by resolving its own location, following symlinks
# — which is what lets the Desktop copy *be* a symlink into the checkout rather
# than a snapshot of it. Update the checkout, and the launcher follows. There is
# nothing to re-copy, so there is nothing to forget to re-copy.
#
# `tests/test_launcher.py` fails if an absolute path reappears here, and drives
# `--check` through a symlink in a temporary directory to prove the resolution
# still works rather than merely that the text looks right.
# ---------------------------------------------------------------------------

set -u

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
REPO="$(cd -- "$HERE/.." && pwd -P)"

# The repository's own virtualenv first, then whatever is on PATH. A Finder
# launch inherits no shell profile, so PATH is the bare system one and an
# activated venv is not in it — the explicit path is the case that actually
# works when this is double-clicked.
if [ -x "$REPO/.venv/bin/manu" ]; then
    MANU="$REPO/.venv/bin/manu"
elif command -v manu >/dev/null 2>&1; then
    MANU="$(command -v manu)"
else
    MANU=""
fi

# Run the source next to this launcher rather than whatever a stale install
# resolves to. Guarded on the directory existing so that a pip-installed copy
# with no checkout beside it still works.
if [ -d "$REPO/src/amanuensis" ]; then
    export PYTHONPATH="$REPO/src${PYTHONPATH:+:$PYTHONPATH}"
fi

# `--check` reports what was resolved and exits without starting anything. For
# the test, and for a human working out why a launch went to the wrong tree.
if [ "${1:-}" = "--check" ]; then
    echo "repo:     $REPO"
    echo "manu:     ${MANU:-NOT FOUND}"
    echo "src:      $([ -d "$REPO/src/amanuensis" ] && echo "$REPO/src" || echo "(none — using the installed package)")"
    [ -n "$MANU" ] || exit 1
    exit 0
fi

# `--link` puts a symlink on the Desktop. A symlink and not a copy: a copy is a
# snapshot of the checkout at the moment it was made, which is precisely how the
# Desktop entry went stale. Re-runnable — it replaces its own previous link and
# refuses to touch anything that is not one.
if [ "${1:-}" = "--link" ]; then
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
    echo "Looked for $REPO/.venv/bin/manu and then on PATH."
    echo "Install it first — see the README:"
    echo
    echo "    cd $REPO"
    echo "    python3.12 -m venv .venv && source .venv/bin/activate"
    echo "    pip install ."
    echo
    read -r -p "Press return to close."
    exit 1
fi

cd "$REPO" || { echo "cannot enter $REPO"; read -r -p "Press return to close."; exit 1; }

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
