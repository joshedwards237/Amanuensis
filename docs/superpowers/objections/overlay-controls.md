---
spec: docs/superpowers/specs/overlay-controls.md
date: 2026-09-10
mode: spec
diaboli_model: claude-opus-5[1m]
objections:
  - id: O1
    category: implementation
    severity: critical
    claim: "Ending a latched session through ✕ or ✓ tells the controller but not the listener, leaving `_latched = True` — after which a hold-to-dictate is ignored indefinitely and the hotkey appears dead."
    evidence: "Spec §6.2 wires the buttons past the listener. hotkey/macos.py:511-560 — a press while `_latched` returns without firing `on_press`; a release with `held >= window` returns without firing anything."
    disposition: accepted
    disposition_rationale: "Resolved with O2 — `cli.py` owns the latched flag and clears it on all three exits, so ending through a button and ending through a tap leave the listener in the same state. Blocks S5."
  - id: O2
    category: specification quality
    severity: critical
    claim: "§3 requires the overlay to render differently when latched, §5 rejects the overlay knowing about the latch as a §6.2 violation, and no component outside the listener can observe latch state. The spec adds a signal for the latch opening and none for it closing."
    evidence: "Spec §3 table; spec §5 rejection; spec §6.2 constructor has no latch input. hotkey/macos.py:261 `_latched` private, no accessor. cli.py:848-854 fan-out carries one enum. dictation_controller.py:104-107 — 'Exactly §5.4's values, and no more'."
    disposition: accepted
    disposition_rationale: "`cli.py` owns a latched flag and calls `overlay.set_latched()`, fanned out beside `set_state`. §5's rejection is narrowed in the spec to what it actually argued — suppressing an IDLE — rather than reading as a ban on rendering. The missing closing edge is the substance and is now named. Blocks S5."
  - id: O3
    category: risk
    severity: critical
    claim: "A 16 px irreversible discard sits 4 px from a 16 px confirm, on a panel that never takes focus and may have no hover state, guarding the gesture used for the longest dictations — no confirmation, no undo, nothing persisted to recover from."
    evidence: "Spec §4 geometry; spec §11 'the only cancel affordance'; dictation_controller.py:414-427 `abort_session` — 'Nothing is persisted'. PRD §5.2 — the latch exists for 'a seventy-five second dictation'."
    disposition: accepted
    disposition_rationale: "The ✕ and ✓ separate by more than `_CONTROL_GAP`, and the ✕ requires a deliberate gesture rather than a single click. Sized at S5, not here; recorded now so it is not decided by geometry defaults."
  - id: O4
    category: implementation
    severity: critical
    claim: "The state stream is not a per-session sequence — the worker sets IDLE for session N while the event tap has already set RECORDING for session N+1 — so §7's two-element history reads that IDLE as an abort and hides the panel over a live microphone."
    evidence: "dictation_controller.py:679-684 (worker sets terminal state) vs 349-361 (`start_session` on the event tap). Controller preamble 26-32: 'sessions can overlap'. PRD §5.4."
    disposition: accepted
    disposition_rationale: "The state signal carries session identity, or §7's history rule is dropped for an explicit injection signal. §7 is rewritten at S4. **Also raised as a third mechanism against gate finding 1**, independent of this spec."
  - id: O5
    category: implementation
    severity: high
    claim: "`on_finish → controller.end_session` binds an AppKit click action directly to a method that raises `RuntimeError` when no session is open, on the main queue, where an uncaught Python exception terminates the process."
    evidence: "dictation_controller.py:375-377 'Raises when no session is open'. overlay.py:258-273 — the 2026-09-02 process termination."
    disposition: accepted
    disposition_rationale: "`cli.py` wraps both bindings. `abort_session` is already safe; `end_session` is not, and the asymmetry is invisible at the binding site."
  - id: O6
    category: risk
    severity: high
    claim: "The 'indistinguishable downstream' claim rests on non-activation holding, which §9 lists as unverifiable here. If it does not hold, §6.3's focus guard declines to inject and the words go to history and the dropdown nobody opens."
    evidence: "dictation_controller.py:394 `focus_identity()` read inside `end_session`; 186-197 `deliver` returns 'the focused application changed'. Gate finding 3. INFERRED — depends on AppKit runtime behaviour not observable by reading."
    disposition: accepted
    disposition_rationale: "Recorded as a data-delivery risk rather than a UI one, with the fallback named: if non-activation does not hold, the focus identity is captured when the panel is shown rather than at the click."
  - id: O7
    category: premise
    severity: high
    claim: "The transcribing animation is ~3× longer than the measured duration of the state it renders, so on an ordinary dictation the user sees a dim dot appear and vanish, never a breath."
    evidence: "Spec §7 '~900 ms'. docs/gates/phase-4.md:46 — G1 p50 312.4 ms / p95 344.5 ms, which is TRANSCRIBING end to end. dictation_controller.py:88-89."
    disposition: accepted
    disposition_rationale: "The period is sized against the measured p50 of 312.4 ms, or the spec states it is for the long-form case and marks the number UNMEASURED."
  - id: O8
    category: alternatives
    severity: high
    claim: "`restart_session` discards audio for a reason that no longer applies once the session never ends. Continuing the same session is simpler, loses nothing, needs no new capture operation — and the spec does not weigh it."
    evidence: "PRD §5.2's discard exists so a fragment does not become its own dictation — a hazard requiring a separately queued session, which §5's own resolution removes. PRD §5.2 praises push-to-talk for losing 'no leading audio'; this discards up to 350 ms of it."
    disposition: accepted
    disposition_rationale: "Weighed in the spec. The discard is kept only if a reason survives that is not the stray-word hazard §5's own resolution removes."
  - id: O9
    category: scope
    severity: high
    claim: "`restart_session` requires an `AudioCapture` operation that does not exist — discarding the buffer without closing the stream — and requires resetting session bookkeeping the spec never mentions."
    evidence: "audio/capture.py:131-134 `start` raises if the stream is live; 150-167 `stop` is the only path clearing `_blocks`. dictation_controller.py:360, 382-389 (`started_at`, `capture_ms`)."
    disposition: accepted
    disposition_rationale: "The `AudioCapture` operation and the session bookkeeping are named in the spec before S2 is built."
  - id: O10
    category: specification quality
    severity: high
    claim: "`_latch_enabled` gates the entire latch on `on_cancel is not None`, so replacing the latch's callback pair with `on_latch` silently disables the latch unless that gate moves too. §5's '`on_cancel` remains' conflates the listener's callback with the overlay's new one of the same name."
    evidence: "hotkey/macos.py:450-464. Spec §5 and §6.2 use the name for two different objects."
    disposition: accepted
    disposition_rationale: "`_latch_enabled`'s gate moves in the same edit, and the two `on_cancel` names are disambiguated."
  - id: O11
    category: implementation
    severity: medium
    claim: "§2's invariant is a property of what is on screen; §7 places the guard on the producer (`set_level`). The drawing is dispatched to the main queue and §9's test exercises only the producer path."
    evidence: "overlay.py:227-233 (append, then dispatch), 235-249 (`_draw_bars` guards only on `if not self._bars`)."
    disposition: accepted
    disposition_rationale: "The guard moves to `_draw_bars`, which runs on the thread the invariant is about."
  - id: O12
    category: specification quality
    severity: medium
    claim: "Visibility is a single boolean and `should_show` is public API. Extending it to include TRANSCRIBING makes the RECORDING→TRANSCRIBING transition satisfy `wanted == self._visible` and early-return, leaving the live waveform on screen."
    evidence: "overlay.py:111-117, exported at 54; 202-216 early return."
    disposition: accepted
    disposition_rationale: "`should_show` is not extended. The render path takes the state, not a boolean, so the RECORDING→TRANSCRIBING transition cannot early-return."
---

# Objection record — overlay controls, the latch transition, the transcribing state

Spec mode, dispatched 2026-09-10 against `docs/superpowers/specs/overlay-controls.md`
before any implementation exists. Twelve objections; **ten high or critical**.
**All twelve accepted, 2026-09-10.** The operator disposed on the recommended
resolutions; the rationale for each is in the frontmatter. Nothing here was
deferred and nothing was rejected — the spec was wrong in the ways the record
says, and O4 turned out to be a defect in the *product*, not only in the spec.

No code was executed. Two objections (O6, and part of O3) turn on AppKit runtime
behaviour that cannot be observed by reading; both are marked inferred.

**The four that carry the most weight — O1, O2, O3, O4 — are the ones where a
test written from the spec's own §9 list would pass.**

## O1 — the hotkey goes dead after a click — critical

§6.2 wires the buttons past the listener entirely. Neither `abort_session` nor
`end_session` touches `MacOSHotkeyListener._latched`. Trace the next press:

```python
elif self._latched:
    return  # a press mid-latch decides nothing; its release does
```

`_latched` is still `True`, so nothing starts recording. Then the release:

```python
if self._latched:
    if held >= window:
        return  # a hold during a latch is ignored (§5.2)
```

A hold — every ordinary dictation by §5.2's definition — returns. `_latched`
stays `True`. **The next hold does the same.** The only escape is a release under
`double_tap_ms`, which clears the flag and fires `on_release` → `end_session` →
the `RuntimeError`, swallowed by `_fire`. So the recovery gesture also does
nothing visible.

Invisible to every test in §9's list, all of which exercise the overlay or the
controller. Only a test driving the listener *and* the controller sees it.

## O2 — the spec forbids in §5 what it requires in §3 — critical

§3 requires controls only when latched. §5 rejects letting the overlay know
about the latch. §6.2's constructor carries no latch input. The fan-out carries
one enum, and the enum is closed by its own docstring.

Even `cli.py` cannot answer "is this session latched?" today. The proposed
`on_latch` gives an edge *in* and **no edge out** — a latched session ends
through `on_release`, ✓, or ✕, and the overlay must clear the flag on all three
or the next unlatched dictation shows two buttons.

There is a charitable reading — `cli.py` owns the flag and calls
`overlay.set_latched(...)` — and it is probably what was meant. It is not
written, §5 reads as forbidding it, and **the closing edge is genuinely missing
from the design.** O1 falls out of the same missing edge.

## O3 — an irreversible discard guarded by aim — critical

16 px targets, 4 px apart, on a panel that never takes focus, with the hover
question left open in §11. ✕ destroys audio that was never persisted — §8's
protection does not reach here, and the spec says so approvingly.

§9 names reachability as the deciding question. **The other half is the mis-hit
rate on a two-target cluster 36 px wide, and the spec does not name it as a risk
at all** — it treats ✕ and ✓ as symmetric when their outcomes are 75 seconds of
speech versus 75 seconds of speech. Every other irreversible path in this
product is guarded. This one is guarded by aim.

## O4 — a third mechanism for gate finding 1 — critical

`DictationState` is a process-wide variable written by two threads for two
sessions, not a per-session sequence. The controller's own preamble says overlap
is designed for: "sessions can overlap: dictate twice quickly and session N's
text can land in whatever window has focus when the worker reaches it."

Start a second dictation while the first transcribes: the worker's `IDLE` for
session N arrives *after* the event tap's `RECORDING` for N+1, and §7's history
reads it as "an abort, where nothing is coming" — **cutting the panel while the
microphone is open.**

This is §5.4's named failure direction and the exact symptom of gate finding 1.
The gate record enumerates two mechanisms; **this is a third**, it needs no days
of uptime, and finding 1's investigation is not looking for it.

The spec widens the window twice over: keeping the panel through TRANSCRIBING
invites the user to start speaking again sooner, and the transcribing panel is
the cue that they may.

**A state stream carrying no session identity cannot support any history-based
rule.** Decide that before §7 is built on top of it.

## O5 — a click that can kill the daemon — high

`end_session` raises when no session is open. Its docstring calls that
"unreachable through `HotkeyListener`" — a premise this spec removes. Two
reachable paths: a double-click on ✓ (the hide is dispatched asynchronously),
and the hotkey tap racing the click. `manu toggle` is a third.

`abort_session` is safe — it returns on `None`. `end_session` is not, and the
asymmetry is invisible at the binding site. §6.2's framing makes it *more*
likely: the overlay correctly does not guard, so the guard must be elsewhere,
and the spec does not say where.

## O6 — silent non-delivery if non-activation fails — high

`end_session` samples `focus_identity()` at the click. The panel belongs to the
daemon's own process. If non-activation does not hold, `deliver` declines to
inject, the transcript goes to history, and the user is told through the surface
finding 3 established nobody reads.

The failure presents identically to "the feature doesn't work". The spec files
non-activation as a UI-correctness item; **it is also a data-delivery item**, and
there is no stated fallback if it turns out false.

## O7 — an animation sized against nothing — high

~900 ms against a measured p50 of 312.4 ms. The dot completes about a third of
one cycle; the user's experience is hard cut, dim dot, ~120 ms fade — three
visual events inside half a second.

The long case is where it earns its keep: a 75-second dictation decodes in ~1.1 s.
That is a perfectly good answer — but it should be the *recorded* answer, and
900 ms should be chosen against 312 ms rather than against nothing.

## O8 / O9 — `restart_session` discards for a reason that no longer applies — high

PRD §5.2's discard exists so a fragment does not **become its own dictation** —
a hazard requiring a separately queued session, which §5's own resolution
removes. What is discarded instead is up to 350 ms of the user's own audio, at
the head, where §5.2 specifically praises push-to-talk for losing none.

And it requires an `AudioCapture` operation that does not exist: `_blocks` is
cleared in exactly two places, both of which open or close the stream. Plus
session bookkeeping (`started_at`, `capture_ms`) the spec never mentions.

An implementer will write it, discover the capture API refuses, and improvise —
either stop/start the stream (the flash moved down a layer) or reach into
`_blocks`. Both deserve a decision.

## O10 — replacing the callback disables the latch — high

`_latch_enabled` requires `self._on_cancel is not None`, with a docstring saying
the requirement "is not a convenience". Replace the pair with `on_latch` and the
listener's `on_cancel` has no emitter while still gating the latch.

The failure mode is a latch that silently does not engage — a double-tap
behaving as two taps. §9's test list has no case for "the latch is enabled".

## O11 / O12 — the guard and the seam — medium

§2's invariant is about the screen; §7's guard is on the producer. A block
already on the main queue when TRANSCRIBING arrives is not observable through
`set_level` at all. **The repository has this exact shape on record: a check
satisfied by an adjacent signal.**

And extending `should_show` — the smallest edit §3 suggests — makes the
RECORDING→TRANSCRIBING transition early-return, leaving the live waveform up.
That is §2's forbidden outcome reached by the most natural reading of §3, and it
would pass a test asserting `overlay.visible is True` during TRANSCRIBING.

## Explicitly not objecting to

- **Keeping the panel through TRANSCRIBING at all.** §2's resolution is a genuine
  engagement with the preamble it reverses, and the invariant is the right shape.
- **Rejecting the cross-fade.** "A dimming waveform is still a waveform" is
  correct and is the sort of reasoning that usually goes missing.
- **Accepting the click-through cost rather than removing it.** Stated in the same
  place as the benefit, quantified, with the config key that moves it and a note
  that nothing removes it. The repository's own standard, met.
- **Both changes being config keys defaulting true.**
- **The sequencing behind findings 1 and 3.** The strongest paragraph in the spec.
  O4 argues the list is incomplete, not that the sequencing is wrong.
- **The Escape analysis in §11.** Reads `hotkey/macos.py` correctly.
- **`_WIDTH_LATCHED` as a derived constant.**
- **Leaving "should ✓ end an unlatched hold" open.**
