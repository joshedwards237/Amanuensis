---
target: "docs/superpowers/specs/dictionary.md (revision 2, 2026-08-03)"
task_slug: dictionary
date: 2026-08-03
authored_by: "main session — the choice-cartographer sentinel was dispatched twice and returned nothing"
stories:
  - id: C1
    title: "initial_prompt was inherited as the biasing mechanism, never chosen"
    stated: false
    disposition: pending
  - id: C2
    title: "The dictionary is global, and per-application was rejected before it got cheap"
    stated: partially
    disposition: accepted
    disposition_rationale: "Human decision, 2026-08-04. The rejection is overturned: [boost] is scoped per application. TextInjector.focus_identity() already returns the frontmost bundle identifier and is already called on every dictation for the §6.3 focus check, so the information a per-application dictionary needs is on the path and measured. The cost is a table key, not a subsystem. This is also the only mechanism on the table that addresses C8 — the limit on [boost] is relevance, not term count, and scoping is how relevance gets expressed."
  - id: C3
    title: "A file edit takes effect on daemon restart, and nothing says so"
    stated: false
    disposition: accepted
    disposition_rationale: "Human decision, 2026-08-04. vocabulary.toml is re-read when its mtime changes, not only at startup. §6.3's argument against ambient configuration was made for config.toml, which changes rarely; a dictionary's whole use pattern is notice a mangled word, add a line, try again, and under restart-only semantics 'try again' means reloading a model. The §6.3 contract is not weakened for config.toml itself."
  - id: C4
    title: "The guard fails open, and the alternative was never named"
    stated: partially
    disposition: accepted
    disposition_rationale: "Human decision, 2026-08-04, confirmed 2026-08-05. The guard retries with the bias removed, and if the retry also fails the transcript is not injected and the failure is reported loudly. Transcription is ~200 ms at 10 s, so a retry is affordable on a path already known to be broken. §7.5's 'degrade rather than stall' precedent does not apply — that governs a pass that is too slow, and this is a pass that is wrong. Two consequences recorded rather than discovered later: the retry must drop initial_prompt or it is worthless, because beam_size = 1 is greedy and re-running the same audio the same way returns the same words; and where no initial_prompt is configured there is nothing to retry, so the guard goes straight to the loud failure rather than reporting a recovery attempt it never made."
  - id: C5
    title: "'The user's words' silently became final_text"
    stated: false
    disposition: pending
  - id: C6
    title: "The user is assumed to be someone who edits TOML by hand"
    stated: partially
    disposition: pending
  - id: C7
    title: "Two tables was chosen before the mechanisms were known to differ"
    stated: true
    disposition: pending
  - id: C8
    title: "[boost] was assumed free"
    stated: false
    disposition: pending
---

# Choice-story record — Dictionary

## Provenance

**The choice-cartographer sentinel did not produce this.** Dispatched with an
absolute charter path and an explicit output contract; nudged once with the new
measurements; went idle without ever emitting text. Zero output across its
entire lifetime.

All three sentinels dispatched for this feature returned nothing. This record is
the main session's own, and is marked as such.

---

## C1 — `initial_prompt` was inherited as the biasing mechanism, never chosen
**Stated? No. Load-bearing? Yes. Now resolved by measurement.**

**Decision:** boosting happens through `initial_prompt`.

**Where it came from:** §5.6, written before implementation, names it. The spec
quoted §5.6 and built two slices on it. Nobody asked what the library offers.

**The alternative that existed the whole time:** `faster_whisper 1.2.1` has a
**`hotwords`** parameter, and a `prefix` parameter, neither of which appears in
§5.6, this spec's first revision, or any prior document in this project.

**Resolved:** measured, `hotwords` produces **identical WER on all six corpus
samples** — 18.2 macro, the same per-sample deltas, the same two regressions.
It is not a distinct mechanism in effect. The inherited choice happens to be
correct.

**Why it still matters:** it was correct by luck. The same inheritance produced
§5.6's "whole-word substitutions", which §4 of the spec had to overturn from one
dictation. A spec written before the library was read will be right about some
things and wrong about others, and it cannot tell you which.

**Consequence worth recording:** the trade is now known to be **inherent to
prompt-based biasing**, not an artefact of one API. There is no boosting
mechanism available here that avoids degrading unrelated speech.

---

## C2 — The dictionary is global, and per-application was rejected before it got cheap
**Stated? As a non-goal, with no reasoning. Hidden? The reasoning is.**

**Decision:** one dictionary, applied to every dictation.

**Rejected:** per-application dictionaries — "not asked for and doubles the
surface" (revision 1, §5.5).

**What that reasoning missed:** Phase 2b built `TextInjector.focus_identity()`,
which returns the frontmost application's bundle identifier and is already
called on every dictation for the §6.3 focus check. The information a
per-application dictionary needs is **already in hand, already measured, already
on the path**. The cost is a table key, not a subsystem.

**Why it matters more than it looks:** C1 establishes that boosting degrades
unrelated speech. Scoping a boost list to the application it is relevant to is
the obvious mitigation for the exact problem that makes V3 doubtful — and it was
rejected in a sentence, before the problem was known.

**Disposition:** the rejection should be re-decided, not inherited.

---

## C3 — A file edit takes effect on daemon restart, and nothing says so
**Stated? No. Hidden? Completely.**

**Decision:** `vocabulary.toml` is read at startup.

**How it was made:** by inheriting `config.py`'s contract — "loaded once and
passed explicitly", frozen, no ambient accessor (§6.3, choice-story #3). That
decision was argued for *configuration*, which changes rarely.

**A dictionary is not configuration.** Its whole use pattern is: notice a
mangled word, add a line, try again. Under this decision "try again" means
restarting a daemon that takes several seconds to reload a model.

**The alternative nobody weighed:** re-read `vocabulary.toml` on change, or on
each dictation. It is a small file; the §6.3 argument against ambient config
does not obviously extend to a data file the user edits during use.

**Disposition:** decide explicitly. If it is restart-only, the docs must say so,
because the failure mode is a user concluding their entry did not work.

---

## C4 — The guard fails open, and the alternative was never named
**Stated? Half. The alternative? Not at all.**

**Decision:** when the collapse guard fires, the transcript is kept, the session
records why, the indicator reports it.

**Never named:** discarding the suspect transcript and **re-running without the
prompt**. Transcription is ~200 ms. The guard fires on a transcript already
known to be probably-destroyed. A retry is affordable inside G1 and would turn a
reported failure into a recovered dictation.

**Why the spec did not consider it:** §7.5's precedent is "degrade rather than
stall — skip, never queue", which is about a pass that is *too slow*. This is a
pass that is *wrong*, which is a different failure and does not inherit that
reasoning.

**Disposition:** weigh the retry. It may be the better default and it costs one
transcription.

---

## C5 — "The user's words" silently became `final_text`
**Stated? No. Consequence? Objection O1.**

**Decision:** history stores one transcript, and post-processing's output wins.

**Made where:** `to_history_row()` — `final_text or raw_transcript` — in Phase
2a, as a convenience, with no discussion.

**What it decided:** that §8's "never lose a transcript" protects the
*processed* transcript. So a dictionary rule that corrupts a word makes the
original unrecoverable, and §8's guarantee holds over text the user never said.

**The alternative:** store both. §7.5 already requires it for the LLM pass —
"raw transcript persisted" is the first of four constraints — and the schema
cannot express it.

**Why this is the most consequential story here:** it is a decision nobody made.
It was a defaulting expression in a row builder, and it now constrains two
features.

---

## C6 — The user is assumed to be someone who edits TOML by hand
**Stated? Celebrated. Examined? No.**

**Decision:** the file is the interface. `manu vocab add/list/boost` rejected.

**Rests on:** §4's privacy-motivated primary user, and story S4 — "my vocabulary
is a plain text file I can read, edit, diff, back up, and delete."

**Not weighed:** §4's *secondary* user, who has a motor impairment and for whom
"a dropped transcription is not a minor annoyance". That user is the one most
dependent on dictation working and the least well served by "open a text editor
and write TOML". The PRD invokes them elsewhere to justify recovery paths.

**Disposition:** the rejection may still be right, but it should be made in
front of both users rather than one.

---

## C7 — Two tables was chosen before the mechanisms were known to differ
**Stated? Yes. Justified? By a sentence that had never been tested.**

**Decision:** `[boost]` and `[replace]` are separate tables because "they fail in
different places" (§5.6).

**Now measured, and the split is vindicated for a reason §5.6 did not give:**
`[boost]` fails by degrading *other* utterances — collateral damage at a
distance. `[replace]` fails locally and visibly in the file. Those are not two
points on one axis; they are different kinds of thing, and merging them would
have hidden it.

**Recorded because the reasoning was luck.** The split was made on an untested
sentence and turned out right.

---

## C8 — `[boost]` was assumed free
**Stated? No — assumed throughout revision 1.**

**Decision:** boost terms are additive and harmless, so the table can be
generous.

**Measured false.** +3.2 WER on `01-natural`, +5.2 on `02-code`, from a term
list irrelevant to both. Net macro gain 1.1 points. And a prose prompt collapsed
a transcript entirely.

**What the assumption caused:** revision 1 gave `[boost]` a 100-term cap
justified only by the prompt window, and no guard. Both were wrong for the same
reason — the cost was assumed to be size, when it is *relevance*.

**Disposition:** the limit on `[boost]` is not how many terms; it is how
unrelated they are to what is being said. Nothing in the design currently
expresses that. C2's per-application scoping is the only mechanism on the table
that could.
