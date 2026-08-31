# Amanuensis — Landing Page PRD

**Status:** draft, revision 4 · **Created** 2026-08-26 · **Track:** parallel, outside the PRD §9 phase sequence

This document specifies a hosted landing page for Amanuensis. It is subordinate
to `AMANUENSIS_PRD.md` on every question of product fact: where this document
and the PRD disagree about what the software does, the PRD wins and this
document is wrong.

It governs one deliverable — a static site at `site/` — and nothing else. It
does not amend the product, does not add a runtime dependency, and does not
touch `src/`.

> **Revision 4 splits the site into three pages after the single-route version
> was judged too wordy to work as a product page.** The one-route decision was
> recorded in rev 2 as a prohibition with no reason attached, and the choice
> cartographer flagged that it staked the audience bet whole — no shallow
> surface for the skimmer, no deep one for the checker. That is what happened.
> `/` is now a feature-forward landing page, `/how-it-works` is the dense
> technical argument rev 3 specified almost unchanged, and `/docs` is the
> install guide the primary CTA points at. A persistent nav carries all three.
> Type changed with it: Instrument Serif for display and Geist / Geist Mono for
> body and data, replacing IBM Plex, all four files self-hosted. The palette
> gains two ranked hues — `--iris` for the product's own colour and `--lime`
> used once, for the moment text lands — above the same near-monochrome ground.
> §2's claims register, §7's pipeline and §12's criteria are **unchanged** and
> still bind every page.
>
> **Revision 3 folded an adversarial review: twelve objections, two critical.**
> The one that matters most is **O4** — revision 2's headline band was selected
> after the data was seen, and it had a *better* p95 than the band G1 actually
> binds. §2.2 now chooses the band by rule rather than by outcome, and the
> published p95 gets 47% worse as a result. Also folded: the no-literals grep was
> replaced (it could not fail for the reason it claimed), the row-exclusion rule
> was unimplementable as written, session selection was unconstrained against a
> database of the author's real dictations, and the `percentile` import dragged
> an ASR runtime into the page build. Marked **[AD-n]**.
>
> **Revision 2 existed because revision 1 was written against a tree one commit
> stale.** Phase 3 had already landed on `origin/main` (87034f4, 2026-08-08):
> post-processing is implemented and wired, the dictionary is live, history
> retains and purges. Revision 1 specified a page that announced post-processing
> as unbuilt. That is the failure mode `CLAUDE.md` warns about in its own words —
> never report "feature X does not exist" from a stale tree — and it reached a
> full spec before anything caught it. Revision 2 also folds twelve findings from
> a choice-cartography pass; the material ones are marked **[CC-n]**.

---

## 0. How to use this document

**§2 is the claims register.** Revision 1 made it the origin of both the
*permission* to publish a figure and the *value* of that figure. Those are
different kinds of thing and only one of them belongs in a written document
[CC-3].

- **§2 holds judgments**: which bands are publishable, which rows are excluded
  and why, and what may never be said. Human-authored, reviewed, stable.
- **`claims.json` holds values**, computed at build time by the export in §7.
  Never typed by hand, never quoted into prose.

Where this document shows a number, it shows it as a **dated snapshot for
review**, explicitly not as the source the page reads. §12 requires CI to
re-derive the snapshot and fail on divergence, so this document cannot quietly
go stale the way six documents in this project once did.

If you are implementing: §2, §5, §6, §7, §8 and §12. If you are reviewing: §2,
§10 and §13 are where this document is most likely to be wrong.

---

## 1. Summary

### 1.1 What this is

A single-route static page, published from this repository, that explains
Amanuensis and proves its two load-bearing claims — that text arrives fast, and
that nothing leaves the machine — using the product's own recorded output rather
than assertion.

### 1.2 Why it exists

Amanuensis's differentiator is not a feature list; PRD §1 says so explicitly. It
is a set of engineering decisions with published measurements and published
costs. That is difficult to communicate through a README, because a README is
read by people who have already decided to look. The page makes the argument to
someone who has not.

The strategy follows from one observation: **every dictation tool claims privacy
and speed, and none of them show you the measurement.** The only durable advantage
available is to publish the evidence, including the evidence that is unflattering.

**Who this is for, stated once so §3 and §12 can be checked against it** [AD-1].
The reader is a developer who has *heard of* local dictation, is sceptical that it
is fast enough to use, and will not clone a repository to find out. They are not
yet a README reader — the README serves the person who already decided. What they
lack today is any way to see the thing run and check the number without installing
it. That is the gap, it is the only gap this page closes, and §13.1's bet is about
how many such readers exist, not about whether they are served.

### 1.3 What it is not

- Not a waitlist. No form, no email capture, no field that accepts input. A tool
  whose pitch is "no account, nothing leaves your machine" cannot open by asking
  for your email address.
- Not a marketing site for a shipped product. Amanuensis runs from a source
  checkout; there is no packaged app. The page says so above the fold.
- Not a mirror of the repository's documents. The PRD, the gate records and the
  ADRs stay where they are versioned and reviewed. The page links them.

### 1.4 Current product state, as of 2026-08-26

Derived from `origin/main` at 87034f4, not from any README.

| | |
| --- | --- |
| Phase 3 | **Built 2026-08-08. Gate not run — it needs the operator.** |
| Post-processing | **Implemented and wired.** `build_chain(config.postprocess, vocabulary)` at `cli.py:488` and `:724`. `RuleBasedPostProcessor` ported from `experiments/scripts/exp4_rules_only.py`. |
| Dictionary | Live on both mechanisms. `vocabulary.toml`, `[replace]` compiled to one alternation, `[boost]` scoped per bundle identifier. `manu vocab check`. |
| History | `manu history` with `--pending`, `--purge`, `--raw`. `retain_days` reaches `history.db`. |
| Still refusing | `toggle` and `status`, both naming Phase 4 (`cli.py:85–86`). |
| Not packaged | No installer, no signed binary. Phase 4. |
| Licence | Apache-2.0 declared in `pyproject.toml:10`. **No `LICENSE` file exists.** |

**What this means for the page.** The page must not claim any Phase 3 *gate*
outcome — end-to-end accuracy on long dictation is unmeasured, and the gate that
would measure it needs ten real dictations the operator has not yet done. It may
state what the code does, and it may cite experiment-level measurements as
experiment-level.

### 1.5 Decisions already taken

Settled before this document; not open for re-litigation.

| Decision | Value |
| --- | --- |
| Demo mechanism | Replay of real recorded sessions — real audio, real transcript, real `history.db` timings. Nothing simulated, nothing live. |
| Waitlist | None. CTA is GitHub plus the install command. |
| Location | `site/` in this repository. Requires the PRD §6.4 amendment in §11. |
| Phase relationship | Parallel track. Does not block, unblock, or constitute any part of the Phase 3 gate or Phase 4. |
| Build | Astro + Tailwind, static output. |
| Islands | **Preact** via `@astrojs/preact`, not React [CC-12]. See §6.11. |
| Hosting | GitHub Pages via GitHub Actions, base path `/Amanuensis`. |
| Components | 21st.dev / shadcn registry items as **reference**, pulled by registry URL where they transfer. No runtime registry dependency. See §6.11. |
| Fonts | **Self-hosted woff2 subsets.** No third-party font host [CC-2]. |
| Visual lane | Quiet technical. Reference set: Zed, Ghostty, Obsidian. |
| Demo audio | A freshly recorded, scripted, public-safe corpus. §10.2. |

---

## 2. The claims register

**This section is judgment. Values are a dated snapshot for review; the page
reads `claims.json`.** Snapshot taken 2026-08-26 against 70 rows,
`engine = faster_whisper:tiny.en`. Percentiles nearest-rank, never interpolated.

### 2.1 Definitions

`g1_ms = vad_ms + transcribe_ms + postprocess_ms + persist_ms + inject_ms` —
hotkey release to text fully present. It **excludes** `capture_ms`, which is the
time the user spent speaking, and **excludes** `restore_ms`, which happens after
the text is already on screen.

### 2.2 Eligibility — which rows may be published

1. `error is null` and `injected = 1`.
2. **Rows belonging to a same-second group of more than one are excluded.** See
   §2.4(c). 18 of 70 rows are dropped by this rule.
3. A band may be published only if it has n ≥ 10 after exclusions.
4. Bands are published with their `n`, never without.
5. **The headline band is the band the specification binds, not the band that
   measures best** [AD-4]. PRD §2 binds G1 at a ten-second utterance, so the
   headline band is `≤ 10 s`. This rule exists because revision 2 broke it:
   offered five candidate bands, it selected `7–16 s` — which has half the rows
   of `≤ 10 s` and a p95 47% better — labelled it "the headline pair", and then
   §5.1 attributed that figure to "a ten-second utterance". That is the exact
   failure §2 exists to prevent, committed inside §2. A band chosen after the
   data is seen is a band chosen by its outcome, and no amount of accurate
   arithmetic downstream repairs it.

### 2.3 Snapshot — for review only

| Band | n | p50 | p95 | Publishable? |
| --- | ---: | ---: | ---: | --- |
| **≤ 10 s** | **27** | **206.0 ms** | **538.9 ms** | **Yes. The headline pair** — G1's binding duration (§2.2 rule 5). |
| 7–16 s | 13 | 223.0 ms | 366.5 ms | Yes, labeled with its band. Not the headline. |
| ≥ 60 s | 11 | 1566.4 ms | 4203.6 ms | Yes, and §4 stage 3 requires it. |
| 16–60 s | — | — | — | **No band exists.** See §2.5 and §10.2. |
| All rows, unfiltered | 70 | 428.3 ms | 5182.5 ms | No. Mixes bands and excluded rows. |

G1's targets are p50 ≤ 400 ms and p95 ≤ 800 ms, and PRD §2 binds G1 at a
ten-second utterance. **The ≤ 10 s band meets both** — 206.0 against 400,
538.9 against 800.

Publishing 538.9 rather than 366.5 costs the page its prettiest number and buys
back the only thing it is actually selling. §1.2's whole strategy is that this
page publishes the measurement including the unflattering one; a headline chosen
for being flattering would have refuted the strategy in the first screen.

**Post-processing**, over the 25 rows where the chain was active: p50 **0.43 ms**,
p95 **1.17 ms**, max **1.30 ms**. `rules.py` additionally carries experiment-level
figures — p50 0.0445 ms, p95 0.0505 ms, strict WER 24.66 → 24.32, 0/6 INVENT,
0/6 SHRINK — measured against the Phase 1 corpus on 2026-07-31. **Those are
experiment figures, not gate figures, and the page labels them as such.**

### 2.4 Three corrections against figures elsewhere in the repository

**(a) The p95 in `CLAUDE.md` is a ten-row subset.** It states 270.0 ms; that is
the Phase 2b gate's ten dictations. There are 13 rows in the 7–16 s band and the
p95 over all of them is 366.5 ms. Both are honestly derived and answer different
questions. The page publishes the figure that reproduces from the whole table.

**(b) The scaling law is not usable, and revision 2 argued it badly** [AD-5].

`CLAUDE.md` states `transcribe_ms ≈ 48.8 + 13.69 × seconds`. Revision 2 refuted
it with four least-squares fits sliced by calendar day, naming no `n`, no R², no
duration range and no regressor column — and one of the four was fitted over
rows §2.4(c) declares invalid. That is a refutation held to a lower evidentiary
standard than the claim it overturns, which is this project's own signature
defect pointed the other way.

**The adversarial review proposed a mechanism, and the mechanism is wrong.** Its
hypothesis was a wrong denominator: `duration_seconds` is the *untrimmed* capture
while the engine decodes *trimmed* audio, so silence would ride into the slope.
Testable, and tested — over the 21 clean rows carrying `guard_retained_seconds`:

| Regressor | Fit | R² |
| --- | --- | ---: |
| `duration_seconds` (untrimmed) | `125.5 + 19.08·s` | 0.590 |
| `guard_retained_seconds` (speech only) | `117.1 + 19.41·s` | 0.598 |

The two are indistinguishable; trimming removes a mean of 2.7% of the capture in
this corpus. The denominator is not the problem. Recorded because a plausible
mechanism that survives into a document unchecked becomes a finding about the
product six weeks later.

**The argument that does survive**, and the only one the page relies on:

- The law was fitted over **n = 14, spanning 0.7–43.4 s** (`docs/gates/phase-2b.md`).
  It is used to predict at 60 s and beyond — outside the range it was fitted on.
  A model is not evidence about durations it never saw.
- Refitting the clean rows over 0.8–104.4 s gives **R² ≈ 0.59**. A duration-only
  linear model explains under 60% of the variance in a single decode; it is not a
  predictor, whatever its coefficients.
- `CLAUDE.md` reaches the same conclusion from a third dataset: "Measured over ten
  ~74 s takes: p50 917–938 ms against a predicted 1069, and p95 1247–1345 ms
  against 1083, on two runs of the same files. A duration-only linear model
  cannot predict a single decode."

**The page prints no scaling equation and extrapolates to no duration it has not
measured.** It may plot the measured points — a scatter states only measured
values and is not an extrapolation [CC-7].

Related, recorded in advance so it cannot read as a regression: **G1 is missed at
75 s on decode alone**, p50 ~930 ms against an 800 ms p95. PRD §2 binds G1 at ten
seconds. It is utterance length, not post-processing.

**(c) Eighteen rows are concurrent decodes.** `started_at` is stored at
microsecond resolution (`models/session.py:189`). The excluded rows form pairs
whose timestamps differ by **2 to 48 microseconds** — machine-dispatched, not a
human pressing a hotkey twice. Within each pair exactly one row carries
`raw_transcript` and one does not, and the two transcripts differ in length: a
two-configuration comparison decoding the same audio simultaneously. Both members
are inflated by contention (58.4 ms of transcribe per second of audio, against
20.9 ms/s for single-run rows), so the whole pair is dropped rather than the
slower half.

**The rule must be written against the stored format, not against the prose**
[AD-6]. Revision 2 said "a row whose `started_at` is shared with another row is
dropped" — string equality on a microsecond ISO timestamp, which matches nothing.
It would have logged "0 dropped" forever while reproducing none of the exclusions
this register depends on: a rule that cannot fire, inside the mechanism §13.3
calls the whole defence.

The export groups on `started_at` **truncated to the second**, and then
discriminates rather than assuming:

| Observation within a group | Reading | Action |
| --- | --- | --- |
| Transcripts and durations identical | one session written twice | dedupe, keep one, timings valid |
| Transcripts differ, `raw_transcript` present on some and absent on others | two configurations in parallel | **drop the whole group** |
| `guard_outcome` indicates a retry | a real product cost, not contention | **keep** |
| Distinct transcripts, sequential ids, one shared timestamp | a batch script reusing a stamp | keep all |

**The export logs the group count, the reading it applied, and the rows dropped.**
Silent exclusion is how a filtered dataset comes to look like a complete one, and
this exclusion moves the published ≥ 60 s p95 by more than a second — an effect
that large is not permitted to rest on one signal.

### 2.5 What the page cannot answer, stated as such

Named here because §4 stage 8 must display them at body size, not as footnotes
[CC-7].

- **Anything between 16 and 60 seconds.** No band exists. This is the modal
  dictation length for prose, and §10.2 adds a ~30 s session to close it.
- **Any machine that is not Tier A.** Every figure is one machine, one speaker,
  one room. Tier B is unmeasured against its own published p50 ≤ 2000 ms bar.
- **End-to-end accuracy.** The Phase 3 gate has not run.
- **The collapse guard's false-positive direction.** Untested, and the blind spot
  is at the short end.

### 2.6 Rules binding every number on the page

1. A latency figure never appears without its p50, its p95 and its band — not in
   a heading, a tile, the `<title>`, an OG description, or image alt text.
2. No scaling equation. No extrapolation. Measured points may be plotted.
3. Unmeasured is stated as unmeasured **at body size**, never in a smaller or
   muted token.
4. Every displayed number comes from the build-time export, never a literal.
5. Provenance — band, `n`, and a link to the record — is on the page.
6. An experiment-level figure is labeled as such and never presented as a gate
   result.

---

## 3. Audience, and the bet

PRD §4's primary user is a privacy-motivated developer comfortable with a config
file who reads a README before installing. The secondary user has RSI or a motor
impairment, for whom a dropped transcription is not a minor annoyance.

The page has one job: **make a sceptical technical reader believe the two claims,
and know the costs, in under five minutes.**

This is a bet, and it is named as one: the page is optimised for the reader who
checks, and most visitors do not. A skimmer meets qualifications and mono tables
where a competitor's page shows a hero statistic. The mitigation is structural —
the hero is self-sufficient — but it is a mitigation, not a fix. §13.1.

**The secondary user is addressed once and then dropped** [CC-11]. The hero
headline is precisely their requirement and is never connected back to them, and
the only CTA is a source checkout. §4 stage 4 carries the connection explicitly.

---

## 4. Structure

The page is the pipeline. The reader scrolls from microphone to cursor.

`capture → trim → transcribe → guard → postprocess → persist → inject`

Not a metaphor imposed on the product: these are the serial-worker stages in
`DictationController`, and each has its own column in `history.db` — with one
naming mismatch worth knowing, since the page shows the columns: **the trim stage's
column is `vad_ms`**, after the mechanism rather than the effect. The page's spine and
the widget's stage bar use the same stages in the same order and colours.

### 4.1 The privacy rail [CC-4]

Dataflow order has no slot for a property that is not a stage, so revision 1 put
G3 — half the thesis — at section 8 of 10, in the second-smallest block, off the
spine entirely.

**Fixed by making it cross-cutting.** Every pipeline section carries a fixed
marker in its header:

```
BYTES OFF THIS MACHINE AT THIS STAGE:  0
```

At stage 7 (Inject) the marker reads differently, and that difference is the
whole privacy argument delivered at the moment it becomes true:

```
BYTES OFF THIS MACHINE AT THIS STAGE:  0, unless you run a clipboard manager
```

The rail uses the pipeline to carry the privacy claim rather than appending it
after the structure ends, and it puts the clipboard caveat at the stage that
causes it, in causal order, rather than one section later. The evidence block
(packet capture, control, scope limit) remains as a section, now at position 8
of 11, and is **on** the spine.

### 4.2 Section anatomy

Each pipeline section:

> **stage number · stage name** · the privacy rail marker · this session's
> `⟨row⟩` ms · what happens · why it is built this way · **what it costs**

The cost block is mandatory. Two refinements from [CC-1]:

- **A section with no material cost says so explicitly** — `WHAT IT COSTS · no
  material cost to you; the cost is on the measurement, below` — rather than
  filling the slot with a methodology caveat dressed as a cost. A template that
  is always filled trains the reader that it is sometimes empty.
- **The block carries a weight cue.** Three levels of left border (1px / 2px /
  3px in `--rule`) so that a 2 ms disk write and a clipboard-manager leak are not
  typographically identical. Never accent — a cost is content, not an alert.

### 4.3 Sections

> **Rev 4:** the table below is `/how-it-works`. The hero row is replaced by a
> page header; the marketing hero moved to `/` and is specified in §4.6.


| # | Section | Job | Height |
| --- | --- | --- | --- |
| 1 | **Hero** | Complete the pitch and the CTA before any scrolling. | ~100vh incl. widget |
| 2 | **The loop, in one screen** | Legend and contents. Horizontal stage diagram; the note that capture is not in the number because the time you spend talking is yours. | ~60vh |
| 3 | **Stage 1 — Capture** | Residency and the hotkey. The daemon holds the model because loading per invocation costs 3–8 s. Listen-only `CGEventTap`. Glyphs `○ ● ◐` inline. **Cost (3px):** a resident process holding the microphone permanently — which is why recording state may never be ambiguous. | ~80vh |
| 4 | **Stage 2 — Trim** | The largest latency lever is invisible. Silero VAD strips silence before the model sees audio. **Cost (1px):** no material cost to you. The VAD parameters are the ones the published figures were measured under; changing one invalidates them. | ~60vh |
| 5 | **Stage 3 — Transcribe** | The model and the measured bands. Batch, not streaming — nothing appears until release, by design. Carries §2.3's table at full weight, the §2.5 gaps, and the scatter of measured points. **Cost (2px):** latency grows with utterance length; batch means silence on screen until release. | ~120vh |
| 6 | **Stage 4 — The guard** | Told as the incident it was: a 30.5 s dictation returned two words, no error, injected. The guard measures decoded coverage; below the floor it re-decodes without the bias, and failing that withholds the text — `manu history --last` still has your words. Fires at 8.3% on a reproduced collapse; floor 82.8% across six samples. Glyphs `◍ ⚠`. **Explicit connection to the secondary user** [CC-11]. **Cost (2px):** the false-positive direction is untested, and the blind spot is at the short end. | ~90vh |
| 7 | **Stage 5 — Post-processing** | **New in revision 2.** The rules pass, shown as a real diff from one row: `raw_transcript` → `transcript`, with `fired_entries` naming the rules that ran. Costs p50 0.43 ms / p95 1.17 ms. Then the two rules deliberately *absent* — lowercasing a spurious capital, and folding spoken numbers into digits — each with the measurement that rejected it. **A section about what was refused, and why, is worth more than a feature list.** **Cost (1px):** no material cost to you; the pass is under 1.2 ms at p95. | ~90vh |
| 8 | **Stage 6 — Persist** | Pay off the headline. The transcript is written before injection is attempted, unconditionally. `retain = false` does not skip the write — it writes to a `0600` temp file that never enters the database and is unlinked on successful injection. The guarantee is deliberately not user-settable. **Cost (1px):** `⟨row⟩` ms of disk write on the critical path, spent on purpose. | ~90vh |
| 9 | **Stage 7 — Inject** | How text lands. Clipboard paste with save/restore; keystroke fallback. Verified in TextEdit, Terminal, VS Code, Chrome, both strategies, read back via Accessibility. **Cost (3px, two blocks):** the clipboard manager leak, measured against Maccy on defaults; and keystroke substitution, five changes in one measured sentence — the strategy that protects your privacy is the one that alters your words. Restore footnote. | ~100vh |
| 10 | **Nothing leaves — the evidence** | The rail's claim, proven. 0 sockets / 0 bytes against a control that saw 865. Weights download once at install, checksummed, pinned. The scope limit: the capture covers this process only, and stage 7 is precisely the blind spot. **On the spine.** | ~60vh |
| 11 | **What isn't measured** | §2.5, at body size. Plus: `toggle` and `status` refuse and name Phase 4; there is no packaged app; the Phase 3 gate has not run. | ~50vh |
| 12 | **Colophon** | Exits. Install block, the two-permissions note, GitHub, licence, PRD / gates / ADRs, the etymology (§5.3), and the alternatives named without flinching: nerd-dictation and Talon, with PRD §1's build-vs-adopt reasoning. | ~50vh |

Total ~8 viewports.

### 4.4 The spine

A 1px vertical rule in the left margin from section 2 to section 10 — **including
the evidence section** [CC-4] — with one tick per stage. On viewports ≥ 1024px
the labels sit beside it in a `position: sticky` rail. An `IntersectionObserver`
sets the active tick, 150 ms crossfade. Ticks are anchor links. Clicking a
segment in the widget scrolls to that stage.

Below 1024px the rail is dropped and section headers carry the structure.

**Scroll position changes exactly one thing on this page: which tick is
accented.** No pinned sections, no scroll-driven transforms, no scrolljacking,
no build-in reveals, no progress bar. No `scroll` listeners and no reads of
`scrollY` anywhere in the codebase.

### 4.5 Cut, with reasons

A features grid (the stages are the features). An architecture diagram (G5's
answer is "read the source in an afternoon" — link it). An FAQ (every question it
would answer is answered in order; an accordion is where landing pages hide
caveats, and here the caveats are the content). A roadmap (a page of unmeasured
claims).

**Sub-pages: cut, and here is the reason revision 1 omitted** [CC-11]. One route
means one reading order and no navigation to design, and it stakes §13.1's
audience bet whole — there is no shallow surface for the skimmer and no deep one
for the checker. Accepted anyway, because two surfaces means two things to keep
true and this project's recorded failure is duplicated documents drifting. **One
mitigation is adopted:** `claims.json` is served at a stable URL, so a sceptic
gets a citable machine-readable artefact without a second authored page.

### 4.6 Routes (rev 4)

| Route | Job | Reader |
| --- | --- | --- |
| `/` | Sell the product in one screen. Feature cards, three honest numbers, two CTAs. Under 400 words. | Someone who has heard of local dictation and does not yet care enough to read. |
| `/how-it-works` | The pipeline argument, unchanged from rev 3 — seven stages, each with what it costs, the replay widget, the measured bands, the gaps. | The reader who checks. |
| `/docs` | Install, permissions, first dictation, configuration, troubleshooting. The primary CTA's destination. | Someone who has decided and wants it working. |

The nav names exactly four things: How it works, Docs, GitHub, Install. A
product with one loop does not need a mega-menu, and every extra destination is
a page somebody has to keep true.

**What did not move.** Every rule in §2 binds all three pages: no latency figure
without its p50, p95 and band; no extrapolation; unmeasured stated at body size.
The landing page shows three numbers and each one carries its band. §12.1's
regeneration diff and §12.2's origin check run over the whole build.

---

## 5. Copy

### 5.1 Hero, verbatim

> # Hold a key. Speak. Your words are on disk before they're on screen.
>
> Amanuensis is open-source dictation for macOS that runs entirely on your
> machine. Hold right-option, speak, release — the transcript is written to local
> history, then pasted at your cursor. No account. No network at runtime. No
> audio leaving the machine.
>
> For utterances of ten seconds or less — the duration this project's own goal
> is written against — **p50 {p50} / p95 {p95}** from release to text present,
> over {n} real dictations read from the daemon's own timing rows. The target was
> 400 and 800. Longer dictations take longer, and stage three shows you the
> measurements rather than a formula.

**Every brace is a build-time substitution from `claims.json`, including `{n}`**
[AD-7]. Revision 2 wrote this paragraph with the figures inline and marked it
*verbatim*, which meant either CI failed the build on the spec's own copy or the
most-read numbers on the page were the ones nothing checked. No number in the
hero is typed.
>
> Below is a real session: real audio, the transcript the model actually
> produced, the stage timings pulled from the daemon's SQLite history. Recorded,
> not live.

The headline is the §8 persist-before-inject ordering used as a hook. It sounds
backwards for a product selling speed, which forces the question *why*, and the
page is the answer. No competitor would lead with it, because none treats that
ordering as binding.

### 5.2 CTA row, verbatim

```
[ Star on GitHub ]     [ Watch releases → ]

git clone https://github.com/joshedwards237/Amanuensis && cd Amanuensis
pip install -e .
manu install     # downloads the model once, measures this machine's tier
manu daemon      # hold right-option, speak, release
```

> Runs from a source checkout. No packaged app, no installer, no signed binary
> yet — that's Phase 4. Needs Python 3.12+ and two macOS permissions
> (Accessibility and Input Monitoring); the daemon names whichever is missing.

**No star count.** A build-time count goes stale silently, which is the class of
unverified number §2 exists to prevent, and a runtime fetch is forbidden below.

**Zero runtime network, without exemption** [CC-2]. The page makes no
cross-origin request of any kind. Fonts are self-hosted woff2 subsets under
`site/public/fonts/`; there is no Google Fonts stylesheet, no CDN, no analytics,
no error reporting. Revision 1 carved the font host out of the acceptance
criterion that would have caught it — an exemption written into the verifier
rather than into the design, which is the same shape as a check that passes by
looking at nothing. The devtools network panel showing nothing third-party is
the cleanest rhetorical artefact this page has; it is not traded for a build
step.

### 5.3 The name

The etymology — *amanuensis*, from Latin `servus a manu`, one employed to take
down the words of another — appears in the colophon **and in the `<title>` and OG
description** [CC-10], where it costs no visual register and is the surface a
link-sharer sees first.

It is not the hero. Revision 1 rejected that on typographic grounds, which was
adjudicating a copy decision in the design system's frame. The real argument is
the one that gets the clause: the page's credibility comes from measurement
rather than from erudition, and a reader who arrives for the etymology and finds
no numbers has been sold something the page cannot deliver.

### 5.4 Register

Flat, declarative, short. No superlatives, no "blazingly", no exclamation marks,
no second-person imperatives outside the install block. Total non-mono prose
under 1,200 words; if it exceeds that, cut prose rather than evidence.

---

## 6. The replay widget

### 6.1 What it is

Playback of one real dictation: the actual audio, the actual transcript, the
actual `LatencyBreakdown` row. A build-time script emits `session.json`; the
widget consumes it. **No hardcoded millisecond value, no hardcoded transcript.**

Header reads `RECORDED SESSION · <date> · one row of history.db`. Permanently.
Never "demo", never "live".

### 6.2 Layout — three bands

Top to bottom: **voice** (waveform), **cursor** (a bordered line styled as a bare
text field), **measurement** (stage bars). Time flows left to right in all three;
cause flows top to bottom.

The release point on the waveform sits directly above the left edge of the stage
bars. That alignment *is* the claim "the clock starts when your thumb comes up",
and it must survive every breakpoint.

```
┌──────────────────────────────────────────────────────────────────────┐
│ RECORDED SESSION            2026-08-DD · one row of history.db       │
│ faster-whisper tiny.en · Tier A · push-to-talk                ○ idle │
├──────────────────────────────────────────────────────────────────────┤
│  ▶   ┈╌▂▃▅▆▄▂▁▃▅▆▅▃▁▁▂▄▆▅▄▂▁▁▃▅▄▃▂▁▂▃▂▁╌┈          0:00.0 / 0:09.8  │
│      ⌥ held ── speaking ──────────────────── released ▲              │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ ▍                                                              │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ▸ what the rules pass changed          [ raw ] [ processed ]        │
│                                                                      │
│  THE GAP, MAGNIFIED — shown at 1/20×; it played above at 1×          │
│    trim         ██                                        ⟨row⟩ ms   │
│    transcribe   ████████████████████████████████          ⟨row⟩ ms   │
│    guard        ▏·································        ⟨row⟩ ms   │
│    postprocess  ▏·································        ⟨row⟩ ms   │
│    persist      ▎·································        ⟨row⟩ ms   │
│    inject       ███                                       ⟨row⟩ ms   │
│    ├──── release → text fully present ──────────────┤     ⟨row⟩ ms   │
│    restore      ▒▒▒▒▒▒▒  after your text is present — outside g1     │
├──────────────────────────────────────────────────────────────────────┤
│  [ ↺ replay ]   [ replay at 1/20× ]   ▸ the history.db row           │
│  This session: ⟨row⟩ ms. Thirteen sessions of 7–16 s: p50 223.0 /    │
│  p95 366.5.                                                          │
└──────────────────────────────────────────────────────────────────────┘
```

`⟨row⟩` marks a value filled from the export. **This document does not contain
those numbers and the implementer must not invent them.**

### 6.3 Three states

**Before play.** Entirely still. Static waveform from an inline peaks array — it
can never fail to load. `○ idle`. Empty cursor line, caret not blinking. Stage
bars as unlabeled empty tracks. One `▶`. The widget is fully legible unplayed.

**During playback.** Two phases, split at the release tick.

*Capture phase:* audio plays, an accent playhead tracks the waveform linearly at
1×, glyph `●`, caret blinks. **The transcript area shows nothing.** Not a loading
state — PRD §7.1 made visible. The product is batch; streaming partials are a §3
non-goal.

*Release phase:* glyph `◐`. Stage bars fill in sequence over the actual elapsed
milliseconds. At ~230 ms this reads as one near-instant flick. That is the point.
Then the transcript appears **in one frame**, glyph returns to `○`.

**After.** End state persists, with `↺ replay` and `replay at 1/20×`.

### 6.4 The 1/20× replay, and the legibility floor [CC-9]

~230 ms is below the threshold at which a viewer perceives sequence, so the
real-time replay has a real payoff and no legible one. The slow replay supplies
the legible one: bars fill one after another and **the persist bar visibly
completes before the inject bar begins.** That is the headline, animated,
truthfully — the most valuable frame on the page.

**The magnification does not recurse, and revision 1 did not notice.** At 1/20×,
223 ms becomes 4.46 s, but `guard`, `postprocess` and `persist` are all under
1.5 ms in `history.db` — a 1 ms stage becomes 20 ms, one frame at 60 Hz. The
stages the magnification exists to reveal are exactly the ones it fails to
reveal.

**Resolution: bar width stays proportional; label dwell does not.** Each stage's
bar is drawn to true scale at all times, so magnitude is never distorted. What is
extended is the *label*: as each stage completes, its name and value hold at full
contrast for a minimum 250 ms dwell before the next stage's label takes over.
Sequence becomes legible without any bar misrepresenting its duration. A stage
whose bar is sub-pixel renders as a `▏` minimum-width tick with a dotted
continuation, visibly distinguishing "too small to draw" from "zero".

The magnification label is present from the first frame of the slow replay,
never revealed after it. The transcript still appears in one frame at every rate.

### 6.5 The rules-pass diff — post-processing made visible

**Revision 1 specified this stage as an empty track labeled "not built". It is
built.** `history.db` carries both strings for every chain-active row, and 16 of
16 differ.

The widget shows a `[ raw ] [ processed ]` toggle over the cursor line and a
disclosure, `▸ what the rules pass changed`, which expands to:

- the raw string with leading whitespace rendered as a visible `␣`,
- the processed string,
- `fired_entries` verbatim — e.g. `collapse_whitespace, capitalise_sentences`,
- the cost: `postprocess_ms` for this row, against the band's p50 0.43 / p95 1.17.

Both strings are real, from one row, from the same dictation. This is a better
exhibit than an empty track ever was: it shows a stage doing something small,
naming exactly what it did, for a cost under 1.2 ms.

### 6.6 The receipt

A disclosure row, `▸ the history.db row this came from`, expands to the literal
row as mono `key: value` pairs. Collapsed by default. The SQLite row is the
receipt; the toggle keeps the panel calm while making "pulled from the daemon's
own records" checkable rather than trusted.

### 6.7 Controls

`▶ / ⏸`, `↺ replay`, `replay at 1/20×`, the two disclosures, the raw/processed
toggle, and the stage bars as focusable links to their sections. Click-to-seek on
the waveform.

No volume control. **No arbitrary speed control** — speed manipulation on a
latency demo is self-harm. No share buttons.

All controls are real `<button>` elements with visible focus rings. Space toggles
playback when the widget has focus. Audio never autoplays, on any viewport.

### 6.8 Accessibility

The transcript is real DOM text in an `aria-live="polite"` region announced on
landing. Stage values are duplicated in a visually-hidden `<table>` with proper
headers — the bars are a visual encoding of tabular data and the table is its
accessible form. The region carries an `aria-label` of "Recorded dictation
session with measured latency".

Under `prefers-reduced-motion: reduce`: the playhead still moves (media
progress), the caret stops blinking, bar fills become discrete steps at their
completion times, and 1/20× renders as a static exploded view with everything
labeled.

### 6.9 Mobile

Single column below 640px. Waveform full-bleed at 48px. Stage labels above their
bars. Tap targets ≥ 44px. Seek by touch-drag. The 1/20× control is retained and
matters more here. The panel never scrolls horizontally; disclosures scroll
inside their own `overflow-x: auto` containers.

### 6.10 Failure

Peaks, transcript and timings ship inline. The audio file is the only fetched
asset. If it fails: the play control is replaced by mono text — `audio
unavailable — the record below is the session as stored` — the widget renders its
end state statically, and **the 1/20× stage replay remains available**, because
it needs no audio.

Under `<noscript>` or a failed hydrate, Astro's server-rendered output is that
same complete end state.

The widget has no broken state. Worst case it degrades from *replay* to *record*,
and a record from `history.db` is still evidence.

### 6.11 Implementation notes [CC-9, CC-12]

**Preact, not React.** Revision 1 selected React as a side effect of choosing a
shadcn component source, and recorded the two as independent decisions. There is
one island on the page, nothing to amortise a view-library runtime against, and
an acceptance criterion of Lighthouse ≥ 95 on a page whose thesis is that waiting
is the enemy. `@astrojs/preact`. Registry components are read for structure and
interaction handling; their surface is discarded regardless (§13.5), and
structure is the part that transfers between frameworks most easily.

**The widget is a timeline, not a bar chart.** §6.4's claim — that persist
completes before inject begins — is about cumulative offsets and ordering. Build
it as a transport with **rate as a parameter** (1, 1/20, ∞ for reduced motion),
one clock abstraction with two sources: `HTMLAudioElement.currentTime` during the
capture phase, and a `requestAnimationFrame` clock for the release phase and for
all of 1/20× — which must run with no audio present at all, per §6.10. Durations
are data, not CSS keyframes, because §7.2 forbids millisecond literals.

---

## 7. The data pipeline

The page must not be able to drift from the product. Enforced mechanically.

### 7.1 Export

**`scripts/export_site_session.py`** — under `scripts/`, not under `site/`
[AD-12]. Revision 2 put it in the one directory §11 excludes from `mypy --strict`,
`ruff` and `pytest`, which would have made the only Python that computes every
public number the only Python outside the type checker — in a project whose most
recent recorded lesson is that 337 tests went green with `manu transcribe` broken
by a return-type change the checker names. It lives with the project's other
measurement harnesses, is covered by the toolchain, and writes into `site/`.

It reads `history.db` and the demo audio and emits:

```
site/src/data/sessions/<id>.json      # transcript, raw_transcript, fired_entries,
                                      # per-stage ms, duration, engine, tier,
                                      # guard fields, the raw row
site/src/data/sessions/<id>.peaks.json
site/public/audio/<id>.<ext>
site/src/data/claims.json             # the §2.3 bands, with n, p50, p95, and
                                      # the count of rows excluded by §2.2
```

`claims.json` is copied to the published root at a stable URL (§4.5).

### 7.2 Rules

**1. Session selection is an explicit committed allowlist** [AD-9]. The export
refuses to run without one. It never queries for a session, and in particular
never calls the `latest()` helper `history.py` already ships — which is what a
hurried implementer reaches for, and which would publish whatever the author last
dictated. §10.2 is careful about the audio; the transcript is the same disclosure
in a different encoding, and revision 2 routed the pipeline straight through the
database holding it with no rule against selecting a row from it.

**2. Columns are an explicit allowlist**, never `SELECT *` [AD-9]. `history.py`
grows by migration — `restore_ms`, then five guard columns, then `raw_transcript`,
`fired_entries`, `vocab_ms`. A column added next phase is not published until
someone adds it to the list.

**3. Row exclusion follows §2.4(c)**, grouping on second-truncated `started_at`,
discriminating between the four readings, and logging the group count, the reading
applied, and the rows dropped.

**4. The export imports `percentile` from a dependency-free module** [AD-12].
`percentile` currently lives in `tier.py`, whose module-level imports pull `numpy`,
`amanuensis.audio.vad` and `amanuensis.engines.faster_whisper` — and through them
`faster-whisper`, CTranslate2 and the Silero ONNX asset. Installing an ASR runtime
in a Pages job to sort a list is the wrong trade for a principle that is otherwise
correct. **Extract `percentile` to `src/amanuensis/percentile.py`; `tier.py`
imports it from there; the export imports the same function.** One definition,
still owned by `mypy --strict`, no runtime. The principle §7.2 was defending —
call the product's own function, because a reimplementation is a second
implementation whose disagreements read as findings — is preserved exactly.

**5. The export refuses to run against a missing or empty database** rather than
emitting zeroes.

### 7.3 How the numbers are verified — and why the grep was replaced

Revision 2's defence was a CI grep for `\d+\s*ms` in the component tree. **It
could not fail for the reason it claimed** [AD-7], on four counts:

- It fires on values the spec itself mandates — §9's `150 ms` crossfade, `120 ms`
  hover, `0 ms` under reduced motion. The first CI run is red for reasons
  unrelated to truthfulness, and the fix is an ignore convention, after which it
  discriminates less.
- Three trivial spellings escape it: splitting the unit across elements, detaching
  the number (`const P95 = 538.9` rendered as `{P95}ms`), or spelling it —
  revision 2's own widget caption said "**Thirteen** sessions".
- It never inspects a value. A `claims.json` typed by hand passes every criterion.
- The property it claims to test is "this number came from `history.db` via the
  export." The property it actually tests is "this substring is absent."

**Replaced with a regeneration diff, which discriminates on the token the product
itself writes.** A fixture database is committed at
`tests/fixtures/site/history-fixture.db`. CI runs the export against it and fails
if the regenerated `claims.json` and session JSONs differ byte-for-byte from the
committed ones. This catches a hand-edited value, a hand-edited component reading
a stale value, *and* the export script silently changing behaviour — none of which
the grep could see.

**Two controls, because one control is passed by a constant** (`CLAUDE.md`):

| Control | Input | Must |
| --- | --- | --- |
| Negative | fixture with one row's `transcribe_ms` perturbed | **produce a diff.** If it does not, the check is not reading the database. |
| Positive | the clean committed fixture | **produce no diff.** If it does, the export is non-deterministic. |

Both run on every build. A check that has only ever seen agreement is
indistinguishable from a check that reads nothing.

---

## 8. Design system

### 8.1 Typefaces

- **IBM Plex Sans** — 400 and 600. Self-hosted woff2 subsets.
- **IBM Plex Mono** — 400 and 500. Self-hosted woff2 subsets.

Fallbacks declared: `-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`
and `ui-monospace, "SF Mono", Menlo, Consolas, monospace`.

**The mono rule, narrowed** [CC-5]. Revision 1 stated it as *"if it is set in
mono, a machine produced it"* — a rule inherited from a design direction that
paired mono against a serif. On a Plex Sans / Plex Mono pairing the perceptual
contrast is width and letterfit within one superfamily, and the rule was
additionally false of two of the three tokens it governed: a section overline and
a provenance caption are authored English that no machine produced and nothing
would parse.

The rule now reads: **if it is set in mono, it is a value the product produced or
would parse.** Transcripts, millisecond figures, config keys, glyphs, the install
block, the `history.db` row, stage names, `fired_entries`. Section overlines and
provenance captions move to **Sans 600, uppercase, letterspaced** — they are
labels, not data, and the type system should say so.

`font-variant-numeric: tabular-nums` globally.

### 8.2 Type scale

Base 17px. Single centred column at `max-width: 44rem`; the widget, the §2.3
table and the scatter break out to `56rem`.

| Token | Size / leading | Face | Use |
| --- | --- | --- | --- |
| `display` | `clamp(2.25rem, 5vw, 3.5rem)` / 1.12 | Sans 600 | H1 only |
| `h2` | 1.75rem / 1.3 | Sans 600 | Section headings |
| `lede` | 1.3125rem / 1.5 | Sans 400 | First sentence of a section |
| `body` | 1.0625rem / 1.65 | Sans 400 | Prose, max measure 66ch |
| `data` | 0.9375rem / 1.7 | Mono 400 | Transcript, tables, code, the row |
| `label` | 0.8125rem, ls 0.08em, uppercase | **Sans 600** | Section overlines, rail markers |
| `caption` | 0.9375rem / 1.55 | Sans 400, `--ink` | Provenance lines |

**`caption` is no longer muted** [CC-5]. §2.6 rule 3 requires unmeasured figures
at body size, and revision 1 simultaneously put provenance — the material that
rule protects — at the lowest contrast in the system. Provenance is `--ink`.

**One licensed exception:** §2.3's band table sets its figures at `h2` size in
mono. That table is the most honest object on the page and gets the largest
numerals.

### 8.3 Colour

Near-monochrome, warm. Both themes first-class; dark is not an inversion.

| Token | Light | Dark | Role |
| --- | --- | --- | --- |
| `--bg` | `#FBFAF7` | `#141311` | page ground, explicit on `body` |
| `--panel` | `#F5F3EC` | `#1B1A17` | shell blocks, widget strips |
| `--ink` | `#1C1B18` | `#E9E6DD` | primary text, filled stage bars |
| `--muted` | `#6E6B62` | `#8F8B80` | secondary text, unfilled waveform |
| `--rule` | `#E5E2D9` | `#2B2925` | hairlines, spine, empty tracks |
| `--link` | `#3A5F7D` | `#8FB4CE` | **new** — links and their underline |
| `--accent` | `#B23B22` | `#E06845` | live, or being measured |

**`--link` is new** [CC-6]. Revision 1 gave links `--ink` text with a `--rule`
underline — roughly 1.2:1 against the page — while simultaneously resting the
entire no-restatement strategy on links being found and followed, and requiring
every figure to carry a link to its record. The page's least-emphasised element
was the one its architecture depended on. A seventh token costs less than either
reopening the accent rule or shipping invisible exits. `#3A5F7D` on `#FBFAF7` ≈
6.4:1; `#8FB4CE` on `#141311` ≈ 8.1:1. Underline in `--link` at 60% opacity —
visible, not loud.

**The accent means one thing: live, or being measured.** The `●` glyph, the
playhead, the active spine tick, the caret, the g1 bracket. Two acknowledged
exceptions, named rather than pretended away: focus rings (where you are) and
the `⌥` keycap in the subhead (a depiction). It is never spent on headings,
backgrounds, buttons at rest, or decoration.

Stage bars are `--ink`, deliberately not accent: they are the record, not the
event.

Rationale: rubrication — scribes set in red the marks a reader must not miss.
It also collides usefully with the recording-dot convention, so one colour reads
as both the scribe's ink and "the mic is hot", which is the product's one
non-negotiable feedback requirement (PRD §5.4).

### 8.4 Space and rule

8px grid; tokens 8 / 16 / 24 / 40 / 64 / 96 / 144. Sections separated by a
full-measure 1px `--rule` hairline, 96px above and below (56px mobile).

**Rules, not cards.** Radius 0 everywhere except the widget frame at 2px. **No
shadows anywhere.** Separation comes from hairlines and the `--panel` / `--bg`
step.

Cost blocks: left border 1px / 2px / 3px in `--rule` by weight (§4.2), under the
shared `WHAT IT COSTS` label.

---

## 9. Motion

**Motion may only depict a measured duration, at true scale or at a labeled
scale. Everything else is static.** A page that makes the reader wait for content
to fade in refutes itself, and a 400 ms entrance animation is longer than the
product's p95.

### 9.1 What moves

1. The widget at 1×. Playhead linear — it is time, and time does not ease. Glyph
   swaps instantaneous. Text landing in one frame.
2. The 1/20× magnification, per §6.4. Bars proportional; labels dwell.
3. Spine tick activation: 150 ms crossfade, `ease-out`.
4. Hover and focus: 120 ms, `ease-out`, opacity and colour only.
5. Anchor scrolls: native `scroll-behavior: smooth`.

### 9.2 What does not move

No scroll-triggered reveals, fades or staggered entrances. No parallax. No pinned
or scrolljacked sections. No animated background. No hover lift. **No count-up
number animations** — a figure that spins from 0 to 223 spends its first 500 ms
being false.

The complete list of scroll-linked behaviour: spine tick activation, via
`IntersectionObserver`.

### 9.3 Reduced motion

Crossfade becomes an instant swap. Transitions drop to 0 ms. Smooth scroll
becomes instant, natively. The widget follows §6.8. Content never waits on
animation, so a reduced-motion reader loses zero information.

---

## 10. Prerequisites

Both block publication. Neither blocks code.

### 10.1 The licence file

`pyproject.toml:10` declares Apache-2.0. There is no `LICENSE` file on
`origin/main`.

A page saying "open source" that links a repository granting no licence claims
something the repository does not give. Add `LICENSE` (Apache-2.0, full text)
before publication.

### 10.2 The demo corpus

The existing corpora may not be used. `.gitignore` argues the case in three
places and is right: *"a voice recording is not something you can unpublish."*
`tests/fixtures/spontaneous/` and `tests/fixtures/phase3/` are unscripted speech
about the author's life and work.

**Required:** a purpose-recorded public corpus, at
`site/scripts/record_demo_corpus.py`, recording through the real daemon so the
timings are the product's own.

**Specified along two axes, not one** [CC-8]. Revision 1 specified only
*publishable*, which is how `tests/fixtures/asr/` came to contain no disfluencies
and four Phase 5 experiments produced "four converging negatives" that were one
confound. `AGENTS.md` carries the rule: *state what a fixture's construction
guarantees is present, not just what it contains.*

| Axis | Requirement |
| --- | --- |
| Publishable | Scripted, written for public display, committed with reference text. |
| Representative | **The script contains planted disfluencies** — a self-correction, a filled pause, a restart — read as written. Public-safe and demonstrates what PRD §1 rests the product claim on. |

**Sessions to record:**

| Session | Length | Purpose |
| --- | --- | --- |
| Hero | ~10 s, inside the 7–16 s band | The widget. Sits inside the headline figures. |
| Mid | **~30 s** | Closes the 16–60 s gap §2.5 names [CC-7]. |
| Long | ~60 s | Stage 3's long-form case as a real recording rather than a table row. |

Sized from the author's measured reading rate of **205 wpm**, not a textbook
figure.

`**The `.gitignore` exception is an exact-filename allowlist, not a directory
negation** [AD-10]. Revision 2 proposed `!site/public/audio/` — which is scoped by
*path* where the property is *provenance*, and which inverts the existing
enumerated-deny policy to allow-by-default inside that directory. Every `.wav` that
later reaches it is committed silently, and `history.py`'s `store_audio` writes
real dictation WAVs to the data directory, so a developer copying one in to debug
§6.10's failure path is one `cp` from publishing a private recording forever.

One negation line per published file:

```
!site/public/audio/hero-<date>.wav
!site/public/audio/mid-<date>.wav
!site/public/audio/long-<date>.wav
```

Each appears in a diff as a deliberate act a reviewer can question. "Recorded for
publication" is a fact about a recording session; git cannot verify it, so the
commit must name the file rather than the folder.

**Considered and rejected: keeping the audio out of git entirely**, attaching it
to the Pages deploy artefact instead. It is strictly safer — a deployed asset can
be deleted, a committed one is in every clone forever — and §6.10 already
establishes the audio is served rather than imported. Rejected because it splits
the corpus from the transcripts and timings that must stay in step with it, and a
demo whose audio and row can drift apart is worse than the risk the allowlist
already closes. Recorded so the trade is visible.

**A second speaker was considered and deferred** [CC-8]: §4 stage 6 concedes the
guard's false-positive direction is untested because six samples from one speaker
cannot produce a speaker it is wrong about, and this recording session could
supply a seventh at near-zero marginal cost. Deferred because it is a product
measurement, not a page asset, and belongs to the Phase 3 gate. Recorded here so
the opportunity is not lost silently.

**The corpus does not exist. The widget can be built against a fixture;
publication cannot.**

### 10.3 The repository must agree with the page

**Promoted from an open decision to a prerequisite** [AD-11]. The page will
publish `p50 206.0 / p95 538.9`. `README.md:111` and `CLAUDE.md` both publish
`p50 223.0 ms / p95 270.0 ms`, and `README.md:122` prints the scaling law and its
10/30/60 s table that §2.4(b) forbids the page from showing.

The page's CTA sends the reader to that repository. §3's reader checks. The first
check available to them returns two different numbers for the same claim and a
formula the page refused to print — and the page's entire strategy converts, at
that moment, into evidence that this project's numbers do not reproduce across its
own documents.

Before publication, in the source documents rather than only here:

1. Correct the p95 in `README.md` and `CLAUDE.md`, **and say in the revision note
   that the earlier figure was wrong**. Silent in-place editing destroys the
   evidence that the documents once agreed on something false.
2. Remove or requalify `README.md`'s scaling table, per §2.4(b).
3. Correct `README.md`'s "Not built yet: post-processing" — it has been built
   since 2026-08-08.

This has the same standing as §10.1 and for the same reason: the page would
otherwise claim something the repository does not support.

---

## 11. PRD §6.4 amendment

PRD §6.4 owns the repository layout; `CLAUDE.md` requires a gate amendment before
a top-level directory is added.

> **`site/` — the landing page.** A static Astro site, built and deployed by
> GitHub Actions to GitHub Pages. It is not a Python package, is not importable,
> is not on `sys.path`, and adds no runtime or test dependency to `amanuensis`.
> `pytest`, `mypy --strict` and `ruff` do not traverse it; its own toolchain
> lints and type-checks it in a separate CI job. It reads `history.db` at build
> time through `site/scripts/export-session.py`, importing `percentile` from
> `src/amanuensis/tier.py` and writing only into `site/`. The dependency
> direction is one-way: the site depends on the product, the product never on
> the site.

Also required: `mypy` and `ruff` configuration in `pyproject.toml` excludes
`site/`; `.gitignore` excludes `site/node_modules/` and `site/dist/`.

---

## 12. Acceptance criteria

### 12.1 Truthfulness

1. **The regeneration diff of §7.3 passes, with both controls.** The negative
   control (perturbed fixture) produces a diff; the positive control (clean
   fixture) does not.
2. No latency figure appears anywhere — heading, tile, `<title>`, OG description,
   alt text — without its p50, p95 and band.
3. No scaling equation and no extrapolated duration appears anywhere.
4. Every §2.5 gap is displayed at body size in section 11.
5. Experiment-level figures are labeled as experiment-level.
6. The transcript renders raw and processed, both real, from one row, with
   `fired_entries` shown.
7. **CI re-derives §2.3 from the fixture and fails on divergence from
   `claims.json`, printing both values.**
8. **The headline band is the band §2.2 rule 5 selects**, checked by asserting
   that `claims.json`'s headline entry is the `≤ 10 s` band — not by reading the
   prose. A rule about not choosing by outcome is worth nothing if the choice is
   re-made by hand at render time.

### 12.2 Zero runtime network

9. **The discriminating token is third-party origin count, not request count**
   [AD-8]. The page fetches a document, CSS, fonts and audio; a check asking "did
   I see a request" is satisfied by the page's own audio file. The criterion is:
   **origins other than the page's own == 0.**
10. **A committed script, not a person with devtools.** `scripts/verify_site_network.py`,
    exit code, run in CI. §12 promises criteria checkable by someone who did not
    build the page; a browser and a claim is neither. The tester's own content
    blocker would otherwise suppress the requests the check looks for and produce
    a clean reading — the failure `scripts/verify_g3.py:37` was written about.
11. **Two controls, per instrument.** A *positive* control page making one known
    third-party request must be observed by the same harness — proving it can see
    an origin at all. A *negative* control asserts the adjacent signal alone does
    not satisfy it: a page fetching only same-origin assets must read zero
    third-party origins while reading non-zero requests. `verify_g3.py:286` is the
    standard being imitated: "Each instrument is validated separately. A control
    that exercises only one of them licenses a clean reading from the other."
12. **The interaction surface is covered, not just load** [AD-8]. §6.7 gives the
    widget play, seek, replay, two disclosures and stage links. The harness
    exercises every control and re-checks. A beacon on `visibilitychange`, or a
    fetch behind the receipt toggle, is invisible to a page-load check.

### 12.3 Degradation

13. With JavaScript disabled the page renders completely and the widget shows its
    full end state.
14. With the audio asset returning 404, the widget shows its end state, the
    fallback line, and a working 1/20× replay.
15. At 320px width no element causes horizontal page scroll.
16. Under `prefers-reduced-motion: reduce`, no information is unavailable.

### 12.4 Craft

17. Both themes complete: full light palette on bare `:root`, dark redefinitions
    under both `prefers-color-scheme` and `[data-theme]`. No colour defined only
    inside a media query. `body` has an explicit token background.
18. Keyboard-only: every control reachable, focus always visible, the widget
    operable end to end.
19. **Every link meets WCAG 1.4.1** — link text is distinguishable from body text
    by more than colour alone, and the underline is visible against the page.
20. Lighthouse ≥ 95 on performance and accessibility.
21. The release point on the waveform aligns vertically with the left edge of the
    stage bars at every breakpoint.
22. **At 1/20×, every stage's label is legible for at least 250 ms**, including
    stages whose bars are sub-pixel. Verified by recording the replay and stepping
    frames, not by watching it.

### 12.5 Prerequisites

23. `LICENSE` exists at the repository root.
24. The demo corpus was recorded for publication, contains the planted
    disfluencies §10.2 requires, and `.gitignore`'s exception is scoped to `site/`
    and carries its reasoning.

---

## 13. Risks

**13.1 The page is optimised for the reader who checks, and most visitors do
not.** The defining bet. Depth-of-proof front-loads qualifications, and the best
material lives below the fold. Mitigated by a self-sufficient hero and a widget
legible unplayed; not fixed. §4.5 records that one route stakes this bet whole
and that the mitigation adopted is a served `claims.json` rather than a second
authored page.

**13.2 The corpus is a human dependency with an unknown schedule.** The widget
builds against a fixture; the page cannot ship until someone reads scripted
sentences into a microphone. The only task here nobody can delegate.

**13.3 The page will drift from the product unless §7 holds.** The export, the
no-literals grep and the register-diff check are the whole defence. If any is
disabled "temporarily", the page becomes another document agreeing with others
about a number nobody re-derived.

**13.4 This document was already stale once.** Revision 1 was written against a
tree one commit behind `origin/main` and specified a page announcing a shipped
feature as unbuilt. §12.1 criterion 7 exists so the *numbers* cannot repeat that;
nothing mechanically protects the *prose*. Re-read `CLAUDE.md`'s status block
against `origin/main` before every revision of this file.

**13.5 A 21st.dev component may not survive the design system.** No shadows,
radius 0, one semantic accent. Most registry components ship with elevation,
rounded corners and a colourful palette. Take structure and behaviour; discard
the surface. Budget for that rather than being surprised by it.

**13.6 The widget's timeline engine is load-bearing from the first commit**
[CC-9]. §6.10's no-broken-state requirement and §7.2's no-literals rule between
them rule out a pre-rendered clip and a CSS-keyframe implementation. There is no
cheap substitution available later.

---

## 14. Decisions taken since revision 1

| # | Question | Resolution |
| --- | --- | --- |
| 1 | Custom domain? | **No.** `joshedwards237.github.io/Amanuensis`, base path `/Amanuensis`. No DNS dependency; swapping later is one config line. Note the base path governs the audio asset, the fonts and the OG image — not internal anchors [CC-11]. |
| 2 | Ship before or after Phase 3? | **Moot — Phase 3 is built.** The page ships without waiting for the Phase 3 *gate*, and claims no gate outcome. |
| 3 | A long session in the corpus? | **Yes, plus a ~30 s session** to close the gap §2.5 names. |
| 4 | Star count? | **Omitted entirely.** Stale silently if baked; forbidden if fetched. |
| 5 | Apply §2.4's corrections to `CLAUDE.md` / `README.md`? | **Promoted to a publication prerequisite, §10.3** [AD-11]. Not an open decision: the page's CTA points at those documents, and they currently publish a different p95 and a formula the page refuses to print. Dated correction notes, not silent edits. |

---

## Revision log

- **2026-08-26, rev 3** — Twelve adversarial objections folded, two critical. The
  load-bearing one: **the headline band had been selected by outcome.** Revision 2
  chose `7–16 s` from five candidates, which has half the rows of `≤ 10 s` and a
  p95 47% better, and then attributed it to "a ten-second utterance" — the exact
  failure §2 exists to prevent, committed inside §2. §2.2 rule 5 now selects the
  band the specification binds, the published p95 moves 366.5 → 538.9, and §12.1
  asserts the choice against `claims.json` rather than trusting the prose. Also:
  the no-literals grep replaced by a regeneration diff with two controls, after it
  was shown to fire on the spec's own mandated motion durations and to be escaped
  by three trivial spellings while never inspecting a value (§7.3); the row
  exclusion rule rewritten against the stored timestamp format, having been
  unimplementable as written, and given a discrimination table instead of an
  assertion (§2.4c); session and column selection constrained to committed
  allowlists after the pipeline was found routed through the author's real
  dictation history with no rule against selecting from it (§7.2); `percentile`
  extracted to a dependency-free module and the export moved under `scripts/`,
  after the import was found dragging CTranslate2 into the Pages build and landing
  the only Python computing public numbers outside `mypy --strict` (§7.2, §11);
  the `.gitignore` exception narrowed from a directory negation to per-file
  allowlisting (§10.2); repository reconciliation promoted from an open decision to
  a prerequisite (§10.3); the network check given a discriminating token, a
  committed script, per-instrument controls and interaction coverage (§12.2).
  One objection was **rejected on evidence**: the proposed mechanism for the
  scaling law's failure — a wrong denominator, untrimmed capture versus trimmed
  audio — does not hold; refitting on `guard_retained_seconds` moves R² from 0.590
  to 0.598. The conclusion survives on range and fit quality instead (§2.4b).
- **2026-08-26, rev 2** — Rewritten against `origin/main` at 87034f4 after
  discovering revision 1 was authored from a tree one commit stale, in which
  Phase 3 appeared unbuilt. Post-processing promoted from an empty track to its
  own section and the widget's raw→processed diff (§4.3 stage 7, §6.5). Twelve
  choice-cartography findings folded; the material ones: the font CDN removed
  from both the design and the acceptance criterion it had been exempted from
  (§5.2, §12.2); the privacy claim converted from an appended section to a
  cross-cutting rail on the spine (§4.1); the mono rule narrowed to values the
  product produces, with overlines and captions moved to sans (§8.1); a `--link`
  token added after the underline was found at ~1.2:1 on a page whose strategy
  depends on links (§8.3); the 1/20× magnification given a label-dwell floor
  after the sub-10 ms stages proved illegible at one frame (§6.4); the corpus
  given a representativeness axis and planted disfluencies (§10.2); React
  replaced by Preact after it was found to have arrived as a side effect of the
  component-source decision (§6.11); a ~30 s session added to close the
  16–60 s gap (§2.5, §10.2); the claims register split into judgment and
  generated values with a CI divergence check (§0, §7.2, §12.1).
- **2026-08-26, rev 1** — Created. Three design directions generated
  independently and synthesised: structure and headline from *the loop*; the
  mono rule and rubrication accent from *the word*; the `history.db` receipt from
  *the evidence page*. All three independently refused the same four things —
  typewriter transcript, comparison table, hero stat tile, in-browser WASM demo —
  so those are prohibitions rather than preferences. §2 re-derived every figure
  from `history.db` rather than inheriting it from prose.
