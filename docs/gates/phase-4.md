# Phase 4 gate — tray, modes, the IPC transport, the latch

**Date opened:** 2026-09-10 · **status: OPEN. The gate itself has not run.**
**Branch:** built across PRs #14, #16, #17 on `main`; #18 open at the time of writing
**Hardware:** Apple M3 Max, 14 cores (10 performance / 4 efficiency), 36 GB, macOS 27.0
**Interpreter:** CPython 3.14.5 · **Tier on this machine: A**
**Binding in use:** `right_command` — the operator moved off `right_option`
because its double-tap fires another application's shortcut

**Verdict: not yet reached.** §9's Phase 4 gate is a second person installing
from the README unaided. That has not been booked. This record is opened now
because four of its lanes are done and one of them found a defect, and a finding
that waits for the record to be written is a finding that gets rounded off.

---

## Lane results

| Lane | Result | Date |
|---|---|---|
| 1. Daemon starts and stops | **PASS** | 2026-09-03, re-verified 2026-09-08 |
| 2. Recording panel confidence test (§5.4) | **PASS — 6 / 6**, qualified twice below | 2026-09-08 |
| 3. Network capture (G3) | **PASS** — 0 sockets, 0 bytes, live control | 2026-09-03 |
| 4. Ten short corrections | **not run** — optional; the short-utterance punctuation comparison stays unmeasured | — |
| 4b. The latch and the second daemon | **PASS** | 2026-09-10 |
| 5. This record | open | — |
| 6. The install gate | **not run** — this is the gate | — |

**Lane 1 was re-verified because the artefact under it changed twice.** The
original pass tested a hand-copied `.command` file naming a git worktree; that
worktree was removed when PR #14 merged and the launcher answered `cannot find`
for four days. It is now a symlink into the checkout (PR #16), and `manu install`
writes one for installed users (PR #17). The daemon half of lane 1 never moved;
the launcher half was tested against something that no longer exists, which is
why it was run again rather than carried forward.

---

## What was built

`TrayApp` with mode and binding pickers, `RecordingOverlay`, `toggle` and
`vad_auto`, the `push_to_talk` double-tap latch, `manu status` and `manu toggle`
over a unix socket, the single-instance guard, §7.6's checksummed weight
download, `engines/moonshine.py`, and the Desktop launcher.

**G1 is met at ten seconds** — p50 **312.4 ms** / p95 **344.5 ms** over ten
dictations of 7.5–10.0 s recorded for the purpose, full shipped chain, config
digest recorded. `docs/gates/g1-at-ten-seconds.md` carries the conditions and the
contaminated first attempt.

---

## Finding 1 — the recording panel died in place, and the microphone did not

**Reported by the operator, 2026-09-10, from ordinary use.** After the daemon had
run for a couple of days across at least one lid close and sleep cycle, dictation
still worked and still injected text — and **the panel had stopped appearing.**
Restarting the daemon restored it.

**This is a §5.4 violation and it is the one §5.4 exists to name.** The
requirement is not that a panel appears; it is that *recording state is never
ambiguous*, and the failure direction that matters is a live microphone with a
dead indicator. That is exactly what happened, for an unknown span of days.

**Two independent mechanisms are present in the code, both real, and neither is
eliminated by the report.**

1. **`_failed` is a one-way latch with no recovery.** `overlay.py:277` sets it
   on any exception out of `_render`; lines 204 and 225 gate every subsequent
   `set_state` and `set_level` on it. **One transient exception disables the
   panel for the life of the process** — there is no retry and no reset. A
   restart clears it, which matches the report. This path *does* call
   `on_error` → `TrayApp.set_error`, so it should have left a visible message.
2. **The panel is built once against `NSScreen.mainScreen()` and never rebuilt.**
   `grep` finds no handler for `NSApplicationDidChangeScreenParameters`, wake,
   or any display-change notification. A lid close, a display change or a
   resolution change moves or removes the screen the panel was positioned
   against; `orderFrontRegardless()` still succeeds and raises nothing, so the
   panel is ordered front somewhere the user cannot see it. **This path is
   silent** — no exception, no tray error, no log line.

> **RESOLVED IN PART, 2026-09-10.** Both mechanisms are fixed and finding 3 with
> them; a **third** mechanism was found by review and is open. See the closing
> note at the end of this finding.

**The discriminator was supposed to be whether the tray showed an error.
Operator observation, 2026-09-10: the menu-bar glyph was present and cycling
correctly, and no error was visible.** That looks like it eliminates mechanism 1,
and it does not — which is finding 3 below, and is the more useful result.

`TrayApp.set_error` appends a **menu item** (`tray.py:283`). It does not change
the glyph, the title, or anything else visible without opening the dropdown. So
"no error was visible in the menu bar" is not an observation about whether an
error was raised; it is an observation about a surface that never displays one.
**Absence of evidence, from an instrument that cannot produce that evidence.**

Both mechanisms therefore remain open. What the observation *does* establish is
that the glyph kept cycling — so the main queue was alive, AppKit was working,
and `RecordingIndicator.set_state` was being reached throughout. Whatever failed
was specific to the overlay, not to the UI thread.

**What this does to lane 2.** The 6/6 was scored in a **fresh daemon session**,
minutes after start. The failure mode is time- and sleep-dependent, so six trials
in one sitting cannot see it. **The panel passed the test it was given, and the
test does not answer the question §5.4 asks**, which is whether a user can tell
the microphone is live — *at any point during the daemon's life*, not within ten
minutes of launching it. The `.app`-stays-deferred decision below inherits that
qualification.

**No diagnostic survives.** The daemon logs to the terminal window it was
launched from, the operator restarted the service, and nothing is written to
disk. Reproducing this means running for days and watching for it, which is the
opposite of a cheap check.

### Does lane 2's 6/6 still describe the panel that ships?

**Yes, and the reason is worth stating rather than assumed.** Between the score
on 2026-09-08 and today the overlay changed three times — S1, its stress pass,
and S2 — and a confidence test scored against a panel that no longer exists
would be a stale number that reads as a current one.

Every one of those changes is to **failure behaviour or to what the listener
emits**, and none is to what the panel looks like when it is working:

| change | touches appearance? |
|---|---|
| `_failed` becomes a bounded budget | no — only when it stops drawing |
| re-frame on a screen change | position only, and only after a display moves |
| discard the panel a render failed on | no — rebuilt identically |
| guard the level path | no — the drawing is unchanged when it succeeds |
| a nil screen is not a fault | no |
| the latch emits nothing | no — it *removes* a hide the panel should never have had |

The bars, the pill, the geometry, the position and the states shown are byte-for
-byte what was judged. **The one visible difference is a fault mark in the
menu-bar title**, which is a new signal on a *different* surface and cannot make
the panel harder to read.

S2 changes the panel's behaviour in the direction lane 2 measures rather than
against it: the double-tap no longer blinks the panel out and back, so a user
watching for "is the microphone live" sees one fewer misleading transition.

**Still qualified by finding 1**, unchanged: the score is for a *fresh session*,
and the failure that started this took days. Fixing the two mechanisms does not
turn a ten-minute test into a multi-day one. What can now be said that could not
be said on 2026-09-08 is that a panel which does stop drawing **says so in the
menu bar**, so a future occurrence is reportable rather than silent.

**Not re-run, and not claimed as re-run.**

### What was done, 2026-09-10

Both mechanisms are fixed, and finding 3 with them, because finding 3 is why
neither could be diagnosed.

- **Mechanism 1 — the one-way latch.** `_failed` now has a **budget**:
  `OVERLAY_FAILURE_LIMIT` consecutive failures disable the panel, and any
  successful render resets the count. The original argument was right about the
  persistent case — retrying forever means a broken panel that also runs code on
  every audio block — and wrong about the transient one. A failed render also
  discards the panel it failed on, so recovery is a fresh panel rather than
  another attempt at the broken one.
- **Mechanism 2 — the never-rebuilt panel.** The screen rect the frame was
  derived from is remembered and compared on every show; a change re-frames.
  Checked on show rather than driven by a notification, because a panel that is
  not visible does not need to be right and a notification is one more thing to
  register and get wrong on a component whose failures are silent. Conditional,
  with a control asserting an unchanged screen does **not** re-frame — re-framing
  unconditionally would pass the first test while proving nothing and would nudge
  a panel the user is looking at.
- **Finding 3 — the notice nobody sees.** `TrayApp.set_error` now marks the
  menu-bar **title** as well as adding the menu row. The words stay in the menu,
  which has room for them; the *mark* goes where §5.4 requires state to be
  readable. It is an addition to the state glyph, never a replacement — trading
  the microphone state away to report a fault would break the requirement in the
  act of reporting that it is broken.

- **The level path was the unguarded one, and it was worse.** Found by a stress
  pass over S1, not by S1. `set_level` dispatched `_draw_bars` **raw** — outside
  the wrapper — so an exception out of a `CALayer` call crossed the PyObjC
  bridge inside an `NSBlockOperation` and **terminated the process**, on the
  path that runs about thirty times a second while the microphone is open,
  against layers a display change can invalidate. Verbatim the 2026-09-02
  failure the wrapper exists for. Both paths now share `_guarded` and the
  budget. Pre-existing; S1 extended the guard to the state path and never asked
  about the other one.
- **A nil `NSScreen.mainScreen()` was charged to the budget**, and S1 introduced
  that by putting a screen read on every show. Nil is a real state — every
  display asleep, a clamshell with nothing attached — and three of them disabled
  the panel. A panel that cannot be positioned because there is no screen has
  nothing to position on; that is not a fault.

**What this does not do:** it does not prove the reported failure is gone. That
took days of uptime across a sleep cycle and no diagnostic survived it. What can
be claimed is narrower and is what the tests hold — a transient failure now
recovers, a persistent one still gives up, a moved screen re-frames, and a fault
is visible without opening a menu.

### Finding 1c — a third mechanism, found by review rather than by use

The sentinel pass over `docs/superpowers/specs/overlay-controls.md` on
2026-09-10 (objection **O4**) found a third route to this same symptom, and it
needs no uptime at all.

`DictationState` is a **process-wide** value written by two threads for two
different sessions — the controller's own preamble says overlap is designed for:
"sessions can overlap: dictate twice quickly and session N's text can land in
whatever window has focus when the worker reaches it." The worker sets the
terminal state for session N while the event tap has already set `RECORDING` for
session N+1.

Any rule that reads the state *stream* as a per-session sequence is therefore
wrong. The overlay does not read it that way today, so **this is not currently
reachable** — but the proposed transcribing-fade rule did, which is how it was
found, and the same hazard sits under anything that infers an event from a
transition.

**Open.** The fix is either session identity in the signal or an explicit
injection event; both are S4's decision and neither is built.

---

## Finding 3 — the affordance's own failure is reported where §5.4 says not to look

`TrayApp.set_error` renders into the dropdown and nowhere else. The glyph does
not change, so **a user learns the recording overlay has died only by opening a
menu they have no reason to open** — and §5.4's entire premise is that the user
should not have to open the tray menu to know whether the microphone is live.

The overlay is the affordance §5.4 asked for; its failure notice is delivered
through the surface §5.4 exists to avoid depending on. That is a design defect
independent of finding 1's cause, and it is what made finding 1 undiagnosable:
the one signal that would have separated the two mechanisms was routed somewhere
nobody was looking.

It also means `_failed`'s comment — "the failure is reported through `on_error`
… the surface built in this same phase for exactly this: saying what happened in
words" — is true about the mechanism and wrong about the outcome. The words are
written; nobody reads them.

**Any fix to finding 1 should make the failure loud before it makes the panel
robust**, because a silent failure of a privacy affordance is the worse half.

---

## Finding 2 — `manu` is not on `PATH` in a new terminal

Hit by the operator on 2026-09-08 while trying to run lane 4b's second daemon:
`zsh: command not found: manu`. The commands live in the virtualenv and a new
shell has not activated it.

**This would have been a step 6 finding**, and an expensive one — a second person
opens a terminal, hits this, and burns minutes of their thirty on it. It reads as
a README defect because it is one. Patched in PR #18 (step 1 says so and offers
the symlink-onto-`PATH` alternative; troubleshooting carries the error verbatim).
Recorded here because the gate is supposed to *find* these, and this one was
found early by accident rather than by design.

---

## Decisions this gate is required to record

- **§5.4 is discharged by the panel and the `.app` bundle stays deferred.**
  Lane 2 scored 6/6, which §9 makes the deciding criterion. **Qualified by
  finding 1**: the score is for a fresh session, and the panel has since been
  observed dead on a long-lived one. The bundle stays deferred; whether that
  survives finding 1's resolution is an open question, not a settled one.
- **`double_tap_ms` remains 350 ms and remains UNMEASURED.** The operator ran
  lane 4b without changing it and reported the gesture worked. That is one hand
  on one day, which is not a measurement of a motor threshold, and §5.3 keeps the
  key marked accordingly.
- **G2 — the Phase 3 gate deferred this here and it is now actionable.** The
  engine question is settled: Moonshine is disqualified on G3 grounds and
  collapses on long form, so 8.59% belongs to the decoder and the chain, and
  §7.5 records that 99 of 171 edits are a class no rule reaches. §9 permits
  confirming 5% or moving it with the reason stated; it does not permit silence.
  **OPERATOR DECISION, NOT YET TAKEN.**

---

## Carried forward, unmeasured or unbuilt

- **No Tier B machine has ever been measured.** §2 gives Tier B a bar and nothing
  has run against it. Unmeasured, not missed.
- **Parakeet has never been benchmarked.** NeMo has no CoreML or Metal path on
  macOS. ADR 0001 named it; nothing has ever run it.
- **The short-utterance punctuation comparison is unmeasured** (lane 4, not run).
  The dictations now exist — **nine takes of 6.1–11.9 s recorded 2026-09-10**,
  decode cost 12–25 ms per second of audio with no outliers, so nothing was
  competing for the machine. What is missing is the corrections half, which is
  the operator's. `bench_punctuation.py --emit-corrections --since` writes the
  template as of 2026-09-10; before that, lane 4 had no starting point, because
  the only emitter in the repository selects the *long* corpus by construction.
- **CI does not run the test suite.** `harness.yml` enforces constraints;
  `site.yml` runs `ruff` and `mypy` over four site scripts. Nothing in CI runs
  `pytest`, `mypy --strict src/`, or `ruff check src/ tests/`. **A green PR
  attests to the harness constraints and GitGuardian, not to the tests.** Every
  suite figure in this repository is from a local run.
- **The single-instance guard's ordering is proven in the suite, not in a menu
  bar.** `tests/test_cli.py` stubs `TrayApp` to raise so the broken order fails
  on the tray rather than the exit code. Lane 4b confirmed the refusal from the
  operator's side; nobody has watched the menu bar during a *deliberately*
  mis-ordered build.

---

## What the phase revealed that the PRD got wrong

- **Four commits of Phase 3 work were never on `main`.** `phase-3-postprocessing`
  was squash-merged as PR #9 and had four more commits pushed to it nine days
  later, including the double-tap latch specification — which was then declared
  never to have existed, in the governing document, for about an hour. A squash
  copies content rather than history and no tooling objected. All five stale
  branches are now audited and deleted. **`git branch -d` refusing a merged
  branch is a signal and the Phase 3 close read it as bookkeeping.**
- **The Phase 3 gate record cites a `store_audio` clause that could not fail at
  the time it ran** — it globbed for any `.wav` rather than joining a row to its
  file. Fixed 2026-09-03; the Phase 3 record should carry the correction.
- **§5.2 specified "discard before the decoder" with no mechanism.**
  `push_to_talk` queues on the physical release and the worker holds the session
  within microseconds, so the stated guarantee was unreachable by any cancel and
  would have shipped as a race nobody had raced. Resolved by splitting tap from
  hold on the release; §5.2 carries the resolution and its cost.
- **§6.4's tree was missing `tier.py` and `guard.py` for three phases.**

---

---

## Work landed after this record opened

Sequenced by `docs/superpowers/slices/overlay-controls.md`, which exists because
§10 of the overlay spec named findings 1 and 3 as blockers and assigned them to
nobody.

- **S1 — the panel's death becomes visible** (#27, #28). Findings 1 and 3 above.
- **S2 — the double-tap latches without stopping the session** (#29). The flash
  was a state machine reporting an event that did not happen: the latch fired a
  discard, `abort_session` reported `IDLE`, and the overlay hid on the way past
  — between two presses during which the microphone never closed. The specified
  fix was a `restart_session`; review found it needed an `AudioCapture`
  operation that does not exist and left `capture_ms` unstated, and then that
  **the discard buys nothing** — its hazard requires a separately queued
  session, which a session that never ends never creates. The latch now emits
  nothing, and the up-to-350 ms of speech the discard was throwing away is kept.
  §5.2 records the withdrawal.
- **S6's criterion** (#30) — `overlay-controls-reachability.md`, written while
  the controls do not exist, which is the only time it can be written honestly.

**S3, S4 and S5 are not built and should not be**, per the operator's own
sequencing: they change the panel lane 2 scored, and lane 6 has not run.

**One defect S2 surfaced and closed:** `_latch_enabled` gated the latch on an
`on_cancel` callback, so any caller passing none silently got **no latch**. That
surfaced four tests which had been exercising push-to-talk with the latch
accidentally off — a configuration `cli.py` never runs.

---

## To close this record

1. ~~Resolve finding 1, or record a decision to ship with it stated.~~
   **Done 2026-09-10** for both known mechanisms and for finding 3. **Finding
   1c remains open** — it is a decision for S4 and is not reachable today.
2. Take the G2 decision.
3. Run lane 6 with a second person, and paste their question list in verbatim —
   that list is the README's defect report and is the output of the gate.
4. Re-run the G3 packet capture against the assembled product (§9, objection O5)
   and qualify the claim as choice-story #11 requires: packet capture covers this
   process only, and transcripts transit the system clipboard by default.
