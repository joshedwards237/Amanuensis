# Self-hosted fonts

**No external font host. This is a hard constraint, not a preference.**

The page's central claim is that nothing leaves your machine. A stylesheet
fetched from `fonts.googleapis.com` sends every visitor's IP and User-Agent to a
third party on first paint — the same shape the site refuses for a GitHub star
count, and refuted by exactly the devtools panel a sceptical reader would open.
`scripts/verify_site_network.py` fails the build on any origin that is not our
own, with **no allowlist**.

These four files are committed. There is nothing to fetch and nothing to
install.

| File | Family | Role | Size |
| --- | --- | --- | ---: |
| `InstrumentSerif-400.woff2` | Instrument Serif | display | 15 KB |
| `InstrumentSerif-400i.woff2` | Instrument Serif italic | display emphasis | 16 KB |
| `Geist-var.woff2` | Geist (variable, 100–900) | body, UI | 29 KB |
| `GeistMono-var.woff2` | Geist Mono (variable, 100–900) | data, code, glyphs | 23 KB |

**92 KB total**, latin subset.

## Why these two

**Instrument Serif** for display. High-contrast, editorial, and it ships in a
single weight — which is the point. You cannot bold your way out of a weak
headline, so the headline has to work at 400 or be rewritten.

**Geist and Geist Mono** for everything else. Drawn for developer products, and
crucially they are one superfamily: body text and machine values agree with each
other instead of arguing. That matters here because the site's typographic rule
is semantic — *if it is set in mono, it is a value the product produced or would
parse* — and the rule reads as a change of register rather than a change of
voice when the two faces share a skeleton.

Both are **SIL Open Font License 1.1**, which is what makes self-hosting
available rather than merely preferable.

## Variable, deduplicated

Google serves Geist and Geist Mono as single variable files covering the whole
weight range. The first download pulled `Geist-400/500/600` and all three were
byte-identical (`sha256 9b6f5ff4…`), so they are stored once and declared with
`font-weight: 100 900`. That is 87 KB saved by checking rather than assuming.

## Regenerating

```
curl -H "User-Agent: Mozilla/5.0 …" \
  "https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&display=swap"
```

Take the `url(...)` from the block whose `unicode-range` contains `U+0000-00FF`
— that is the latin subset — and download it with `curl`. Note that Python's
`urllib` has no CA bundle on macOS by default and will fail with
`CERTIFICATE_VERIFY_FAILED`; use `curl`.

Keep `U+25CB ○`, `U+25CF ●`, `U+25D0 ◐`, `U+25D1 ◍`, `U+26A0 ⚠` and
`U+2423 ␣` if you ever re-subset by hand. Those are the daemon's own menu-bar
glyphs and the open-box the replay widget uses to make leading whitespace
visible. Subset them out and the page silently falls back for exactly the
characters that carry the product's state.
