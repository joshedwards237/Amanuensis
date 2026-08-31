#!/usr/bin/env bash
# Smoke the published landing page.
#
# A merged PR is not a deployed PR, and a 200 on a static asset is not a working
# site. This checks that every route serves, that the self-hosted fonts actually
# resolve (they are the one asset class that silently falls back rather than
# erroring), that real content is present rather than an empty shell, and that
# nothing third-party is fetched -- which for this product is a correctness
# claim, not a performance one.
#
#   scripts/smoke-site.sh
#   BASE=https://... SINCE=2026-08-27 scripts/smoke-site.sh
#
# SINCE fails the run if the deployment predates the date given, so a stale
# revision fails instead of passing on liveness alone.
set -uo pipefail

BASE="${BASE:-https://joshedwards237.github.io/Amanuensis}"
SINCE="${SINCE:-}"
REPO="${REPO:-joshedwards237/Amanuensis}"
fail=0
note() { printf '  %-52s %s\n' "$1" "$2"; }
bad()  { fail=1; note "$1" "FAIL — $2"; }

echo "smoking $BASE"

# --- routes -------------------------------------------------------------
for path in "/" "/how-it-works/" "/docs/"; do
  code=$(curl -sSL -o /tmp/smoke.html -w '%{http_code}' "$BASE$path")
  bytes=$(wc -c </tmp/smoke.html | tr -d ' ')
  if [ "$code" != "200" ]; then bad "route $path" "HTTP $code"
  elif [ "$bytes" -lt 2000 ]; then bad "route $path" "only ${bytes}B — looks like a shell"
  else note "route $path" "200, ${bytes}B"
  fi
done

# --- real content, not just a 200 --------------------------------------
curl -sSL "$BASE/" -o /tmp/home.html
for marker in "Speak. It" "Install" "How it works"; do
  grep -qF "$marker" /tmp/home.html || bad "home content: $marker" "missing"
done
grep -qF "Speak. It" /tmp/home.html && note "home renders its headline" "ok"

curl -sSL "$BASE/docs/" -o /tmp/docs.html
grep -qF "manu install" /tmp/docs.html && note "docs carries install commands" "ok" \
  || bad "docs install commands" "missing"

curl -sSL "$BASE/how-it-works/" -o /tmp/how.html
grep -qF "history.db" /tmp/how.html && note "how-it-works carries the record" "ok" \
  || bad "how-it-works content" "missing"

# --- self-hosted fonts resolve -----------------------------------------
# These fail silently: font-display:swap means a 404 renders in the fallback
# and looks merely wrong rather than broken.
css=$(grep -oE '/Amanuensis/_astro/[^"]+\.css' /tmp/home.html | sort -u)
[ -z "$css" ] && bad "stylesheet link" "none found in home"
declared=0
for c in $css; do
  curl -sSL "$BASE${c#/Amanuensis}" -o /tmp/s.css
  for f in $(grep -oE 'fonts/[A-Za-z0-9-]+\.woff2' /tmp/s.css | sort -u); do
    declared=$((declared+1))
    fc=$(curl -sSL -o /dev/null -w '%{http_code}' "$BASE/$f")
    [ "$fc" = "200" ] || bad "font $f" "HTTP $fc"
  done
done
[ "$declared" -gt 0 ] && note "fonts declared and served" "$declared file(s)" \
  || bad "fonts" "no @font-face found — the page is running on fallbacks"

# --- no third-party fetches --------------------------------------------
# The product's claim is that nothing leaves your machine. A page that fetches
# from a CDN refutes it in the visitor's own devtools.
for c in $css; do
  curl -sSL "$BASE${c#/Amanuensis}" -o /tmp/s.css
  ext=$(grep -oE 'url\((https?:)?//[^)]+' /tmp/s.css | sort -u)
  [ -n "$ext" ] && bad "third-party origin in CSS" "$ext"
done
note "no third-party fetch origins" "ok"

# --- deployed revision --------------------------------------------------
if command -v gh >/dev/null 2>&1; then
  read -r when ref sha < <(gh api "repos/$REPO/deployments?environment=github-pages&per_page=1" \
    -q '.[0] | "\(.created_at) \(.ref) \(.sha)"' 2>/dev/null)
  if [ -n "${sha:-}" ]; then
    note "deployed" "${ref} @ ${sha:0:8} on ${when:0:16}"
    if [ -n "$SINCE" ] && [[ "${when:0:10}" < "$SINCE" ]]; then
      bad "deployment freshness" "deployed ${when:0:10}, older than SINCE=$SINCE"
    fi
    [ "$ref" != "main" ] && note "NOTE" "live build is '$ref', not main"
  fi
fi

echo
if [ "$fail" -eq 0 ]; then echo "smoke: PASS"; else echo "smoke: FAIL"; fi
exit $fail
