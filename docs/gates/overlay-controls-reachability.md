# Can the ✕ be reached while speaking? — the criterion

**Written 2026-09-10. The controls it judges do not exist yet, and that is the
point.** Slice S6 of `docs/superpowers/slices/overlay-controls.md`; the spec is
`docs/superpowers/specs/overlay-controls.md` §9, which states that this is *"the
only question that decides if the feature works"* and that it cannot be answered
by any test in this repository.

**Do not amend this document after seeing the buttons.** A criterion written
once the thing exists is a criterion written to pass, and this project has that
event on record twice:

- The landing page's headline band was chosen from five candidates by which one
  looked best — inside the section written to prevent outcome selection.
- Lane 2's confidence test scored 6/6 in a fresh daemon session minutes after
  start. The gate record now qualifies it: the panel passed the test it was
  given, and the test does not answer the question §5.4 asks.

If this criterion turns out to be the wrong question, say so **and record that
the question changed**, with the date and the reason. Do not adjust the
threshold.

---

## 1. What is being judged

Slice S5 puts two controls on the recording panel during a latched, hands-free
session: **✕** discards the dictation, **✓** ends it and processes.

Two facts make this worth a gate rather than a look.

~~**The ✕ is the only cancel affordance the product has.**~~ **The question
changed on 2026-09-17, and this section records that rather than adjusting for
it.** The document's own instruction is to say so with the date and the reason
and *not* to move the threshold, so the threshold does not move.

The original reasoning:

> §5.2's latch removes your hand from the key, and PRD §7.3's hotkey tap
> watches `flagsChanged` only — it refuses `keyDown` because a tap that watched
> it would see every character typed. So there is no Escape and cannot cheaply
> be one. If the ✕ is unreachable, a latched session has no way out except
> letting it run to `max_duration_seconds`.

**There is now an Escape**, via `RegisterEventHotKey`, which delivers one key
and never sees another — so the keystroke-surface objection that made this
impossible does not apply to it. `hotkey/escape.py`, spec §11.

What that does to this criterion, stated rather than assumed:

* **Question 1, reachability, is worth less than it was.** A latched session
  now has a way out that needs no pointer at all. A ✕ that is hard to hit is a
  worse product and no longer a trap.
* **Question 2, discrimination, is worth exactly what it was.** Escape does not
  help someone who reached for ✓ and hit ✕. The irreversibility in the next
  paragraph is unchanged: `abort_session` persists nothing, and a mis-hit
  destroys the dictation with no confirmation and no undo.
* **A new question this document does not ask**, and should not acquire by
  amendment: whether users reach for Escape or for the button. That is a
  different trial with a different criterion, written before it is run.

**The ✕ is irreversible and unguarded** (objection O3). `abort_session` persists
nothing — §8's guarantee does not reach a session that was never transcribed,
and the spec says so approvingly. A mis-hit destroys the dictation with no
confirmation, no undo, and nothing in `manu history` to recover.

So there are **two** questions, and the second is the one the spec did not ask:

1. **Reachability** — can you hit ✕ or ✓ while speaking?
2. **Discrimination** — when you go for one, do you get the one you meant?

---

## 2. Conditions, fixed in advance

- **The operator's own machine and own binding.** `right_command` as of
  2026-09-10, not the `right_option` default — the binding was changed because
  right-option's double-tap fires another application's shortcut, and testing
  the default would test a configuration this user does not run.
- **`double_tap_ms` at whatever value is in `config.toml` at the time**, and the
  value recorded in the result. It is a motor threshold and remains UNMEASURED.
- **Real work, not exercises.** Each trial is a dictation the operator actually
  needed to write. A trial performed for the trial measures the operator's
  attention to the trial.
- **A full-screen application with the menu bar hidden**, matching lane 2's
  condition — that is where the panel is the only signal, and it is where this
  product is used.
- **The pointer starts wherever it happens to be.** Parking it near the panel
  first is the single most likely way to make this pass falsely: the whole
  question is whether the control is reachable *from where you are*, mid-thought.
- **Nothing else running on the machine.** A previous measurement was ruined
  this way.

---

## 3. The trials

**Twenty latched sessions**, spread over at least **two separate days**.

Twenty rather than ten because this measures a rate, not a capability, and a
mis-hit rate of one in ten is invisible in ten trials. Two days because the
first session with a new control is not the same as the tenth, and shipping on
the first would publish a novelty effect.

Each trial is one latched dictation, ended deliberately:

| Trials | End it with | Recording |
|---|---|---|
| 10 | **✓**, mid-sentence, without stopping to look | outcome + whether you looked |
| 5 | **✕**, having decided mid-utterance to abandon it | outcome + whether you looked |
| 5 | a **single tap** on the key, as today | outcome — the control group |

The last five are the control. If tapping is comfortable and clicking is not,
the buttons have not earned the click-through cost §6 accepts on the whole panel
— and without those five there is nothing to compare against.

**Record for every trial**, before doing anything else:

1. **Did the intended thing happen?** yes / no.
2. **If no, what happened instead?** Missed the panel entirely / hit the other
   control / hit nothing / the panel was not there.
3. **Did you have to stop speaking to do it?** yes / no.
4. **Did you have to look at the panel?** yes / no.
5. **Anything you noticed.** Verbatim, before rationalising it.

Write them down as they happen. A tally reconstructed at the end is a memory of
a rate, not a rate.

---

## 4. The thresholds, and what each one forces

Set now, so no result can move them.

### Reachability — **18 of 20**

Fewer than 18 intended outcomes across the twenty trials and the controls do not
work as an affordance.

**What a failure forces, decided now:** not "make the buttons bigger". §11
establishes the ✕ would be the product's only cancel, so an unreachable ✕ is a
live question about whether the **latch** should ship at all in its current
form. The options, in the order they should be considered:

1. Move the cancel somewhere reachable that is not the panel — the tray has a
   working verb-dispatch surface and is reachable without aim (choice story #1).
2. Reconsider `_MARGIN`. It is 44 px, chosen when the panel was a *display* so
   it would not cover the caret. A control 44 px from an edge forfeits the
   infinite depth an edge-flush control has (Fitts). It is now a control
   parameter and was never re-derived for that.
3. Only then, geometry.

### Discrimination — **zero wrong-control hits in 20**

**Any** trial where you went for ✓ and got ✕ fails this outright. Not a rate: a
single instance is a destroyed dictation with no undo, and the trial set is far
too small to estimate a rate that small honestly. One is evidence the targets
are too close or too alike; zero is not evidence they are safe, and this
criterion does not claim otherwise.

**What a failure forces:** the ✕ stops being a single click. Confirmation, a
hold, a longer separation, or moving it off the panel — decided then, not now.

### Interruption — **recorded, not gated**

If most trials required stopping speech or looking at the panel, the controls
work and the feature does not: the latch exists so a long dictation does not pin
your hand to a key, and a control that pins your attention instead has moved the
cost rather than removed it.

Not a threshold, because no number for it is defensible in advance. **It is
required in the result**, and if it is high the honest report says the feature
was reachable and not worth reaching.

---

## 5. What this cannot answer

- **Anyone else's hands.** n = 1, one machine, one binding, one room — the same
  qualification every latency figure in this repository carries.
- **Whether the panel is in the way.** That is `overlay_position`, and it is a
  different question.
- **Long-term mis-hit rate.** Twenty trials cannot see a one-in-a-hundred error,
  and the discrimination threshold above is deliberately zero-tolerance rather
  than a rate for exactly that reason.
- **Whether the ✕ is *wanted*.** Reachable and useless is a possible outcome;
  the interruption note is where it would show up.

---

## 6. Where the result goes

`docs/gates/phase-4.md` if Phase 4 is still open when this runs, otherwise its
own record. It carries: the twenty rows, both scores against both thresholds,
the `double_tap_ms` and binding in force, and the decision each threshold forced.

**A trial that is not written down did not happen**, and a threshold that moves
after the result is not a threshold.
