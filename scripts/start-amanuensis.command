#!/bin/bash
# Double-clickable launcher for the Amanuensis daemon.
#
# A `.command` file rather than an `.app` bundle, deliberately. The bundle is
# PRD §9 Phase 4 work that is currently deferred pending §5.4's confidence
# test, and it changes the *permission identity*: macOS attaches Accessibility
# and Input Monitoring to whatever launches the process. Double-clicking this
# launches it from **Terminal.app**, so Terminal is the app that needs both
# grants — not "Amanuensis", and not whatever terminal you usually use.
#
# The window it opens is also the second way to stop the daemon. The tray's
# "Quit Amanuensis" item is the first; Ctrl-C here is the fallback, and §5.4's
# recorded failure is a daemon that cannot be stopped at all.

set -u

REPO="/Users/joshuaedwards/Development/personal/worktrees/phase-4-tray-modes"
VENV="/Users/joshuaedwards/Development/personal/Amanuensis/.venv/bin"

cd "$REPO" || { echo "cannot find $REPO"; read -r -p "Press return to close."; exit 1; }
export PYTHONPATH="$REPO/src"

# Two daemons share one hotkey and would both inject and both persist every
# dictation. `manu status` answers from a running one, which is the cheapest
# way to know before starting a second.
if "$VENV/manu" status >/dev/null 2>&1; then
    echo "A daemon is already running:"
    echo
    "$VENV/manu" status
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

exec "$VENV/manu" daemon
