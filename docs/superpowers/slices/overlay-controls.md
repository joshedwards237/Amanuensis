---
task: "Overlay controls, the latch transition, and the transcribing state (docs/superpowers/specs/overlay-controls.md)"
task_slug: overlay-controls
date: 2026-09-10
carpaccio_model: claude-opus-5[1m]
inseparable: false
progressed_slice: null
slices:
  - id: S1
    title: "The panel's own death becomes visible, and it survives a display change"
    scope: "Gate findings 1 and 3, which §10 names as blockers and no phase owns. The failure notice moves off the dropdown onto a surface a user sees without opening a menu; the `_failed` one-way latch gains a bounded recovery; the panel is rebuilt or re-framed when the screen it was positioned against changes. Excludes every one of the spec's four changes."
    decision_focus: "Which surface carries an overlay failure, given §5.4's premise is that the user must not have to open the tray menu. And: does this work ship at all, or does the gate record close with 'ship with it stated'?"
    lens_used: decision-boundary
    sequencing_note: "Blocks S3 hard and S5 hard. §10: findings 1 and 3 → lane 6 → this."
    disposition: accepted
    disposition_rationale: "Accepted 2026-09-10. S1 built the same day; S2-S6 wait on the spec amendment the objection dispositions require."
  - id: S2
    title: "A double-tap latches without the session ever stopping"
    scope: "`DictationController.restart_session`; the listener's latch branch emitting one `on_latch`; `cli.py` wiring it. Excludes every pixel — `overlay.py` is not edited."
    decision_focus: "Does a UI symptom justify a new operation on the controller? Is `restart_session` a real domain event or a rendering workaround wearing a controller method's name?"
    lens_used: decision-boundary
    sequencing_note: "Independent of S3, S4, S5. Its user-visible effect is invisible until S1."
    disposition: accepted
    disposition_rationale: "Accepted 2026-09-10. S1 built the same day; S2-S6 wait on the spec amendment the objection dispositions require."
  - id: S3
    title: "The panel outlives the microphone, and nothing on it reacts to sound"
    scope: "`should_show` extended to TRANSCRIBING behind `[feedback] overlay_transcribing`; the hard cut to a time-driven breathing dot; `set_level` ignored — not merely unfed — while transcribing. Excludes the fade (S4) and the controls (S5)."
    decision_focus: "This reverses a documented §5.4 reading. §2 claims the reversal is satisfaction rather than override. Is that distinction real to a user, or only to the author of §2?"
    lens_used: decision-boundary
    sequencing_note: "Hard dependency on S1. Must precede S4."
    disposition: accepted
    disposition_rationale: "Accepted 2026-09-10. S1 built the same day; S2-S6 wait on the spec amendment the objection dispositions require."
  - id: S4
    title: "The panel fades when the words land, and cuts when nothing is coming"
    scope: "A ~120 ms fade on IDLE from TRANSCRIBING; immediate hide on IDLE from RECORDING; no fade after ERROR; cancellable by a new dictation."
    decision_focus: "'The text has been injected' is not a state. Either the overlay holds transition history — a component §6.2 says renders and reports — or the controller gains a state §5.4 does not have."
    lens_used: decision-boundary
    sequencing_note: "Unbuildable before S3: today IDLE after TRANSCRIBING reaches an already-hidden panel."
    disposition: accepted
    disposition_rationale: "Accepted 2026-09-10. S1 built the same day; S2-S6 wait on the spec amendment the objection dispositions require."
  - id: S5
    title: "✕ and ✓ in a latched session, and the click-through the panel now costs"
    scope: "The two 16 px controls, `_WIDTH_LATCHED = 114`, the animated width change, `setIgnoresMouseEvents_(False)`, `acceptsFirstMouse`, the `on_cancel`/`on_finish` arguments, `[feedback] overlay_controls`, and the README known-costs entry. Excludes hover, Escape, and ✓ for unlatched holds — all §11 open."
    decision_focus: "How does the overlay learn it is latched? §3 requires latched-only controls; §5 rejects the overlay knowing; §6.2's constructor carries neither parameter nor setter. The spec asks for both and specifies neither."
    lens_used: decision-boundary
    sequencing_note: "Hard dependency on S1. S6's criterion must be written before this is built."
    disposition: accepted
    disposition_rationale: "Accepted 2026-09-10. S1 built the same day; S2-S6 wait on the spec amendment the objection dispositions require."
  - id: S6
    title: "Can the operator hit the ✕ while speaking — criterion written first, then tried"
    scope: "A written reachability criterion authored *before* S5 is built, then a trial. Excludes all code. **The criterion is written: `docs/gates/overlay-controls-reachability.md`, 2026-09-10, before any control exists. The trial waits on S5.**"
    decision_focus: "A criterion written after the buttons are seen will be written to pass — this repository has that event on record twice."
    lens_used: acceptance-criterion
    sequencing_note: "Criterion before S5. Trial after S5. Needs a person at the keyboard."
    disposition: accepted
    disposition_rationale: "Accepted 2026-09-10. S1 built the same day; S2-S6 wait on the spec amendment the objection dispositions require."
---

# Slicing record — overlay controls, the latch transition, the transcribing state

Six slices from four requested changes. The arithmetic is not tidy and the
reasons are worth stating.

**One slice is not in the spec.** §10 says "fix those first" about gate findings
1 and 3 and assigns them to nobody. The phase-4 gate record's own closing list
carries "resolve finding 1, or record a decision to ship with it stated" as item
1, still open. **A blocker named in prose and owned by no work item** is the
shape §9's language already has a sentence for. S1 exists so the disposition on
it is taken rather than inherited.

**Two of the spec's four changes are one heading and two decisions.** §7 carries
the fade as a subsection of the transcribing state, but the fade's constraints —
must not outlive an injection failure, must be cancellable, must distinguish two
arrivals at the same state — are a separate engagement, and §2's argument runs
long enough that anything folded inside it is cheap to accept by the time the
reader arrives. S3 and S4.

**The spec has a gap S5 will hit on its first day.** §3 requires controls "only
in a latched session". §5 rejects, on §6.2 grounds, letting the overlay know
about the latch. §6.2's constructor has no latch argument and `_on_state_change`
carries a `DictationState` which does not encode latching. **Three sections
written against different answers.** This is decision content, not an error to
fix quietly, and it is S5's.

## Verification notes that travel with the slices

**S1.** Three tests at the fake-AppKit seam, each with a control: a raising
`_render` changes a surface that needs no menu (positive control: a healthy
render leaves it unchanged); a transient raise recovers (negative control: a
persistent raise still latches off); `frame_for` re-derives against a changed
screen tuple. **The original defect is not reproducible on demand** and a fix
must not be reported as confirming its absence.

**S2.** `restart_session` records no state change and leaves RECORDING —
asserted with a positive control **in the same file** that `abort_session` still
emits IDLE, because a test checking only "no IDLE" is satisfied by an unwired
callback. The flash itself is assertable: drive the double-tap through the
`cli.py` fan-out with a fake overlay and assert it never receives a hide between
the two recording states.

**S3.** The invariant, held: `set_level` during TRANSCRIBING leaves every
rendered geometry unchanged, **with a positive control that the same calls during
RECORDING change bar heights.** Without it the test passes on a panel rendering
nothing. The test must call `set_level` explicitly — a test that simply stops
feeding it proves nothing and will read as though it did.

**S4.** Four assertions, and the discrimination is the whole feature. Plus a
control proving the fade does reduce opacity when left alone, because "opacity is
1.0" passes trivially on a fade that never started.

**S5.** Six tests on the fake seam, including a boundary test that `overlay.py`
imports no controller symbol. **Three properties the fakes cannot hold** —
`acceptsFirstMouse` delivering the first click without activating, the panel not
becoming key, the width animation not leaving the panel off-centre. §9 names
three prior occasions where the fakes passed and the machine failed. **Do not
report this slice complete on green fakes.**

## Sequencing

**Hard chains:**

1. `S1 → S3` and `S1 → S5`. Not advisory: both add surface to a component that
   fails without saying so.
2. `S3 → S4`. No IDLE-after-TRANSCRIBING to fade until the panel survives it.
3. `S6's criterion → S5`. **Done 2026-09-10** —
   `docs/gates/overlay-controls-reachability.md`, written while the controls do
   not exist, which is the only time it can be written honestly.
4. `S5 → S6's trial`.

**Recommended order:** S6's criterion (one sitting), then S1, then S2 and S5 in
either order, then S3, then S4, then S6's trial. S2 sits early because it is the
cheapest complete thing here and its test seams exist.

**One cross-slice note the spec does not carry.** S2 introduces `on_latch` wired
in `cli.py`; S5's open decision may want that same callback fanned out to the
overlay. If S2 lands first, wire it through the same one-to-many pattern
`_on_state_change` already uses, so S5 need not restructure it.

## Explicitly not slicing on

- **Files.** Four files, and the temptation is four slices. Three slices touch
  `overlay.py` and one touches nothing else.
- **Layers.** "The two config keys" is not a slice. `overlay_controls` and
  `overlay_transcribing` are deliberately split across S5 and S3 rather than
  clustered, because each belongs to the behaviour it gates.
- **Commit boundaries.** "The dot, then the `set_level` guard" is the order the
  code would be written in and the wrong order for a decision — the guard is what
  makes the reversal safe.
- **Finding 1's two mechanisms.** Two causes of one symptom, and the gate could
  not discriminate them precisely because the failure was silent. Slicing them
  apart would let the robustness half ship first, which the gate argues against.
- **§11's three open questions.** A slice would manufacture a decision the spec
  deliberately declined to take.
- **The real-AppKit list in §9.** S5's acceptance conditions, not a separate
  deliverable — moving them out is how they become optional.
