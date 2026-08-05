# Dictionary — feature scope (revision 2, post-review)

**Status:** reviewed and revised. Ready for a phase decision; not scheduled, not built.
**Date:** 2026-08-03
**Supersedes:** revision 1, same date, which is wrong in three places recorded below.
**Review:** `docs/superpowers/objections/dictionary.md` (11 objections),
`docs/superpowers/slices/dictionary.md` (4 slices).
**Folds into:** PRD §5.6, which specifies two mechanisms and neither a format nor a surface.

---

## 0. What the review changed

Revision 1 was attacked, and three of its claims did not survive contact with a
measurement. They are recorded here rather than quietly corrected, because two
of them were things I told the operator with more confidence than they deserved.

| Revision 1 said | Measured | Effect |
|---|---|---|
| `[boost]` is a clean win — 4/10 → 9/10 proper nouns | **True on one sample; net macro WER improvement is 1.1 points, and it makes two of six samples measurably worse** | V3 is a trade, not a win. Reshapes the slice. |
| B9: the raw transcript is persisted, so a bad rule is recoverable | **False.** `to_history_row()` stores `final_text or raw_transcript` — one column. The raw is lost the moment post-processing runs | Blocks V2. Needs a schema change Phase 5 also needs. |
| The collapse is domain mismatch | **False.** The prose prompt *matched* the domain of the only clip that collapsed | O3 open. The guard's shape is provisional. |

---

## 1. Why this exists

Three failures in one dictation session on 2026-08-03, all on one word:
`breadchute`, `breadshoe`, `spread sheet`, and `CSP` for CSV. The second
utterance produced **both** a correct split form and a wrong form in one
sentence — the model is not deaf to the word, it is inconsistent about it.

The operator asked whether a bigger model or fine-tuning would fix this rather
than patching over it. Measured on the real Phase 1 corpus:

| | p50 | p95 | vs G1 400/800 | proper nouns missed (of 10) |
|---|---|---|---|---|
| `tiny.en` | 271.0 | 389.4 | **PASS** | 5 |
| `base.en` | 486.1 | 1047.8 | **MISS** | 4 |

Double the parameters bought **one proper noun in five** and missed G1's p95 by
248 ms. `beam_size` was the other candidate lever and is worse: beam 5 costs
2.5× the latency for 1.6 WER points, and beam 3 is *worse* than greedy.

**The claim this feature rests on:** for proper nouns and domain jargon there is
no model-size fix available inside G1. §5.6 asserts this in one line; it is now
measured. A dictionary is not a patch over a fixable deficiency — it is the only
mechanism that addresses this class of word at all.

## 2. Prior art — Wispr Flow

PRD §1 names Wispr Flow as the comparison
([docs](https://docs.wisprflow.ai/articles/4052411709-teach-flow-your-words-with-the-dictionary)):
words and phrases up to 60 characters, two mechanisms (word boosting and
explicit misspelling→correct replacement), one replacement per key,
auto-learning from corrections filtered to distinctive words, bulk import,
cross-device sync.

**Three of these are non-goals here and the spec says so rather than omitting
them.** Sync is PRD §3 and §1. Auto-learning requires reading other
applications' text after injection — the capability `scripts/gate_2a_inject.py`
needs a separate dependency for and which §7.6 keeps out of the product. The
60-character limit is inherited from a product with a mobile text field; this
writes a local TOML file and has nothing to inherit (O8).

## 3. What §5.6 already says

> Users have proper nouns the model will never get right. Two mechanisms:
> 1. `initial_prompt` passed to the ASR engine — cheap, works today, limited length.
> 2. A post-processing replacement map (`vocabulary.toml` …) applying
>    case-insensitive whole-word substitutions.
>
> Both. They fail in different places.

Eight lines. No format, no surface, no ordering, no failure behaviour. Mechanism
1 is built and wired (`faster_whisper.py:292`). Mechanism 2 is a named Phase 3
deliverable with no specification behind it. **This document is that
specification.**

## 4. What §5.6 gets wrong, from real data

**"Whole-word substitutions" cannot fix the observed failure.** `spread sheet →
spreadsheet` is two tokens becoming one. A whole-word map matches `breadshoe`
and misses `spread sheet` entirely — and `spread sheet` is the *more* likely
error, because it is what the model produces when it half-hears the word. **The
map must match phrases.**

**"They fail in different places" is load-bearing and was never examined** (O9).
Now partly measurable, and the answer is not flattering to the two-table design:

- `[boost]` fails by **degrading unrelated speech** (+3.2 and +5.2 WER on two of
  six samples) and by collapsing a transcript entirely on one.
- `[replace]` fails by firing on a homonym, invisibly.

## 5. Scope

### 5.1 The file

`vocabulary.toml`, beside `config.toml` in the `platformdirs` config directory.

```toml
[boost]
terms = ["Airtable", "Firestore", "XLSX", "OAuth", "CDE", "Alma SIS"]

[replace]
"breadshoe"    = "spreadsheet"
"breadchute"   = "spreadsheet"
"spread sheet" = "spreadsheet"   # phrase, not a word — see §4
"CSP"          = "CSV"
```

Two tables because the two mechanisms fail in different places and a user needs
to know which one they are reaching for. `[boost]` is probabilistic, global, and
**can make unrelated dictation worse**. `[replace]` is deterministic and local.

### 5.2 Behaviour

**B1 — `[boost]` terms append to `[engine] initial_prompt`, prose first.** See
O7: this is one behaviour with two config keys and the ambiguity is real.
Resolved by making `[boost]` authoritative and documenting `initial_prompt` as
prose framing only.

**B2 — `[replace]` runs in the §5.3 chain after `RuleBasedPostProcessor`**,
because the rules pass changes capitalisation and punctuation and would
otherwise rewrite the map's output.

**B3 — Matching is case-insensitive, whole-token, phrase-aware.** `breadshoe`
matches `Breadshoe` and `breadshoe.`; not `breadshoes`, not `abreadshoe`.
Multi-word keys match across whitespace runs.

**B4 — Replacement is literal.** ~~Casing is preserved from what was matched.~~
**Rejected in review (O4).** §7.3's Phase 2a finding is that silent heuristic
rewriting of the user's words is the hazard — measured, from macOS text
substitution, and documented as unacceptable. A casing heuristic is that hazard
re-committed by the one mechanism whose selling point is determinism. What the
user writes on the right-hand side is what lands.

**B5 — Longest key wins**, and the shorter does not re-fire inside the match.

**B6 — One replacement per key.** Two rules for one key have no precedence a
user could predict.

**B7 — Replacements do not cascade.** `a → b`, `b → c` yields `b`. Cascading
makes order significant, cycles possible, and the result unreadable from the
file.

**B8 — A malformed file is an error at load, naming the key.** Same contract as
`config.py`. A missing file is not an error.

**B9 — The raw transcript is persisted alongside the final text.** **This does
not work today (O1)** and is the precondition for the whole `[replace]` half.
`to_history_row()` emits one transcript, `history.db` has one column, and the
raw output is lost the moment `final_text` is set. §7.5's four Phase 5
constraints open with "raw transcript persisted" — the same guard, for the same
class of hazard, specified for the LLM and unimplementable in the schema.

**B10 — The session records which entries fired** (O5). A rule firing wrongly
presents as an ASR error, which is the one explanation that sends the user to
the wrong fix.

**B11 — A transcript implausibly short for the speech that produced it is
flagged.** See §5.3.

### 5.3 The collapse guard

`initial_prompt` can silently destroy a transcript. Measured: a prose prompt
collapsed a 25-second clip to `"And how much is this?"` — 5 words against a
47-word reference, **deterministically, 5 runs of 5**.

| | words / second of retained speech |
|---|---|
| Corpus, slowest genuine sample | 2.18 |
| Corpus, fastest | 3.33 |
| **The collapse** | **0.20** |

**10.8× below the slowest real sample.** A floor between 25% and 50% of the
slowest observed catches it and flags zero real samples. Starts permissive at
0.5 w/s and tightens on evidence.

Operates on trimmed audio, so the denominator is speech by construction. Must
not fire when `TrimResult.fell_back` is set.

**Open, and it blocks the guard's design (O3).** The collapse hit exactly one of
six samples and the trigger is **not** domain mismatch — the prose prompt
matched that clip's subject. Until the mechanism is understood, a words-per-second
*floor* is a guard against the symptom, and the opposite failure — a
hallucinated expansion, plausible and wrong — is invisible to it. §7.5 carries a
no-invent check for exactly that direction.

### 5.4 Limits

| | value | why |
|---|---|---|
| Key length | **none** | O8 — the 60-char limit was cargo from a product with a mobile keyboard |
| `[replace]` entries | **no cap; the implementation is constrained instead** | Measured: 0.21 ms p95 at 500 entries, 18.4 ms at 5000 on a 60 s transcript. Latency does not constrain this feature |
| Implementation | one compiled alternation, not a loop of `re.sub` | **70× at 1000 entries** — 0.35 ms vs 12.01 ms p50. This is the real constraint |
| `[boost]` terms | ≤ 100, truncated with a warning | The prompt window is finite and silently drops overflow |

### 5.5 Non-goals

No sync. No account. No bulk vendor import. No regex — a user debugging a regex
against their own speech is worse off than one adding three literal entries. No
per-application dictionaries. No auto-learning (§2).

## 6. Surface

`manu vocab check "<text>"` — shows which entries would fire.

**Nothing else.** `add`, `list` and `boost` are rejected: §6.1 treats the verb
set as the process model's public contract, and they are a second way to do what
a text editor already does. The file is the interface, which is the point.

## 7. Slices

Full reasoning in `docs/superpowers/slices/dictionary.md`.

| | | depends on |
|---|---|---|
| ~~**V1**~~ | ~~the collapse guard~~ | **shipped 2026-08-05 — no longer this feature's** |
| **V0** | `raw_transcript` column + migration (O1) | — |
| **V2** | `[replace]` map, B3–B8, B10 | V0 |
| **V3** | `[boost]` list, scoped per application | V0 |
| **V4** | `manu vocab check` | V2 |

**V1 left this feature and that was the right reading of its own argument.** The
slice was justified as *"first, and not because of the dictionary"* — and a
slice that is not about the feature is not a slice of the feature. It is built
as a **Phase 2b follow-up defect fix**, specified at PRD §5.7.

What settled it was not the argument. On 2026-08-05 a 30.5-second dictation on
the operator's machine returned two words at **0.066 w/s**, three times worse
than the collapse measured here, with `initial_prompt` live and no dictionary in
existence. This document predicted the hazard was already in production. It was.

**V3 no longer depends on a slice of this feature**, but it still must not ship
without the guard, which is now a precondition met outside the plan rather than
inside it.

**V3 is now doubtful and that is the review's most consequential finding.** The
boost list improves macro WER by **1.1 points** while making two of six samples
**worse** — a trade, not a win. It should not ship as a global always-on prompt
without either a mechanism that scopes it to relevant utterances, or evidence
from more than one speaker that the trade is favourable in practice.

## 8. Open questions

- **O3 — what is the collapse?** Reproducible, total, one clip in six, not
  domain mismatch. The guard's shape depends on the answer.
- **V3's trade — is +1.1 macro WER worth degrading unrelated dictation?** One
  speaker, six samples. Needs the Phase 3 dictation set before it is decided.
- **O6 — the Phase 3 gate is gameable.** The dictionary reduces edit rate by
  construction. It must be frozen before the gate dictations are recorded, and
  the gate record must say when it was last edited.
- **O7 — `[boost]` and `initial_prompt` are two keys for one behaviour.**
  Resolved above by making `[boost]` authoritative; the deprecation needs
  writing into §5.3.
- **O10 — the guard trusts the VAD.** Over-trimming inflates the rate and the
  guard never fires. Record `retained_seconds` with the verdict.
