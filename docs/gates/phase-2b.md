# Phase 2b gate — the loop closes

**Date:** 2026-08-03
**Branch:** `phase-2b-hotkey`
**Hardware:** Apple M3 Max, 14 cores (10 performance / 4 efficiency), 36 GB, macOS 27.0
**Interpreter:** CPython 3.14.5
**Tier on this machine: A** (recorded at the Phase 1 gate)

**Verdict: PASS.**

Hold right-option, speak, release, and the words appear at the cursor. This is
the first end-to-end G1 measurement as §2 defines it — hotkey release to text
fully present — and it is taken from the daemon's own `history.db` rows rather
than from a harness, because `LatencyBreakdown` already persists and every
column exists.

**G1: p50 223.0 ms / p95 270.0 ms** against 400 / 800, over ten real dictations
in the 7–16 s band G1 is defined against. Still a floor — post-processing is
Phase 3 — and one that now has only one stage missing.

Two defects were found by running the daemon rather than by reading it, and one
of them made the product unstoppable.

---

## What the gate asked

PRD §9, Phase 2b:

> **Gate:** **First end-to-end G1 measurement** as §2 actually defines it —
> hotkey release to text fully present, via `g1_ms`, on a Tier A machine, with
> `chain = ["rules"]`. Confirm the recording indicator is visible without
> opening a menu.
>
> **Rejects if:** G1 is missed on a Tier A machine, or recording state is
> ambiguous at any point while the mic is live.

`chain = ["rules"]` names a component Phase 3 builds. Resolved before the phase
started, following Phase 2a's precedent: measure with an empty chain and label
`g1_ms` a floor once more, naming `postprocess_ms` as the stage still missing.

## What was measured

### G1, from the daemon's own rows

Fourteen real dictations by one speaker on 2026-08-03, through the hotkey, into
whatever application had focus. Nearest-rank, no interpolation. §2 defines G1
against a **ten-second** utterance, so the band is reported separately from the
full set — and the difference between the two is finding 3.

**The ten dictations in the 7–16 s band (n=10):**

| Stage | p50 | p95 | min | max |
|---|---|---|---|---|
| `capture_ms` | 10,298.7 | 15,153.8 | 7,916.3 | 15,153.8 (excluded from G1) |
| `vad_ms` | 36.4 | 59.3 | 30.8 | 59.3 |
| `transcribe_ms` | 180.5 | 211.3 | 139.9 | 211.3 |
| `asr_ms` | 214.9 | 265.6 | 172.0 | 265.6 |
| `postprocess_ms` | 0.0 | 0.0 | 0.0 | 0.0 (**not built — Phase 3**) |
| `persist_ms` | 1.3 | 3.4 | 1.2 | 3.4 |
| `inject_ms` | 0.7 | 14.9 | 0.6 | 14.9 |
| `restore_ms` | 155.3 | 156.0 | 0.0 | 156.0 (excluded from G1) |
| **`g1_ms`** | **223.0** | **270.0** | **173.8** | **270.0** |

**All fourteen, including a 0.7 s tap and a 43 s paragraph (n=14):**

| Stage | p50 | p95 | min | max |
|---|---|---|---|---|
| `asr_ms` | 213.4 | 792.2 | 140.7 | 792.2 |
| **`g1_ms`** | **215.3** | **795.0** | **144.5** | **795.0** |

Both readings pass. The second passes by **5 ms**, and that is finding 3.

Zero errors, zero failed injections, fourteen of fourteen `injected = 1`.

**The p95 here is the maximum observation, and that is a real limit.** At n=14
the nearest-rank p95 is the 14th value; at n=10 it is the 10th. Neither is an
estimate of a 95th percentile — each is an extreme. The number is honest about
what it measured and should not be read as a distribution. More samples accrue
without any further work, because the daemon measures itself every time it is
used.

### The recording indicator

Confirmed by the operator, not by me — I cannot see the menu bar:

> "I do see the glyph and it responds to fill when I hold the key and then goes
> back to the empty circle when it's idle."

`○` idle, `●` recording, `◐` transcribing, `⚠` error. In the status item's
title, not behind a click, because §5.4 says "visible without the tray menu
open" and an indicator whose state requires opening it is that requirement
restated as its own violation.

**A second, independent indicator exists and Amanuensis does not control it.**
The operator also observed macOS's own microphone-in-use indicator. That is
worth recording because it is the one recording signal this product cannot
suppress, cannot get wrong, and does not have to be trusted for — §5.4's
requirement is met twice over, once by something outside the process.

**The operator wants more than a glyph.** See finding 4; it is a §5.4
amendment, not a gate failure.

### Scaling — measured because the samples happened to span 0.7 s to 43 s

| capture | `transcribe_ms` | ms per second of audio |
|---|---|---|
| 0.7 s | 132.3 | 183.3 |
| 5.5 s | 141.6 | 25.7 |
| 9.8 s | 139.9 | 14.3 |
| 15.2 s | 211.3 | 13.9 |
| 43.4 s | 703.1 | 16.2 |

Least squares over all fourteen: `transcribe_ms ≈ 48.8 + 13.69 × seconds`.
A fixed cost of about 49 ms plus 13.7 ms per second of speech. This is finding 3.

## What was built

```
src/amanuensis/
├── hotkey/
│   ├── base.py            + check_permissions() on the ABC (finding 5)
│   ├── macos.py           NEW — MacOSHotkeyListener, listen-only CGEventTap
│   └── factory.py         darwin -> MacOSHotkeyListener; the Phase 0 stub is gone
├── controllers/
│   └── dictation_controller.py  NEW — DictationController, DictationState,
│                                and `deliver` lifted from cli.py unchanged
├── ui/
│   └── indicator.py       NEW — RecordingIndicator, the minimum §5.4 surface
├── injection/
│   ├── base.py            + focus_identity() on the ABC
│   └── macos.py           + focus_identity() via NSWorkspace
├── storage/
│   └── history.py         + sweep_pending(), + restore_ms column, + migrations
└── cli.py                 `daemon` implemented; `deliver` now imported
```

259 tests (184 at the Phase 2a gate), `mypy --strict src/` clean across 31
files, `ruff` clean, `black` clean.

## Deferred, by design

- **`manu toggle` and `manu status` still refuse**, and now name Phase 4. See
  finding 6.
- **`manu history` does not surface pending transcripts.** §5.5 gap 3. Phase 3.
- **Post-processing.** Every `g1_ms` here is still a floor. Phase 3.
- **The asynchronous restore.** 155 ms of worker thread spent holding the
  transcript on the clipboard, outside G1 and real. Not done: it races the next
  dictation, and the serial worker is what makes the focus check meaningful.
  Revisit in Phase 4 with the tray, which is where a restore that outlives its
  session would need somewhere to report failure.

## What this phase revealed that the PRD got wrong

Six findings. Four need a PRD amendment and are marked.

### 1. The daemon could not be stopped — **no amendment, a defect**

`Ctrl-C` did nothing. `SIGTERM` did nothing. The only way to stop a process
holding the microphone was `kill -9`. Two independent causes, and fixing either
alone leaves it broken:

- **CPython cannot run a signal handler while the main thread is inside
  `NSApplication.run()`.** Handlers execute between bytecodes; `run()` is a C
  call that does not return until the loop ends. The signal was recorded and
  never delivered — the handler that stops the daemon could not run until the
  daemon had stopped.
- **`NSApplication.stop_` does not end the loop.** It sets a flag checked the
  next time an event is *dequeued*, and an idle dictation daemon has no events.

A repeating `NSTimer` (250 ms) yields to the interpreter so the handler runs; a
posted application-defined event makes the loop notice the flag.

This is worth more than its fix. §5.4 makes ambiguous recording state
non-negotiable *because it is a privacy problem* — and a daemon holding the
microphone that the user cannot stop is that same problem with the escape hatch
removed. The indicator said `○` correctly the entire time. Nothing about the
state display was wrong. The failure was that knowing did not help.

### 2. `restore_ms` had no column — **no amendment, the PRD was right**

Phase 2a added `restore_ms` to `LatencyBreakdown` as that phase's headline
finding, argued it across §2 and §6.3, and **never added the column**.
`to_history_row()` emitted the value and `_insert` dropped it, silently, for
every row written since. Found here by reading a real row.

This is the second instance of a pattern AGENTS.md already records: *a PRD
amendment that withdraws or adds a number must reach the tooling that can
regenerate it.* The first was `bench_engines.py` still computing a withdrawn WER
figure two months after its withdrawal.

The test asserts structurally — it iterates `dataclasses.fields(LatencyBreakdown)`
and requires a column for each — rather than naming `restore_ms`. The defect was
a hand-maintained list that stopped being checked against the dataclass, and
adding one more name to that list would not have fixed it.

`mark_injected` now completes `restore_ms` for the same structural reason it
completes `inject_ms`: at write time the restore has not happened.

### 3. G1 is defined at 10 s and the product is used at every length — **amend §2**

The gated number and the number the user experiences are not the same number,
and the gap is a function of utterance length:

```
transcribe_ms ≈ 48.8 + 13.69 × seconds_of_audio        (n=14, R² visibly high)
  10 s ->  186 ms  ->  g1 ≈ 225 ms
  30 s ->  460 ms  ->  g1 ≈ 499 ms
  60 s ->  870 ms  ->  g1 ≈ 909 ms                     OVER G1's 800 ms p95
```

§2 already says G1 binds at 10 s and that §7.1's 15–30 s band is a *revisit
trigger* rather than a second budget. That reading holds and nothing here
violates it. What §2 does not say is that **the gated figure is the best case
of a linear relationship**, so a user dictating a paragraph — the ordinary case,
not an edge case — waits proportionally longer and G1 says nothing about it.

**This lands on Phase 3 immediately.** Phase 3's gate is *ten real dictations of
≥ 60 seconds*, which is precisely where this model predicts ~909 ms. Phase 3
will therefore measure long utterances against a budget calibrated at 10 s, and
without this note the result reads as a regression introduced by
post-processing. It is not: it is the utterance length, and it was already true
here.

Recorded now rather than discovered there. §2 gains the scaling statement and
the honest consequence.

### 4. The minimum indicator is minimal, and the operator said so — **amend §5.4, §9 Phase 4**

Asked to confirm the gate condition, the operator confirmed it and then said:

> "I do want to have an app of sorts or some sort front-end visual confirmation
> that it's recording other than just the tiny dot. If the dot is all we can do
> right now [without] building an app, then put this desire into the PRD for
> later down the line."

The gate condition is met — the state is visible without opening a menu, which
is what §5.4 requires and what the reject condition tests. The request is for
something §5.4 does not currently ask for: a recording affordance with more
presence than a menu-bar glyph.

Recorded as Phase 4 scope rather than built here, because building it means
either an `NSPanel` overlay or a real `.app` bundle, and both are the Phase 4
work §9 already names. §5.4 gains the requirement; Phase 4's deliverable list
gains the item.

Worth stating plainly: this is the first requirement in this project that came
from using the product rather than from specifying it.

### 5. `HotkeyListener` had no permission check — **amend §6.3**

The ABC declared `start`, `stop` and `is_running`. Its own docstring said
`start` "raises if the OS refuses the tap — on macOS that means Input
Monitoring has not been granted, which is a startup-time condition the tray must
surface". A condition the tray must surface needs a method that answers it
without raising.

`TextInjector.check_permissions` exists on exactly this argument, and §7.3's
portability floor item 4 says the hotkey listener should get the same treatment
as the injector. Added, non-prompting, with its own remediation naming Input
Monitoring **and** saying it is not Accessibility — the two are separate grants
in separate panes and a user who granted one for Phase 2a will believe they
granted both.

The daemon reports both missing grants at once rather than one at a time. A user
who fixes one, restarts, and is then told about the other has been sent to
System Settings twice for a condition fully known the first time.

### 6. `manu toggle` and `manu status` had a phase that did not want them — **amend §9 Phase 4**

`cli.py` said both were Phase 2b. §9's Phase 2b text names the listener, the
controller and the indicator, and names neither. Both are IPC to a running
daemon, and the transport is §7.3's portability floor item 3 — which **no phase
ever scheduled**.

Moved to Phase 4, which owns `toggle` mode and the tray. Recorded rather than
silently left, because a floor item with no phase is a floor item that does not
exist, and this is the phase that would have shipped `_VERB_PHASES` saying
"Phase 2b" about work Phase 2b had just finished without doing.

## Also worth recording

- **The event tap is listen-only, and that is the most consequential argument in
  the phase.** It sees every modifier event on the machine. An active tap can
  rewrite or discard them; a dictation tool that swallows a keystroke has broken
  another application's input, and the user cannot tell that from a hardware
  fault. A missed hotkey is recoverable by pressing the key again.
- **Modifier state cannot be read from `kCGEventFlagMaskAlternate`.** That bit
  is set while *either* option key is down, so releasing right-option while
  left-option is held does not change it — and a listener reading it never sees
  the release and never stops recording. The per-side device bits
  (`NX_DEVICERALTKEYMASK` and friends, IOKit `IOLLEvent.h`) answer the question
  actually being asked. They are absent from the CoreGraphics headers; the
  alternative is tracking key identity by hand across events, which is the same
  information with a bug in it.
- **A preflight `True` was verified before the operator's time was spent.**
  `CGPreflightListenEventAccess()` returned True, which is exactly the answer
  Phase 2a caught being uninformative — the grant belongs to the hosting
  terminal, not to this project. So the tap was installed and a synthetic
  right-option press and release were posted through the HID tap: both arrived
  at the callback. Only then was a human asked to speak.
- **The first log check said the daemon had hung. It had not.** `print()` to a
  pipe is block-buffered, so "listening" sat unflushed while the process ran
  normally. Three minutes were spent on a sampling profiler before the stack
  showed a healthy `NSApplication.run()`. The instrument was wrong, again, and
  the tell was that the failure was reported by the *observer* rather than by the
  subject. The daemon now flushes.
- **`restore_ms` is 0.0 on the first daemon dictation and ~155 ms on the other
  thirteen.** The restore returns 0 when the previous clipboard contents were
  not text (`stringForType_` returns nil) — there was nothing to put back, so
  nothing was slept for. Correct behaviour, and the reason the `min` column of
  `restore_ms` reads 0.0 rather than 150.
- **The operator dictated their reply to me using the product.** Row 18 of
  `history.db` is a 43-second dictation whose transcript is the message that
  reported finding 4. That is the dogfooding §9 asks for, arriving without being
  arranged.
- **Maccy was running throughout.** Every one of these transcripts is in the
  operator's clipboard history. That is the measured Phase 2a exposure behaving
  exactly as §7.3 says it does, now over real dictations rather than markers.

## Gate decision

**PASS.**

- `Rejects if: G1 is missed on a Tier A machine` — p50 **223.0** ms, p95
  **270.0** ms against 400 / 800, over the utterance band §2 defines G1 against.
  Passes on the full set too, at p50 215.3 / p95 795.0.
- `Rejects if: recording state is ambiguous at any point while the mic is live`
  — confirmed by the operator against the running daemon. The glyph fills on
  press and empties on release, and macOS's own microphone indicator agrees.

The Phase 1 go/no-go was **re-armed, not spent** (decided 2026-08-02, backfilled
into `docs/gates/phase-1.md`). It is not triggered: G1 is met with roughly
130 ms of p95 headroom on the defined band, which is what Phase 3's
post-processing has to fit inside.

Phase 3 is released. It inherits: the utterance-length scaling in finding 3,
which its own gate will run straight into; `postprocess_ms` as the last unfilled
stage; `manu history` surfacing `pending/` orphans (§5.5 gap 3); and a
deliverable list in §9 that still names two things already built.

Carried from Phase 1, unchanged: the tier-check reference clip's provenance
(blocks Phase 4), `beam_size` unswept, and the thread sweep still n=1.

## Rollback

Everything is additive on a branch. `git checkout main` restores the tree as of
the PR #4 merge. No new runtime dependencies — `pyobjc-framework-Cocoa` and
`pyobjc-framework-Quartz` were already present from Phase 2a, and
`Foundation` and `AppKit` both ship inside Cocoa.

The one non-additive change is the `history.db` schema: `restore_ms` is added by
`_MIGRATIONS` to databases that already exist. Rolling back leaves the column in
place and unread, which is harmless.
