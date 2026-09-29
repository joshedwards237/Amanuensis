# Can a punctuation model fix the run-on? — measured, and no

**Measured 2026-09-29.** `1-800-BAD-CODE/punctuation_fullstop_truecase_english`,
209 MB ONNX, scored against the operator's own corpus: 1,896 words, ten takes,
`gate_phase3.classify_edits`. Harness: `scripts/eval_punctuation_model.py`.

**Best achievable: +5 edits out of 164.** Below the noise floor of a ten-take
corpus. Candidate 2 is closed.

---

## 1. What this candidate had going for it, and it was real

The 3B instruct pass in `phase5-feasibility.md` took `tiny.en` from 19.6% WER to
**110%** — chat preamble emitted as literal text, 93 invented words, a refusal
pasted into the user's document, half a sentence deleted. Every one of those is
a **word-level** failure.

This model is token classification: one label per existing sub-token, no text
emitted. **Token identity held on all ten takes** — not one word altered across
1,896. The failure table above is unreachable by construction rather than by
prompting, exactly as `phase5-experiments.md`'s monotone ordering predicts.

It is also fast: **p50 20 ms, p95 29 ms**, two orders under §7.5's ceiling.

The mechanism was sound. The accuracy is not there.

## 2. Three operating points, none of which pays

| approach | fires | right | precision | recall |
|---|---|---|---|---|
| model alone | 96 | 25 | **26%** | 62% |
| Whisper boundary alone | 136 | 18 | 13% | 45% |
| both must agree | 28 | 14 | 50% | 35% |
| confidence ≥0.90 **and** boundary | 8 | 7 | **88%** | 18% |

Edit rate, scored through the product's chain:

| variant | edits | rate | sentences | words each |
|---|---|---|---|---|
| ships today | 164 | 8.65% | 35 | 54.2 |
| model alone | 282 | **14.87%** | 121 | 15.7 |
| model ∩ boundary | 161 | 8.49% | 63 | 30.1 |
| *operator's correction* | — | — | 56 | 33.9 |

**26% precision is the same figure the Phase 3 gate rejected the one-line
segment-join heuristic at.** A 209 MB neural model and `insert "." at every
boundary` score alike on this corpus.

## 3. The arithmetic that closes it

A correct mark removes one missing-mark edit. A wrong mark adds one **and
manufactures a wrong capital after it** — the mechanism the Phase 3 gate
measured directly (`decoder_capital` 38 → 63 when it tried the flat rule).

So break-even is ≈50% precision, and a feature needs ≈75%.

The intersection measured **exactly 50%** and delivered exactly what that
predicts: 3 edits out of 164. `decoder_segmentation` 86 → 80, six better;
`decoder_capital` 64 → 68, four worse. The wash is arithmetic, not luck.

**Thresholding cannot rescue it, and this was measured rather than assumed.**
The ONNX graph emits decided labels; its logits were exposed by graph surgery in
a throwaway environment — `post_preds` comes from an `ArgMax` over
`/_decoder/_punct_head_post/_linears.1/Add_output_0`, and `seg_preds` from a
`Greater` against a built-in 0.5. Sweeping both:

* Confidence alone tops out at **54% precision at P ≥ 0.98**, 18% recall.
* With the boundary intersection, **88% at P ≥ 0.90** — and 8 fires, 18% recall,
  **+5 net edits**.

Precision was reachable. Recall at that precision was not. Thresholding buys
precision by discarding volume, never by improving judgement.

## 4. The density question is still open and still blocks things

| | sentences | words each |
|---|---|---|
| decoder | 35 | 54.2 |
| model | 121 | 15.7 |
| operator, this corpus | 56 | 33.9 |
| operator, Phase 3 corpus | — | ≈21 (implied) |

Asked directly on 2026-09-29 which he preferred, the operator answered
**"between"** — more marks than his own correction, fewer than the model. That
is consistent with the Phase 3 density and **inconsistent with the corpus this
model was scored against**.

So every precision figure above is measured against a ground truth the operator
has since said is too sparse. It does not rescue the candidate — the +5 ceiling
comes from recall, and a denser ground truth raises the denominator too — but it
is recorded because it is the second result this uncertainty has qualified.

## 5. What this corpus cannot do, and why

`small.en` was re-scored here for comparison and came out **worse** than
`tiny.en` (13.98% against 9.49%), which contradicts the Phase 3 gate's table
(7.88% against 9.59%). The class breakdown explains it:

| class | tiny.en | small.en | delta |
|---|---|---|---|
| decoder_words | 9 | **74** | **+65** |
| decoder_segmentation | 92 | 123 | +31 |
| decoder_capital | 64 | 56 | −8 |

**The corpus instruction was "correct punctuation and case only; do not fix
misheard words."** That was right for the pause question — it keeps the ground
truth independent of the variable under test — and it makes this corpus
**structurally unable to compare engines**. The reference holds `tiny.en`'s
mishearings, so an engine that hears correctly is charged an edit for it, and
once 74 words diverge the alignment degrades and the segmentation column stops
being trustworthy either.

The Phase 3 corrections fixed words as well, which is why that table could rank
engines and this one cannot. **The `small.en` reading here is void, not
negative.**

## 6. Disposition

**Candidate 2 is closed.** Not deferred: the ceiling is a property of the
model's accuracy at this task, and the harness that measured it is committed.

**The engine question is reopened and is the strongest remaining lead.** The
Phase 3 gate wrote it down on 2026-09-01 and nothing has tested it since:

> The model may be the constraint, not the chain. `small.en` reaches 7.88%
> against `tiny.en`'s 9.59% and is unreachable only because of G1's p95.

Three candidates have now been closed trying to fix the chain. `small.en`
remains the largest measured improvement anyone has found here, and it was
rejected on latency alone — a constraint the operator relaxed on 2026-09-29
("I'm fine waiting longer"). Testing it needs a **verbatim** reference, which is
what `--combine-words` exists to produce.

**Relaxing G1 is not free and is not decided here.** §2 binds it, and
`site/` publishes the ≤10 s band from `claims.json` — the landing page would be
making a claim the product no longer meets. That is a §9 amendment with a dated
revision note, at a gate, not a config change.
