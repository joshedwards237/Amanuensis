# Overlay controls, the latch transition, and the transcribing state

**Status: SPECIFIED, NOT BUILT.** Operator disposition 2026-09-10: spec now,
build after lane 6. Building it before the gate would re-open lane 2's 6/6 —
that score describes the panel as it exists today — and leave the install gate
measuring a panel nobody has lived with for more than a day.

**Origin:** operator request, 2026-09-10, from use. Four changes, one component.

---

## 1. What is being asked for

1. **Controls in a latched session.** An **✕** and a **✓** to the right of the
   waveform. ✕ discards the dictation; ✓ ends it and processes. Tight — no
   generous padding. Each icon sits on a circle of slightly lighter background.
   Mirrors Wispr's affordance.
2. **No flash when latching.** A double-tap currently makes the panel disappear
   and reappear. It should open as the ordinary push-to-talk panel and then
   *transition* into the latched one.
3. **A transcribing state.** The panel currently vanishes the moment the
   microphone closes, before the words arrive. It should stay, showing motion
   that is not a generic spinner, until the text is injected.
4. **Fade out on paste**, rather than a cut.

---

## 2. The constraint that shapes all of it, and how it is resolved

`overlay.py`'s preamble decided this, before the panel existed:

> **It shows only while RECORDING, and TRANSCRIBING is the trap.** Transcribing
> is the longest state, it looks busy, and carrying the panel through it is the
> natural thing to do. The microphone is already closed by then, so a panel that
> stayed up would tell the user they were being recorded when they were not. For
> a privacy affordance, an over-report is not the safe direction — it is the
> direction that teaches people to ignore it.

Change 3 asks for exactly the thing that paragraph refuses. It is **not**
overruled. It is satisfied, because the argument is against *the panel that
means recording* outliving the microphone — not against the panel's pixels.

**Resolution (operator disposition, 2026-09-10): the panel persists and the
waveform does not.** At the instant the microphone closes the bars are
**replaced**, in one frame, by a form that could not be mistaken for them.

- **Hard cut, never a fade, at the recording→transcribing boundary.** A
  cross-fade produces intermediate frames in which a dimming waveform is still a
  waveform, which is the over-report the section forbids, briefly, on every
  dictation.
- **The `●` state carries no audio-derived motion.** Its animation must be
  time-driven and constant. Motion that responds to sound is a recording
  signal whatever shape it is drawn in.
- **The accent colour belongs to RECORDING alone.** Transcribing is rendered
  dimmed.

**The invariant, stated so a test can hold it:** *no audio-reactive element is
visible while the microphone is closed, and nothing rendered during
TRANSCRIBING varies with input.*

---

## 3. States and their appearance

| State | Panel | Bars | Controls | Motion |
|---|---|---|---|---|
| `IDLE` | hidden | — | — | — |
| `RECORDING`, unlatched | shown, 72×22 | live, accent | none | audio-driven |
| `RECORDING`, latched | shown, widened | live, accent | **✕ ✓** | audio-driven |
| `TRANSCRIBING` | shown, unchanged width | **replaced by `●`** | hidden | breathing, time-driven |
| injected | fades out ~120 ms | — | — | — |
| `ERROR` / `RECOVERED` | hidden | — | — | — |

**Controls appear only in a latched session**, because they answer a question
only a latched session raises. In push-to-talk the hand is already on the key
and the release *is* the ✓; an ✕ there would be a second way to do what letting
go already does, on a panel whose whole argument is that it says one thing.

**Controls are hidden during TRANSCRIBING.** ✓ would be a no-op and ✕ would
imply the audio is still discardable when §8 has already persisted it.

---

## 4. Geometry

Today: `_WIDTH 72`, `_HEIGHT 22`, seven bars of `_BAR_WIDTH 3` with `_BAR_GAP 3`
— 39 px of bars inside a 72 px pill.

Latched adds, to the right of the bars:

```
  ┌────────────────────────────────────┐
  │  ▂▅█▅▂▅▂   (⊗)(⊙)                  │   _HEIGHT 22 unchanged
  └────────────────────────────────────┘
     39px      2 × 16px circles
               _CONTROL_DIAMETER 16
               _CONTROL_GAP 4   (between the two)
               _CONTROL_INSET 6 (bars → first circle)
```

`_WIDTH_LATCHED = _WIDTH + _CONTROL_INSET + 2 × _CONTROL_DIAMETER + _CONTROL_GAP`
= 72 + 6 + 32 + 4 = **114**. "Tight" is the requirement, so these are minima: a
16 px circle in a 22 px pill leaves 3 px above and below.

**The pill re-centres on width change**, since `frame_for` centres horizontally.
The width change is animated (~120 ms) so the panel grows rather than jumping —
that animation *is* change 2's "smooth transition".

**Circle fill is the pill's background lightened**, not a new colour. It reads as
a raised area of the same object rather than two foreign badges.

---

## 5. Change 2 — why the panel currently flashes, and the fix

The flash is not a rendering artefact. It is the state machine doing what it was
told.

```
press 1 down   →  on_press   →  start_session  →  RECORDING  → panel shown
release 1 (tap)→  deferred end scheduled
press 2 inside →  on_cancel  →  abort_session  →  IDLE       → panel HIDDEN
                  on_press   →  start_session  →  RECORDING  → panel shown
```

`abort_session` sets `IDLE`, `_on_state_change` fans that out, and the overlay
hides on the way past. The user sees the panel blink.

**Rejected: debounce the hide.** Suppressing an `IDLE` that is followed quickly
by a `RECORDING` would work and would be a lie in the one component whose
correctness is "it shows exactly when the microphone is open". A timing rule that
hides a genuine close because another open followed is the §5.4 failure with a
stopwatch attached.

**Rejected: let the overlay know about the latch and ignore the IDLE.** Same
defect, plus §6.2 — the overlay would be reasoning about capture modes.

**Chosen: the session never passes through IDLE, because it never actually
stopped.** `DictationController` gains one operation:

```python
def restart_session(self) -> None:
    """Discard the audio captured so far and begin again, without closing.

    The microphone does not close and the state does not leave RECORDING.
    §5.2's latch discards the first tap's fragment *before the decoder*, and
    the user's finger never left the key in a way they would call "stopping" —
    so a state machine that reports IDLE between the two presses is reporting
    an event that did not happen.
    """
```

The listener's latch branch then emits **one** callback, `on_latch`, in place of
today's `on_cancel` + `on_press` pair, and `cli.py` wires it to
`controller.restart_session()`.

**§8 is untouched.** Nothing was transcribed, so nothing was persisted; this is
the same discard `abort_session` performs, minus the state transition.

**`on_cancel` remains** — it is what the ✕ needs, and it *does* mean IDLE.

---

## 6. Change 1 — clicking, and what it costs

**Operator disposition 2026-09-10: the whole panel accepts clicks.** Offered
against hit-testing only the two circles; the simpler option was chosen
knowingly.

`overlay.py:328` sets `setIgnoresMouseEvents_(True)` today, and the preamble
gives the reason: "mouse events ignored so it cannot swallow a click either."
That reasoning is not wrong, and the cost is now accepted rather than removed:

> **While the panel is visible, clicks inside its rectangle do not reach the
> application beneath it.** At the default `overlay_position = "bottom"` that is
> a 114 × 22 region, 44 px up from the bottom edge, centred. A user who clicks
> there mid-dictation will find the click went nowhere. `overlay_position =
> "top"` moves it; nothing removes it.

**This must be written into the README's known-costs section when built**, under
the same rule that put the clipboard-manager leak there.

Two properties that are not negotiable and need explicit tests:

- **The panel must never become key.** It appears over the application about to
  receive the transcript; taking focus would send keystrokes to the wrong
  window, from the exact window that is about to be typed into.
  `NSWindowStyleMaskNonactivatingPanel` is already set and must remain, and the
  content view must return **`acceptsFirstMouse: True`** so a click registers
  without activating.
- **A click is not a keystroke.** ✕ and ✓ must reach the controller by the same
  route the hotkey does, so that a latched session ended by ✓ is
  indistinguishable downstream from one ended by a tap.

### §6.2 boundary

The overlay renders and reports; it does not act. Same shape as the tray's
hotkey picker, which "renders a list and hands a name to `on_hotkey`".

```python
RecordingOverlay(
    config, on_error=..., on_cancel=..., on_finish=...
)
```

`cli.py` binds `on_cancel → controller.abort_session` and
`on_finish → controller.end_session`. The overlay must not import the
controller, and must not know what either verb does.

---

## 7. Change 3 — the transcribing animation

**Operator disposition: the bars merge into a single breathing dot.**

```
▂▅█▅▂▅▂   →   ──●──   →   ──●──   →   ──●──
recording      opacity 0.4 ↔ 1.0, ~900 ms, sinusoidal
```

Chosen over a travelling pulse across the existing bars for the reason §2 gives:
maximum visual distance from the recording state. A pulse that moves along seven
bars is still seven bars, and the requirement is that nothing which looks like a
waveform outlives the microphone.

- One `CALayer`, `_CONTROL_DIAMETER / 2` across, centred where the bars were.
- **Time-driven only.** `set_level` must be **ignored** while transcribing, not
  merely unused — the PortAudio thread stops delivering blocks when capture
  stops, so "no data arrives" would make this look correct without being it.
- The dot is dimmed relative to the recording accent.

### Change 4 — the fade

On successful injection, fade to zero opacity over ~120 ms, then `orderOut_`.
Two things it must not do: outlive an injection **failure** (the tray owns
errors, and a panel that lingered after a failure would be reporting nothing at
all), and it must be cancellable — a new dictation started mid-fade shows the
recording panel immediately, at full opacity.

**The overlay needs a signal it does not currently receive.** `_on_state_change`
fires for `TRANSCRIBING`, but "the text has been injected" is not a state — the
controller goes `TRANSCRIBING → IDLE` on success. The fade therefore hangs off
that `IDLE`, and the overlay distinguishes *`IDLE` arriving from `TRANSCRIBING`*
(fade) from *`IDLE` arriving from `RECORDING`* (immediate hide — an abort, where
nothing is coming). That is a two-element history, held in the overlay, and it
is the smallest thing that works without inventing a state §5.4 does not have.

---

## 8. Configuration (§5.3)

```toml
[feedback]
overlay_controls = true      # the ✕ and ✓ in a latched session
overlay_transcribing = true  # keep the panel up until the words land
```

Both default **true** — they are the requested behaviour. Both are keys because
each could reasonably go either way: `overlay_controls` costs the click-through
of a 114 × 22 region, and `overlay_transcribing` is the one that reverses a
documented §5.4 reading, so a user who wants the old behaviour must be able to
have it without editing code.

**`overlay_controls = false` does not disable the latch**, only its buttons.

---

## 9. What must be verified, and what cannot be

**Testable without a display**, on the existing fake-AppKit seam:

- Controls appear only when latched *and* recording — the four-way state table.
- `restart_session` never emits `IDLE`, with a control asserting that
  `abort_session` still does.
- ✕ and ✓ reach `on_cancel` / `on_finish` and nothing else.
- `set_level` during `TRANSCRIBING` changes no rendered geometry — with a
  positive control proving `set_level` during `RECORDING` does.
- Width switches with the latch, and `frame_for` re-centres.
- The `IDLE`-after-`TRANSCRIBING` fade versus `IDLE`-after-`RECORDING` cut.

**Not testable that way, and the fakes have been wrong three times** — the
`NSRect` shape, a missing `representedObject` getter, and a menu item with no
target or action, each of which passed its tests and failed on the machine.
Verify against real AppKit before believing any of these:

- `acceptsFirstMouse` actually delivering the first click without activating.
- The panel not becoming key when clicked.
- The width animation not leaving the panel off-centre.

**Cannot be tested at all here:** whether the ✕ is reachable *while speaking*,
which is the only question that decides if the feature works. That is lane
2-shaped and needs the operator.

---

## 10. Sequencing, and a blocker worth stating

**This is specified against a component that currently dies silently.** Gate
record findings 1 and 3: after days of running, the panel stopped appearing while
the microphone stayed live, and the failure notice goes to a dropdown nobody
opens. Two mechanisms are open — the `_failed` one-way latch, and the panel being
built once against `NSScreen.mainScreen()` and never rebuilt.

**Fix those first.** Everything specified here adds surface to a component that
already fails without saying so, and a ✕ that silently stops rendering is worse
than no ✕ — the user believes they have a way out of a latched session and does
not.

Order: findings 1 and 3 → lane 6 → this.

---

## 11. Open, and not decided here

- **There is no Escape-to-cancel, and it cannot cheaply be added.** The request
  described ✕ as "the UI version of pressing escape". `hotkey/macos.py` watches
  `kCGEventFlagsChanged` only and refuses `keyDown` by design — "a tap that
  watched keyDown would see every character the user types, which is a much
  larger surface than a dictation hotkey needs." An Escape binding means a
  second tap over every keystroke on the machine, which is a §7.6 decision, not
  a UI one. **The ✕ is therefore the only cancel affordance the product has**,
  which raises its importance rather than lowering it.
- Whether ✓ should also end an **unlatched** hold. Currently release does it;
  no request, and §3's non-goals do not cover it.
- Whether the controls need a hover state. macOS convention says yes; a panel
  that never takes focus makes it cheap to get subtly wrong.
