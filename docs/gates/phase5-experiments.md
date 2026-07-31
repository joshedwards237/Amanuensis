# Phase 5 experiments — four approaches, one frozen corpus

**Date:** 2026-07-31
**Input:** `experiments/asr-baseline.json` — 6 samples, `tiny.en` + VAD, mean raw WER
19.33% as re-measured (the fixture records 19.62%; the 0.29-point gap is jiwer
normalisation and is noted in every result file)
**Records:** `experiments/results/0{1,2,3,4}-*.md`
**Scripts:** `experiments/scripts/exp{1,2,3,4}_*.py`

**Verdict: no approach ships. The corpus cannot answer the question, and that is
the finding.**

---

## 1. The four, side by side

| # | Approach | mean WER 19.33% → | p50 | INVENT | SHRINK | Budget |
|---|---|---|---|---|---|---|
| 1 | Constrained decoding | **34.58%** | 908 ms | **0/6** | 2/6 | **FAIL** |
| 2 | Fine-tuned seq2seq (t5-small) | **21.27%** | 300 ms | 0/6 | 0/6 | PASS |
| 3 | Token keep/delete | **20.35%** | **13.6 ms** | 0/6 | 0/6 | PASS |
| 4 | Rules-only (control) | **19.33%** | 0.044 ms | 0/6 | 0/6 | PASS |
| — | *3B instruct (feasibility record)* | *110.0%* | *373–2201 ms* | *3/6* | *2/6* | *FAIL* |

**Not one approach improved WER on a single sample.** The control — which changes
nothing measurable and costs 44 microseconds — is the best performer in the table.
Every ML approach is a more expensive way to be slightly worse.

The ordering is nonetheless informative: it is monotonic in *how much freedom the
mechanism has*. Rules change nothing. Token classification deletes. Seq2seq
regenerates. Constrained decoding regenerates under a constraint that turns out not
to bind on the failure that matters. A 3B instruct model does whatever it likes. Error
rate tracks that ordering exactly.

## 2. The confound that governs all four

Experiment 4 quantified the corpus and found:

> **0.0%** of the 19.33% mean WER is disfluency. ~7% is the reference penalising
> written-form numbers. ~93% is genuine mistranscription.

Three of the four experiments are deletion mechanisms aimed at disfluencies. The
corpus contains none. Verified independently here — a filler scan across all six
`raw_asr` fields returns one hit, `"actually"` in `01-natural`, which is a genuine
adverb and not a filler.

**Why the corpus contains none is the part that matters, and experiment 4 got it
wrong.** Its explanation:

> The disfluencies in those hand-written strings do not survive Whisper's decoder, so
> the feature was specified against an input distribution that the ASR stage does not
> produce.

**No experiment tested that, and it should not be recorded as a finding.** It is an
unverified claim about Whisper's behaviour, stated with the confidence of a
measurement. The simpler explanation is visible in the fixture: every sample was
**read from a prepared script**. `05-noisy`'s own reference says so — *"while I read
this sentence."* People do not produce false starts when reading text they wrote.

The distinction is not academic, because the two explanations imply opposite next
steps:

- If **Whisper strips disfluencies**, Phase 5 is dead on arrival and the four
  approaches are all aimed at nothing.
- If **the corpus has no disfluencies because it was read aloud**, Phase 5 is
  *untested*, and these four results say nothing about it either way.

The corpus was designed to measure ASR accuracy against a known reference, which
requires a script. That design is correct for what it was built for — the Phase 1
benchmark — and it makes the corpus structurally incapable of testing a disfluency
remover. Reusing it here was the error, and it was mine.

## 3. What was learned anyway

These hold regardless of the confound, because they are not WER claims.

**Constrained decoding works as a mechanism and does not solve the problem.**
Insertion became structurally impossible — INVENT 0/6, verified empirically on
output rather than asserted from the construction. Mean WER still rose to 34.58%,
because the feasibility record's own failure list included *content deletion*, which
constraining the output alphabet does nothing about. The record diagnosed the failure
correctly and then proposed a fix for half of its own list.

**MPS is slower than CPU for models this size.** The same t5-small checkpoint measured
300 ms on CPU and 804 ms on MPS — the difference between passing and failing the
budget. Transfer overhead dominates at this scale. This bears directly on PRD §7.2's
device selection and is the second time this project has found an accelerator
assumption backwards.

**Both safety constraints are individually insufficient, and in opposite directions.**

- `INVENT` is **blind to function-word substitution**. Experiment 2's primary
  checkpoint rewrote `"faster whisper"` → `"the whisper"`, introducing two words the
  input never contained, and INVENT did not fire because neither is a content word.
  Only SHRINK caught it.
- `SHRINK` at 25% **would discard the single best output any experiment produced**.
  Experiment 3's only genuine self-correction resolution shrinks content words by
  44.4%. For a deletion-only mechanism, large shrink is the feature, and a guard
  calibrated against a generator is the wrong guard.

**A fifth constraint is missing: measure the firing rate.** All four existing checks
are *shape* checks — did it insert, did it delete too much. Nothing asks whether the
pass had a job to do. A pass that correctly no-ops on every input satisfies all four
perfectly and delivers nothing, and is indistinguishable under those checks from one
that is genuinely helping. On this corpus that distinction is the entire question.

**No maintained public seq2seq disfluency checkpoint exists.** Experiment 2 searched
and ran four candidates; three collapse — one summarises, one rewrites statements into
questions, one emits the empty string on every input. The absence is itself a result
about how much engineering the fine-tuned route would actually cost.

**The fixture's 19.62% raw WER is overstated by ~1.4 points.** 7–13% of `tiny.en`'s
error rate is the reference spelling out numbers the engine correctly rendered as
digits. HANDOFF risk #1 argues model selection on this metric; it is pessimistic and
unevenly so across samples.

## 4. What this does not license

Phase 5 was un-deferred on 2026-07-31 from three hand-written cases and killed the
same day by real data. The lesson recorded then was *test against real pipeline output
before recommending*. These four experiments did that — and still cannot decide the
question, because the real pipeline output tested was of the wrong kind.

So: **no approach is selected, and Phase 5 is not re-killed either.** Declaring it
dead from a corpus that structurally cannot contain the phenomenon would repeat the
original error with the sign flipped.

## 5. What would actually answer it

One thing, and it is cheap:

**Record 6–10 samples of genuinely spontaneous speech** — thinking aloud, no script,
with the false starts and self-corrections that occur naturally — and transcribe them
with `tiny.en` + VAD. Then look at the output and answer the single question nobody
has asked: **do disfluencies survive the decoder?**

That is a 20-minute recording session and one script run. It settles whether Phase 5
has any subject matter at all, which is a prerequisite for every other decision here.
Reference transcripts are the hard part — spontaneous speech has no script to compare
against, so this corpus measures *presence of disfluency*, not WER, and does not need
one.

If disfluencies do survive: experiment 3 is the standing candidate — 13.6 ms, cannot
hallucinate by construction, and its named cost (no self-correction resolution) was
partly refuted by its own out-of-fixture probe. Re-run all four against the new corpus
before choosing.

If they do not survive: Phase 5 has no subject matter, Amanuensis is a verbatim
transcriber, and the README should say so plainly rather than list the feature as
specified-but-not-working.

---

## Operational notes

All four agents honoured their boundaries — `git status` after the run showed only new
untracked files, with `AMANUENSIS_PRD.md`, `HARNESS.md`, `HANDOFF.md`, `AGENTS.md` and
the fixture untouched. Per-agent venvs prevented the concurrent-install collision that
motivated them.

Every result file was told that a negative result is a complete finding. All four
returned one, and none tuned to a pass. That instruction is the reason this record can
be trusted at all.
