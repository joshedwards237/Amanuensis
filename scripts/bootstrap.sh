#!/bin/bash
#
# Amanuensis — the install lane (PRD §9, Phase 4i).
#
# This exists because two people attempted the README unaided and neither
# reached a dictation. The second never reached a `git clone`: on a Mac that has
# never built software there is no `git`, and before that Terminal itself needed
# permission to touch the folder being cloned into. Step 1 of the README had
# three prerequisites stacked in one code block and mentioned none of them.
#
# So this script's job is not convenience. It is to make every prerequisite
# visible, say what each system dialog is before it appears, and refuse to
# report success into an install that does not work.
#
# Run it with:
#
#     curl -fsSL https://raw.githubusercontent.com/joshedwards237/Amanuensis/main/scripts/bootstrap.sh | bash
#
# or, from a checkout you already have:
#
#     ./scripts/bootstrap.sh
#
# Design rules it follows, each from the Phase 4i gate:
#
#   - **Nothing installs without being announced first.** Every step that
#     changes the machine prints what it is about to do and what dialog will
#     appear, then asks. A user who has never opened Terminal cannot tell an
#     expected prompt from a hijack, and the only difference is whether
#     something told them in advance.
#   - **No `sudo`, anywhere.** Python is installed through Apple's own GUI
#     installer, which asks for an administrator password itself in the dialog
#     a Mac user already recognises. A script that collects a password is
#     teaching a habit worth more than the ten seconds it saves.
#   - **It must never exit 0 into a broken install.** The last thing it does is
#     run the product and check the answer. Reporting success into something
#     that does not dictate is §5.7's failure one layer out: a green light over
#     a thing that did not happen.
#   - **Safe to run twice.** Every step checks before it acts, so a second run
#     over a finished install changes nothing and says so.
#
# What it deliberately does NOT do: grant permissions. macOS does not permit
# that and should not. It raises the prompts and opens the right panes; the
# clicking is the user's, and the README says which row to look for.

set -euo pipefail

REPO_URL="https://github.com/joshedwards237/Amanuensis.git"
# Pinned rather than "latest": the newest macOS package python.org publishes for
# 3.12, verified to exist at the time of writing. A moving target would make
# this script's behaviour depend on the day it ran.
PY_VERSION="3.12.10"
PY_PKG="python-${PY_VERSION}-macos11.pkg"
PY_URL="https://www.python.org/ftp/python/${PY_VERSION}/${PY_PKG}"

BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'

step()  { printf '\n%s==> %s%s\n' "$BOLD" "$1" "$RESET"; }
info()  { printf '    %s\n' "$1"; }
dim()   { printf '    %s%s%s\n' "$DIM" "$1" "$RESET"; }
ok()    { printf '    %s✓%s %s\n' "$GREEN" "$RESET" "$1"; }
warn()  { printf '    %s!%s %s\n' "$YELLOW" "$RESET" "$1"; }
die()   { printf '\n%sStopped:%s %s\n\n' "$RED" "$RESET" "$1" >&2; exit 1; }

# Asks before anything that changes the machine. Defaults to no: a user who
# hits return because they have stopped reading should not thereby install
# something.
confirm() {
    local reply=""
    printf '    %s[y/N]%s ' "$BOLD" "$RESET"
    # `< /dev/tty` because this script is designed to be piped from curl, where
    # stdin is the script itself and `read` would silently consume it.
    read -r reply < /dev/tty || true
    [[ "$reply" =~ ^[Yy]$ ]]
}

require_network() {
    curl -fsS --head --max-time 10 https://www.python.org >/dev/null 2>&1 \
        || die "no network. This step downloads from python.org and GitHub; the
    product itself never uses the network once installed (goal G3)."
}

# ---------------------------------------------------------------------------
# 0. Where are we
# ---------------------------------------------------------------------------

printf '\n%sAmanuensis — install%s\n' "$BOLD" "$RESET"
dim "Fully local dictation. This sets up everything it needs and stops if it cannot."

[[ "$(uname -s)" == "Darwin" ]] || die "macOS only (PRD §3). This is $(uname -s)."
MACOS_VERSION="$(sw_vers -productVersion)"
info "macOS ${MACOS_VERSION}"

# Recorded rather than acted on. `CGRequestListenEventAccess` raised no dialog on
# 26.6 (gate finding 4b); `IOHIDRequestAccess` replaced it on 2026-09-17 and is
# **unverified on 26.x** — both development machines run 27.0 holding both
# grants, so neither can see this fail. Worded to be honest whichever way it
# goes, because a promise that does not come true at the last step is worse than
# no promise.
case "$MACOS_VERSION" in
    26.*) warn "on macOS 26.x the Input Monitoring prompt has failed to appear before."
          dim  "A different API is used as of 2026-09-17 and it has not yet been"
          dim  "confirmed on 26.x. If no dialog appears, add Terminal by hand with"
          dim  "the + button — step 5 of the README has the procedure."
          dim  "Either way, \`scripts/diagnose_permissions.py\` will say what happened." ;;
esac

# ---------------------------------------------------------------------------
# 1. The Xcode Command Line Tools — where the second tester stopped
# ---------------------------------------------------------------------------

step "1/6  Developer tools (this is what provides \`git\`)"

if xcode-select -p >/dev/null 2>&1 && command -v git >/dev/null 2>&1; then
    ok "already installed"
else
    info "Not installed. macOS keeps \`git\` inside Apple's Command Line Tools,"
    info "so nothing can be downloaded from GitHub until they are present."
    info ""
    info "A macOS dialog titled \"Install Command Line Developer Tools\" will"
    info "appear. It is Apple's, not ours. It downloads about 1 GB and can take"
    info "several minutes. Install it?"
    confirm || die "nothing was changed. \`git\` is required; re-run when ready."

    xcode-select --install >/dev/null 2>&1 || true
    info ""
    info "Waiting for the install to finish — click through the dialog."
    dim  "(this window will continue by itself; Ctrl-C to abandon)"
    # Poll rather than trusting the trigger: `xcode-select --install` returns
    # immediately and an interrupted or declined install is indistinguishable
    # from a slow one except by looking.
    for _ in $(seq 1 240); do
        if xcode-select -p >/dev/null 2>&1 && command -v git >/dev/null 2>&1; then
            break
        fi
        sleep 5
    done
    if ! command -v git >/dev/null 2>&1; then
        die "the developer tools did not finish installing (or were cancelled).
    Re-run this script once the Apple installer has completed."
    fi
    ok "installed"
fi

# ---------------------------------------------------------------------------
# 2. Python 3.12
# ---------------------------------------------------------------------------

step "2/6  Python 3.12"

find_python() {
    local candidate
    for candidate in python3.12 python3.13 python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 12) else 1)' 2>/dev/null; then
                command -v "$candidate"
                return 0
            fi
        fi
    done
    return 1
}

if PYTHON="$(find_python)"; then
    ok "$("$PYTHON" --version) at $PYTHON"
else
    info "Amanuensis needs Python 3.12 or newer. The version macOS ships with"
    info "the developer tools is older, so one has to be installed."
    info ""
    info "This downloads Apple-signed installer ${PY_PKG} from python.org and"
    info "opens it. **Apple's installer will ask for your password** — that is"
    info "the normal macOS admin prompt, and this script never sees it."
    confirm || die "nothing was changed. Python 3.12 is required; re-run when ready."

    require_network
    PKG_PATH="$(mktemp -d)/${PY_PKG}"
    info "Downloading (about 60 MB)..."
    curl -fL --progress-bar -o "$PKG_PATH" "$PY_URL" \
        || die "the download failed. Check the connection and re-run."

    # Verified by signature rather than by a hash pinned in this file. A hash
    # would have to be updated by hand every release and would be wrong exactly
    # when nobody was looking; the signature check asks macOS whether the
    # Python Software Foundation signed this package, which stays true.
    info "Checking the signature..."
    if pkgutil --check-signature "$PKG_PATH" 2>/dev/null | grep -qi 'Python Software Foundation'; then
        ok "signed by the Python Software Foundation"
    else
        die "that package is not signed by the Python Software Foundation.
    It has not been opened. Nothing was installed."
    fi

    open -W "$PKG_PATH"
    if ! PYTHON="$(find_python)"; then
        die "Python 3.12 still is not available. If the installer was cancelled,
    re-run this script; if it completed, open a new Terminal window and re-run."
    fi
    ok "$("$PYTHON" --version) at $PYTHON"
fi

# ---------------------------------------------------------------------------
# 3. The source
# ---------------------------------------------------------------------------

step "3/6  The Amanuensis source"

# Run from inside a checkout, use it. Piped from curl, clone into the user's
# home rather than wherever the shell happens to be — the second tester was in
# ~/Documents, which is a folder macOS guards, and a clone into a guarded folder
# is a permission dialog nobody explained.
if [[ -f "pyproject.toml" ]] && grep -q '^name = "amanuensis"' pyproject.toml 2>/dev/null; then
    CHECKOUT="$PWD"
    ok "using the checkout you are in: $CHECKOUT"
else
    CHECKOUT="$HOME/Amanuensis"
    if [[ -d "$CHECKOUT/.git" ]]; then
        ok "already cloned at $CHECKOUT"
    else
        info "Cloning into $CHECKOUT"
        dim  "(your home folder, deliberately — macOS guards Documents, Desktop"
        dim  " and Downloads, and a clone into one of those raises a permission"
        dim  " dialog that has nothing to do with this product)"
        require_network
        git clone --quiet "$REPO_URL" "$CHECKOUT" \
            || die "the clone failed. Check the connection and re-run."
        ok "cloned"
    fi
fi
cd "$CHECKOUT"

# ---------------------------------------------------------------------------
# 4. The environment
# ---------------------------------------------------------------------------

step "4/6  Installing Amanuensis"

if [[ ! -d ".venv" ]]; then
    "$PYTHON" -m venv .venv || die "could not create the virtual environment in $CHECKOUT/.venv"
fi
info "Installing into $CHECKOUT/.venv — nothing is installed system-wide."
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install --quiet . || die "the install failed. The output above says why."
MANU="$CHECKOUT/.venv/bin/manu"
[[ -x "$MANU" ]] || die "the install reported success but produced no \`manu\` command."
ok "installed"

# ---------------------------------------------------------------------------
# 5. The model, and this machine's speed
# ---------------------------------------------------------------------------

step "5/6  The speech model"

info "This is the only time Amanuensis uses the network. It downloads the"
info "speech model once, checks it against a hash this project recorded, and"
info "times your machine. After this the product never connects to anything."
info "Expect a few minutes."

# The reference clip the timed check measures against (PRD §7.2). Three things
# here were wrong on 2026-09-16 and cost a tester the install:
#
#   1. The guard tested `tests/fixtures/tier-clip.wav`. `make_tier_clip.sh`
#      writes `src/amanuensis/assets/tier_check.wav`. Nothing has ever written
#      the path being guarded, so the guard was decorative.
#   2. Step 4 installs NON-EDITABLE, so the package is copied into
#      site-packages before this runs, and `tier.py`'s `default_clip_path()`
#      resolves inside that copy. A clip generated into the checkout afterwards
#      can never reach it. Passing `--clip` sidesteps the packaging question
#      entirely and works editable or not.
#   3. Errors were swallowed by `>/dev/null 2>&1 || true`, so a failed
#      generation was indistinguishable from a successful one.
#
# None of it was visible here: the file is gitignored and every development
# machine already has one, which is the same shape as the permission grants
# both machines already held.
CLIP="$CHECKOUT/src/amanuensis/assets/tier_check.wav"
if [[ ! -f "$CLIP" ]]; then
    [[ -x "scripts/make_tier_clip.sh" ]] \
        || die "the reference clip is missing and scripts/make_tier_clip.sh is not
    executable. Re-clone, or point the check at a ten-second recording of your
    own with: $MANU install --clip /path/to/clip.wav"
    dim "Generating the reference clip with the macOS \`say\` voice (no microphone)..."
    ./scripts/make_tier_clip.sh "$CLIP" >/dev/null \
        || die "could not generate the reference clip. The output above says why.
    You can supply your own ten-second recording instead:
        $MANU install --clip /path/to/clip.wav"
fi
[[ -f "$CLIP" ]] || die "the reference clip was reported generated and is not at
    $CLIP. This is a bug — please report it."

require_network
"$MANU" install --clip "$CLIP" || die "\`manu install\` failed. The output above says why.
    Nothing is broken — re-run this script to try again."
ok "model downloaded and verified"

# ---------------------------------------------------------------------------
# 6. Permissions — raised, never granted
# ---------------------------------------------------------------------------

step "6/6  macOS permissions"

info "Amanuensis needs two permissions, and macOS grants them to the"
info "application that launched it — which is **Terminal**, not Amanuensis."
info "So the row you are looking for in System Settings says \"Terminal\"."
info ""
info "  Accessibility     — lets it type your words into other apps"
info "  Input Monitoring  — lets it see the hotkey you press"
info ""
info "Starting the daemon now. It will ask for whichever it does not have."
dim  "Answer the dialogs, then this script will check what you granted."
info ""

# The daemon raises both prompts and exits non-zero when a grant is missing,
# which is the documented behaviour and not a failure of this script.
"$MANU" daemon >/dev/null 2>&1 || true

open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" 2>/dev/null || true

# ---------------------------------------------------------------------------
# The check that makes this script trustworthy
# ---------------------------------------------------------------------------

step "Checking the install actually works"

FAILED=0
if "$MANU" --version >/dev/null 2>&1; then
    ok "the \`manu\` command runs"
else
    warn "the \`manu\` command does not run"; FAILED=1
fi

if "$MANU" history --limit 1 >/dev/null 2>&1; then
    ok "the transcript store is readable"
else
    warn "the transcript store could not be opened"; FAILED=1
fi

# **The check this script nearly shipped without.** An earlier version verified
# that `manu` ran and that the database opened, and reported "Installed" — on a
# machine where the model download had never happened. Found by running the
# script with `manu install` stubbed out and watching it congratulate itself.
# That is precisely what the Phase 4i gate rejects: exiting 0 into an install
# that does not dictate.
#
# It asks the product's own resolver rather than looking for files. Weights live
# in a Hugging Face cache whose layout is not this script's business, and a
# reimplemented path check is a second implementation that can disagree with the
# one that matters.
if "$CHECKOUT/.venv/bin/python" - <<'PYCHECK' >/dev/null 2>&1
from amanuensis.config import AppConfig
from amanuensis.engines.faster_whisper import (
    resolve_device,
    resolve_model_name,
    resolve_model_path,
)

config = AppConfig()
device = resolve_device(config.engine.device)
resolve_model_path(resolve_model_name(config.engine.model, device))
PYCHECK
then
    ok "the speech model is on disk and resolvable"
else
    warn "the speech model is not available — dictation cannot work"; FAILED=1
fi

if [[ $FAILED -ne 0 ]]; then
    die "the install is not working. Nothing above is a permission problem —
    those are expected at this stage. Send this whole output to whoever
    pointed you here."
fi

printf '\n%sInstalled.%s\n\n' "$GREEN$BOLD" "$RESET"
info "Start dictating:"
printf '\n      %s\n\n' "$MANU daemon"
info "Then hold **right-option**, speak, and release. Your words appear"
info "wherever your cursor is."
info ""
info "If nothing happens when you hold the key, the permissions above are not"
info "granted yet — the daemon prints which one is missing when it starts."
dim  "Full instructions, including how to change the hotkey: $CHECKOUT/README.md"
printf '\n'
