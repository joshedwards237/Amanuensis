# Experiment 1 — Constrained decoding (subsequence-restricted output)

**Date:** 2026-07-31
**Hardware:** Apple M3 Max, 36 GB, macOS 27.0
**Model:** `mlx-community/Llama-3.2-3B-Instruct-4bit` (MLX 0.32.0, mlx-lm 0.31.3)
**Script:** `experiments/scripts/exp1_constrained_decoding.py`
**Input:** `experiments/asr-baseline.json`, unmodified (six `tiny.en` + VAD transcripts)

**Verdict: FAIL.** Insertion was structurally eliminated — INVENT is 0 across all six
samples, empirically verified, not asserted. But mean WER still rose from **19.33% to
34.58%**, and end-to-end p50 lands at **908 ms** against a 700 ms budget. The constraint
removed one failure mode and made a second one worse.

---

## What was implemented, and why this shape

A **subsequence automaton** wrapped around greedy MLX decoding. The raw ASR text is
tokenised once into `src` (N token ids). Decoding carries a pointer `i` into `src`. At
each step the permitted token set is `{src[j] : j >= i} ∪ {eos}`; logits are gathered
down to those candidates and argmax is taken over that set; emitting token `t` advances
`i` to `(first j >= i where src[j] == t) + 1`. Greedy leftmost matching is complete for
subsequence recognition, so the accepted language is exactly the subsequences of `src`.

Three deliberate choices:

- **Same model as the failed run.** The feasibility record measured
  `Llama-3.2-3B-Instruct-4bit`; using anything else would change two variables at once
  and make "the constraint caused this" unprovable. A smaller model was available and
  tempting given the collapsed search space — that is a separate experiment, not this one.
- **A hand-rolled decode loop rather than `mlx_lm.generate`'s `logits_processors`.**
  The constraint is stateful and needs the *chosen* token to advance its pointer; owning
  the loop keeps the pointer and the mask in one object where the invariant is checkable.
- **Gather-then-argmax rather than a full-vocabulary mask.** Candidate sets are ≤ N ids
  (~70), not 128k. This is why per-token cost stays low despite a Python-level constraint
  in the hot loop.

Greedy, `temp=0`, same as the feasibility run. Max tokens is not a parameter: a
subsequence cannot exceed its source, so `N+1` is a structural bound.

---

## 1. WER before → after

| Sample | before (measured) | fixture `raw_wer` | after | Δ |
|---|---|---|---|---|
| 01-natural | 3.33% | 3.33% | 5.00% | +1.67 |
| 02-code | **17.24%** | **18.97%** ⚠️ | 62.07% | +44.83 |
| 03-proper-nouns | 31.91% | 31.91% | 34.04% | +2.13 |
| 04-fast | 2.04% | 2.04% | 2.04% | 0.00 |
| 05-noisy | 18.60% | 18.60% | 18.60% | 0.00 |
| 06-short | 42.86% | 42.86% | 85.71% | +42.86 |
| **mean** | **19.33%** | 19.62% | **34.58%** | **+15.25** |

⚠️ **Disagreement with the fixture on `02-code`, flagged as instructed.** I measure
17.24% (10 errors / 58 reference words); the fixture records 18.97% (11 / 58). I computed
it two independent ways — `jiwer` and a hand-written Levenshtein — over the same
`normalise()` from `scripts/bench_engines.py`, and both give 17.24%. The other five
samples match the fixture exactly. I report my own numbers throughout; the mean I use is
19.33%, not the fixture's 19.62%. One error's worth of disagreement on one sample does
not change any conclusion here, but the fixture field is the thing I'd trust less.

Two samples (`04-fast`, `05-noisy`) came back **byte-identical to the input** — the model
emitted the whole source and stopped. On those the pass is a pure no-op that costs 546–614 ms.

---

## 2. Latency

Model load and warm-up excluded, as required. One warm-up inference discarded before timing.

| Sample | ms | output/input tokens |
|---|---|---|
| 01-natural | 784 | 70 / 71 |
| 02-code | 432 | 31 / 67 |
| 03-proper-nouns | 755 | 64 / 68 |
| 04-fast | 614 | 53 / 53 |
| 05-noisy | 546 | 46 / 46 |
| 06-short | 158 | 6 / 9 |

| | ms |
|---|---|
| **p50 (cleanup alone)** | **580** |
| **p95 (cleanup alone)** | **784** |
| mean | 548 |
| model load (weights cached) | 1,561 |
| warm-up inference (discarded) | 1,229 |

The p95 here is the max of six samples; with n=6 that is what "p95" can mean, and it
should be read as a floor rather than an estimate.

**Latency is well-behaved, which is the one clear win.** The unconstrained run measured
373–2,201 ms end-to-end because the model generated *more* text than it was given.
Output length is now bounded by input length by construction, so the tail is gone: the
spread is 158–784 ms and it tracks input length almost linearly.

---

## 3. Safety violations

| Sample | INVENT | content words in→out | SHRINK % | verdict |
|---|---|---|---|---|
| 01-natural | **0** | 33 → 32 | 3.0% | pass |
| 02-code | **0** | 42 → 20 | **52.4%** | **SHRINK** |
| 03-proper-nouns | **0** | 34 → 32 | 5.9% | pass |
| 04-fast | **0** | 29 → 29 | 0.0% | pass |
| 05-noisy | **0** | 21 → 21 | 0.0% | pass |
| 06-short | **0** | 3 → 2 | **33.3%** | **SHRINK** |
| **total** | **0** | | | 2/6 violate |

**INVENT = 0 was verified, not assumed.** Two independent checks: (a) the content-word
multiset of each output is a subset of the input's — zero words appear that were not
said; (b) the normalised *word* sequence of each output is a subsequence of the input's
word sequence, checked directly, true for all six.

That second check matters because the guarantee the automaton actually provides is
subsequence-of-*tokens*, not subsequence-of-*words*. BPE splits rare words across tokens
(`aminesis` → `amin` + `esis`), so dropping a leading subtoken while keeping a trailing
one could in principle emit a fragment that never appeared in the input. On this corpus
it did not fire once. The leak is real in theory and unobserved in practice at n=6; it
is not something to rely on being absent.

Compare to the unconstrained run, which produced INVENT on 3 of 6 samples including 93
invented words on `05-noisy`, a literal `"Here is the cleaned text:"` preamble, and an
outright refusal. **None of those are reachable under this constraint.** The chat
preamble is not merely unlikely — those tokens are not in the input, so no path exists.

---

## 4. Verdict against the budget

Phase 5's budget is **end-to-end p50 ≤ 700 ms** — that is how §7.5 and the feasibility
record apply it (`tiny.en 328 ms + Llama 390 ms = ~718 ms`, judged "marginally over").

| | p50 | p95 |
|---|---|---|
| cleanup alone | 580 ms | 784 ms |
| `tiny.en` + VAD (Phase 1 benchmark) | 328 ms | 420 ms |
| **end-to-end** | **908 ms** | **1,204 ms** |

**FAIL — 908 ms against a 700 ms budget, 30% over.**

Stated plainly for comparability: the *cleanup stage in isolation* is 580 ms, which
would PASS a 700 ms stage-level budget. It is not a stage-level budget. The whole
pipeline misses.

For context, this is a large improvement on the unconstrained run's 373–2,201 ms — it
misses the budget by 30% rather than by 3×. It still misses.

---

## What this reveals that the feasibility record got wrong

### 1. The diagnosis was right and the remedy does not follow from it

The record's diagnosis — "a *generator* being asked to perform a *deletion*, and nothing
in its architecture constrains it to that" — is confirmed. Constrain the architecture and
every insertion failure disappears, exactly as predicted.

But the record listed four failure modes: preamble leak, hallucination, refusal, **and
content deletion**. Constraining to subsequences kills the first three and leaves the
fourth entirely unbounded. Deletion was 1 of 4 problems; it is now 1 of 1, and it got
*worse*, not better. The record proposed subsequence-restriction as the fix for the
diagnosis without noticing that its own failure list included a mode the fix cannot touch.

### 2. The automaton hands the model a free "skip to the end" move — this is the mechanism

Both catastrophic samples failed the same way, and it is not premature EOS. Traced:

```
02-code    emit '.'  pointer 30 → 67   SKIPPED 36 tokens:
           " Then run py test dash clv equals src and check that the coverage
            stays above 80%. If the cij job fails, look at the github actions
            log before you push again"

06-short   emit '.'  pointer  5 →  9   SKIPPED 3 tokens: " and copy me"
```

In both cases the model emitted a single `.` intending to end a sentence. Leftmost
matching found the *final* period of the transcript and advanced the pointer over
everything in between. The pointer then sat at the end of the input, so EOS was legal and
the model took it — `stopped_early` is `False` on both. The model never chose to truncate;
the constraint executed a 36-token deletion on its behalf and reported it as valid.

This is not a bug in the implementation. Leftmost matching is the standard and correct
subsequence automaton. It is a property of the constraint class: **any token that recurs
later in the input — punctuation, `the`, `and` — is a legal jump of arbitrary length.**
The more common the token, the further the model can accidentally skip. Punctuation is
the worst case and it is exactly what a language model reaches for when it wants to end a
clause.

Any future attempt at this needs a *monotone bounded* constraint (advance by at most k, or
a per-position keep/delete decision) rather than a subsequence constraint. That is
Experiment 3's shape, and this result is an argument for it.

### 3. The 25% SHRINK floor is far too loose, and the record's read of it was too generous

The record concluded: *"The two samples that passed the checks were genuinely improved or
neutral."* Under constrained decoding that is false. Of the four samples passing both
checks:

- `04-fast`, `05-noisy` — identity. True no-ops, 546–614 ms for nothing.
- `01-natural` — deleted `somewhere` from "a server somewhere". 3.0% shrink. Passes. WER 3.33 → 5.00.
- `03-proper-nouns` — deleted `talent voice,` from the list "nerd dictation, talent voice,
  and whisper flow". 5.9% shrink. Passes. WER 31.91 → 34.04.

`03` is the one to look at. The model deleted an entire list item — a product name (Talon
Voice, misrecognised) that the speaker definitely said — and the safety net waved it
through because one item out of 34 content words is 3% of the transcript. **A 25% floor
cannot see the deletion of a single proper noun, and the deletion of a single proper noun
is precisely the "silently changes what you said" hazard the record named as
unacceptable.** The checks catch catastrophes. They do not catch the failure the record
was actually worried about.

### 4. WER against a verbatim reference cannot show this feature working — and this caps all four experiments

This is the finding with the widest blast radius, and it is not specific to Experiment 1.

A deletion-only system can only remove words. Every removed word that appears in the
reference becomes a deletion error. So the best WER any deletion-only method can reach on
this fixture is computable exactly — a DP where skipping a hypothesis word is free:

| Sample | raw WER | best possible, deletion-only | max gain |
|---|---|---|---|
| 01-natural | 3.33% | 3.33% | 0.00 pp |
| 02-code | 17.24% | 15.52% | 1.72 pp |
| 03-proper-nouns | 31.91% | 14.89% | 17.02 pp |
| 04-fast | 2.04% | 2.04% | 0.00 pp |
| 05-noisy | 18.60% | 16.28% | 2.33 pp |
| 06-short | 42.86% | 42.86% | 0.00 pp |
| **mean** | **19.33%** | **15.82%** | **3.51 pp** |

**A perfect oracle scores 15.82%.** On three of six samples the ceiling is zero — no
deletion can help at all. And the 17 pp available on `03-proper-nouns` comes from deleting
*misrecognitions* ("near" in "near nerd dictation"), not disfluencies — that is WER
gaming, not cleanup.

The reason is that the corpus was read from prepared scripts. The references are verbatim
and contain no fillers, no stutters, and no self-corrections. **The fixture does not
contain the phenomenon the feature exists to remove.** WER on it measures whether a
cleanup pass damages good transcription, which is worth knowing, but it cannot measure
whether the pass does its job.

The feasibility record already said this in "What is still unknown" — *"n=3 prompts, one
author… no accuracy measurement of the pass itself"* — but then reported an end-to-end WER
table as though it settled the question. It settles the safety question. It cannot settle
the quality question, and no amount of running the other three experiments on this fixture
will change that.

---

## Reproduce

```bash
python3 -m venv /tmp/venv-exp1
/tmp/venv-exp1/bin/pip install mlx mlx-lm jiwer
/tmp/venv-exp1/bin/python experiments/scripts/exp1_constrained_decoding.py
```

Deterministic: greedy decoding, `temp=0`, frozen fixture. Re-running reproduces the
tables above exactly apart from latency.

## What was not tried, on purpose

No prompt iteration, no second model, no beam search, no constrained-plus-fallback
hybrid, no tuning of the SHRINK threshold. The instruction was to measure the hypothesis
once and report. The hypothesis — *"restricting output to a subsequence of the input makes
insertion structurally impossible"* — is **true**. The implied conclusion, that this makes
the cleanup pass shippable, is **false**.
