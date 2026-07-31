# Amanuensis

Fully local, open-source dictation for macOS. Press a hotkey, speak, release —
your words appear as text at the cursor in whatever application has focus.

No account. No network at runtime. No audio leaving the machine.

---

## Status: pre-implementation

**There is no code in this repository yet.** Phase 0 has not started.

What exists is a specification that has been adversarially reviewed and, in the
parts that matter, *measured* — the latency targets are not estimates any more.
See [`docs/gates/probe.md`](docs/gates/probe.md) and
[`HANDOFF.md`](HANDOFF.md).

| | |
|---|---|
| [`AMANUENSIS_PRD.md`](AMANUENSIS_PRD.md) | The standing specification — what and why |
| [`HARNESS.md`](HARNESS.md) | The operating contract — how work is allowed to proceed |
| [`CLAUDE.md`](CLAUDE.md) | Project conventions for AI-assisted development |
| [`docs/superpowers/`](docs/superpowers/) | Adversarial review records — 32/32 dispositions resolved |
| [`docs/gates/`](docs/gates/) | Measurement records: the pre-Phase-0 probe and the Phase 5 feasibility test |
| [`HANDOFF.md`](HANDOFF.md) | Current state, next steps, open risks |

If you are looking for a dictation tool you can use today, this is not one yet.
[nerd-dictation](https://github.com/ideasman42/nerd-dictation) (Linux) and
[Talon](https://talonvoice.com/) both work now; PRD §1 records why this exists
alongside them.

## What it will do

Press and hold a hotkey, speak, release. The transcript is post-processed and
injected at the cursor. A daemon keeps the ASR model resident in memory, because
loading a model per invocation costs 3–8 seconds and there is no version of that
which is acceptable.

- **Batch transcription**, not streaming, for v1 (PRD §7.1)
- **faster-whisper** by default, behind an abstraction so the engine can be
  swapped (§7.2)
- **Clipboard paste** by default with a keystroke fallback (§7.3)
- **Deterministic post-processing** first; an optional local LLM pass is
  specified but deferred (§7.5, §9)

## Targets

Every number below is a **pre-implementation estimate**, not a measurement.
Replacing them with real numbers is what the first phases are for.

| Goal | Target |
|---|---|
| Latency (accelerated: Apple Silicon / CUDA) | p50 ≤ 400 ms, p95 ≤ 800 ms, hotkey release → text present, 10 s utterance |
| Latency (CPU-only) | p50 ≤ 2 000 ms — published, not gated; a tier missing it is dropped rather than shipped |
| Accuracy | edit rate ≤ 5% (provisional) |
| Network traffic at runtime | zero, verified by packet capture |

**The latency claim is hardware-conditional and that is a real caveat**, not a
footnote. Privacy motivation and offline constraint correlate with older
machines, so the users this exists for are disproportionately the ones on the
slower tier. PRD §4 says so in the same place it makes the speed claim.

## Known costs, stated up front

The PRD's rule is that a cost gets documented rather than papered over. Two that
will affect you as a user:

- **Transcripts transit the system clipboard by default.** Any installed
  clipboard manager may capture them, and several sync across devices. This is
  the normal operation of that class of app, not a race condition. Amanuensis
  detects known managers and surfaces the exposure, but detection is
  **incomplete** — absence of a warning means "no known manager detected", never
  "no manager present". `strategy = "keystroke"` avoids the clipboard entirely
  at some cost in speed. (§7.3)
- **Zero-network verification covers this process only.** Packet capture on
  Amanuensis cannot see egress that happens inside a different process, which is
  exactly where the clipboard path goes. (§2 G3)

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
choice stories and 7 slicing decisions have been raised against it and
adjudicated, and every amendment carries a dated revision-log row.

That process is the reason this README can be specific about what is unmeasured.

## Licence

Apache-2.0 (intended). See PRD header for the reasoning.
