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
| 2. Recording panel confidence test (§5.4) | **PASS — 6 / 6**, and see the finding below | 2026-09-08 |
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

**The discriminator is whether the tray showed an error**, and it was not
observed either way. Mechanism 1 is loud, mechanism 2 is silent, and the report
does not mention an error appearing. That is weak evidence for mechanism 2 and it
is not enough to close either. **Both are defects on their own terms regardless
of which caused this instance**, and both are open.

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

## To close this record

1. Resolve finding 1, or record a decision to ship with it stated.
2. Take the G2 decision.
3. Run lane 6 with a second person, and paste their question list in verbatim —
   that list is the README's defect report and is the output of the gate.
4. Re-run the G3 packet capture against the assembled product (§9, objection O5)
   and qualify the claim as choice-story #11 requires: packet capture covers this
   process only, and transcripts transit the system clipboard by default.
