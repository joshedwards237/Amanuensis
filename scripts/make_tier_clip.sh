#!/usr/bin/env bash
# Generate the reference clip the install-time tier check times against (PRD §7.2).
#
# §7.2 specifies "a bundled 10-second reference clip, shipped with the app.
# Not the user's voice — the check must be reproducible and must not require a
# microphone permission before first use."
#
# The repository does not ship one. That is not an oversight, it is an open
# item recorded in docs/gates/phase-1.md: the clip has to be speech (Whisper's
# decoder time scales with the tokens it emits, and it repetition-loops on
# silence, so a synthetic tone would measure the failure mode rather than the
# product), and the two ways to get speech both have a problem. A recording of
# a person cannot be unpublished once it is in a public repo — the same
# reasoning that gitignores the desk-mic corpus. And macOS `say` output, which
# is what this script uses, has no clear redistribution grant.
#
# So: generate it locally, measure with it, and settle the provenance before
# Phase 4 packages anything. The generated file is gitignored.
#
# Usage:
#     scripts/make_tier_clip.sh [output.wav]

set -euo pipefail

OUT="${1:-src/amanuensis/assets/tier_check.wav}"
VOICE="${AMANUENSIS_TIER_CLIP_VOICE:-Samantha}"

# Roughly ten seconds at a natural rate, and deliberately ordinary prose — the
# clip is a latency instrument, not an accuracy one, but a decoder given
# unusual vocabulary emits more tokens and therefore takes longer, which would
# make the tier boundary depend on how strange this paragraph is.
#
# Length was tuned to land near ten seconds at the default voice and rate; the
# check below warns if it drifts, because G1 is defined against a ten-second
# utterance and a clip of a different length is measuring something else.
TEXT="The tier check measures how long this machine takes to turn ten seconds \
of speech into text. It runs once, when Amanuensis is installed, and the \
result is written down and never sent anywhere."

if ! command -v say >/dev/null 2>&1; then
    echo "error: this script needs macOS 'say'." >&2
    echo "Point the check at your own ten-second recording instead:" >&2
    echo "    manu install --clip /path/to/clip.wav" >&2
    exit 1
fi

mkdir -p "$(dirname "$OUT")"
TMP="$(mktemp -t amanuensis-tier).aiff"
trap 'rm -f "$TMP"' EXIT

say -v "$VOICE" -o "$TMP" "$TEXT"

# 16 kHz mono 16-bit PCM — the one format the pipeline accepts end to end
# (config.py pins [audio] sample_rate for the same reason).
if command -v ffmpeg >/dev/null 2>&1; then
    ffmpeg -loglevel error -y -i "$TMP" -ar 16000 -ac 1 -c:a pcm_s16le "$OUT"
else
    afconvert -f WAVE -d LEI16@16000 -c 1 "$TMP" "$OUT"
fi

python3 - "$OUT" <<'PY'
import sys, wave
with wave.open(sys.argv[1], "rb") as handle:
    seconds = handle.getnframes() / handle.getframerate()
    print(f"{sys.argv[1]}: {seconds:.1f}s, {handle.getframerate()} Hz, "
          f"{handle.getnchannels()} channel(s)")
if not 8.0 <= seconds <= 12.0:
    print(f"warning: G1 is defined against a ten-second utterance (PRD §2); "
          f"this clip is {seconds:.1f}s", file=sys.stderr)
PY
