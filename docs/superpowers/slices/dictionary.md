---
task: "Dictionary — custom vocabulary for Amanuensis (docs/superpowers/specs/dictionary.md, draft 2026-08-03)"
task_slug: dictionary
date: 2026-08-03
carpaccio_model: null
authored_by: "main session — the carpaccio sentinel was dispatched twice and returned nothing both times"
inseparable: false
progressed_slice: null
---

# Slicing record — Dictionary

## Provenance, stated plainly

**The carpaccio sentinel did not produce this.** It was dispatched with an
absolute charter path and an explicit output contract, went idle without
emitting a word, was re-asked once with the new measurements folded in, and went
idle again. Two attempts, nothing returned. This record is the main session's
own slicing, and it is marked as such rather than presented as reviewed.

This is the third time in this project that a read-only sentinel has failed to
deliver — it is already in `AGENTS.md` GOTCHAS. The gotcha understates it: the
recorded advice is "say so in the dispatch", which was done here and did not
help.

## What the draft proposed, and why it is wrong

The spec's §7 proposes D1–D5, with D1 = "load `vocabulary.toml` + wire `[boost]`
to `initial_prompt`" and D2 = "`VocabularyPostProcessor`". Three problems, all
of them found by measuring rather than by reading:

1. **D1 is not the first thing to build. The guard is.** `initial_prompt` is
   wired, live, and set on the operator's machine *right now*. Measured, a
   mismatched prompt collapsed a 25-second transcript to 10.6% of its reference
   words. That hazard is in production use today and does not wait for a
   dictionary to exist.
2. **The draft's §5.4 entry cap is invented.** Measured at 0.21 ms p95 for 500
   entries. Latency does not constrain this feature at any plausible size, so no
   slice should be shaped around it.
3. **`[boost]` is the strong half, not the weak one.** The draft's open question
   O2 doubts whether it is worth having. Measured: 4/10 → 9/10 proper nouns,
   beating `base.en` at half the latency. O2 is answered and the doubt was
   backwards.

---

## Slices

### V1 — The collapse guard

**Scope.** A deterministic check that a transcript is not implausibly short for
the speech that produced it, applied to every transcription regardless of
whether any dictionary exists. Fires on the trimmed audio, which is speech by
construction. Does not fire when the VAD reports `fell_back`. On failure the
transcript is kept, the session records the reason, and the indicator reports it.

**Decision focus.** Is `initial_prompt` safe to expose to users at all, and
what does the product do when a probabilistic input silently deletes the user's
words?

**Lens.** Safety floor — the same lens S4 used for §8's persist-before-inject
write and §5.4's recording indicator.

**Sequencing.** **First, and not because of the dictionary.** `initial_prompt`
is a config key in §5.3 that any user can set, is wired today, and is set on the
operator's machine now. Every slice below increases the number of people setting
it. The guard is what makes the rest shippable.

**Measurement.** Already taken and it is what justifies the slice: real speech
in the corpus runs 2.18–3.33 words per second of retained speech; the measured
collapse ran 0.20 w/s, **10.8× below the slowest real sample**. A floor between
25% and 50% of the slowest observed catches the collapse and flags zero real
samples. Starts permissive at 0.5 w/s per the standing rule and tightens on
evidence.

**Precedent this follows.** S4 in the previous slicing record proposed a safety
floor as its own slice, and it was *merged* into the slices that first made it
applicable rather than shipped separately. The same reasoning applies inverted
here: the hazard is already applicable, so the guard leads rather than follows.

---

### V2 — `[replace]`: the transcript says what I meant

**Scope.** `vocabulary.toml` with a `[replace]` table only. Load, validate,
apply as `VocabularyPostProcessor` in the §5.3 chain. Case-insensitive,
whole-token, phrase-aware, longest-key-wins, no cascading. Compiled to a single
alternation at load.

**Decision focus.** Is a deterministic replacement map enough on its own, and
does phrase matching behave acceptably on real dictation?

**Lens.** Decision-boundary.

**Sequencing.** Independent of V1 in mechanism — it touches text after decoding
and cannot collapse anything — but should follow it, because V1 is the one that
protects a live hazard.

**Why this before `[boost]`.** It is the half a user can *reason about*. Add
`breadshoe = "spreadsheet"`, get spreadsheet, every time. When it is wrong, the
file says why. That makes it the better first experience of the feature, and it
is the half that fixes the operator's actual reported failure including the
`spread sheet` phrase case that a whole-word map would miss.

**Measurement.** Implementation strategy, not entry count: one compiled
alternation versus a loop of `re.sub` is **70× at 1000 entries** (0.35 ms vs
12.01 ms p50). The spec must constrain the approach. The cap can be generous or
absent.

---

### V3 — `[boost]`: the model hears my vocabulary

**Scope.** The `[boost]` table, concatenated onto `[engine] initial_prompt`,
prose first. Truncation with a warning when the prompt window overflows.

**Decision focus.** How do a user's boost terms combine with a config key that
already exists and may already be set?

**Lens.** Decision-boundary.

**Sequencing.** **Depends on V1 and must not ship without it.** This is the
slice that makes the collapse hazard reachable by more users, by more paths, with
longer prompts. Shipping V3 before V1 is shipping the failure mode as a feature.

**Measurement.** Taken: 4/10 → 8/10 with terms alone, 9/10 with prose + terms,
0/10 with prose alone. The last figure is the collapse and is why V1 leads.

---

### V4 — `manu vocab check`

**Scope.** One verb. Takes text, prints which entries would fire and what the
result would be. No file writes.

**Decision focus.** Can a user debug their own dictionary without dictating into
it?

**Lens.** Acceptance-criterion — this is what makes story S3 true.

**Sequencing.** After V2. Trivial once the map is loadable.

**Why it survives when the CRUD verbs do not.** Everything else `manu vocab`
was proposed to do is editing a TOML file, which the user can already do in the
editor they prefer. This is the only operation the file cannot perform on
itself.

---

## Recommended NOT to build

**`manu vocab add` / `list` / `boost` (the draft's D4).** §6.1 treats the verb
surface as the process model's public contract, and this is a second way to do
something a text editor already does well. The draft's own open question O1
raises this and then proposes the verbs anyway. Declining them costs the user
nothing: the file is the interface, which is story S4's entire point.

**Auto-learning (the draft's D5).** Requires reading other applications' text
after injection. `scripts/gate_2a_inject.py` needs a separate dependency
(`gate` extra) for exactly that capability, deliberately kept out of the
product by §7.6. Not "later" — **no**, unless the mechanism changes.

## Which slice teaches the most

**V1**, and not for the reason a slicing record usually gives. It does not teach
whether the dictionary is worth building; V3's measurement already settled that.
It teaches whether this project can ship a probabilistic accuracy mechanism at
all — because if a words-per-second floor turns out to fire on real dictation
from a slow or quiet speaker, then `[boost]` is not shippable, and the feature
collapses to V2 alone. That is the one outcome that would change the plan
rather than refine it.

## Where the measurement goes

Phase 3's gate is already **edit rate over ten real dictations of ≥ 60 seconds**.
The dictionary's whole purpose is to move edit rate, so it needs no gate of its
own — it needs the *same* dictations measured twice, with the dictionary
disabled and enabled. That is a config toggle over one corpus, not a second
harness.

Two things that gate must additionally record, because they are not edit rate:

- **`postprocess_ms` with the dictionary loaded**, since it is now inside G1's
  window and §2's scaling note means the ≥ 60 s dictations are already the worst
  case for latency.
- **Whether the V1 guard fired, and on what.** A guard that never fires across
  ten long dictations is either correct or untested, and the gate record has to
  say which — this project has two gates that could have passed by measuring
  nothing.
