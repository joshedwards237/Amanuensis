# Amanuensis

Fully local, open-source dictation for macOS. Press a hotkey, speak, release —
your words appear as text at the cursor in whatever application has focus.

No account. No network at runtime. No audio leaving the machine.

---

## Status: Phase 2a complete. Phase 2b next.

**Words now reach the cursor, but there is still no hotkey.** `manu transcribe
--inject` records from the microphone, transcribes, persists the transcript, and
pastes it into whatever application has focus. That is the product's whole path
except the thing that triggers it — a global hotkey and the resident daemon are
Phase 2b, so today you type a command instead of pressing a key.

Working: model download and the install-time tier check (`manu install`),
microphone capture, silence trimming, transcription, the pre-injection history
write, and injection with clipboard save/restore. Still refusing and naming
their phase: `daemon`, `toggle`, `status`, `history`.

Injection is verified in TextEdit, Terminal, VS Code and Chrome, on both
strategies, by reading the text back out of each application rather than by eye.
Zero failures. See [`docs/gates/phase-2a.md`](docs/gates/phase-2a.md).

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

If you are looking for a dictation tool you can use today, this is not one yet —
a tool you must run a command to start is not a dictation tool.
[nerd-dictation](https://github.com/ideasman42/nerd-dictation) (Linux) and
[Talon](https://talonvoice.com/) both work now; PRD §1 records why this exists
alongside them.

## What it will do

Press and hold a hotkey, speak, release. The transcript is post-processed and
injected at the cursor. A daemon keeps the ASR model resident in memory, because
loading a model per invocation costs 3–8 seconds and there is no version of that
which is acceptable.

Today the same path runs from a command instead of a key:

```sh
manu install                        # download the model once, measure this machine's tier
manu transcribe --seconds 10        # record and print, no injection
manu transcribe --inject            # record, persist, and paste at the cursor
```

`--inject` needs macOS **Accessibility** permission, and it will tell you which
application to grant it to — macOS attaches the grant to whatever launched
`manu`, so until this ships as an `.app` the entry you are looking for carries
your terminal's name.

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
| Latency, Tier A | p50 ≤ 400 ms, p95 ≤ 800 ms — hotkey release → text present, 10 s utterance | **Met, still a floor.** ASR p50 299.7 / p95 373.3 ms over 54 observations; injection and the history write add p50 3.3 / p95 6.9 ms. A real end-to-end dictation measured **231.6 ms**. Post-processing is the one stage not yet in the number |
| Latency, Tier B | p50 ≤ 2 000 ms — published, not gated; a class missing it is dropped rather than shipped | **unmeasured.** No Tier B machine has run this. A simulated thread constraint is not a slower computer |
| Accuracy | edit rate ≤ 5% | **not yet measured.** Edit rate is a Phase 3 measurement; the WER figures in `docs/adr/0001-engine-selection.md` are a different quantity |
| Network traffic at runtime | zero | **verified twice**, most recently with pyobjc added: 0 sockets and 0 bytes against a control that saw 865 bytes. Scope caveat below |

Tiers are **measured, not named after silicon** (§7.2). CTranslate2 has no Metal
backend, so "Apple Silicon" was never a distinct execution path — a machine's tier
is decided by what it measures at install.

Every latency figure here is from **one machine and one speaker in one room**.
The 231.6 ms end-to-end number is a single dictation; the distributions behind it
come from replayed corpus audio, not from ten people using it.

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
