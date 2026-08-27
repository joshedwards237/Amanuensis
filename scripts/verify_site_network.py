"""Prove the built page fetches nothing from anywhere (SITE_PRD §12.2).

The page's most-repeated claim is that nothing leaves your machine. A landing
page for it that pulls a stylesheet from a CDN is refuted by its own devtools
panel — and an earlier revision of the spec did worse than that, carving the
font host out of the acceptance criterion that would have caught it. An
exemption written into the verifier rather than into the design is how a check
comes to pass on a page that violates the constraint it exists to enforce.

There are no exemptions here.

What this checks, and what it does not
---------------------------------------
This is **static analysis of the built output**, not a browser. It parses
`dist/` and fails if any fetchable position names an origin other than the
page's own: `src`, `href` on a stylesheet or preload, `@import`, `url()` in
CSS, `fetch(`, `XMLHttpRequest`, `new WebSocket`, `navigator.sendBeacon`,
`importScripts`.

**The gap, stated rather than papered over:** SITE_PRD §12.2 criterion 12 also
requires the *interaction* surface to be covered — a beacon on
`visibilitychange`, or a fetch behind the receipt disclosure, is invisible to
anything that only reads the shipped bytes. Closing that needs a headless
browser driving the widget's controls, which would add a dependency this repo
does not have. **Criterion 12 is therefore NOT met by this script**, and saying
so here is the point: a check that silently covers less than its criterion is
the failure mode this whole file exists to argue against. Run a browser pass
before the first public deploy, or accept the gap knowingly.

Two controls, per instrument
-----------------------------
`scripts/verify_g3.py` is the standard being imitated, and its lesson is that a
control exercising one instrument licenses a clean reading from another. So:

- **Positive control.** A synthetic page containing a known third-party origin
  MUST be flagged. If it is not, the scanner is not scanning, and its silence
  on the real output means nothing.
- **Negative control.** A synthetic page whose only references are same-origin
  MUST NOT be flagged. Without it, a scanner that flags everything would also
  "pass" the positive control while being useless.

Either control alone is satisfied by a constant.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path
from typing import Final

#: Origins are anything with a scheme and authority, or a protocol-relative URL.
ORIGIN: Final = re.compile(r"""(?:https?:)?//([A-Za-z0-9._-]+(?::\d+)?)""")

#: Positions that cause a fetch. A bare mention of a URL in prose does not.
FETCHING: Final = (
    re.compile(r"""<link[^>]+href\s*=\s*["']([^"']+)["']""", re.I),
    re.compile(r"""<script[^>]+src\s*=\s*["']([^"']+)["']""", re.I),
    re.compile(r"""<img[^>]+src\s*=\s*["']([^"']+)["']""", re.I),
    re.compile(
        r"""<(?:audio|video|source|iframe|embed)[^>]+src\s*=\s*["']([^"']+)["']""", re.I
    ),
    re.compile(r"""@import\s+(?:url\()?["']?([^"')]+)""", re.I),
    re.compile(r"""url\(\s*["']?([^"')]+)""", re.I),
    re.compile(r"""\bfetch\(\s*["'`]([^"'`]+)""", re.I),
    re.compile(r"""\bimportScripts\(\s*["'`]([^"'`]+)""", re.I),
    re.compile(r"""\bnew\s+WebSocket\(\s*["'`]([^"'`]+)""", re.I),
    re.compile(r"""\bsendBeacon\(\s*["'`]([^"'`]+)""", re.I),
    re.compile(r"""\.open\(\s*["'][A-Z]+["']\s*,\s*["'`]([^"'`]+)""", re.I),
)

#: The SVG namespace is a identifier, never fetched. It is the one string that
#: looks like an origin in every SVG ever written.
NOT_FETCHED: Final = frozenset({"www.w3.org"})


def scan_text(text: str) -> set[str]:
    found: set[str] = set()
    for pattern in FETCHING:
        for value in pattern.findall(text):
            match = ORIGIN.match(value.strip())
            if match and match.group(1) not in NOT_FETCHED:
                found.add(match.group(1))
    return found


def scan_tree(root: Path) -> dict[str, set[str]]:
    hits: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in {".html", ".js", ".css", ".mjs", ".json"}:
            continue
        found = scan_text(path.read_text(errors="replace"))
        if found:
            hits[str(path.relative_to(root))] = found
    return hits


POSITIVE = """<html><head>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=X">
</head><body></body></html>"""

NEGATIVE = """<html><head>
<link rel="stylesheet" href="/Amanuensis/_astro/index.css">
<script src="/Amanuensis/_astro/client.js"></script>
</head><body>
<p>Read the source at https://github.com/joshedwards237/Amanuensis</p>
<svg xmlns="http://www.w3.org/2000/svg"></svg>
</body></html>"""


def controls() -> list[str]:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "positive.html").write_text(POSITIVE)
        if not scan_text(POSITIVE):
            failures.append(
                "POSITIVE CONTROL FAILED — a page linking fonts.googleapis.com "
                "was not flagged. This scanner is not scanning, so its silence "
                "on the real output proves nothing."
            )
        if scan_text(NEGATIVE):
            failures.append(
                "NEGATIVE CONTROL FAILED — a page whose only references are "
                "same-origin was flagged. A scanner that flags everything also "
                "passes the positive control while being useless. Offenders: "
                f"{sorted(scan_text(NEGATIVE))}"
            )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dist",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "site" / "dist",
        help="built output to scan",
    )
    args = parser.parse_args(argv)

    failures = controls()
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("controls: positive flags a CDN, negative passes same-origin")

    if not args.dist.exists():
        print(f"no build at {args.dist} — run `npm run build` first", file=sys.stderr)
        return 1

    hits = scan_tree(args.dist)
    if hits:
        print("\nTHIRD-PARTY ORIGINS IN BUILT OUTPUT:", file=sys.stderr)
        for path, origins in hits.items():
            print(f"  {path}: {', '.join(sorted(origins))}", file=sys.stderr)
        print(
            "\nThe page claims nothing leaves your machine. Self-host the asset "
            "or remove it; there is no allowlist here on purpose.",
            file=sys.stderr,
        )
        return 1

    print(f"no third-party origins in {args.dist}")
    print(
        "NOTE: this is static analysis. SITE_PRD §12.2 criterion 12 "
        "(interaction surface) is NOT covered and needs a browser pass."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
