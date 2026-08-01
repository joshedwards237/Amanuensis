# Experiment 4 — rules-only post-processing (the control)

**Run 2026-07-31.** Apple M3 Max / 36 GB. Python 3.14, `jiwer` only, no model, no
network. Script: `experiments/scripts/exp4_rules_only.py`. Fixture:
`experiments/asr-baseline.json`, unmodified.

**Headline: rules change the WER by exactly 0.00 points, and 0.0% of the corpus's
errors are disfluencies.** `tiny.en` emits no fillers, no stutters, and no repeated
words — not few, *none*. The disfluency-removal task that experiments 1–3 are all
built to perform does not occur in this data.

---

## 1. WER before → after

Both `strip_fillers` variants are reported. They are **byte-identical on every
sample**, because the corpus contains zero filler tokens.

### Variant A — `strip_fillers = false` (the PRD §5.3 default)

| sample | WER before | WER after | Δ | strict before | strict after | rules fired |
|---|---|---|---|---|---|---|
| 01-natural | 3.33 | 3.33 | +0.00 | 6.67 | 6.67 | — |
| 02-code | 17.24 | 17.24 | +0.00 | 20.69 | 20.69 | — |
| 03-proper-nouns | 31.91 | 31.91 | +0.00 | 48.94 | 48.94 | `capitalise_sentences` |
| 04-fast | 2.04 | 2.04 | +0.00 | 10.20 | **8.16** | `ensure_terminal_punctuation` |
| 05-noisy | 18.60 | 18.60 | +0.00 | 18.60 | 18.60 | — |
| 06-short | 42.86 | 42.86 | +0.00 | 42.86 | 42.86 | — |
| **MEAN** | **19.33** | **19.33** | **+0.00** | **24.66** | **24.32** | 2/6 samples touched |

### Variant B — `strip_fillers = true`

| sample | WER before | WER after | Δ |
|---|---|---|---|
| all six | *identical to variant A* | *identical to variant A* | **+0.00** |
| **MEAN** | **19.33** | **19.33** | **+0.00** |

Filler removal fires **zero times across all six samples**. This is not evidence that
the option is safe — it is evidence that this corpus **cannot measure it**. The PRD's
`strip_fillers = false` default should stay where it is, but this experiment provides
no support for it either way. The argument for it remains the lossiness argument in
§7.5, not a number.

### Variant C — `spoken_forms = true` (proposed, off by default)

| sample | WER before | WER after | Δ | INVENT | invented tokens |
|---|---|---|---|---|---|
| 01-natural | 3.33 | 3.33 | +0.00 | — | |
| 02-code | 17.24 | 18.97 | **+1.72** | **YES** | `8` |
| 03-proper-nouns | 31.91 | 31.91 | +0.00 | — | |
| 04-fast | 2.04 | 6.12 | **+4.08** | **YES** | `1`, `1` |
| 05-noisy | 18.60 | 18.60 | +0.00 | — | |
| 06-short | 42.86 | 42.86 | +0.00 | — | |
| **MEAN** | **19.33** | **20.30** | **+0.97** | **2/6** | |

Reported because it is informative, not because it is recommended. Two separate
findings, in opposite directions:

- **02-code**: `int eight` → `int 8`. WER gets worse; the *user-visible output gets
  better*. The reference spells the number out; every engine emits digits. This is
  HANDOFF risk #7 firing in a measurable way.
- **04-fast**: `one thought ends and the next one starts` → `1 thought ends and the
  next 1 starts`. This is straightforwardly **wrong**, and it is the rule's own defect,
  not the reference's. `one` is a pronoun and a determiner as often as it is a numeral,
  and no token-level rule can tell which. That is why the rule ships off by default and
  why it should probably not ship at all without a part-of-speech guard.

### Sanity check against the fixture's `raw_wer`

Five of six agree exactly. One disagrees:

| sample | fixture `raw_wer` | mine | diff |
|---|---|---|---|
| 01-natural | 3.33 | 3.33 | +0.00 |
| **02-code** | **18.97** | **17.24** | **−1.73** |
| 03-proper-nouns | 31.91 | 31.91 | +0.00 |
| 04-fast | 2.04 | 2.04 | +0.00 |
| 05-noisy | 18.60 | 18.60 | +0.00 |
| 06-short | 42.86 | 42.86 | +0.00 |
| **MEAN** | **19.62** | **19.33** | **−0.29** |

02-code differs by exactly one error out of 58 reference words, so the fixture's
generator counted 11 where I count 10 — almost certainly a difference in how `80%` is
tokenised under punctuation stripping. **All numbers in this document are mine**, from
`jiwer.Compose([ToLowerCase, RemovePunctuation, RemoveMultipleSpaces, Strip,
ReduceToListOfListOfWords])`, applied identically to both sides.

### On the two WER columns

`strict` is WER with case and punctuation **retained**. It is here because standard
WER normalisation lowercases the text and strips punctuation, which makes
`capitalise_sentences`, `normalise_punctuation_spacing`, and
`ensure_terminal_punctuation` **structurally incapable of moving the number** — they
cannot help and cannot hurt. That is a property of the metric, not of the rules.

A user does not experience it that way. A missing full stop costs them the same
keystroke as a wrong word. Strict WER improves 24.66 → **24.32** (−0.34 pt), entirely
from 04-fast's restored terminal period. Small, but it is the only real movement any
rule produced, and it would be invisible if this experiment had reported WER alone.

---

## 2. Latency

Median of 200 warmed calls per sample, `time.perf_counter`. Single-shot timing at this
scale measures clock resolution rather than code.

| sample | variant A (ms) | variant C (ms) |
|---|---|---|
| 01-natural | 0.0513 | 0.0728 |
| 02-code | 0.0476 | 0.0678 |
| 03-proper-nouns | 0.0481 | 0.0677 |
| 04-fast | 0.0415 | 0.0594 |
| 05-noisy | 0.0353 | 0.0497 |
| 06-short | 0.0069 | 0.0098 |
| **p50** | **0.0445** | 0.0636 |
| **p95** | **0.0505** | 0.0715 |

p50/p95 are linear-interpolated over six values; with n=6 the p95 is effectively the
maximum and should be read as such, not as a tail estimate. Run-to-run jitter is
roughly ±0.005 ms.

**44 microseconds.** Against the LLM pass's measured 278–390 ms (feasibility record)
that is a factor of ~7,000. Latency is not a consideration for this approach and never
will be.

---

## 3. Safety violations

Same two checks as the feasibility record, same definitions, so the numbers are
directly comparable. Content words = tokens outside a closed-class function-word list.
Multiset semantics.

| variant | INVENT | SHRINK | max shrink % |
|---|---|---|---|
| **A — `strip_fillers=false`** | **0 / 6** | **0 / 6** | 0.0% |
| **B — `strip_fillers=true`** | **0 / 6** | **0 / 6** | 0.0% |
| C — `spoken_forms=true` | **2 / 6** | 0 / 6 | 6.1% |

**Rules can and did invent.** Variant C emitted the token `8` on 02-code and `1` twice
on 04-fast — content words absent from the input, tripping INVENT exactly as the LLM
pass did. This is reported rather than defined away. The distinction that matters is
not "rules are safe and models are not"; it is that a rule's invention is **bounded,
enumerable, and inspectable before it ships**, whereas the LLM's was 93 invented words
discovered only by testing.

In the shipped configuration (A/B) the pass is deletion-free, insertion-free, and
trivially satisfies both constraints — because the only tokens it ever adds are a full
stop and a capital letter, neither of which is a content word.

---

## 4. Verdict against the budget

```
tiny.en + VAD p50    328.0000 ms   (Phase 1 benchmark)
rules pass p50         0.0445 ms
                     ------------
pipeline p50         328.0445 ms   budget: 700 ms
```

# PASS

With 372 ms of headroom. The rules pass consumes **0.013%** of the Phase 5 budget. It
also comfortably satisfies **G1** (p50 ≤ 400 ms), which the LLM pass does not — worth
stating, because G1 is the budget that applies to the shipping default
`chain = ["rules"]`.

---

## 5. The finding that matters: how much of the WER is addressable at all?

Every one of the 39 word-level errors in the corpus, classified. Regions are merged
before classification (jiwer splits `four hundred` → `400` into a substitution plus a
deletion, and classifying those separately mis-attributes both), and mixed
equal-length substitutions are split word-pair-wise (`float sixteen` → `flip 16` is one
mishearing plus one reference artefact, not two of either).

| category | errors | share | addressable by rules? | addressable by *any* post-processor? |
|---|---|---|---|---|
| **disfluency** | **0** | **0.0%** | yes — but there are none | yes — but there are none |
| **reference artefact** | 5 | 12.8% | no (the output is already correct) | **no — the reference is wrong** |
| **orthography** | 0 | 0.0% | yes | invisible to WER by construction |
| **ASR mistranscription** | **34** | **87.2%** | **no** | **no — the information is not in the text** |
| **TOTAL** | 39 | 100% | | |

### 0.0% disfluency is the number to take away

There is not one `um`, `uh`, `er`, stutter, or repeated word anywhere in 6 samples /
~19 seconds mean / 264 reference words of `tiny.en` output. Verified directly against
the raw strings, not inferred.

This is not luck and it is not a quiet corpus. **Whisper-family models are trained on
transcript text and perform disfluency removal implicitly during decoding.** The
disfluencies are gone before any post-processor sees the text.

The consequence for this track is severe and should be checked before reading the other
three results:

> Experiments 1, 2 and 3 are all mechanisms for removing tokens from the input.
> Experiment 1 (constrained decoding to a subsequence) and experiment 3 (token-level
> keep/delete) **cannot do anything except delete**. On input with zero deletable
> tokens, the best achievable outcome for both is a perfect no-op — WER 19.33%,
> identical to this control. Any WER *improvement* they report is arriving from
> somewhere other than disfluency removal, and any WER *degradation* is them deleting
> a word the speaker actually said.

The upper bound on a deletion-only post-processor over this corpus is **0.00 points of
WER improvement**. That is arithmetic from the taxonomy, not a prediction.

**Cross-check against the siblings, read after this analysis was written.** Both
deletion-only experiments landed on the wrong side of that bound, which is the only
direction available to them:

| experiment | mean WER after | Δ vs this control |
|---|---|---|
| 1 — constrained decoding | 34.58% | **+15.25** |
| 3 — token classification | 20.35% | **+1.02** |
| **4 — rules (this)** | **19.33%** | **+0.00** |

Neither improved on the no-op, because there was no improvement available; both
regressed by deleting words the speaker said. Independently, all three experiments
computed the raw baseline as **19.33%**, not the fixture's 19.62% — three separate
derivations agreeing makes the fixture's `raw_wer` field the outlier, and it should be
regenerated.

### 12.8% is the reference penalising correct behaviour

HANDOFF risk #7, quantified. Five errors across two samples:

| sample | reference | `tiny.en` emitted | errors charged |
|---|---|---|---|
| 01-natural | `four hundred` | `400` | 2 |
| 02-code | `sixteen` | `16` | 1 |
| 02-code | `eighty percent` | `80%` | 2 |

Every one of these is the engine producing **what a user actually wants** and being
charged for it. Re-scoring with numbers folded to digits on both sides:

| sample | raw WER | reference-corrected | Δ |
|---|---|---|---|
| 01-natural | 3.33 | **0.00** | −3.33 |
| 02-code | 17.24 | **12.28** | −4.96 |
| 03-proper-nouns | 31.91 | 31.91 | +0.00 |
| 04-fast | 2.04 | 2.04 | +0.00 |
| 05-noisy | 18.60 | 18.60 | +0.00 |
| 06-short | 42.86 | 42.86 | +0.00 |
| **MEAN** | **19.33** | **17.95** | **−1.38** |

**01-natural is a perfect transcription scored at 3.33% WER.** The corrected mean
19.33 → 17.95 differs from the 12.8%-of-errors figure because per-sample WER averaging
weights the short samples heavily; both are correct measures of different things, and
the honest summary is that **7–13% of the reported WER is the fixture's fault, not the
engine's.**

This also means the corpus's headline 19.62% overstates `tiny.en`. That matters for
HANDOFF risk #1 — the model-selection decision is being made against a metric that is
~1.4 points pessimistic, and the pessimism is not evenly distributed across samples.

### 87.2% is unreachable by anything downstream

34 of 39 errors are the engine hearing a different word. `Amanuensis` → `and requested
analysis`. `ONNX` → `o and an x`. `Silero VAD` → `cellular ovad`. `CI` → `cij`.
`conversation` → `competition`. `room is not a dictation` → `news topic detection`.
`Send that to` → `So that's a`.

The correct words are not in the text in any form. No post-processor — rule, seq2seq,
classifier, or LLM — can recover them, because recovering them requires the audio.
A post-processor attempting it is guessing, and a confident guess is precisely the
hallucination the feasibility record caught.

**Where the 87.2% concentrates:** 03-proper-nouns alone contributes 15 of 39 errors
(38%), all proper nouns and acronyms. The lever for those is `initial_prompt`
(PRD §5.6) or `VocabularyPostProcessor` with a user wordlist — biasing the decoder
*before* it commits, or substituting against a list the user supplied. Neither is a
post-processing model, and neither is in this experiment track.

### Consolidated answer

Of the 19.33% mean WER:

- **0.0%** is disfluency — the thing three of four experiments are built to remove
- **~7%** (1.38 pts) is the reference penalising written-form numbers
- **~93%** is genuine mistranscription, addressable only upstream (better model,
  `initial_prompt` biasing, user vocabulary) or not at all

**The addressable share for any post-processing model on this corpus is
indistinguishable from zero.**

---

## 6. Rules implemented, and the argument for each

Ordered as they execute. Deletion rules run before orthography rules, because deleting
a token can create a ` ,` join or expose a new sentence-initial word.

| # | rule | argument | fired |
|---|---|---|---|
| 1 | `collapse_whitespace` | No dictated text wants a double space or a trailing newline at the cursor. The only rule here with a genuinely empty failure set. | 0/6 |
| 2 | `strip_fillers` *(opt-in)* | Fillers carry no propositional content. But removal is lossy and invisible — same hazard class as the LLM's silent deletions — hence §5.3's `false` default. | 0/6 |
| 3 | `collapse_immediate_repeats` | A verbatim stutter is an artefact of speech production, not intent. Guarded by a `LEGITIMATE_DOUBLES` set (`had had`, `that that`, …); without that guard the rule would be indefensible. | 0/6 |
| 4 | `spoken_to_written_numbers` *(opt-in)* | `set the timeout to thirty seconds` → `30`. **The weakest rule here** — see variant C. | 2/6 |
| 5 | `normalise_punctuation_spacing` | ` .` and `word,word` are unambiguously wrong in English prose and appear at VAD segment joins. Deliberately blind to `file.py` and `3.5`. | 0/6 |
| 6 | `capitalise_sentences` | Sentence-initial capitalisation is a hard orthographic rule with no exceptions a dictation tool meets. **Only ever raises case** — never lowercases, because a mid-sentence capital is indistinguishable from a proper noun without a model. | 1/6 |
| 7 | `ensure_terminal_punctuation` | An utterance is a complete thought and the user is about to type after it. Engines truncate the final mark when audio ends on the last syllable — 04-fast does exactly this. | 1/6 |

Actual changes made, in full, on the default config:

- **03-proper-nouns**: `and requested analysis uses…` → `And requested analysis uses…`
- **04-fast**: `…That's the hard part` → `…That's the hard part.`

That is the entire product of deterministic post-processing on this corpus.

### The known limit I did not paper over

04-fast contains `between sentences Which means` and `much help for me and honestly
That's the hard part` — spurious mid-sentence capitals from the engine. Fixing them
requires lowercasing, and no token-level rule can distinguish a spurious capital from
a proper noun. `Josh Edwards`, `Talon`, `July`, `Moonshine` are all in this corpus.
A lowercasing rule would corrupt them, in the corpus area (proper nouns) that already
has the worst WER. Left unfixed, deliberately.

### Rules I was tempted to write and did not

Recorded because the temptation is data about the fixture's size, and because the
brief asked for the temptation rather than the rule.

1. **Near-duplicate collapse.** 03-proper-nouns has `were near nerd dictation` against
   a reference `were nerd dictation`. A rule collapsing phonetically-similar adjacent
   tokens deletes `near` and saves an error. It has no principled similarity threshold,
   would delete half of any alliterative pair, and fires on **n=1**. Rejected.
2. **Compound-identifier joining.** 02-code has `py test` against `pytest`. Joining them
   needs a dictionary of software tool names — which is `VocabularyPostProcessor`'s job
   (§6.2) with a *user-supplied* wordlist. Implementing it here would let this control
   claim credit for a fixture-specific dictionary. Fires on **n=1**. Rejected.

Both are in `_REJECTED_RULES` in the script and are printed by every run, so a future
reader sees the road not taken.

---

## 7. What this reveals that the feasibility record got wrong

The feasibility record is substantially correct and its central conclusion — that the
LLM pass is a generator being asked to perform a deletion — holds up. Four corrections:

### 7.1 "Keep rules-only and accept that Amanuensis is a verbatim transcriber" understates it

The record lists that as one of four options, phrased as a concession. It is not a
concession, it is **already the situation**. `tiny.en` output *is* clean, fluent,
punctuated prose with zero disfluencies. Amanuensis is not choosing to be a verbatim
transcriber instead of a cleanup tool; there is nothing left to clean. Rules-only is
not the fallback option — it is the only one with any evidence behind it, and its
evidence is that it changes nothing measurable and costs 44 µs.

### 7.2 The record never established that the input contains disfluencies

This is the load-bearing gap. Every hand-written case in the record — `"send that to
uh Josh and and copy me on it"`, `"the button to be, um, red, no, blue"` — was
**authored to be disfluent**. The record notices the hand-written/real gap and names it
in *What is still unknown* ("Every case above was hand-written to be disfluent"), but
draws the wrong lesson: it worries the pass will *amplify* transcription errors.

The actual problem is upstream of that. The pass has **nothing to operate on**. The
disfluencies in those hand-written strings do not survive Whisper's decoder, so the
feature was specified against an input distribution that the ASR stage does not
produce. All four proposed remedies inherit the defect — constrained decoding,
fine-tuned deletion, and token classification are all deletion mechanisms aimed at
tokens that are not there.

### 7.3 The four safety constraints are necessary but not sufficient, and they were validated against the wrong risk

The record's claim that the constraints "caught **every** catastrophic failure" is
correct and important. But the constraints are all **shape** checks — did it insert,
did it delete too much. Nothing checks *whether the pass had a job to do*. A pass that
correctly no-ops on every input passes all four constraints perfectly and delivers zero
value; it is indistinguishable, under those checks, from a pass that is genuinely
helping. On this corpus that distinction is the whole question.

A fifth constraint belongs alongside them: **measure the firing rate.** If a
post-processor changes nothing on real input, ship the no-op and delete the code.

### 7.4 The 19.6% raw WER is overstated by ~1.4 points, and the record reasons from it uncorrected

The record's `tiny.en` 19.6% / `small.en` 6.1% table treats those as the engines' error
rates. 7–13% of `tiny.en`'s is the reference spelling out numbers the engine correctly
rendered as digits. This does not change the record's conclusion — 110% and 171%
post-cleanup WER are catastrophic against any baseline — but it does affect HANDOFF
risk #1, where model selection is being argued on a metric that is pessimistic and
unevenly so. The correction is in §5 above and belongs in the fixture's provenance
note, not in a downstream result file.

### 7.5 What holds up

- The failure taxonomy (preamble leakage, wholesale hallucination, refusal, content
  deletion) is real and none of it is reachable by rules.
- Deletion-only as a *checkable property* is the right frame, and INVENT/SHRINK are
  the right two checks. This experiment reuses them unmodified and they behave
  correctly — including catching this experiment's own opt-in rule inventing `8`.
- The latency correction (cold start is not the problem; token count is) stands.
- "Off by default" for anything probabilistic stands, and this result strengthens it:
  the default configuration is now known to cost 44 µs and change nothing, which is
  the cheapest possible default.

---

## 8. Recommendation

**Ship `RuleBasedPostProcessor` as written, in Phase 3, with `chain = ["rules"]` and
`strip_fillers = false` unchanged.** It costs 44 µs, never invents, never shrinks, and
fixes two real orthographic defects. It is not justified by WER — nothing in this
experiment is — but by the strict-WER movement and by being the correct home for the
rules a dictation tool will need as the corpus grows to include speakers the engine
handles less cleanly.

**Do not ship `spoken_to_written_numbers`** without a part-of-speech guard. `one` →
`1` is a real defect, found on the first real corpus it touched.

**Set the bar for experiments 1–3 explicitly: WER 19.33%, latency 0.045 ms, zero safety
violations.** An approach that ties this control on WER — which is the best a
deletion-only method can achieve here — must justify itself entirely on latency, and
none of them will.

**The decision-relevant question is no longer "which post-processing approach".** With
0.0% disfluency and 87.2% mistranscription, the leverage is upstream: `initial_prompt`
vocabulary biasing for the proper-noun failures (38% of all errors, one sample), and a
corpus with more speakers — HANDOFF risk #6 already says more speakers are worth more
than more samples, and this result is the strongest evidence yet for that. A second
speaker who *does* produce disfluencies would falsify the central finding here in one
recording session, and until someone tries, the finding rests on one speaker.

---

## Reproduce

```bash
python3 -m venv /tmp/venv-exp4 && /tmp/venv-exp4/bin/pip install jiwer
/tmp/venv-exp4/bin/python experiments/scripts/exp4_rules_only.py
/tmp/venv-exp4/bin/python experiments/scripts/exp4_rules_only.py --json   # machine-readable
```

No model, no network, no GPU. Runs in under two seconds, nearly all of it interpreter
startup.
