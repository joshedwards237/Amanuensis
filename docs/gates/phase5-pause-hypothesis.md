# Does the pause before a segment boundary predict a sentence mark?

**Measured 2026-09-21. Answer: no, and the reason is structural rather than
statistical.** `tiny.en`, beam 1, ten long takes, 1,898 words, 136 scorable
segment boundaries. Scripts: `make_punctuation_corpus.py`,
`measure_pause_punctuation.py`.

The hypothesis came from the operator's own use of Wispr Flow: *pause long
enough and you get punctuation; speak straight through and you get one
sentence.* It is a real perception. It is not recoverable from what
faster-whisper reports.

---

## 1. The number that settles it

**39% of the boundaries that want a sentence mark have a gap of exactly
0.000 s.** Against 47% for boundaries that want none — an eight-point
difference on the single feature the whole idea rests on.

A predictor absent on 39% of the things it must find has a **recall ceiling of
61%** before precision is considered at all. No threshold, no amount of extra
corpus and no cleverer rule moves that: the information is not in the signal.

Whisper emits segment boundaries on its own decoding windows as often as on
silence. When a speaker runs one sentence into the next — which this one does,
constantly — there is nothing in the timing to see.

## 2. Three tests, none of which disagree

| test | result |
|---|---|
| gap threshold sweep | best 28.6%, **below** the shuffle's 95th percentile of 30.4% |
| difference of means, 20,000 permutations | +0.137 s, **p = 0.165** |
| rank-sum (Mann-Whitney), 20,000 permutations | **p = 0.182** |

|  | n | mean gap | median gap |
|---|---|---|---|
| boundaries wanting a mark | 18 | 0.586 s | 0.630 s |
| boundaries wanting none | 118 | 0.449 s | 0.120 s |

The medians look far apart and the means do not, which is the tell: the
distribution is heavy-tailed and a handful of long pauses carry the median. The
rank-sum test is the one that fits that shape and it is the least significant of
the three.

**The threshold sweep is the weakest instrument here and is reported last for
that reason.** It spends the data finding its own cutoff, so its best row is
optimistic by construction — which is why the negative control is swept the same
way. Comparing a swept real figure against an unswept shuffled one would credit
the sweep's own optimism to the signal.

## 3. What replicated, and it is not nothing

**65% of the marks the operator added landed on a segment boundary.** The Phase
3 gate measured **70%** — different corpus, different session, same speaker.
That reproduces independently.

So the gate's structural finding stands: *boundaries are where sentences end.*
What fails is the converse, exactly as the gate found — only 13% of boundaries
want a mark, so firing on all of them is 2.3 wrong for every 1 right. The gap
does not separate the 13% from the rest.

## 4. The positive control failed, and that is recorded rather than explained away

The flat rule scored **13.2%** here against the gate's **31%**, and the harness
printed its own warning. Two candidate causes were checked:

* **Index drift at segment joins** — ruled out. Per-segment word counts sum
  exactly to the whole on all ten takes.
* **Correction density** — confirmed. This corpus carries **56 sentences over
  1,898 words, a mean of 33.9 words per sentence**. Ordinary written prose runs
  15–20. The Phase 3 corpus needed 58 added marks where this one needed 21.

Same speaker, same ten prompts, two correction sessions, twice the density.
**Which of the two reflects what the operator would actually accept in output is
unresolved, and G2's 8.59% edit rate was computed against the denser one.** That
is a live question for the Phase 5 gate, not a footnote.

## 5. A methodological point that was got backwards first

The corpus was corrected **from text alone, without listening to the audio**.
The first reading of that fact, in session, was that it biased the ground truth
*against* the hypothesis — that marks a listener would have heard could not be
placed.

That was wrong, and the correction is the useful part. **Marking by ear would
have been circular**: a mark placed partly because a pause was heard, then used
to test whether pauses predict marks, measures the annotator. Marking from
syntax alone is independent of the variable under test. The text-only corpus is
the *better* ground truth for this question, and it should not be redone.

## 6. Limits, stated

* **18 positives.** These tests can miss a small effect. What they exclude is an
  effect large enough to build a rule on — and §1's ceiling is not a power
  question.
* **One speaker, one microphone, `tiny.en`.** A larger model segments
  differently; whether it segments *more informatively* is unmeasured.
* **Word-level gaps are untested as a separate predictor.** 79 interior gaps
  exceed 0.3 s, and the Phase 3 gate found 30% of wanted marks fall inside a
  segment where no boundary rule can reach. That is a different hypothesis with
  the same corpus already built for it.

## 7. Disposition

**Candidate 1 — gap-gated segment joins — is closed.** It is not deferred and
not blocked on data; §1 is a property of the signal.

**Candidate 2 — a dedicated punctuation-restoration model — is untouched and now
has a corpus.** The argument for it is unchanged and is structural: every Phase
5 mechanism that failed had the freedom to regenerate *words*, and error rate
tracked that freedom monotonically (`phase5-experiments.md`). A model restricted
to inserting marks and changing case sits below that whole ordering. It is
unmeasured, and this document is not evidence for it.
