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
| 3. Network capture (G3) | **PASS** — re-run against the assembled product, 0 sockets, 0 bytes, live control | 2026-09-03, re-run 2026-09-15 |
| 4. Ten short corrections | **RUN — n = 9, not 10.** Shipped chain **4.38%**; Moonshine 14.37% / 16.25% | 2026-09-11 |
| 4b. The latch and the second daemon | **PASS** | 2026-09-10 |
| 5. This record | open | — |
| 6. The install gate | **2 attempts, 2 rejects, 0 dictations.** Findings 4/4a/4b, then rejected before step 1 | 2026-09-14, 2026-09-16 |

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

## Lane 4 — the short-utterance engine comparison (2026-09-11)

**It is nine takes, not ten.** `--emit-corrections --since 2026-09-10` found
nine stored dictations in the 6–12 s window; all nine had audio. The operator
edited six of the nine. 160 reference words in total, which is a corpus small
enough that every figure below is a direction, not a rate.

    python scripts/bench_punctuation.py --corrections corrections-short-2026-09-10.json

| engine | edit rate | missing marks | stray caps | deletions | p50 | p95 |
|---|---|---|---|---|---|---|
| `faster_whisper:auto` (as shipped, not re-decoded) | **4.38%** (7 / 160) | 2 | 1 | 0 | shipped | shipped |
| `moonshine/tiny` | 14.37% | 5 | 3 | **9** | 82 ms | 91 ms |
| `moonshine/base` | 16.25% | 7 | 2 | **12** | 143 ms | 161 ms |

**§7.2's open engine question is answered in the same direction short as long.**
It was left open because ADR 0001 declined Moonshine on *deletions* over 67–97 s
utterances and nobody had asked whether it **punctuates** better at the length
this operator actually dictates. It does not: 3.3× the edit rate on the same
classifier and the same chain, and the deletion axis ADR 0001 decided on is
worse here too — 9 and 12 deleted words against faster-whisper's **0**. §7.2
froze the Phase 4 default before this ran, so this table could not have moved
the shipped engine in any case; what it removes is the possibility that the
freeze was hiding something.

**What this is not.** It is not a G2 verdict. G2's 5% is defined over the Phase 3
long corpus (67–97 s, 8.59%), and 4.38% here is a **different corpus measured
with the same instrument** — 160 words against that gate's 1,991. Reading it as
"G2 is met" would be selecting the corpus that clears the bar, which is the
failure §7.2 was frozen to prevent. The honest statement is narrower and still
useful: **at this operator's ordinary dictation length the chain is not the
constraint, and neither Moonshine size is an alternative.**

Two caveats that travel with the number. `history.db` still carries no config
digest, so `--since` is the only thing separating these takes from every other
short take ever stored — and the shipped column is *what was injected on the
day*, not a re-decode, which is the only way to avoid scoring yesterday's
corrections against today's config. Transcript text is not reproduced here; the
corrections file is the operator's own speech and stays out of the repository
(`.gitignore:62`).

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

> **No, as of 2026-09-17. The persistent idle pill voided it.** Everything below
> this line was true and is kept because the *method* is what matters — it is
> the criterion this section applies, and it is the criterion the idle pill
> fails. The panel is now drawn whenever the daemon runs, as a narrow pill with
> a static dot, widening to the full pill with live bars while recording (PRD
> §5.4, amended that day). That changes what the panel looks like when it is
> working, which is exactly the test below, and it changes the perceptual task
> from *presence versus absence* to *state A versus state B*.
>
> **Re-run 2026-09-18: 6/6 on the panel that ships.** Operator's reading, after
> the idle pill, the animated transition, the ✕/✓ controls and the circled
> Lucide icons had all landed. §5.4 is discharged by the panel and the `.app`
> bundle **stays deferred** — which is a decision recorded explicitly, not an
> omission.
>
> **The criterion was not rewritten first, and this record says so rather than
> implying otherwise.** The runbook's step 2b required a new one in advance,
> and no such document exists in this repository. So what was applied is step
> 2's original criterion — *"answer 'is the microphone live right now?'
> correctly, without moving the pointer, without keyboard input, and without
> waiting, on both a live and an idle daemon, three trials each"* — against the
> new panel.
>
> That reading is real and it is the §5.4 question. Two things step 2b added are
> therefore **still unasked**:
>
> 1. **Peripheral vision.** The pill is on screen permanently now, so it will
>    normally be seen out of the corner of the eye rather than looked at. Step
>    2's protocol has the subject answer before looking anywhere else, which is
>    close but is not the same as never looking.
> 2. **A frozen panel.** The case the two-cue rule exists for — a panel that has
>    stopped updating shows the recording form with motionless bars, and width
>    is the only thing separating that from idle.
>
> Neither is a reason to withhold the 6/6. Both are recorded because a gate that
> rounds "the question I asked" up to "the question I meant to ask" is how lane
> 2's first score came to need this note in the first place.
>
> Operator disposition 2026-09-17: build it, re-score, and let lane 6 see the
> panel that ships rather than one it will not recognise. Done.
>
> The re-run is not the same test. The old criterion asked whether the user
> noticed the panel appear. The new one has to ask whether they can tell the two
> forms apart — including at a glance, in peripheral vision, and on a panel that
> has stopped updating, which is the failure mode the two-cue rule exists for.
> Writing that criterion before the re-run, not after, is S6's lesson and this
> repository has the counter-example on record twice.

**Everything from here is the 2026-09-15 reading, retained for its method.**

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

**RESOLVED IN PART, 2026-09-15, and the "not currently reachable" above was
wrong.** It is reachable today, with nothing more exotic than dictating twice in
quick succession, and it does not need the transcribing-fade rule that found it.

`end_session` clears `_recording` **before** it queues, so a second press passes
`start_session`'s guard and sets `RECORDING` while the worker still owns the
first session. When that worker finished it published a terminal state for a
session that is no longer the one in front of the user — and `cli.py`'s
`_on_state_change` hands every state straight to `overlay.set_state`, so an
`IDLE` arriving there **hid the recording panel over a live microphone.** §5.4's
named failure, reached without reading the state stream as a sequence at all: a
single out-of-order terminal state is enough.

**Demonstrated before it was fixed.**
`test_a_finished_session_does_not_report_idle_over_a_live_microphone` asserts
against `capture.is_recording` at the moment each state is emitted, rather than
against the sequence of states — the sequence cannot say whether the microphone
was open, which is the entire question. It fails against the old code and passes
against the new, verified by sabotage.

**The fix is a `_settle_state` helper**: a *finished* session's terminal state is
dropped when a newer session is recording. The process is recording; publishing
`IDLE` is not a stale opinion but a wrong one. `_report_error` deliberately does
**not** route through it — the words describing a failure belong to the session
that failed and stay truthful whenever they arrive; only the *state* is a claim
about the microphone right now.

**Still open, and narrower.** The signal carries no session identity, so the
check reads `_recording` at publication time and a press landing microseconds
later still races. The window goes from *every overlapping dictation* to a
sliver; it does not close. **The general shape remains S4's** — identity in the
signal, or an explicit injection event — and this fix does not preclude either.

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
- **G2 — CONFIRMED AT 5%, and it stays missed. Operator decision, 2026-09-15.**
  The threshold does not move. The product's measured edit rate is **8.59%**
  over the Phase 3 corpus and the goal remains **≤ 5%**, carried as debt and
  revisited at the **Phase 5** gate rather than here.

  The engine question that deferred this is settled. Moonshine is disqualified
  in both directions — ADR 0001 rejected it on deletions over long form, and
  lane 4 showed it worse short as well (14.37% and 16.25% against the shipped
  chain's 4.38%, with 9 and 12 deleted words against faster-whisper's 0). No
  model size rescues it: `small.en` reaches 7.88% at 4.2× the decode, `base.en`
  is worse *and* slower, and the stray capitals survive every size. So 8.59%
  belongs to the decoder and the chain, and §7.5 records that **99 of 171 edits
  are a class no rule reaches**.

  **Why confirm rather than move, when §9 permits either.** The candidate
  replacement was 9%, and 9% is 8.59% rounded up. Its only property is that the
  product passes, which means it cannot be missed by construction — and a target
  that cannot be missed is not a target. §2 already labels 5% **provisional**,
  and its own G2 note says a number presented as derived when it was inherited
  is worse than one labelled a guess. A provisional guess set *before* the data
  retains the one quality that matters; a number computed from the measurement
  it judges does not. This repository has the same failure on file at
  `docs/site/SITE_PRD.md`, where a headline band was chosen from five candidates
  because it had the best p95.

  **The argument for moving it is not wrong, it is unevidenced.** "5% is strict
  for this product" may well be true and nothing here can show it: there is no
  external benchmark, competitor figure or user-tolerance measurement in this
  repository for what a good dictation edit rate is. §9 requires a *stated
  reason*, which means one a reader could check. Should such a measurement
  appear, this decision is the right one to revisit.

  **The attribution escape is closed by the spec.** 163 of 171 edits are the
  decoder's and the chain missed 8, so a chain-only metric would read ~0.4% and
  pass. §2's G2 note forbids it: *"Edit rate is the product goal. It measures
  what the §4 user experiences — how much correcting they had to do."* The user
  experiences 8.59% whoever caused it.

  **What confirming costs, stated plainly:** v1 ships against a stated goal it
  visibly misses. That is the intended state. Phase 5 is the phase aimed at the
  99 unreachable edits, and moving the bar to today's number would remove the
  only thing that gives Phase 5 a target.

  **This decision does not gate Phase 4.** The single reject criterion in the
  runbook is lane 6's, line 345. G2 is a decision this record must *contain*,
  not a bar it must clear, and either answer would have closed the item — which
  is the reason to take the one that keeps the number honest.

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

## Lane 6 — first install by a second person (2026-09-14)

**Partial. One person, one machine, unaided, and it found a defect in the first
five minutes.** This is not the completed lane: it is one install, the question
list was not collected systematically, and the run stopped at the defect rather
than reaching a first dictation. Recorded now because a finding that waits for
the lane to finish is a finding that gets rounded off.

**What happened.** `git clone` through `pip install .` was smooth — their words.
`manu daemon` then printed both remediation messages, correctly, naming both
grants and both panes. They ran the `open` command from the first one. **The
Accessibility list was empty.** No row for their terminal, nothing to toggle,
and no instruction anywhere that covers an empty list.

Terminal output, verbatim:

```
(.venv) (base) michaelprior@Not-Jeffs-Mac-Book-Pro Amanuensis % manu daemon
manu daemon: Amanuensis cannot type into other applications until macOS grants
Accessibility access. Open the pane:

    open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"

macOS grants this per application, and it grants it to whatever launched
`manu` — so look for your terminal in the list (Terminal, iTerm, Ghostty,
VS Code), not for "Amanuensis". Toggle it on, then run the command again;
the grant is read once at launch, so an already-running process will not
notice it.

Input Monitoring is a *separate* permission and is not needed for this —
it is what the global hotkey will need, and nothing here uses it yet.

manu daemon: Amanuensis cannot see the hotkey until macOS grants Input Monitoring.
Open the pane:

    open "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"

This is **not** the Accessibility permission. Accessibility lets Amanuensis
type text into other applications; Input Monitoring lets it see the key you
press to start. They are granted separately, in different panes, and granting
one does not grant the other.

macOS grants this per application, and it grants it to whatever launched
`manu` — so look for your terminal in the list (Terminal, iTerm, Ghostty,
VS Code), not for "Amanuensis". Toggle it on, then start the daemon again;
the grant is read at launch, so an already-running process will not notice
it.
```

### Finding 4 — the product sent the user to a list it had guaranteed was empty

**Cause, from the code rather than from the report.** Both permission surfaces
called only the non-prompting half of their pair — `CGPreflightPostEventAccess`
(`injection/macos.py:214`) and `CGPreflightListenEventAccess`
(`hotkey/macos.py:310`) — and **nothing in the tree had ever called the
`CGRequest*` twins.** Preflight asks TCC a question. The request is what
registers the process as an applicant, which is what puts a row in the pane. No
request, no row, for the life of the install.

So the remediation was accurate about the pane, accurate about which grant,
accurate that the name would be the terminal's — and then instructed the user to
toggle a row the product had ensured would not exist. Every sentence true, the
whole unusable.

**This was specified, not an oversight.** PRD §6.3 said "Both are the
non-prompting halves of documented pairs; the `CGRequest*` twins raise a system
dialog, which a daemon that starts at login must never do at startup." Right
about the steady state, wrong about first run — and resting on a premise this
product does not have, since it has no login item (§5.4) and macOS suppresses a
repeat prompt once TCC records a decision. §6.3 is amended with a dated revision
note; the disagreement was opened here rather than diverged from silently.

**The discriminator was cheap and was asked.** Two mechanisms produce "no clear
toggle": an empty list (nothing registered) or a present-but-off row (the URL
anchor landing on the wrong pane under macOS 26/27). One question — *was the
list empty, or was your terminal in it and switched off?* — separates them, and
the answer was **empty**, which eliminates the anchor hypothesis and confirms
the mechanism above.

**Fixed 2026-09-14.** `request_permissions` on both ABCs, concrete and
defaulting to a no-op, overridden on macOS, called by the CLI **only** after a
check has already failed and **for every** missing grant rather than stopping at
the first. `check_permissions` is untouched and stays non-prompting, which
matters because it also runs on `inject()` and on `warm_up()`. Both remediation
texts and README step 4 now say that a dialog may have appeared, that asking is
what creates the row, and how to add the terminal manually through `+` — the
picker hides `/System/Applications/Utilities/Terminal.app` until Cmd-Shift-G.

**One harness defect found on the way.** `test_permission_check_does_not_prompt`
asserted `not hasattr(quartz, "CGRequestListenEventAccess")` — a fact about the
test double, satisfied by the double not defining the method. No product
behaviour could falsify it. It now counts calls against the real attribute, with
a positive control beside it (the request half **must** be called) and the
negative kept (the check half **must not**). Verified by sabotage: reverting the
fix turns all three new tests red, and restoring it turns them green — 701 pass,
`mypy --strict src/` clean, `ruff check src/ tests/` clean.

### Finding 4a — the fix did not work, and the machine that proved it is the only one that can

**2026-09-14, same day.** He pulled, reinstalled, reran. `grep -c
CGRequestPostEventAccess` on his installed module returned **1**, so the fix was
present and running. **No dialog appeared and the Accessibility pane stayed
empty.**

`sw_vers -productVersion` — **26.6**. Both machines that validated the fix run
**27.0**: the operator's, and a fresh local user account created to rehearse
this lane. The one variable nobody controlled is the one that differed, and the
rehearsal could not see it *because* it was a rehearsal on the same OS.

**Replaced with `AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt:
True})`** — the older route to the same grant, and the one that presents the
dialog carrying "Open System Settings". The option must be `True`; the identical
call without it is a silent check, which is the behaviour already known not to
help. It lives in `HIServices`, so **`pyobjc-framework-ApplicationServices`
moves from the `gate` extra to a runtime dependency** — verified by building a
clean `pip install .` before and after: absent before, present after. The
`CGRequest*` call is kept as a fallback for an install without the bridge and is
not called in addition, since two dialogs for one grant teach the dismissal
reflex §6.3 was protecting against.

**Input Monitoring is unchanged and unmeasured on 26.6.** Its equivalent,
`IOHIDRequestAccess`, needs `pyobjc-framework-IOKit` — a second dependency for a
second unverified hypothesis. Whether that half registers on 26.6 is not known
and is not assumed to follow Accessibility.

**A test guard came out of it.** The AX call with the prompt option raises a
*modal* dialog. On every machine this has been developed on the grant is already
held, so it returns silently and the hazard is invisible exactly where the suite
is run; on a fresh contributor's machine the same test puts a dialog on screen,
and a modal dialog **blocks** a pytest run rather than failing it.
`tests/conftest.py::_no_real_ax_prompt` is autouse for the same reason
`_no_real_microphone` is, and **caught a pre-existing test reaching the real
bridge on its first run**.

**This fix is also unverified against the failure it was written for.** No
machine here runs 26.6 without the grant. That is now twice in two days that a
fix for this lane could only be confirmed by the person who found it — which is
itself a finding about the lane: **the operator cannot verify lane 6 defects on
the operator's machine**, by construction, and a second OS version is not
optional equipment for this gate.

### Finding 4b — measured on 26.6, and the Input Monitoring half is still broken

**2026-09-14, from `scripts/diagnose_permissions.py` run on the reporter's
machine.** The first hard measurements this lane has produced about an OS
neither development machine runs.

    macOS 26.6 · Apple_Terminal · python 3.12.0 · copied install

| call | returned | dialog? |
|---|---|---|
| `CGPreflightPostEventAccess` | False | — (never prompts) |
| `CGPreflightListenEventAccess` | False | — (never prompts) |
| `AXIsProcessTrustedWithOptions(prompt=True)` | False | **YES — opened the Accessibility pane** |
| `CGRequestPostEventAccess` | False | no |
| `CGRequestListenEventAccess` | False | **no** |

**Three things are now measured rather than assumed.**

1. **The AX call is correct on 26.6.** It presented the dialog and opened the
   pane. Finding 4a's replacement was the right call, confirmed on the machine
   that falsified its predecessor.
2. **`CGRequestPostEventAccess` does not prompt on 26.6** — same run, same
   process, no dialog. Finding 4a's diagnosis holds and was not a coincidence
   of some other state.
3. **`CGRequestListenEventAccess` does not prompt either, and that is the call
   Input Monitoring still ships.** Recorded in finding 4a as *unmeasured*; it is
   now measured, and it is broken. A user on 26.6 gets prompted for
   Accessibility and silently not for Input Monitoring, then finds one pane
   populated and the other empty — which is more confusing than the original
   defect, not less.

**The reporter is unblocked**: he granted both by hand and `manu daemon` now
runs. That is the end of his block and **not** a verification of the daemon's
prompt path. His machine is no longer a fresh client, so the question "does
`manu daemon` raise the dialog on 26.6" has become unanswerable there. It was
never answered: his one no-prompt `manu daemon` run cannot be attributed, since
`manu --version` was not captured at the time and the stale-copy explanation was
never eliminated.

**A timing hypothesis was raised and is dropped.** `_daemon` prints and returns
within milliseconds of requesting, where the diagnostic makes three more
framework calls first, and a prompt whose requesting process exits immediately
could plausibly be torn down before presentation. There is no evidence for it,
the boring explanation was never excluded, and building against it would be a
fourth fix aimed at a guess. **Recorded as a hypothesis, not a finding.**

**Open, with evidence: the Input Monitoring half.** The only candidate is
`IOHIDRequestAccess(kIOHIDRequestTypeListenEvent)`, which needs
`pyobjc-framework-IOKit` — a fifth pyobjc framework. That is an operator
decision about a dependency, not an implementation detail. Until it is taken,
**26.6 users must add their terminal to Input Monitoring by hand**, and the
README's `+` instructions are load-bearing rather than a fallback.

### Second attempt, 2026-09-16 — rejected before step 1

**A different person, a machine that had never built software, and it never
reached a clone.**

    mikecarter@Mikes-MacBook-Pro-3 Documents % git clone https://github.com/joshedwards237/Amanuensis.git
    xcode-select: note: No developer tools were found, requesting install.

Before that, Terminal itself had to be granted access to `~/Documents`.

**The README's step 1 has three unstated prerequisites, stacked in one code
block**, and `grep -i 'xcode\|command line tools\|developer tools' README.md`
returns nothing:

1. **Folder access.** Terminal needs a TCC grant for the directory being cloned
   into, before a single command runs.
2. **The Xcode Command Line Tools.** There is no `git` until they are installed —
   a multi-gigabyte download behind a dialog the README never mentions.
3. **Python 3.12.** The Requirements line demands it and no step supplies it. The
   tools ship an older interpreter, so `python3.12 -m venv` was the next wall
   even had `git` worked.

**Two subjects, two rejects, two different walls.** The first died on permissions
after installing cleanly; the second died before installing at all. What lane 6
has measured so far is not the README's prose — it is that **the install path is
this product's weakest surface, and the daemon is not the problem.**

**This opened Phase 4i** (PRD §9, 2026-09-16): a bootstrap script and a README
that states its prerequisites, sitting between Phase 4's build and Phase 4's
gate because lane 6 cannot produce a believable reading until the path to the
README works.

**Neither attempt is a resumable run** and neither counts as the gate. Lane 6
still requires a clean run, a different person again, and — per finding 4b — not
on macOS 26.x.

**What this does not establish.** One person is not the lane. The install was not
completed to a first dictation, no question list was collected, and the defect
above was found in the first five minutes — which says nothing about the rest of
the README. **Lane 6 remains the gate and remains unrun as specified.**

---

## G3 re-run against the assembled product (2026-09-15)

**Objection O5 asked for the capture against the *assembled* product** — tray
drawn, IPC acceptor listening, event tap installed — rather than against the
subprocess the default mode spawns, which is a different pid and cannot see a
daemon running beside it. `--daemon SECONDS` is that mode. **PASS.**

| window | what was running | sockets | bytes in/out | control |
|---|---|---|---|---|
| 20 s | daemon idle, tray drawn, acceptor listening | 0 | 0 / 0 | 1 socket, 866 B |
| 22 s | as above, with a session driven over IPC — it **errored** | 0 | 0 / 0 | 1 socket, 866 B |
| 40 s | as above, with a **real spoken dictation**, hotkey to cursor | 0 | 0 / 0 | 1 socket, 866 B |

The control saw traffic on both runs, so the instrument was live rather than
silently broken — which is the failure this project has shipped before
(`sentinel-integrity-check.sh` globbed the wrong extension and exited 0 with
"OK (0 checked)").

**The third window is the one §9 asked for, and it was taken 2026-09-15.** The
operator held the binding and spoke; the transcript landed at **19:09:17.7Z**,
inside the window, with a 440 KB stored `.wav` beside it, and the daemon ended
the window in `idle` rather than `error` — so the run covered a hotkey press,
a capture, a decode, §8's persist and an injection that reached the cursor.
**Zero sockets and zero bytes across all of it.**

That the evidence had to be *looked for* is worth recording. The capture reports
the daemon's state at both ends and both were `idle`, which is equally
consistent with a completed dictation and with nobody dictating at all — the
script says so itself. A row in `history.db` timestamped inside the window is
what distinguishes them, and a PASS quoted without that check would be a reading
of an idle process wearing the words "assembled product working".

**The second window is kept rather than replaced.** It covered capture and a
decode attempt and no successful injection — weaker evidence in the direction §9
wanted, and incidentally stronger in another, since the *error* path also opened
no sockets.

**Scope, which travels with the result (choice-story #11) rather than being
recorded once and dropped.**

- Amanuensis's own sockets only. This says nothing about the rest of the machine.
- The unix socket behind `manu status` / `manu toggle` is not an internet socket
  and is correctly absent here. That is a property of the transport, not a
  finding of this capture.
- **Transcripts transit the system clipboard by default**, where another process
  may capture them — measured, Maccy 2.7.0 captured every one. That path is
  invisible to packet capture, and it is the one place a transcript can leave
  the machine as a direct consequence of the defaults.

---

## Finding 5 — WITHDRAWN. The daemon was not wedged; the instrument was two samples

> **Corrected 2026-09-15, hours after it was written.** The central claim below
> — that the daemon was stuck — **is false**, and the entry is kept rather than
> deleted because the error it records is more useful than the finding was.
>
> `manu status` reported `idle` on the next check, and `history.db` carries
> successful dictations at **09:17, 09:22 and 09:26** local, after the 09:13
> test. The daemon returned to `IDLE` on the next successful session and has run
> normally since.
>
> **`ERROR` is the terminal state of one failed session, not a latch.** The
> worker sets it and the following successful session sets `IDLE`
> (`dictation_controller.py`, terminal block). It was sampled twice inside two
> minutes and never again, and a state that clears on the next session is
> indistinguishable from a stuck one until there *is* a next session. **Two
> samples of a persistent indicator were read as a wedge.**
>
> Two further claims in the entry were also designed behaviour rather than
> defects. **No history row and no stored audio is correct**: `write_pending`
> returns False for an empty or whitespace transcript by contract, "so a caller
> can say nothing was captured rather than reporting a successful write of an
> empty string" (`storage/history.py:309`). And the session ending in `ERROR` at
> all is one of three designed routes — the §5.7 guard refusal, a caught
> exception, or a non-fatal `session.error` such as an injection declined
> because focus changed. **Which one fired is still unknown**, and with silence
> sent over `toggle` to a `push_to_talk` daemon, at least two are plausible.
>
> **What survives, correctly scoped:** `manu status` names the state and cannot
> name the reason — the text goes to the daemon's stderr, so a remote caller
> gets a word where the 2026-09-11 constraint wants a sentence. That is a real
> and much smaller finding than the one written below. **Fixed 2026-09-15**:
> `_status_detail` is module-level, the reason is appended in `ERROR`, and the
> string has tests for the first time — which also closes the extraction the
> 2026-09-11 constraint had carried as its open item.
>
> **And the error has a second use.** Reading a process-wide state value as
> though it described one session is *precisely* the hazard finding 1c names.
> It was committed to this record by the author on the same day 1c was being
> called unreachable.

### The entry as originally written, 2026-09-15



**2026-09-15, during the G3 re-run above, and it was induced rather than
observed in use.** A dictation was started and stopped over the IPC socket
(`manu toggle`, ~6 s, `manu toggle`) with no speech. The daemon entered
`state error`, **stayed there**, and produced **no history row and no stored
audio** — the newest `.wav` is still from the previous day, so it failed before
§8's persist-before-inject write.

`manu status` reports `state error` and cannot say **why**. The text went to the
daemon's stderr, which belongs to the terminal the operator launched it from —
so the diagnosis lives in a scrollback this session cannot read, and a restart
destroys it. **That is the 2026-09-11 finding one layer along**: `on_error` now
reaches a surface, and the surface a *remote* caller sees still carries no
reason.

**Not diagnosed, and deliberately not reproduced** — a second attempt would
overwrite the state that holds the evidence.

**Two things it is evidence for, and one it is not.**

- **"Degrade rather than stall" is a hard constraint** (PRD §5.3, §7.5). A
  session that wedges the daemon in a terminal state, rather than failing one
  dictation and returning to `IDLE`, is the stall.
- **A status verb that reports a failure state without the reason repeats the
  shape the 2026-09-11 constraint was written for.** `manu status` has room for
  a sentence and prints a word.
- **It is not evidence about ordinary use.** The input was silence over the IPC
  path, which is not how a person dictates, and `toggle` was sent to a daemon in
  `push_to_talk` mode. Whether an ordinary spoken dictation can reach the same
  state is **unknown**.

**Open.** The next step is the operator's terminal scrollback, before anything
restarts that process.

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

> **S5 was built 2026-09-17** on the same disposition as the idle pill, which
> is the operator's to make. The re-score owed by step 2b now covers the ✕ and
> ✓ as well, and **S6's reachability trial is unblocked** — its criterion was
> written 2026-09-10, before any control existed, and must not be amended now
> that they do. S3 and S4 remain unbuilt.
>
> **Superseded in part, 2026-09-17.** The persistent idle pill was built ahead
> of lane 6 on an explicit operator disposition, which voids lane 2 outright —
> see the note under *Does lane 2's 6/6 still describe the panel that ships?*.
> That removes the argument that was holding S3–S5 back, since the re-score they
> were waiting to avoid is now owed regardless. **It does not make them urgent**:
> each still has to be worth its own risk, and folding three unbuilt slices into
> a re-score that is already going to be hard to read is how a confidence test
> ends up measuring four things at once. Sequence them deliberately or not at
> all.

- **The microphone picker** (2026-09-11, §5.4 and §11.6). A `Device:` row in the
  tray with every input on the machine beneath it, closing the discoverability
  half of §11.6 the day after it was recorded. **It does not touch the panel**,
  which is why it is here and S3–S5 are not: lane 2 scored the overlay, and this
  adds a menu row. Lane 6's install walk-through now has one more menu to
  explain, which is a question for the second person rather than a defect.

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
   **Started 2026-09-14 and not complete**: one install, stopped at finding 4,
   no question list collected, no first dictation reached. The finding is fixed;
   the lane is not discharged by it.
4. ~~Re-run the G3 packet capture against the assembled product (§9, objection
   O5) and qualify the claim as choice-story #11 requires.~~ **Done 2026-09-15**,
   three windows, the last over a real spoken dictation confirmed by a
   `history.db` row inside it. Zero sockets and zero bytes throughout, live
   control on every run. The qualification travels with the result above:
   packet capture covers this process only, and transcripts transit the system
   clipboard by default.
