---
target: "docs/superpowers/specs/dictionary.md (draft 2026-08-03)"
task_slug: dictionary
date: 2026-08-03
mode: spec
authored_by: "main session — the advocatus-diaboli sentinel was dispatched three times and returned nothing"
objections: 11
---

# Objection record — Dictionary

## Provenance, stated plainly

**The advocatus-diaboli sentinel did not produce this.** Dispatched with an
absolute charter path and an explicit output contract; went idle without
emitting text; re-asked with new measurements folded in; went idle again;
re-asked a third time with the ask reduced to "three objections, plain prose,
no format". This record is the main session attacking its own draft, which is
structurally weaker than an independent reviewer and is marked as such.

Two of three sentinels failed identically. That is now the dominant fact about
this repo's review tooling and it belongs in `AGENTS.md`, not in a footnote.

---

## O1 — B9 is false as the code stands, and cannot be made true by this feature
**Severity: high. Disposition: accept — blocks V2.**

The draft's B9 says: *"The raw transcript is persisted before replacement …
so a bad rule is always recoverable from history."*

`DictationSession.to_history_row()` emits **one** transcript:

```python
"transcript": self.final_text or self.raw_transcript,
```

`history.db` has one `transcript` column. Once post-processing sets
`final_text`, the raw output is **not persisted anywhere**. B9 describes
behaviour that does not exist and that the schema cannot express.

This is not merely a spec error. §7.5's four Phase 5 constraints open with
**"raw transcript persisted"** — the same guard, for the same class of hazard
(a pass that rewrites the transcript), specified for the LLM and absent for the
dictionary. And it is absent *in the schema*, so Phase 5 will hit it too.

**Third instance of "an amendment must reach the tooling."** The first was
`bench_engines.py` regenerating a withdrawn WER figure. The second was
`restore_ms` having no column. This is a constraint the PRD states and the
storage layer cannot honour.

**Disposition:** `history.db` needs a `raw_transcript` column and a migration,
and it is V2's precondition rather than V2's business — Phase 5 needs it
identically.

---

## O2 — The headline result is n=1
**Severity: high. Disposition: accept — qualify every claim built on it.**

"4/10 → 9/10 proper nouns" comes from **one corpus sample**, transcribed a
handful of times. The `[boost]` table, slice V3, and the answer to open question
O2 all rest on it.

This project has a written rule about exactly this: *measure the tail, not the
median*, added after a p50 from one clean sample said GO and a p95 over six real
samples said the opposite. A single sample is weaker than that was.

The corpus has six samples. `03-proper-nouns` was chosen because it is the one
with proper nouns in it — which is legitimate for the *phenomenon* and
illegitimate for the *rate*. Nothing establishes that boosting helps on
`01-natural`, and boosting a term list irrelevant to the audio is precisely the
configuration that produced the collapse.

**Disposition:** before V3 ships, run the boost list against all six samples and
report per-sample. If boosting degrades unrelated dictation, the two-table design
is wrong and `[boost]` should be scoped to something narrower than a global
prompt.

---

## O3 — The collapse mechanism is unexplained, so the guard may be aimed wrong
**Severity: high. Disposition: accept — V1 cannot be designed on one observation.**

The prose-only prompt collapsed exactly **one** of six samples. Five were
unaffected. Nothing in the record says why `03-proper-nouns` and not the others.

A guard built against an unexplained failure is a guard against a symptom. If
the cause is prompt/audio domain mismatch, the same mismatch could equally
produce a *hallucinated expansion* — a transcript that is too long, plausible,
and wrong — which a words-per-second **floor** cannot see at all. §7.5's Phase 5
constraints include a no-invent check precisely because that direction exists.

**Disposition:** V1's scope must include finding out what the collapse is before
choosing what to check. If the mechanism is early-termination, a floor is right.
If it is domain drift, a floor is half a guard.

---

## O4 — B4 (casing preservation) is the keystroke hazard, re-committed
**Severity: medium-high. Disposition: reject B4 as drafted.**

§7.3's Phase 2a finding is that macOS text substitution silently rewrites the
user's words and that this is unacceptable *because it is silent and
heuristic* — five changes in one sentence, invisible until read.

B4 says a matched key at sentence-start "yields a capitalised replacement unless
the replacement is itself explicitly cased". That is a heuristic that rewrites
the user's words, in a project that has already documented this exact hazard
and declined to accept it from macOS.

The `[replace]` table's selling point over `[boost]` is that it is
**deterministic**. B4 makes it conditional on position and on a guess about
whether `XLSX` was "explicitly cased".

**Disposition:** replacement is literal. What the user writes on the right-hand
side is what lands. If they want both cases, that is two entries — which B6
already forces on them anyway, and which is honest.

---

## O5 — Nothing tells the user a rule fired
**Severity: medium-high. Disposition: accept — affects V2 and V4.**

The failure mode is a rule firing where it should not: `sheet → worksheet`
rewriting a sentence about bedding. The user sees wrong text and has no signal
that the dictionary touched it — the transcript looks like an ASR error, which
is the one explanation that leads them to the wrong fix.

§7.5's four constraints exist because a pass that rewrites text needs to be
auditable. `manu vocab check` (V4) is the draft's answer and it is *offline* —
it answers "what would fire", never "what did fire".

**Disposition:** the session records which entries fired. V4 becomes the way to
read that, not a separate simulator.

---

## O6 — The Phase 3 gate is trivially gamed by this feature
**Severity: medium. Disposition: accept — constrain the gate.**

Phase 3 gates on edit rate over ten dictations. The dictionary reduces edit rate
by construction. Adding entries for the exact words in those ten dictations
produces an excellent number that measures nothing.

The slicing record proposes "the same dictations, dictionary off and on", which
is right and insufficient — it does not stop the dictionary being *written
against the test set*.

**Disposition:** the dictionary must be frozen before the gate dictations are
recorded, and the gate record states when it was last edited. Entries added
after are a separate measurement.

---

## O7 — `[boost]` and `[engine] initial_prompt` are two keys for one thing
**Severity: medium. Disposition: needs a decision, not a default.**

B1 concatenates them, prose first. So the same behaviour is now configured from
two files with an ordering rule between them, and §5.3's policy — every
decision that could go either way is a key with a sane default — has been
satisfied twice for one decision.

The live config on this machine already sets `initial_prompt` to prose *with
terms embedded*, which is neither of the two things B1 imagines.

**Disposition:** pick one. Either `[boost]` is the only supported way to bias
and `initial_prompt` is deprecated to prose-only with that stated, or
`[boost]` is sugar that appends and the docs say so in one line. The draft has
it both ways.

---

## O8 — The 60-character limit is cargo
**Severity: low. Disposition: accept — drop it.**

§5.4 takes 60 characters from Wispr Flow with the reasoning "no reason to
differ". Wispr Flow syncs to iOS and has a mobile text field; this writes a
local TOML file. There is no constraint here to inherit.

**Disposition:** no key-length limit. If one is ever needed it starts permissive
and tightens on evidence, like every other threshold in this project.

---

## O9 — "They fail in different places" is unexamined
**Severity: medium. Disposition: accept — the spec must say where.**

§5.6's entire justification for two mechanisms is one sentence: *"Both. They
fail in different places."* The draft quotes it and never says where either one
fails. That sentence is load-bearing for the two-table design and it has never
been tested.

Now partially measurable: `[boost]` fails by collapsing an unrelated transcript
and by being unreliable per-term. `[replace]` fails by firing on a homonym and
by being invisible when it does.

**Disposition:** write the failure modes into the spec. If they turn out to
overlap, one table is right.

---

## O10 — The guard's denominator trusts the VAD
**Severity: low-medium. Disposition: note.**

Words per second of *retained* speech assumes trimming is correct. An
over-trimming VAD shrinks the denominator, inflates the rate, and the guard
never fires. `TrimResult.fell_back` is handled; partial over-trim is not, and is
not observable from inside the guard.

**Disposition:** record `retained_seconds` alongside the guard's verdict so a
false negative is diagnosable after the fact.

---

## O11 — V4 is last and is what makes V2 debuggable
**Severity: low. Disposition: consider resequencing.**

The slicing puts `manu vocab check` fourth. B5's longest-key-wins means entry
interactions are invisible from reading the file — and the tool that reveals
them arrives after users have been writing entries for two slices.

**Disposition:** either V4 moves up, or V2 ships with the fired-entry reporting
from O5, which covers the same need from the other direction.

---

## Summary

| # | Severity | Disposition |
|---|---|---|
| O1 | high | accept — `raw_transcript` column blocks V2, and Phase 5 needs it too |
| O2 | high | accept — n=1; measure all six before V3 |
| O3 | high | accept — explain the collapse before designing the guard |
| O4 | medium-high | reject B4; replacement is literal |
| O5 | medium-high | accept — record which entries fired |
| O6 | medium | accept — freeze the dictionary before the gate |
| O7 | medium | decide — two keys, one behaviour |
| O8 | low | accept — drop the character limit |
| O9 | medium | accept — state the failure modes |
| O10 | low-medium | note — record `retained_seconds` |
| O11 | low | consider — resequence V4 or fold O5 into V2 |

**Three of eleven are high and two of those attack the evidence rather than the
design.** The draft's measurements are real and thin: one sample for the
headline result, one observation for the hazard the whole plan now leads with.
