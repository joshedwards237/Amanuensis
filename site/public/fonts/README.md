# Self-hosted fonts

**No external font host. This is a hard constraint, not a preference.**

SITE_PRD §5.2 and §12.2. The page's most-repeated claim is that nothing leaves
your machine. A stylesheet fetched from `fonts.googleapis.com` sends every
visitor's IP and User-Agent to a third party on first paint — the same shape the
spec refuses for a GitHub star count, and refuted by exactly the devtools panel
§5.2 invokes. An earlier revision carved the font host out of the acceptance
criterion that would have caught it, which is an exemption written into the
verifier rather than into the design.

`scripts/verify_site_network.py` fails the build if any origin other than the
page's own appears. There is no allowlist for fonts.

## Files this directory must contain

`site/src/styles/base.css` references these four by exact name:

| File | Family | Weight |
| --- | --- | ---: |
| `IBMPlexSans-Regular-latin.woff2` | IBM Plex Sans | 400 |
| `IBMPlexSans-SemiBold-latin.woff2` | IBM Plex Sans | 600 |
| `IBMPlexMono-Regular-latin.woff2` | IBM Plex Mono | 400 |
| `IBMPlexMono-Medium-latin.woff2` | IBM Plex Mono | 500 |

Four files, two families, four weights. Nothing else loads. Adding a weight
means adding an `@font-face` block and a file; it is not free, and §5.4's prose
budget is a reminder that the page does not need more voices than it has.

## Where to get them

IBM Plex is **SIL Open Font License 1.1** — redistribution is permitted, which
is what makes self-hosting available rather than merely preferable.

Upstream: <https://github.com/IBM/plex> (`IBM-Plex-Sans/fonts/complete/woff2/`
and `IBM-Plex-Mono/fonts/complete/woff2/`).

Subset to latin before committing — the complete faces carry Cyrillic, Greek and
Vietnamese this page never renders, and a page selling latency should not ship
glyphs it cannot display. `pyftsubset` from `fonttools`:

```
pyftsubset IBMPlexSans-Regular.ttf \
  --unicodes="U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD,U+25CB,U+25CF,U+25D0,U+25D1,U+26A0,U+2423" \
  --flavor=woff2 --layout-features="*" \
  --output-file=IBMPlexSans-Regular-latin.woff2
```

The tail of that unicode range is deliberate and easy to lose: `U+25CB ○`,
`U+25CF ●`, `U+25D0 ◐`, `U+25D1 ◍`, `U+26A0 ⚠` are the daemon's own menu-bar
glyphs, which the page renders inline, and `U+2423 ␣` is the open-box the replay
widget uses to make leading whitespace visible in a raw transcript (§6.5). Subset
them out and the page silently falls back for exactly the characters that carry
the product's state.

## Until the files are here

`font-display: swap` means the page renders in the declared fallbacks —
`-apple-system` and `ui-monospace` / `SF Mono`. On macOS, which is the only
platform this product runs on, that is San Francisco and SF Mono, and it sits
comfortably in the Zed / Ghostty / Obsidian reference lane. The page is not
broken without these files; it is only less specific.
