---
spec: docs/superpowers/specs/overlay-controls.md
date: 2026-09-10
mode: spec
cartographer_model: claude-opus-5[1m]
stories:
  - id: 1
    lens: [forces, consequences, coherence]
    title: Controls keyed to the latch, not hands-free
    disposition: pending
    disposition_rationale: null
  - id: 2
    lens: [coherence, defaults]
    title: No named channel carries latch to overlay
    disposition: pending
    disposition_rationale: null
  - id: 3
    lens: [coherence, consequences]
    title: Panel persists; the confidence test's discriminator changes
    disposition: pending
    disposition_rationale: null
  - id: 4
    lens: [forces, consequences]
    title: Mouse acceptance scoped to panel, not state
    disposition: pending
    disposition_rationale: null
  - id: 5
    lens: [defaults, patterns, consequences]
    title: The tick inherits the key release's thread and focus sample
    disposition: pending
    disposition_rationale: null
  - id: 6
    lens: [patterns, consequences]
    title: Injection completion reconstructed from a two-state history
    disposition: pending
    disposition_rationale: null
  - id: 7
    lens: [defaults, consequences]
    title: Three off switches, precedence left unstated
    disposition: pending
    disposition_rationale: null
  - id: 8
    lens: [defaults, forces]
    title: Breathing period typed, not read from history
    disposition: pending
    disposition_rationale: null
  - id: 9
    lens: [forces, patterns]
    title: Tight inherited from Wispr, forty-four pixels up
    disposition: pending
    disposition_rationale: null
  - id: 10
    lens: [consequences, alternatives]
    title: restart_session discards audio; the clocks unstated
    disposition: pending
    disposition_rationale: null
  - id: 11
    lens: [coherence, defaults]
    title: Geometry re-derived from code, §5.4 unreconciled
    disposition: pending
    disposition_rationale: null
---

# Choice stories — overlay controls, the latch transition, the transcribing state

Eleven decisions this spec makes without recording that it is making them. Four
were taken explicitly by the operator on 2026-09-10 — the persisting panel, the
whole-panel click target, the merging dot, and the sequencing behind the install
gate — and none of those is relitigated here. These are the ones made by
omission, by a predicate chosen for the mechanism rather than the capability, or
by inheriting a property from the gesture the new affordance replaces.

## #1 — Controls keyed to the latch, not hands-free

§3 argues the rule from push-to-talk: "the hand is already on the key and the
release *is* the ✓." Sound about the gesture it names, silent about the others.

`_latch_enabled` is `push_to_talk` only. So "latched" is a property of one branch
of one mode, while **"the user's hand is off the key and they need a way out" is
a property of four situations**: the latch, `toggle`, `vad_auto`, and a session
started by `manu toggle` over IPC. The spec picked the predicate that names the
mechanism rather than the one that names the need.

**Not taken:** key to hands-free-ness. Key to `RECORDING` outright. Put a
*Cancel dictation* row in the tray, which already has a working verb-dispatch
surface the Phase 4 gate exercised — free for every mode, and not on the
component finding 1 reports dying.

**Consequence:** §11 says the ✕ is the only cancel affordance the product has.
Combined with this predicate, the product has **no cancel affordance in `toggle`,
in `vad_auto`, or for an IPC-started session** — the three cases where the user
also cannot end it by letting go. `vad_auto`'s listener never ends the session at
all, which makes it the mode with the strongest claim on a ✕ and the one that
gets none.

PRD §5.2 was amended 2026-09-03 to put all three modes in the tray *specifically*
so users would try them. The population in `toggle` and `vad_auto` is the one the
previous phase went out of its way to grow.

## #2 — No named channel carries latch to overlay

§5 rejects letting the overlay know about the latch. §3 requires it to render
conditional on the latch. The rejection is well argued **for the flash**, where
latch-awareness would suppress a state the overlay should render faithfully.
Rendering an affordance conditional on the gesture is a different use of the same
fact — the spec never separates them.

**Not taken:** a `set_latched(bool)` fanned out from `cli.py` beside
`tray.set_state` / `overlay.set_state`, where the same argument already lives. A
sixth `DictationState`, foreclosed by the enum's docstring. An `OverlayMode`
value object carrying latch and mode together, which would also serve #1.

**Chosen by not naming one**, which resolves it to whoever writes the slice — in
the component §5 just said must not reason about capture modes.

**Consequence:** `on_latch` fires on entry and **nothing fires on exit**. A
latched session ends through `on_release`, ✓, or ✕; the overlay must clear the
flag on all three or the next unlatched dictation shows two buttons.

## #3 — Panel persists; the confidence test's discriminator changes

§5.4's criterion was written 2026-09-02 **before the overlay existed**,
deliberately, because "a criterion written after the overlay is seen is a
criterion written to pass."

Under today's panel the discriminator is **presence versus absence** — the
strongest signal available in peripheral vision. After this change the panel is
present in both answers and the discriminator becomes **bars versus a dot**, at
22 px, dimmed, 44 px from a screen edge.

**Not taken:** change the geometry at the boundary too, so presence/absence is
partly preserved. Move it. Re-word §5.4's criterion at the same time this ships.

**Chosen:** identical position, width, background, radius — the interior glyph
and a dim are the whole distinction.

**Consequence:** the spec's §1 argues for sequencing because lane 2's *score*
describes today's panel. The unaddressed half is that the **test** does too.
Whether the `.app` bundle gets built turns on a re-run against a discriminator
nobody has re-argued.

## #4 — Mouse acceptance scoped to panel, not state

`setIgnoresMouseEvents_` is window-wide and runtime-mutable — flipping it per
state is one call. The spec scopes the cost to the panel by writing the cost
paragraph about a 114 × 22 *latched* panel and reasoning no further.

Under change 3 the panel is also visible throughout TRANSCRIBING — "the longest
state" — and under push-to-talk, the default mode, it is visible at 72 × 22 with
**no controls on it at all**. The default path pays a click-swallowing region on
every dictation for zero affordance.

**Consequence:** the README entry the spec requires is specified as one figure.
The honest entry is three: 72 × 22 during any push-to-talk recording, 114 × 22
latched, and 114 × 22 throughout transcription — where the user's most natural
click, placing the caret for the text about to arrive, is the one that lands
nowhere.

## #5 — The tick inherits the key release's thread and focus sample

`end_session` was written against the event-tap thread and says so. A click
handler runs on **main** — the thread the overlay, tray and indicator dispatch
*onto*. Second inheritance: it samples the frontmost application at the ending
gesture, because a key release cannot change which application is frontmost. A
click on a panel can.

**Not taken:** hop to a thread, which this file already does for the one other
non-tap ender (`amanuensis-vad-auto-end`) and which the spec does not cite. Route
✓ through the listener so the gesture state machine keeps one owner. Pass the
focus identity in from when the panel was shown.

**Consequence:** `_recording` is documented as "Written on the event-tap thread
only" — already stale, since Phase 4 added two writers. This adds a fourth, on
main.

## #6 — Injection completion reconstructed from a two-state history

The controller's terminal transitions out of TRANSCRIBING are **three**: `ERROR`,
`RECOVERED`, `IDLE`. The spec's discrimination set was drawn from the two its
narrative walked through.

`RECOVERED` is a **successful injection** — the enum says "they did get their
words" — and §3's table puts it at `hidden`, so a recovered dictation gets the
cut rather than the fade. `RECOVERED` and `ERROR` are also sticky.

**Not taken:** a dedicated `on_injected` callback, which is what the signal
actually is. A richer payload. Fade on any non-`ERROR` exit from TRANSCRIBING,
which needs no history at all.

**Consequence:** the overlay acquires a private model of the controller's state
graph, kept in step by hand. §5 rejected latch-awareness because "the overlay
would be reasoning about capture modes"; a transition history is the overlay
reasoning about the controller's lifecycle, and §7 does not reconcile the two.

## #7 — Three off switches, precedence left unstated

`[feedback]` now has three switches over one component. The two new ones are not
the same *kind*: `overlay_transcribing = false` restores a documented reading of
§5.4 and costs the user nothing they had. **`overlay_controls = false` removes
the only cancel affordance the product has.**

§8 justifies them symmetrically, naming the cost of *true* and not the cost of
*false*.

**Not taken:** state the precedence. Treat cancel-availability as §5.3's bounded
exception — "behaviour that a stated guarantee depends on is not user-settable."
Give the cancel a second home (see #1).

## #8 — Breathing period typed, not read from history

This module has a strong local precedent against typed constants: `_FULL_SCALE`
is documented across twenty lines, derived from 8,684 blocks of the operator's
speech, with all three candidates recorded. `double_tap_ms` is marked UNMEASURED
in the config block. Neither convention is applied to ~900 ms or ~120 ms.

The tilde reads as approximation, not provenance. CLAUDE.md's standing rule is
that unmeasured numbers are marked unmeasured *when written*, "otherwise they get
quoted back as findings weeks later."

## #9 — Tight inherited from Wispr, forty-four pixels up

`_MARGIN = 44.0` was chosen when the panel was a **display**, so it would not
cover the caret. That forfeits the one thing that would make a 16 px target cheap
to hit: a control at a true screen edge has effectively infinite depth; one 44 px
in does not.

Fitts's law, and the macOS HIG's pointer hit-target guidance (well above 16 pt),
both argue `_MARGIN` is now a *control* parameter rather than a layout one, and
it was not re-derived. §11's open hover question is the same problem under a
different name.

## #10 — restart_session discards audio; the clocks unstated

`start_session` sets `started_at` (wall clock), `at` (`perf_counter` origin), and
the state together. `restart_session` must not touch the third. Whether it
touches the first two is unstated and "begin again" is compatible with both.

**Consequence:** `timings.capture_ms` feeds `LatencyBreakdown`, which PRD §5.5
calls a *product* requirement because G1 cannot be defended without it. A stage
that silently absorbs a `double_tap_ms` window on every latched dictation puts a
systematic offset into the measurement this project defends its headline claim
with — and latched sessions are the long ones, so the most likely to be quoted.

## #11 — Geometry re-derived from code, §5.4 unreconciled

PRD §5.4 (added 2026-09-03) says the pill is **112 × 26** with a **13 px**
radius. `overlay.py` says `_WIDTH 72`, `_HEIGHT 22`, `CORNER_RADIUS 11`. §4
re-derives from the code, silently.

The new §5.4 subsection landed 2026-09-10 carrying "114 × 22" roughly seventy
lines below a paragraph saying 112 × 26 — **one section of the PRD now publishes
two incompatible geometries, both added by the same author within a week, neither
annotated.**

CLAUDE.md: "correct every copy, and say the figure was wrong in the revision
note. Silent in-place editing destroys the evidence that the documents once
agreed on something false." That is the discipline this omission skips, and it
exists because six documents once agreed on a test count no commit produces.
