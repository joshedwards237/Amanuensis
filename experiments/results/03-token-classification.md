# Experiment 3 — token-level keep/delete classification

**Measured 2026-07-31** on Apple M3 Max, CPU (`torch` 2.13.0, `transformers` 5.14.1,
Python venv isolated from the repo `.venv/`).
Script: `experiments/scripts/exp3_token_classification.py`.
Input: `experiments/asr-baseline.json`, unmodified.

**Verdict: PASS on the budget by 51×, and the hypothesis's named cost is wrong.**
Latency p50 **13.6 ms** against a 700 ms budget. Zero safety violations across six
fixture samples *and* three disfluent control inputs. But WER got slightly **worse**
(19.33% → 20.35%), driven entirely by one sample where the tagger deleted content.
And the claim that this approach "loses self-correction resolution" — the stated
reason to discount it — **is false**: it resolved self-corrections correctly in two
of three control cases.

---

## Checkpoint selection

A public checkpoint exists and is a near-exact fit. No training was needed.

Searched the HuggingFace model index for `disfluency` filtered to
`token-classification`; ~32 candidates. They fall into four label schemes:

| Family | Labels | Fit |
|---|---|---|
| `DD0101/disfluency-*` | `B-RM/I-RM/B-IM/I-IM/O` (reparandum/interregnum BIO) | Vietnamese; needs a BIO→delete mapping we would author |
| `Teloxico/*`, `arielcerdap/*` | `fluent/disfluent`, or `O/FP/RP/RV/PW` | English, but no reconstruction contract |
| `hafidev/*` | one model per disfluency subtype | Would need 5 models chained |
| **`stillerman/fdt-disfluency-*`** | **`KEEP` / `DELETE` / `KEEP_STRIP_COMMA` / `KEEP_CAPITALIZE`** | **Native keep/delete + defined reconstruction** |

Chose **`stillerman/fdt-disfluency-distilbert-66m-v3`** — distilbert-base-cased,
65.2M params, the largest and most-downloaded of a five-size family, explicitly
built as a "disfluency **deletion tagger** for live speech transcripts". It is the
only candidate whose output contract *is* the thing Phase 5 needs; every other
candidate would require us to invent the tag→text mapping, which is where the
risk lives.

Its card claims val exact-match 0.9787, DELETE-F1 0.9952, and asserts:

> Deletion-only by construction — it cannot rephrase, hallucinate, or alter names
> and numbers.

That assertion is the hypothesis. It is tested below rather than taken on trust.

**Adoption blocker, unrelated to performance:** the card warns it was trained
partly on DailyDialog (CC BY-NC-SA) — "treat as research artifact, not for
commercial deployment as-is". Amanuensis is open-source, so NC is a real
licensing question, not a footnote. The *approach* is validated by these numbers;
this specific checkpoint may need retraining on permissive data before shipping.

---

## 1. WER before → after

Both ends computed here with `jiwer` under one shared normalisation
(lowercase → strip punctuation → collapse whitespace), so before and after are
comparable to each other.

| Sample | fixture `raw_wer` | before (ours) | after | Δ |
|---|---|---|---|---|
| 01-natural | 3.33 | 3.33 | 3.33 | +0.00 |
| 02-code | 18.97 | **17.24** | 17.24 | +0.00 |
| 03-proper-nouns | 31.91 | 31.91 | 31.91 | +0.00 |
| 04-fast | 2.04 | 2.04 | **8.16** | **+6.12** |
| 05-noisy | 18.60 | 18.60 | 18.60 | +0.00 |
| 06-short | 42.86 | 42.86 | 42.86 | +0.00 |
| **MEAN** | **19.62** | **19.33** | **20.35** | **+1.02** |

**Sanity check against the fixture: one disagreement.** `02-code` — fixture says
18.97%, we measure 17.24%. That is exactly one error's difference (11/58 vs 10/58
on a 58-word reference). Neither lowercase-only, strip-punctuation-only, nor
case-sensitive normalisation reproduces 18.97, so the fixture used a normaliser
we did not recover. Every other sample matches to two decimals. Per the brief, our
own numbers are reported; the delta column is unaffected either way because both
ends use the same transform.

---

## 2. Latency

Per-sample, model load excluded, one warm-up call before timing.

| Sample | CPU (ms) |
|---|---|
| 01-natural | 18.2 |
| 02-code | 15.0 |
| 03-proper-nouns | 15.8 |
| 04-fast | 12.1 |
| 05-noisy | 10.9 |
| 06-short | 8.9 |
| **p50** | **13.6** |
| **p95 (= max, n=6)** | **18.2** |

With n=6 there is no honest 95th percentile, so p95 is reported as the maximum —
a defensible upper bound rather than an interpolation.

**Model load: 693 ms** (warm, weights cached). One-time weight download was ~250 MB
over HTTPS at install, which PRD §7.6 permits.

**`mps` is 4× slower than CPU — measure, do not assume.**

| Device | p50 | p95 (max) | load |
|---|---|---|---|
| **CPU** | **13.6 ms** | **18.2 ms** | 693 ms |
| `mps` | 52.2 ms | 144.9 ms | 753 ms |

At this model size the GPU dispatch overhead dominates the compute. `mps` is also
far less *stable* — 10.7 ms to 144.9 ms across six samples, versus a 9–18 ms CPU
band. For a latency-budgeted product the tail matters more than the median, so CPU
wins twice. **Run this on CPU.** It also leaves the GPU free, which matters because
the ASR stage is already CPU-bound (CTranslate2 has no Metal backend).

---

## 3. Safety

| Sample | INVENT | SHRINK % | verbatim subsequence | violations |
|---|---|---|---|---|
| 01-natural | 0 | 0.0 | yes | — |
| 02-code | 0 | 0.0 | yes | — |
| 03-proper-nouns | 0 | 0.0 | yes | — |
| 04-fast | 0 | 3.1 | yes | — |
| 05-noisy | 0 | 0.0 | yes | — |
| 06-short | 0 | 0.0 | yes | — |

**0/6 INVENT, 0/6 SHRINK.** Compare the generative pass: 3/6 INVENT and 2/6 SHRINK
on the same six inputs, including 93 invented words on `05-noisy`.

### The INVENT check was verified, not asserted — and the fixture alone does not verify it

The tagger emitted only **3 DELETE labels across 270 fixture words**. A model that
never deletes trivially cannot invent, so 0/6 INVENT on the fixture is close to
vacuous as evidence. The claim was therefore also checked on the three control
inputs below, which actually exercise the deletion and reconstruction path
(10 deletions, 1 text mutation). **INVENT remained 0 there too.**

Three checks were run, not one, because subword merging and detokenisation are
exactly where an "impossible" insertion hides:

1. **Content-word multiset** (the feasibility record's definition, case- and
   punctuation-insensitive) — **0 violations everywhere.**
2. **Strict verbatim subsequence** — is every output word a character-exact input
   word, in order? **Failed once**, on `ctl-button`.
3. **Mutation log** — every word the reconstruction kept but altered.

### The one real crack in "cannot hallucinate by construction"

Check 3 caught it. The label set is not purely keep/delete: `KEEP_STRIP_COMMA` and
`KEEP_CAPITALIZE` **rewrite token text**. On `ctl-button` the reconstruction turned
`'be,'` into `'be'`, which is why the strict subsequence check failed there.

This does **not** falsify the no-hallucination claim in the sense that matters —
the mutations are confined to a trailing comma and a leading capital, they cannot
introduce a content word, and the multiset check stayed clean. But it does mean
the checkpoint's flat assertion ("it cannot ... alter names and numbers") is
loosely worded: `KEEP_CAPITALIZE` applied to a name *would* alter it, and nothing
in the architecture stops that. **The honest claim is "cannot insert content",
not "cannot alter text".** If this ships, the safety check must be the content-word
multiset — the strict subsequence check would false-positive on every sentence the
model recapitalises.

---

## Deletions per sample — the thing this experiment was specifically asked to report

| Sample | words | deleted | disfluencies | content | what it deleted |
|---|---|---|---|---|---|
| 01-natural | 59 | 0 | 0 | 0 | — |
| 02-code | 58 | 0 | 0 | 0 | — |
| 03-proper-nouns | 55 | 0 | 0 | 0 | — |
| 04-fast | 49 | **3** | **0** | **1** | `'the'`, `'thing'`, `'is'` |
| 05-noisy | 42 | 0 | 0 | 0 | — |
| 06-short | 7 | 0 | 0 | 0 | — |
| **total** | **270** | **3** | **0** | **1** | KEEP 267 / DELETE 3 |

**Read this carefully, because the headline WER number is misleading.**

Five of six samples: the tagger deleted nothing and WER was unchanged. On a fixture
of read prose containing **zero filled pauses**, that is the *correct* result. The
tagger was not asked to do anything and correctly did nothing.

The sixth is the finding. On `04-fast` it deleted `"the thing is"` from
*"Okay, so the thing is I talk pretty fast…"*. That is a discourse-framing phrase,
and deleting it is defensible as cleanup — but the **reference transcript contains
it**, so WER went 2.04% → 8.16%, and `'thing'` is a content word by any measure.
**Every deletion the tagger made on the fixture was a content deletion. Not one was
a disfluency.** The +1.02 mean WER regression is entirely this one sample.

This is precisely the case the brief warned about, inverted: not a model improving
WER by accident while deleting content, but a model *degrading* WER by deleting
content that a human would plausibly have wanted gone. The 3.1% SHRINK is far under
the 25% floor, so **no guard would have caught it.**

---

## Control probe — does the tagger fire at all when the input *is* disfluent?

Without this, "deleted nothing" is indistinguishable from a broken model. These are
the three hand-written cases from `docs/gates/phase5-feasibility.md`. No reference
transcript exists, so they are not WER-scored — they are a competence probe.

| Case | in → out | deleted | INVENT | SHRINK |
|---|---|---|---|---|
| `ctl-send` | "send that to uh Josh and and copy me on it" → **"send that to Josh and copy me on it"** | `'uh'`, `'and'` | 0 | 25.0% |
| `ctl-meet` | "let's meet on Monday, sorry, Tuesday at like three, no, four o'clock" → **"let's meet on Tuesday at four o'clock"** | `'Monday,'`, `'sorry,'`, `'like'`, `'three,'`, `'no,'` | 0 | 44.4% |
| `ctl-button` | "…the button to be, um, red, no, blue, and it should be like, on the right side of the page, or actually the left." → **"…the button to be red, blue, and it should be on the right side of the page, or actually the left."** | `'um,'`, `'no,'`, `'like,'` | 0 | 18.2% |

The model works. It is not inert.

**`ctl-send` and `ctl-meet` are both fully correct** — including the two things the
3B generative model was kept around for. `ctl-meet` resolved *both* self-corrections
(Monday→Tuesday, three→four) by deletion alone, and preserved `"let's meet"`, which
the 3B model dropped. `ctl-send` removed the filler and the stutter and preserved
`"on it"`, which the 3B model also dropped. On these two cases the tagger is
**strictly better than the 3B model**, at 1/25th the latency.

**`ctl-button` is the failure, and it is a specific, instructive one.** It deleted the
editing term `'no,'` but kept the reparandum `'red'`, yielding *"the button to be red,
blue"* — which reads as **both** colours. And *"on the right side of the page, or
actually the left"* was left entirely unresolved.

That is the real cost of deletion-only, and it is sharper than "loses self-correction
resolution": **deleting the repair marker while keeping the thing being repaired
produces output that is more confusing than the input.** A no-op would have been
better. Self-correction by deletion works when the reparandum is a contiguous span
the model can span-delete (`Monday, sorry,`), and fails when the model deletes the
cue and orphans the alternatives.

---

## 4. Verdict against the budget

| | |
|---|---|
| **p50** | **13.6 ms** |
| **Budget** | **≤ 700 ms** |
| **Result** | **PASS** — by 51×, with 686 ms of headroom |

Against the full pipeline: `tiny.en` + VAD p50 328 ms + 13.6 ms = **~342 ms p50**,
comfortably inside G1's 400 ms p50 target, not merely inside Phase 5's 700 ms. The
generative pass measured 373–2,201 ms end-to-end. This is not a marginal improvement
in cost; the cost effectively disappears.

Load cost: 693 ms added to daemon cold start (3.43 s measured with `tiny.en` + the 3B
model resident). Swapping the 3B model for this one **reduces** cold start and reduces
idle RSS — 65M params at fp32 is ~260 MB against the 3B model's ~1.8 GB, which
materially relieves the unmeasured idle-RSS risk in HANDOFF.md §5.

---

## What this reveals that the feasibility record got wrong

**1. "Loses self-correction resolution" is false, and it was the reason to discount
this option.** The feasibility record listed token-level classification with that
named cost, which reads as *cannot do the thing that motivated un-deferring Phase 5*.
Measured: it resolved self-corrections correctly in 2 of 3 of the record's own
hand-written cases, and on both it beat the 3B model by preserving clauses the 3B
model silently dropped. The accurate statement is narrower: **it cannot resolve a
self-correction when the repair requires deleting a non-contiguous or
earlier-positioned reparandum** — and when it fails it can leave output *worse* than
the input by orphaning the alternatives (`ctl-button`: "red, blue").

**2. The SHRINK ≤ 25% guard would reject the best output this approach produced.**
`ctl-meet` — "let's meet on Tuesday at four o'clock", a perfect resolution of two
self-corrections — shrinks content words by **44.4%** and would be discarded in
favour of the raw text. `ctl-send`, also fully correct, sits exactly **on** the 25%
boundary. This is not a flaw in the guard's implementation; it is a calibration
error. The 25% floor was derived against a *generator* that over-deleted, where
large shrink correlated with damage. For a deletion-only model, **large shrink is
what success looks like** — resolving a self-correction necessarily deletes the
reparandum, and the reparandum is content by definition. Keeping the guard at 25%
neutralises the feature. The guard should be retained for INVENT (which costs
nothing and caught nothing here) and **recalibrated or dropped for SHRINK** if this
approach proceeds.

**3. The guards catch the generative failure mode, not this one.** The record
concluded the four safety constraints "caught **every** catastrophic failure" — true
for a hallucinating generator. But the one bad edit here (`04-fast`, deleting
`"the thing is"`) produced 0 INVENT and 3.1% SHRINK and **passes every guard
cleanly**. Deletion-only shifts the residual risk from *loud, catchable* failures to
*quiet, uncatchable* ones. The worst case is no longer hallucinated text; it is a
handful of silently removed words that no deterministic check can distinguish from
correct cleanup. That is a much smaller hazard, but it is not zero, and constraints
1 (preserve raw) and 4 (undo affordance) are what cover it — not 2 and 3.

**4. The fixture cannot evaluate this class of approach, and that is a corpus
problem the record already half-identified.** The `raw_asr` fields contain **zero**
filled pauses — Whisper is trained on clean written transcripts and removes
disfluencies during decoding. So the ASR stage has *already done* most of what the
cleanup pass is for, before the pass ever runs. Any deletion-only approach will
score ~0 WER change on this fixture no matter how good it is; the fixture measures
whether it does harm, not whether it does good. HANDOFF.md risk 6 says "more
speakers would be worth more than more samples" — for Phase 5 specifically, the
binding gap is **spontaneous disfluent speech**, and no number of read-prose samples
supplies it. **The n=3 hand-written cases remain the only real evidence about
cleanup quality, which is the same weakness the record flagged about the 3B
measurement.** This experiment does not fix that.

**5. Latency was never going to be the constraint, and CPU beats `mps`.** The record
framed Phase 5 as a latency-versus-quality trade at ~700 ms. At 13.6 ms that trade
does not exist for this approach. Worth noting the measured `mps` result inverts the
record's framing that Metal availability is what makes a second pass affordable —
at 65M params the GPU is 4× *slower* and far more variable.

---

## What is still unknown

- **Cleanup quality is measured on n=3 hand-written cases.** Same weakness as the
  original feasibility measurement. 2/3 correct is not a quality metric.
- **Untested on real spontaneous speech.** The corpus has none. Everything above
  about whether the tagger deletes the *right* things rests on three sentences one
  person wrote.
- **The `KEEP_CAPITALIZE` path is barely exercised** — it fired zero times across
  all nine inputs. Its behaviour on proper nouns is untested, and `03-proper-nouns`
  is exactly where it would matter.
- **Licensing.** DailyDialog CC BY-NC-SA in the training mix is an unresolved
  question for an open-source product, independent of whether the numbers are good.
- **Truncation is untested.** Inputs over 512 subword tokens are handled by keeping
  every truncated word (fail-open, by design), but no fixture sample comes close.
