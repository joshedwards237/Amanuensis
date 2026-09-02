# Amanuensis

Fully local, open-source dictation for macOS. Press a hotkey, speak, release —
your words appear as text at the cursor in whatever application has focus.

No account. No network at runtime. No audio leaving the machine.

---

## Status: Phase 3 gate **PASSED** 2026-09-01. Phase 4 in progress.

**The loop is closed.** Run `manu daemon`, hold right-option, speak, release —
your words appear at the cursor in whatever application has focus.

The Phase 3 gate ran on ten real dictations of 67–97 s and **passed**: edit rate
**8.59%**, of which 163 of 171 edits are the decoder's and 8 are the rules
chain's. That misses goal G2's 5% and the threshold was **deliberately not
moved** — the gap is carried as debt and revisited at the Phase 4 gate.
[`docs/gates/phase-3.md`](docs/gates/phase-3.md) has the full record, including
what the measurement cannot see.

Working: model download and the install-time tier check (`manu install`), the
global hotkey, the resident daemon, microphone capture, silence trimming,
transcription, the collapse guard, the pre-injection history write, injection
with clipboard save/restore, and a menu-bar recording indicator. Still refusing
and naming their phase: `history` without `--last` (Phase 3), `toggle` and
`status` (Phase 4).

**The collapse guard** (2026-08-07, PRD §5.7) exists because `initial_prompt`
can silently destroy a transcript, and shipped in Phase 1 with nothing watching
it. A 30.5-second dictation returned two words, no error, injected at the
cursor. The guard measures how much of your speech the decoder actually got
through; below half, the audio is decoded again with the vocabulary bias
dropped, and if that fails too the text is **not** injected — `manu history
--last` gives you the words. Verified on real audio: fires at 8.3% coverage on a
reproduced collapse, silent on all six corpus samples with a floor of 82.8%.
[`docs/gates/phase-2b-followup.md`](docs/gates/phase-2b-followup.md).

Two menu-bar states are worth knowing: `◍` means the guard recovered a
transcript, so what landed was decoded without your `initial_prompt` and is less
reliable at proper nouns. `⚠` after a dictation means the words were withheld.

**Post-processing** shipped 2026-08-08. A deterministic rules pass cleans
whitespace, sentence capitalisation and punctuation spacing before the transcript
is injected; `manu history --raw` shows what the model emitted before it ran. It
is measured at p50 0.0445 ms against the Phase 1 corpus — an experiment figure,
not a gate figure. Two rules are deliberately absent: lowercasing a spurious
mid-sentence capital (indistinguishable from a proper noun without a model) and
folding spoken numbers into digits (measured harmful — *one thought ends* became
*1 thought ends*).

What the guard cannot see: a transcript that is too *long*, and one that covers
the audio and gets the words wrong. It catches a decoder that stopped early,
which is the failure that was observed. The false-positive direction — refusing
something you actually said — is **untested**, because six corpus samples from
one speaker cannot produce a speaker it is wrong about.

Injection is verified in TextEdit, Terminal, VS Code and Chrome, on both
strategies, by reading the text back out of each application rather than by eye.
Zero failures. See [`docs/gates/phase-2a.md`](docs/gates/phase-2a.md) and
[`docs/gates/phase-2b.md`](docs/gates/phase-2b.md).

The specification behind it has been adversarially reviewed twice — 41
dispositions across two rounds, all resolved — and every phase since has
measured rather than assumed. See [`docs/gates/`](docs/gates/).

| | |
|---|---|
| [`AMANUENSIS_PRD.md`](AMANUENSIS_PRD.md) | The standing specification — what and why |
| [`HARNESS.md`](HARNESS.md) | The operating contract — how work is allowed to proceed |
| [`CLAUDE.md`](CLAUDE.md) | Project conventions for AI-assisted development |
| [`docs/superpowers/`](docs/superpowers/) | Adversarial review records — 41 dispositions across two rounds, all resolved |
| [`docs/gates/`](docs/gates/) | One measurement record per phase gate, plus the probe and the Phase 5 experiments |
| [`docs/adr/`](docs/adr/) | Architecture decisions — 0001 selects the ASR engine |

It is usable now, if you are willing to run it from a source checkout and live
without post-processing. There is no packaged app, no installer, and no signed
binary — that is Phase 4.
[nerd-dictation](https://github.com/ideasman42/nerd-dictation) (Linux) and
[Talon](https://talonvoice.com/) are the mature alternatives; PRD §1 records why
this exists alongside them.

---

## Install

macOS only (PRD §3) and Python **3.12 or later**. There is no packaged app, no
installer and no signed binary yet — Phase 4 is where that lands. What follows is
the whole path from nothing to a first dictation.

**1. Get the source and install it.**

```sh
git clone https://github.com/joshedwards237/Amanuensis.git
cd Amanuensis
python3.12 -m venv .venv && source .venv/bin/activate
pip install .
```

**2. Generate the reference clip.**

```sh
scripts/make_tier_clip.sh
```

The install measures your machine against a ten-second speech clip, and **the
repository does not ship one**. That is not an oversight: PRD §7.2 requires a
clip that is not your voice and needs no microphone permission before first use,
which leaves synthesised speech — and the redistribution grant for a macOS
system voice is not clear enough to commit one. So you generate it locally with
`say`. No microphone, no network. Settling this is an open Phase 4 item.

If you are not on macOS-with-`say`, or you would rather use your own recording:
`manu install --clip /path/to/ten-seconds.wav`.

**3. Download the model and measure this machine.**

```sh
manu install
```

This is **the only network access Amanuensis ever makes**, and it happens once.
It fetches the ASR weights from Hugging Face over HTTPS at a pinned revision,
then re-hashes every downloaded file against a SHA-256 this project recorded
itself — a mismatch is refused, not warned about (§7.6). Then it runs nine timed
decodes on the clip from step 2 to find which speed tier your machine is in.

Expect a few minutes; the download was measured at 185 s on the author's
connection and yours will differ. It prints `checksums verified`, then your tier
and the p50 and p95 it measured. Those are your numbers, not ours.

**4. Grant two macOS permissions.**

The daemon needs **Accessibility** (to type into other applications) and **Input
Monitoring** (to see the hotkey). They are separate panes in System Settings →
Privacy & Security, and granting one does not grant the other.

**The entry you are looking for carries your terminal's name, not "Amanuensis".**
macOS attaches these grants to whatever launched the process, so look for
Terminal, iTerm, Ghostty, or VS Code — whichever you ran `manu` from. This is a
real wart and it goes away when Phase 4 ships an `.app` bundle. `manu daemon`
names both permissions and tells you which is missing if you skip this step.

**5. Dictate.**

```sh
manu daemon
```

Hold **right-option**, speak, release. The text appears at your cursor in
whatever application has focus. A glyph appears in your menu bar while the daemon
runs: `○` idle, `●` recording, `◐` transcribing. Stop the daemon with Ctrl-C.

If you would rather check the pieces before binding a hotkey:

```sh
manu transcribe --seconds 10        # record and print, inject nothing
```

**6. Uninstall.**

```sh
manu history --purge                # transcripts, stored audio, and the database
pip uninstall amanuensis
rm -rf ~/Library/Application\ Support/amanuensis    # config, weights cache aside
```

The model weights live in the Hugging Face cache (`~/.cache/huggingface`) and are
shared with anything else that uses them; delete that separately if you want the
disk back. Revoke the two permissions in System Settings — uninstalling does not.

### If it does not work

- **Nothing happens when I hold right-option.** Input Monitoring is not granted
  to the terminal you launched from. `manu daemon` says so on startup.
- **The glyph goes `●` then nothing appears.** Accessibility is missing —
  transcription worked, injection did not. `manu history --last` has your words.
- **`⚠` after a dictation.** The collapse guard withheld the text because the
  decoder stopped early. `manu history --last` has what it got.
- **`manu install` says the reference clip is missing.** Step 2 — the clip is
  generated locally and is not in the repository.
- **I said "new paragraph" and got the words instead of a break.** Known, and
  the cause is documented in PRD §7.5: the rule fires only when the decoder
  supplied sentence marks on both sides of the phrase, and it frequently does
  not.

## What it will do

Press and hold a hotkey, speak, release. The transcript is post-processed and
injected at the cursor. A daemon keeps the ASR model resident in memory, because
loading a model per invocation costs 3–8 seconds and there is no version of that
which is acceptable.

```sh
manu install                        # download the model once, measure this machine's tier
manu daemon                         # hold right-option, speak, release
manu transcribe --seconds 10        # one-shot diagnostic: record and print
manu transcribe --inject            # one-shot: record, persist, paste at the cursor
```

The daemon needs **two separate macOS permissions** and will name both if
either is missing: **Accessibility** to type into other applications, and
**Input Monitoring** to see the hotkey. They live in different Settings panes
and granting one does not grant the other. macOS attaches both to whatever
launched `manu`, so until this ships as an `.app` the entry you are looking for
carries your terminal's name.

While the daemon runs there is a glyph in your menu bar: `○` idle, `●`
recording, `◐` transcribing. macOS shows its own microphone indicator too, and
that one is not ours to get wrong.

- **Batch transcription**, not streaming, for v1 (PRD §7.1)
- **faster-whisper** by default, behind an abstraction so the engine can be
  swapped (§7.2)
- **Clipboard paste** by default with a keystroke fallback (§7.3)
- **Deterministic post-processing** first. An optional local LLM cleanup pass —
  the Wispr-style "remove my false starts" behaviour — is specified but **does
  not work yet**: tested 2026-07-31, it made transcription 5–28× worse on real
  output. Four alternative approaches are recorded and untested
  ([`docs/gates/phase5-feasibility.md`](docs/gates/phase5-feasibility.md))

## Targets

| Goal | Target | Status |
|---|---|---|
| Latency, Tier A | p50 ≤ 400 ms, p95 ≤ 800 ms — hotkey release → text present, 10 s utterance | **Met.** Over every clean row at ≤ 10 s in `history.db` (n = 27): **p50 206.0 ms / p95 538.9 ms**. All stages are now in the number, post-processing included. **Read the scaling note below before quoting this figure** |
| Latency, Tier B | p50 ≤ 2 000 ms — published, not gated; a class missing it is dropped rather than shipped | **unmeasured.** No Tier B machine has run this. A simulated thread constraint is not a slower computer |
| Accuracy | edit rate ≤ 5% | **not yet measured.** Edit rate is a Phase 3 measurement; the WER figures in `docs/adr/0001-engine-selection.md` are a different quantity |
| Network traffic at runtime | zero | **verified twice**, most recently with pyobjc added: 0 sockets and 0 bytes against a control that saw 865 bytes. Scope caveat below |

Tiers are **measured, not named after silicon** (§7.2). CTranslate2 has no Metal
backend, so "Apple Silicon" was never a distinct execution path — a machine's tier
is decided by what it measures at install.

**The latency figure is for a ten-second utterance and it does not generalise
across lengths.** These are measured bands from `history.db`, with concurrent
benchmark rows excluded:

| you spoke for | text appears after | n |
|---|---|---|
| ≤ 10 s | p50 206.0 ms / p95 538.9 ms — the band G1 gates | 27 |
| 16–60 s | **no band exists** — fewer than the ten clean observations needed before a percentile is publishable | 7 |
| ≥ 60 s | p50 1566.4 ms / p95 4203.6 ms — well over the 800 ms p95 | 11 |

That is not a bug and not a missed goal: PRD §2 binds G1 at ten seconds and says
so. But dictating a paragraph is the ordinary case, and the headline number says
nothing about it, so both are here.

> **Correction, 2026-08-31.** This section previously published a fitted model,
> `transcribe_ms ≈ 49 + 13.7 × seconds`, and a 10/30/60 s table derived from it.
> **Those numbers were wrong and are withdrawn.** The model was fitted over
> n = 14 spanning 0.7–43.4 s and then used to predict at 60 s, outside the range
> it ever saw; refitting the clean rows over 0.8–104.4 s gives R² ≈ 0.59, so a
> duration-only linear model does not predict a single decode. `CLAUDE.md`
> reached the same conclusion independently from ten ~74 s takes (p50 917–938 ms
> against a predicted 1069). The table above replaces it with measured bands
> only, and no figure here is extrapolated to a duration that was not measured.

Every latency figure here is from **one machine and one speaker in one room**.

**The latency claim is hardware-conditional and that is a real caveat**, not a
footnote. Privacy motivation and offline constraint correlate with older
machines, so the users this exists for are disproportionately the ones on the
slower tier. PRD §4 says so in the same place it makes the speed claim.

## Known costs, stated up front

The PRD's rule is that a cost gets documented rather than papered over. Three
that will affect you as a user. The first two are now **measured**, not argued.

- **Your transcripts go into your clipboard manager.** Not "may" — measured
  against a real one (Maccy) on default settings: every transcript was captured,
  including with clipboard restore on and its 150 ms window. That window is not
  a mitigation. This is the manager working correctly, and several managers sync
  across devices, so for those users a transcript leaves the machine as a direct
  consequence of the defaults.

  Amanuensis detects known managers and warns before recording starts, but
  detection is **incomplete by nature** — absence of a warning means "no known
  manager detected", never "no manager present". (§7.3)

- **`strategy = "keystroke"` avoids the clipboard and silently rewrites your
  text.** macOS text substitution applies to synthetic keystrokes exactly as it
  does to real ones. Typed into TextEdit:

  ```
  you said : don't use --dashes... "quoted" and i said so
  you get  : don’t use —dashes… “quoted” and I said so
  ```

  Five changes in one sentence — smart quotes, em dash, ellipsis,
  autocapitalisation. Pasting the same text is byte-identical. Nothing
  Amanuensis can do reaches another application's substitution settings, so this
  is a warning rather than a fix; turn substitution off in the applications you
  dictate into. The trade is real and unpleasant: the strategy that protects
  your privacy is the one that alters your words.

- **Zero-network verification covers this process only.** Packet capture on
  Amanuensis cannot see egress that happens inside a different process, which is
  exactly where the clipboard path goes. The Maccy result above *is* that blind
  spot, measured. (§2 G3)

## Scope

**macOS only for v1.** Windows is post-v1 intent — it ships no code and gates
nothing, but the architecture carries a portability floor so the port stays a
port (§7.3). Linux is a non-goal.

Also out of scope for v1: streaming partials on screen, speaker diarization,
mobile, cloud sync, OS voice commands, and text-to-speech.

## How this repository is built

Development is phase-gated. Each phase ends at an approval gate that states what
would **reject** it, and writes its measurements to `docs/gates/`. The
specification is reviewed adversarially before implementation: 12 objections, 13
choice stories and 7 slicing decisions in the first round, 9 more objections in
the second, all adjudicated, and every amendment carries a dated revision-log row.

That process is the reason this README can be specific about what is unmeasured
— and the gate records are the reason it can be specific about what is measured.
Each one states what would have rejected the phase, and three of them record a
number that contradicted the specification.

## Licence

Apache-2.0 (intended). See PRD header for the reasoning.
