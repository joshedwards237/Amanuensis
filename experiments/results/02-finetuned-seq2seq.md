# Experiment 2 — fine-tuned seq2seq disfluency removal

**Date:** 2026-07-31
**Hardware:** Apple M3 Max, 36 GB, macOS 27.0 (arm64)
**Software:** Python 3.14.5, torch 2.13.0, transformers 5.14.1, jiwer (isolated venv)
**Input:** `experiments/asr-baseline.json` — frozen, unmodified, 6 samples, `tiny.en` + VAD
**Script:** `experiments/scripts/exp2_finetuned_seq2seq.py`

**Hypothesis under test:** a seq2seq model fine-tuned specifically on disfluency
removal beats a general instruct model, because it was trained for the actual job.

**Answer: the hypothesis is confirmed on safety and refuted on usefulness.** The
fine-tuned model is dramatically better behaved than the 3B instruct model — it does
not hallucinate, does not emit chat preamble, does not refuse, and fits the latency
budget with room to spare. It also does not improve WER on a single sample. It makes
four of six slightly worse and leaves two unchanged.

---

## Checkpoint search — what exists, and what does not

Searched the HuggingFace model index (API, `search=` over: `disfluency`, `disfluen`,
`disfl`, `DISFL-QA`, `fluency`, `fluent`, `disfluency correction`, `disfluency removal`,
`transcript cleanup`, `speech cleanup`, `asr correction`, `asr post editing`,
`switchboard`, `bart disfluen`, and the same terms filtered to
`pipeline_tag=text2text-generation`).

**Finding: no maintained, widely-adopted public seq2seq disfluency-removal checkpoint
exists.** The task is well-studied and the datasets are public (Google's
`google-research-datasets/disfl_qa`, 206 downloads; Switchboard's disfluency
annotations), but the *models* on the Hub are all hobbyist artefacts. The
highest-download model in the entire disfluency space is
`stillerman/fdt-disfluency-distilbert-66m-v2` at 56 downloads — and that is token
classification, i.e. experiment 3's territory, not seq2seq. Every seq2seq candidate
below has fewer than 6 lifetime downloads, zero likes, and an auto-generated model card
that says "trained on an unknown dataset".

That absence is itself a result. It means this experiment tests *the shape of the
approach*, not a production-grade artefact, and no number here should be read as a
ceiling on what a properly fine-tuned model could do.

Four candidates were shortlisted and **all four were run**, because with checkpoints
this small the marginal cost of a fourth is minutes and a single obscure checkpoint is
not evidence about an approach:

| id | repo | base | disk | why shortlisted |
|---|---|---|---|---|
| `t5-small-disfluency-correction` | `vamshi0310/finetuned-disfluency-correction` | t5-small | 232 MB | card documents an explicit prefix and reports ChrF++ 99.26 |
| `t5-base-disfluent-cleaner` | `abdulbaseermohammedkhan/t5_disfluent_cleaner` | t5-base | 851 MB | best reported metrics of the set (exact-match 0.734, ROUGE-L 0.958) |
| `bart-base-disfl-qa` | `Galmieux/bart_disfl_qa` | BART-base | 537 MB | different architecture, trained on the canonical public dataset (DISFL-QA) |
| `t5-base-disfluent-fluent` | `EmnaBou/t5-base-disfluent-fluent` | t5-base | 1.7 GB | most-searched name in the space; reported BLEU 13.8 |

No model was fine-tuned. Decoding is greedy (`num_beams=1`, `do_sample=False`),
matching the feasibility record's `temp=0.0` baseline, `max_new_tokens=200`.

### Invocation was locked before the fixture was touched

None of the four recorded a custom task prefix in `task_specific_params` — all carry
stock t5 defaults — so the prefix had to come from the README or be empty. A prefix
probe (`--probe`) ran three **hand-written, non-corpus** sentences through each
checkpoint under four prefixes to confirm each was being invoked as its author
intended. The probe fixed one configuration per checkpoint and was not revisited. It
never touched the fixture; nothing here was tuned against the measurement set.

The probe was worth running. `t5-base-disfluent-cleaner` degenerates into an infinite
repetition loop under any non-empty prefix (`"I want to to go to the market: I want to
to go to the market: ..."` for 200 tokens) and is only coherent with `prefix=""`.
`t5-small-disfluency-correction` is prefix-insensitive — identical output under all
four. Had the prefix not been locked first, a repetition loop would have been reported
as a property of the approach rather than of the invocation.

---

## 1. WER before → after

Both ends computed here with the same normalisation — a port of
`scripts/bench_engines.py::normalise` (NFKC, lowercase, apostrophes stripped,
punctuation to space, no number normalisation). WER via `jiwer` over that token stream.

**Sanity check against the fixture passes.** Measured "before" matches the fixture's
`raw_wer` exactly on 5 of 6 samples. `02-code` differs (17.24% measured vs 18.97% in
the fixture, one error out of 58 words); the fixture's figure came from
bench_engines' hand-rolled Levenshtein and mine from `jiwer`, and the two disagree on
one alignment tie-break. Mean 19.33% measured vs 19.62% recorded. **The numbers below
use my own measurement on both ends**, so the before/after comparison is internally
consistent regardless.

### Primary — `vamshi0310/finetuned-disfluency-correction` (t5-small, CPU)

| Sample | WER before | WER after | Δ |
|---|---|---|---|
| 01-natural | 3.33% | 5.00% | **+1.67** |
| 02-code | 17.24% | 18.97% | **+1.73** |
| 03-proper-nouns | 31.91% | 34.04% | **+2.13** |
| 04-fast | 2.04% | 8.16% | **+6.12** |
| 05-noisy | 18.60% | 18.60% | 0.00 |
| 06-short | 42.86% | 42.86% | 0.00 |
| **mean** | **19.33%** | **21.27%** | **+1.94** |

Zero samples improved. Four degraded, two were passed through untouched.

### All four checkpoints

| Checkpoint | mean WER before | mean WER after | outcome |
|---|---|---|---|
| `t5-small-disfluency-correction` | 19.33% | **21.27%** | mild degradation, bounded |
| `t5-base-disfluent-cleaner` | 19.33% | **65.36%** | collapses to one sentence — behaves like a summariser |
| `bart-base-disfl-qa` | 19.33% | **71.56%** | rewrites statements into questions |
| `t5-base-disfluent-fluent` | 19.33% | **100.00%** | emits empty string (or `؟ ؟ ؟`) on every sample |

For context, the 3B instruct model in the feasibility record scored **110.0%** on this
same input. Three of four fine-tuned checkpoints beat it; the best beats it by 5×.

---

## 2. Latency

Model load excluded and reported separately. One warm-up inference (off-corpus)
discarded before timing. n=6, so p95 is effectively the maximum — a floor on the real
tail, not an estimate of it.

### Primary, CPU vs MPS

**MPS is 2.7× slower than CPU for this model.** Measured, not assumed, and it inverts
the verdict:

| device | load | p50 | p95 | min | max |
|---|---|---|---|---|---|
| **CPU** | 592 ms | **300.4 ms** | 379.5 ms | 54.0 ms | 380.0 ms |
| MPS | 994 ms | 804.0 ms | 1834.2 ms | 131.9 ms | 2042.3 ms |

For a 60M-parameter encoder-decoder decoding one token at a time, per-step
kernel-launch overhead dominates the arithmetic. The output is byte-identical on both
devices, so this is purely a device choice. **Run it on CPU.**

### Per-sample, CPU

| Sample | `t5-small-disfl-corr` | `t5-base-cleaner` | `bart-disfl-qa` | `t5-base-disfl-fluent` |
|---|---|---|---|---|
| 01-natural | 364.8 ms | 252.4 ms | 160.3 ms | 51.2 ms |
| 02-code | 377.9 ms | 287.6 ms | 402.7 ms | 45.3 ms |
| 03-proper-nouns | 380.0 ms | 392.3 ms | 165.8 ms | 45.9 ms |
| 04-fast | 235.9 ms | 395.6 ms | 83.9 ms | 46.1 ms |
| 05-noisy | 216.7 ms | 141.1 ms | 273.0 ms | 103.1 ms |
| 06-short | 54.0 ms | 145.5 ms | 81.0 ms | 1277.6 ms |
| **p50** | **300.4 ms** | 270.0 ms | 163.1 ms | 48.7 ms |
| **p95** | **379.5 ms** | 394.8 ms | 370.3 ms | 984.0 ms |
| load | 592 ms | 889 ms | 717 ms | 1043 ms |

Latency tracks output length, which is why the checkpoints that delete the most are
the fastest. Cheap is not a virtue when the mechanism is "emitted less of your text".

---

## 3. Safety violations

Same two checks as the feasibility record. `INVENT` = content words in output absent
from input (multiset, so repetition loops are visible). `SHRINK` = >25% of input
content words removed. Content word = normalised token not in a fixed closed-class
stopword list, defined explicitly in the script.

| Sample | `t5-small-disfl-corr` | `t5-base-cleaner` | `bart-disfl-qa` | `t5-base-disfl-fluent` |
|---|---|---|---|---|
| 01-natural | passed (0 / 0.0%) | SHRINK (76%) | SHRINK (76%) | SHRINK (100%) |
| 02-code | passed (0 / 7.3%) | SHRINK (78%) | INVENT (1) | SHRINK (100%) |
| 03-proper-nouns | passed (0 / 2.9%) | SHRINK (71%) | INVENT (2) + SHRINK (76%) | SHRINK (100%) |
| 04-fast | passed (0 / 3.3%) | SHRINK (47%) | INVENT (1) + SHRINK (90%) | SHRINK (100%) |
| 05-noisy | passed (0 / 0.0%) | SHRINK (76%) | passed (0 / 23.8%) | SHRINK (100%) |
| 06-short | passed (0 / 0.0%) | passed (0 / 0.0%) | INVENT (4) + SHRINK (100%) | SHRINK (100%) |
| **INVENT total** | **0 words, 0 samples** | 0 words, 0 samples | **8 words, 4 samples** | 0 words, 0 samples |
| **SHRINK violations** | **0 / 6** | 5 / 6 | 4 / 6 | 6 / 6 |
| **max shrink** | **7.3%** | 78% | 100% | 100% |

**The primary checkpoint has zero safety violations and a worst-case shrink of 7.3%.**
Compare the same checks on the 3B instruct model in the feasibility record: 4 of 6
samples flagged, including one 93-word hallucination. This is the hypothesis holding.
A model trained to delete deletes; a model trained to generate generates.

`bart-disfl-qa`'s inventions are the DISFL-QA failure mode in plain sight: trained on
disfluent *questions*, it turns `"So that's a Josh and copy me."` into `"What is a
Josh's last name?"` — 4 invented content words and 100% shrink from a 7-word input.

### The INVENT check is blind to function-word substitution

Worth flagging for the other three experiments, because it changes how their numbers
should be read. On `03-proper-nouns` the primary checkpoint rewrote
`"CT translate to under the hood"` → `"CT can be to under the hood"`. That is a
substitution — two words the input never contained — and `INVENT` did not fire,
because `can` and `be` are closed-class and excluded from content words.

Recomputed without the stopword filter:

| Checkpoint | INVENT (content words) | INVENT (all tokens) |
|---|---|---|
| `t5-small-disfluency-correction` | 0 | **2** (`can`, `be`) |
| `t5-base-disfluent-cleaner` | 0 | **3** (`that`, `for`, `me`) |
| `bart-base-disfl-qa` | 8 | 11 |
| `t5-base-disfluent-fluent` | 0 | 0 |

`t5-base-disfluent-fluent` scoring 0 on both is an artefact — it emitted nothing, so
it invented nothing. Only `SHRINK` caught it. **Neither check alone is sufficient; the
pair is.**

---

## 4. Verdict against the budget

**p50 ≤ 700 ms for the cleanup pass.**

| Checkpoint | device | p50 | verdict |
|---|---|---|---|
| **`vamshi0310/finetuned-disfluency-correction`** | **CPU** | **300.4 ms** | **PASS** |
| `vamshi0310/finetuned-disfluency-correction` | MPS | 804.0 ms | FAIL |
| `abdulbaseermohammedkhan/t5_disfluent_cleaner` | CPU | 270.0 ms | PASS |
| `Galmieux/bart_disfl_qa` | CPU | 163.1 ms | PASS |
| `EmnaBou/t5-base-disfluent-fluent` | CPU | 48.7 ms | PASS |

**PASS** — on CPU, for the primary checkpoint, by a factor of 2.3.

Stacked on `tiny.en` + VAD (328 ms p50 / 420 ms p95, `docs/gates/probe.md`):

```
tiny.en 328 ms  +  t5-small cleanup 300 ms  =  628 ms p50
tiny.en 420 ms  +  t5-small cleanup 380 ms  =  800 ms p95
```

That p50 fits inside the 700 ms Phase 5 budget — the first configuration in this
project that does. The p95 does not fit G1's 800 ms ceiling with any margin at all; it
lands exactly on it, on the fastest hardware this product will ever run on.

**Latency passes. The feature still should not ship, for the reason in the next
section.**

---

## What this reveals that the feasibility record got wrong

### 1. The diagnosis was right and the prescription does not follow from it

The feasibility record concluded the 3B model failed because it is "a *generator*
being asked to perform a *deletion*, and nothing in its architecture constrains it to
that." That diagnosis is **correct and confirmed here.** Swapping in a model trained on
deletion eliminated every catastrophic failure: no chat preamble, no refusal, no
93-word hallucination, zero INVENT, max shrink 7.3%, mean WER 110% → 21.27%.

But the record listed the fine-tuned seq2seq as an option that would *fix the feature*.
It does not. It fixes the *damage* and delivers no benefit. WER got worse on four of
six samples and better on zero. Correcting the instrument revealed that the task, as
posed against this corpus, has nothing to gain.

### 2. The corpus contains essentially no disfluencies, so it cannot measure disfluency removal

This is the load-bearing finding and it applies to **all four Track 2 experiments.**

Counted over all six `raw_asr` transcripts: **270 words, 1 filler token, 0 immediate
repetitions — a 0.37% disfluency rate.** The single "filler" is `actually` in "the way
I actually talk", which is an adverb doing its job, not a disfluency.

The corpus samples were read aloud from prepared text. Their errors are *transcription*
errors — `aminesis` for "Amanuensis", `flip 16` for "float sixteen", `cij` for "CI",
`talent voice` for "Talon Voice". A disfluency-removal model has never seen these and
has no mechanism to fix them.

So the six samples decompose into exactly two regimes, and the "before → after" table
above is measuring only the second:

- **Two samples the model correctly left alone** (`05-noisy`, `06-short`) — WER
  unchanged. Correct behaviour: there was nothing to remove.
- **Four samples where the only available action was to delete something correct** —
  and it did, every time.

Traced through the actual diffs:

| Sample | what it removed | verdict |
|---|---|---|
| 01-natural | `about` from "more than about 400 milliseconds" | wrong — hedge is meaningful |
| 02-code | `aminesis` (the ASR error) and `py` from "py test" | one right, one wrong |
| 03-proper-nouns | substituted `translate` → `can be` | wrong, and invisible to the INVENT check |
| 04-fast | `the thing is` from "Okay, so the thing is I talk" | wrong — the user said it |

This is a smaller, quieter instance of the exact hazard the feasibility record named:
*"it silently changes what you said."* The magnitude dropped from catastrophic to
cosmetic. The category did not change.

**The right conclusion is not "experiment 2 failed."** It is that the fixture cannot
answer the question the four experiments were commissioned to answer, because the
question is *does cleanup help disfluent speech* and the fixture contains fluent
speech. Every Track 2 result — including the constrained-decoding and rules-only arms —
is measuring "how much does this approach damage clean input", which is a real and
useful safety measurement but is not the hypothesis.

HANDOFF risk #6 already says the corpus is thin and that "more speakers would be worth
more than more samples." It should be strengthened: **the corpus is not merely thin, it
is the wrong corpus for Track 2.** What is needed is unscripted speech — samples where
the speaker genuinely hesitates and self-corrects, which is the behaviour the feature
exists to serve. Until that exists, no Track 2 experiment can produce a positive result,
because there is no upside available in the input.

### 3. MPS is not a free win, and the record's Metal argument does not generalise

The feasibility record's decisive technical claim was that "MLX and llama.cpp both have
Metal backends. CTranslate2 does not," so the LLM pass runs on GPU while transcription
is stuck on CPU — making the second pass *cheaper* than the transcription before it.

That holds for a 3B model. It inverts for a 60M one: MPS measured **2.7× slower** than
CPU (p50 804 ms vs 300 ms), and MPS alone is the difference between PASS and FAIL
against the budget. The generalisation "Metal makes the second pass cheap" is false at
small model sizes. Any future record should state the model size the claim was measured
at.

### 4. The two safety checks need a third, or a wider definition of "content word"

The record asserts the constraints "caught **every** catastrophic failure" and that
"deletion-only is a checkable property." Both hold here — every catastrophic checkpoint
tripped a check. But two gaps surfaced that only appear once the failures get subtler:

- `INVENT` scored 0 for a checkpoint that emitted **nothing at all**. Vacuously true.
  `SHRINK` is what caught it. Neither check is sufficient alone.
- `INVENT` scored 0 for a genuine word substitution (`translate` → `can be`) because
  the substituted words were closed-class. A model that rewrites function words while
  preserving content words passes both checks and still changes meaning.

Neither is fatal — the pair still turns silent corruption into a visible no-op, which
was the point. But "deletion-only is a checkable property" is only true if the check is
over *all* tokens, not content words. The looser content-word version is what the
record specifies and what all four experiments implemented for comparability.

### 5. The public-checkpoint gap is worth recording as a constraint

There is no production-quality open disfluency-removal seq2seq model. The best result
above comes from a 232 MB t5-small with 3 lifetime downloads and an undocumented
training set. It behaves well, but "behaves well on six samples" is not a basis for
shipping a model into a path that silently edits a user's words.

If Phase 5 is ever revived on this axis, the honest options are (a) fine-tune in-house
on a corpus that matches the product's actual input, or (b) do not do it. Adopting an
anonymous hobbyist checkpoint is a third option that should be named and rejected
rather than drifted into.

---

## Recommendation

**Do not ship a fine-tuned seq2seq cleanup pass.** Not because it is unsafe or slow —
it is neither. Because on the only evidence available it costs 1.94 points of WER and
returns nothing.

The hypothesis was worth testing and the answer is clean: **the fine-tuned model is the
right instrument and there is currently no job for it.** What would change that verdict
is a corpus of genuinely disfluent, unscripted speech. That is a cheaper and more
decisive next step than any further modelling work, and it gates all four Track 2 arms
equally.

## Reproduce

```bash
python3 -m venv venv-exp2
./venv-exp2/bin/pip install torch transformers sentencepiece protobuf jiwer

# lock invocation on non-corpus sentences
./venv-exp2/bin/python experiments/scripts/exp2_finetuned_seq2seq.py --probe

# frozen-fixture measurement, all four checkpoints
./venv-exp2/bin/python experiments/scripts/exp2_finetuned_seq2seq.py \
    --device cpu --json-out exp2-cpu.json

# device comparison for the primary
./venv-exp2/bin/python experiments/scripts/exp2_finetuned_seq2seq.py \
    --device mps --only t5-small-disfluency-correction
```
