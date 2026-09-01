# Phase 3 gate — post-processing, the dictionary, and retention

**Date:** 2026-09-01
**Branch:** built on `phase-3-postprocessing` (PR #9, merged 2026-08-08); the
gate run and the harness corrections below are uncommitted on `main` at
`76a9e15` and need a branch before they land.
**Hardware:** Apple M3 Max, 14 cores (10 performance / 4 efficiency), 36 GB, macOS 27.0
**Interpreter:** CPython 3.14.5
**Tier on this machine: A** (recorded at the Phase 1 gate)

**Verdict: PASS**, with G2 missed and stated rather than moved.

Edit rate **8.59%** against G2's 5%. The gate does not reject, because §9's
clause turns on *what kind* of correction dominates and **163 of 171 edits are
decoder-side**: sentence marks Whisper never emitted, capitals it emitted at its
own segment starts, and mistranscription. The rules chain missed **8**. The
frozen dictionary missed **0** of its covered terms.

The phase's own components met every claim they make. What the corpus is full of
is a class no rule in this phase addresses, and the measurement below shows it
is not reachable by one.

**The gate was run twice.** The first corpus, recorded 2026-08-18, was decoded
under an `initial_prompt` that was removed from `config.toml` at 15:41 the same
afternoon — eight minutes and thirty-nine seconds after the last take. Its
headline number described a configuration the product no longer ships, and one
of its ten takes had lost 21.7 seconds of speech to that bias. It was
re-recorded on 2026-09-01. Both runs are reported.

---

## What the gate asked

PRD §9, Phase 3:

> **Gate:** Ten real dictations of ≥ 60 seconds. Report edit rate — what
> fraction of output needed manual correction, and what kind. This is also the
> phase that takes **the real G1 number**.
>
> **Rejects if:** edit rate exceeds the G2 threshold **and** the corrections are
> dominated by classes the rules chain should have caught (punctuation,
> capitalisation, spoken commands) **or by proper nouns for terms present in the
> frozen `vocabulary.toml`**; or `postprocess_ms` p95 exceeds 5 ms; or
> `vocab_ms` p95 exceeds 10 ms.

Plus, from the same section: `vocabulary.toml` frozen before the first dictation
and recorded by SHA-256 and entry count; at least one `[replace]` entry firing
across the set; `store_audio = true`; `coverage` and `retained_seconds` recorded
for every dictation whether the guard fired or not; and a second set of ten
dictations under five seconds for §5.7's untested false-positive direction.

## What was measured

Ten dictations, 67.3–97.4 s, one speaker, 2026-09-01 19:45–20:05, through the
hotkey into a live daemon. Scored from `history.db` by `scripts/gate_phase3.py`
against corrections written by the operator against the stored audio.

    dictations >= 60s : 10
    vocabulary        : 8 entries  sha256 69dd44fb5035231a5bda82e92fd65adb…
    chain             : ['rules', 'vocabulary']

    edit rate         : 8.59% (171 edits / 1991 words)
      chain_terminal          0
      chain_capital           8
      chain_spacing           0
      vocabulary              0
      decoder_segmentation   58
      decoder_capital        41
      decoder_words          64

### The two latency ceilings — both met, by an order of magnitude

| | measured p50 | measured p95 | ceiling |
|---|---|---|---|
| `postprocess_ms` | 0.333 ms | **0.478 ms** | 5 ms |
| `vocab_ms` | 0.087 ms | **0.171 ms** | 10 ms |

`postprocess_ms` is no longer structurally zero, which was the Phase 2b
condition this phase existed to clear.

### Latency at length — not G1, and reported so

| | p50 | p95 |
|---|---|---|
| `transcribe_ms` | 938.7 ms | 1119.9 ms |
| `g1_ms` computed | 1104.9 ms | 1322.4 ms |

**These are not G1.** §2 binds G1 at a ten-second utterance; these takes are
67–97 s. They are §7.1's revisit trigger, not the gated number, and the gate
record does not claim otherwise. G1 at its own definition was last measured at
the Phase 2b gate (p50 223.0 / p95 270.0, chain empty); with a `postprocess_ms`
p95 of 0.478 ms the chain cannot have moved it more than half a millisecond.
**Taking G1 at 10 s with the full chain is deferred to Phase 4** — see below.

### The guard, every dictation

Ten of ten `passed`. Nine at coverage 100.0%, one at **99.9%** — the only
unclamped reading in this corpus, and the first evidence that the instrument has
any resolution at all.

### The short set — recorded, and it measures less than it appears to

Eleven dictations of 1.02–2.56 s, all `passed` at coverage 1.0. Zero false
positives: §5.7's stated direction is clean.

**That result is arithmetic, not calibration.** Replaying each clip through the
product's own VAD, engine and `guard.evaluate`:

- `speech_pad_ms = 400` subtracts 0.80 s from every single-segment clip, so a
  1.02 s dictation is judged against a **0.22 s** denominator.
- `decoded_seconds` came back **2.00 s on all eleven**. Slicing one long take
  proves it is a floor, not a measurement: 0.50 s → 1.00, 1.00 s → 2.00,
  2.00 s → 2.00, 5.00 s → 4.92, 10.00 s → 9.64. Whole-second quantisation
  below ~3 s.
- The unclamped ratio ran 1.24–8.93. `_by_coverage` clamps at 1.0.

`min_decoded_coverage = 0.5` therefore requires **speech > 2.00 s** before the
refusal gate is reachable at all. The longest speech span in the short set is
1.62 s. **The refusal gate was unreachable on 11 of 11.** Only a decode to
literally nothing (0.00 s, observed at a 0.30 s slice) is caught; a partial
collapse reports ≥ 1.00 s and passes.

Controls: a synthetic 0.05 s span is refused 11/11, so the arithmetic can fail.
An attempt to manufacture a real collapse with §5.7's documented trigger
(`initial_prompt = "And how much is this?"`) collapsed **0 of 11** — prompt echo
is a long-clip phenomenon. No true positive could be produced at short length,
which is the honest limit of this measurement.

## What was built

`RuleBasedPostProcessor` ported from `experiments/scripts/exp4_rules_only.py`;
the chain registry and `TracedPostProcessor`; `vocabulary.toml` with `[replace]`
as one compiled alternation and `[boost]` scoped per bundle identifier; `manu
vocab check`; history retention — `retain_days` against `history.db`, WAL,
purge, `manu history` with `--pending`, `--raw`, `--last`, `--purge`;
`scripts/gate_phase3.py`, `scripts/measure_long_audio.py`,
`scripts/record_phase3_corpus.py`. Three defects in previously shipped code
found by reviewing the spec rather than the code (objections O1/O2/O3).

## Deferred, by design

- **G1 at ten seconds with the full chain.** §9 assigns "the real G1 number" to
  this gate, and this corpus cannot supply it: every take is 67–97 s by the
  gate's own ≥ 60 s requirement, and G1 is defined at 10 s. The two requirements
  are not jointly satisfiable by one corpus. **Amend §9** — see finding 4.
- **The 27 missing commas.** Outside every mechanism this phase ships and
  outside the segment-boundary hypothesis tested below.
- **`spoken_commands`** stays `false`. It reported as a candidate rather than
  firing, per choice-story #2, so its rate is measured at zero lossiness.

---

## What this phase revealed that the PRD got wrong

### 1. Coverage cannot see an interior loss — **amend §5.7**

Take `a605e8a3a7e1` of the 2026-08-18 corpus persisted 197 words. Replaying the
same stored audio unbiased yields **249**, deterministic across five runs; the
operator's correction is 250. The loss is one contiguous block — 56 words
spanning **27.70 s → 49.40 s**, replaced by the single word "microfiber".

The guard recorded **coverage 100.0%, `passed`**.

`decoded_seconds = max(segment.end)` (`faster_whisper.py:329`). Coverage
measures **where decoding stopped, not how much came back**. The final segment
still ended at 79.90 s against 79.89 s of retained speech, so a hole in the
middle is invisible to the ratio by construction. §5.7 was designed against
early termination — the prompt-echo collapse truncates the *end* — and its text
should say that it does not cover interior loss.

`avg_logprob`, `no_speech_prob` and `compression_ratio` cross the engine
boundary and are discarded at the same line. That is where a fix starts. It is
not a one-line change and it is not proposed here.

### 2. The guard is blind below two seconds of speech — **amend §5.7**

Detailed above. §5.7 already records a short-utterance blind spot for the
*fallback* rate instrument, and states that the coverage instrument is
"duration-independent" with "no false-positive population". The first half is
wrong: coverage's numerator quantises to whole seconds below ~3 s and floors at
1.00 s, and its denominator has 0.80 s of padding removed. The second half is
true for the reason that makes the first half matter — it cannot produce a false
positive because at these lengths it cannot produce a positive.

### 3. Prompt length spends the transcript's budget — **already amended, recorded here**

`config.toml` disabled `initial_prompt` on 2026-08-18 at 15:41 with its
reasoning inline. This gate supplies the missing consequence: the ten takes
recorded that afternoon were all decoded under the bias, and replaying them
unbiased recovers **108 words** the live runs never had — 52 on one take, 21 on
another, 12 each on two more. Candidate prompts reproduce the live run's
hallucinated "microfiber"; the unbiased replay never does, 5/5. The int16 round
trip in the stored audio is held constant across both arms, so it cannot explain
the difference.

Removing the prompt also cut the tail: `transcribe_ms` p95 **4018 ms → 1120 ms**
on the same corpus shape, and computed `g1_ms` p95 **4204 ms → 1322 ms**.

### 4. §9 asks this gate for a number its own corpus cannot contain — **amend §9**

"Ten real dictations of ≥ 60 seconds" and "the real G1 number" are in the same
paragraph, and G1 is defined at ten seconds. No corpus satisfies both. The
requirement should move to Phase 4, or the gate should require a second
ten-second set. Same species as the Phase 2a gate requiring a Phase 4 tray and
the Phase 2b gate requiring a Phase 3 chain: a gate condition that cannot be
met by the phase that carries it.

### 5. The reject clause could not distinguish a rules miss from a decoder miss — **instrument, fixed**

`classify_edits` bucketed by the *shape* of a difference: anything equal modulo
case and punctuation was "punctuation" or "capitalisation". §9's clause is about
*responsibility* — "classes the rules chain should have caught". On this corpus
the surface split called **107 of 171** edits punctuation/capitalisation and
fired the reject clause. The responsibility split puts **8** inside the chain.
Same corrections file, opposite verdict.

The classifier now buckets by what `rules.py` can actually do — append the
utterance's final mark, capitalise after a mark already present, fix spacing
around a mark — against what it cannot: insert an interior break, insert a
comma, lowercase anything, join words. Nine controls: four positive, five
negative. Two misattributions were found by running it, not by reading it:

- A span-level rule charged **word-joining** to the chain — `off boarded →
  offboarded`, `code base. → codebase.`, `a K a → AKA`. Nine edits,
  `normalise_punctuation_spacing` can do none of it. Removed.
- Real spacing was **invisible**: `wait , then` splits into a token that bares to
  the empty string, so the aligner deleted it and never reported the mark that
  moved. `_merge_floating` now attaches free-standing marks before alignment.

Verified by sabotage. Charging interior breaks to `chain_terminal` fails two
controls. Charging every capital fix to `chain_capital` **passed at first** — the
down-casing control could not see it — and fails only since an up-casing control
was added. That is the argument for negative controls stated as an event rather
than a principle.

### 6. A stale corrections file was a guaranteed pass — **instrument, fixed**

Running the August corrections against the September takes reported **0 edits /
0 words, PASS**. Every id missed, `entry is None: continue`, silence. The gate
now rejects when any dictation has no entry. Eighth instance in this repository
of a check that could not fail.

### 7. `fired_any` was satisfied by the rules pass — **instrument, fixed**

The "at least one `[replace]` entry fired" check tested `fired_entries` for *any*
content, and `collapse_whitespace` fires on nearly every utterance. On the short
set it was the only entry present on 10 of 11. Now discriminates on the
`replace:` prefix `VocabularyPostProcessor` writes. Verified by sabotage:
stripping the dictionary labels from a copy of the database makes the patched
check reject where the committed one passed.

---

## The dominant error class, and whether a rule can reach it

58 sentence marks the operator added and 41 capitals he removed — **99 of 171
edits**, and the two he named unprompted as the significant defect.

**One root cause.** Whisper capitalises the first word of each of its own
segments and supplies no mark at the end of them, and `_decode` joins the
segment texts while discarding the boundaries. Against a control of 17% (all
unchanged words near a boundary): **70%** of the added marks land on a segment
end, **46%** of the stray capitals on a segment start.

**The obvious rule was measured and rejected.** Insert "." at each segment join
whose preceding segment ends on an alphanumeric character — the predicate
`ensure_terminal_punctuation` already uses — then let the chain run:

| | |
|---|---|
| insertions made | 95 |
| matched a mark the operator added | **29** |
| invented, mid-sentence | **66** |
| knock-on capitals the operator wanted | 33 |
| knock-on capitals he did not | **58** |
| edit rate | 9.59% → **12.35%** (+55 edits) |

2.3 invented periods per correct one, and a false period manufactures a false
capital exactly as predicted: `decoder_capital` 38 → 63 while `chain_capital`
improves only 9 → 6.

**The 70% figure was the wrong direction and nearly sized the rule.** It is
recall — of the marks the operator added, how many sat on a boundary. The rule
runs on boundaries, of which there are 95, and only **31%** want a mark. Sizing
a rule on recall when it is priced on precision is recorded here because it was
caught by measuring rather than by reasoning.

**It is not the operator's delivery.** Speech rate against the two classes,
per take: slower half 2.37 w/s and 4.9 errors per 100 words; faster half
2.82 w/s and **4.4**. No trend, and the cleanest take (0.0 per 100 words) sits
mid-range at 161 wpm. The corpus spans 124–194 wpm, which is ordinary
conversational pace.

**Model size fixes half of half of it, at a cost G1 cannot pay.** All three
models decoded from the local cache, scored on the same corrections:

| model | edit rate | missing marks | stray capitals | p50 | p95 |
|---|---|---|---|---|---|
| `tiny.en` (shipped) | 9.59% | 84 | 38 | 932 ms | 1109 ms |
| `base.en` | 10.04% | 90 | 43 | 1526 ms | 1954 ms |
| `small.en` | **7.88%** | **55** | 40 | 3950 ms | 5311 ms |

`small.en` removes a third of the missing marks and **does nothing for the
capitals** — 38 → 40 — at 4.2× the decode cost. Phase 1 measured `small.en` at
1438 ms on a ten-second clip against a G1 p95 of 800 ms, so this is not a trade
that is available. `base.en` is worse than shipped on both classes *and* slower.

**Conclusion.** Interior sentence structure is not reachable by a rule keyed on
anything the decoder currently emits, and is not bought by a larger model within
G1. §9 asks whether Phase 5 has subject matter. It does, and this is the
measurement that says so — a negative with numbers attached rather than an
absence of evidence, which is what left Phase 5 `UNRESOLVED, corpus-blocked`
before.

---

## Gate decision

**PASS.** The reject clause does not fire: 8 chain-attributable edits and 0
covered-vocabulary misses against 163 decoder-side, both latency ceilings met by
an order of magnitude, the dictionary frozen and firing, the guard reporting on
every dictation, `store_audio` on, and the short set recorded.

**G2 is missed at 8.59% and is neither confirmed nor moved by this record.** §9
says moving the threshold is a legitimate outcome and that moving it without
stating the reason is not. The reason is now measurable — 95% of the gap is
decoder-side and 58% of *that* is one unreachable class — but choosing the
number is the operator's, and the gate prints a NOTE rather than deciding it.

**Two open items carried out of this phase:**

1. **§5.7's guard has two blind spots**, both established here with controls:
   interior loss, and anything under two seconds of speech. Neither is fixed.
2. **G1 has not been taken at ten seconds with the full chain.** Deferred to
   Phase 4 per finding 4.
3. **The model may be the binding constraint, not the chain.** `small.en`
   reaches **7.88%** — the lowest edit rate this project has measured on real
   dictation — and is unreachable only because of G1's p95. `base.en` is
   eliminated outright, worse on accuracy and slower. No size fixes the
   capitals. **Revisit at the Phase 4 gate**, where the per-tier latency table
   is published and the accuracy claim beside it becomes user-facing; Moonshine
   and Parakeet are both named in §7.2 and neither has been benchmarked for
   punctuation. Recorded in §7.2 with a dated revision note.

## Rollback

Nothing in `src/` changed during this gate. The instrument fixes are confined to
`scripts/gate_phase3.py`; reverting that file restores the surface-form
classifier and its verdict of REJECT on the same corrections file. The 2026-08-18
corpus remains in `history.db` with its audio and is displaced from the gate only
by `gate_rows`' most-recent-ten rule.
