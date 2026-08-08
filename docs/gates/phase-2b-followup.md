# Phase 2b follow-up — the collapse guard

**Closed 2026-08-07. PASS.** Merged as `b812b05` (PR #7).

Not a phase gate. Phase 2b closed PASS on 2026-08-03 and stays closed; Phase 3
stays unopened. This is defect work against what Phase 2b shipped, taken before
Phase 3 began because the defect was live on the operator's machine.

---

## What prompted it

On 2026-08-05 a 30.5-second dictation returned **two words** — `" For Tenants."`
— with `initial_prompt` set, no error raised, the audio buffer full, and the
text injected at the cursor as though it were what had been said.

`initial_prompt` shipped in Phase 1. Nothing had been watching it for two
phases.

The hazard was not undiscovered. The dictionary slicing record had put a guard
first among its slices and said, in terms that turned out to decide where it
belonged: *"first, and not because of the dictionary — `initial_prompt` is a
config key any user can set, is wired today, and is set on the operator's
machine now."* A slice that is not about the feature is not a slice of the
feature. It was scheduled inside a Phase 3 feature only because that is where
someone noticed it.

## What was built

PRD §5.7, the `[guard]` block in §5.3, `GuardVerdict` and `Transcription` in
§6.3, `guard_ms` in `LatencyBreakdown`, the verdict in `history.db`,
`DictationState.RECOVERED`, `store_audio` implemented, and `manu history --last`.

337 tests, `mypy --strict` clean over 32 files, ruff clean.

## The measurement

`scripts/verify_guard.py`, both directions over the Phase 1 corpus:

| | coverage |
|---|---|
| Reproduced collapse — `03-proper-nouns` | **8.3%** — fired |
| Genuine speech, lowest of six (`06-short`, 3.2 s) | **82.8%** |
| Genuine speech, highest | 100.0% |

Zero false positives. The collapse and the genuine floor differ by a factor of
ten, with the 50% refusal gate between them — 33 points of margin below, 42
above.

---

## Findings

### 1. The instrument was wrong, and the wrong one is the intuitive one

**Amended the PRD.** The obvious measure is words per second: the transcript is
too short for the speech, so divide one by the other. §5.7 was drafted that way.
An `advocatus-diaboli` sentinel killed it on three counts and all three held:

1. **It measures the speaker, not the decoder.** Speaking rate is a confound the
   product has no evidence about, and its false-positive population — people who
   talk slowly or quietly — overlaps §4's secondary user, for whom "a dropped
   transcription is not a minor annoyance."
2. **It cannot judge short audio at all.** Word count is an integer, so at two
   seconds the rate quantises to 0.5 w/s **per word**: a genuine one-word "Yes."
   and a transcript collapsed to one word are the *same measurement*. The draft's
   `min_audio_seconds` exemption was therefore not a policy choice but
   arithmetic — and short utterances are this product's ordinary case, so the
   exemption was a blind spot over the most common input.
3. **The signal was already in hand and being discarded.**
   `faster_whisper.Segment` carries `start`, `end`, `avg_logprob`,
   `no_speech_prob` and `compression_ratio`. `_decode` joined the texts and
   dropped every one of them.

**Decoded coverage** — last segment `end` over retained speech — is
duration-independent and has no false-positive population.

The operator caught the same thing independently, from use rather than from
review: *"It's often that I would do a genuine two-second clip."* Two
independent routes to the same defect, one from an adversarial reader and one
from someone who dictates.

### 2. The first verification reported a PASS and was worthless

**The most important finding here.** The positive control used a prompt
*reconstructed from the 2026-08-03 record's description*, because the prompt
itself was never written down. It collapsed nothing. So the script ran the
negative control twice, found no false positives both times, and printed a pass.

The real prompt was found by sweeping nine candidates. `verify_guard.py` now
**exits non-zero when the positive control catches nothing**, because a control
that cannot fail is not a control.

**Fourth instance in this repository.** After `sentinel-integrity-check.sh`
passing on zero agents, the generated index that could not see new records, and
that same index reporting zero entries inside records it could see. The pattern
is stable enough to state as a rule: *a check that has never failed has not been
tested, and a check written against a remembered failure is a check written
against a description.*

### 3. The denominator was not speech, and §5.7 claimed it was

**Amended the PRD.** `[vad] speech_pad_ms` adds 400 ms of deliberate non-speech
to each side of every retained segment, and the decoder correctly emits nothing
over it. Dividing by the padded duration under-reports coverage **in proportion
to how short the clip is** — noise in a 30-second dictation, a quarter of a
3.2-second one.

Measured: the shortest genuine sample read **62.2%** against a 50% refusal gate
before the correction, **82.8%** after. Twelve points from withholding a real
transcript.

The bias was systematic, pointed at refusing genuine transcripts, and
concentrated on the input the product's first user produces most often.
`TrimResult` now reports `padding_seconds`.

Worth noting *why* it was caught: only by running the guard against real audio.
Every unit test passed with the uncorrected denominator, because the tests
supplied the numbers.

### 4. The collapse mechanism is prompt echo

**Amended the PRD.** Dictionary objection O3 posed a fork — *"if the cause is
early-termination, a floor is right; if it is domain drift, a floor is half a
guard"* — and said the guard could not be designed until it was answered.

It is early termination. `initial_prompt = "And how much is this?"` makes the
decoder emit **exactly that string** as the transcript of a 25-second clip,
deterministically.

That retires the 2026-08-03 record's "prose prompt" description, which named the
*output* and attributed the failure to the prompt's register. The register is not
the variable: five other prompts of comparable shape, including a 600-character
one, collapsed nothing. What the collapsing prompt has is the form of a complete
short utterance the model can plausibly emit as a whole transcript.

Still unanswered: why that clip and not the other five. The guard does not need
the answer, which is the argument for building against the failure rather than
the cause.

### 5. 337 tests went green with `manu transcribe` broken

`transcribe()` changed from `str` to `Transcription`, and two call sites kept
doing string operations on the result. `manu transcribe` would have raised
`AttributeError: 'Transcription' object has no attribute 'strip'` on the first
real dictation.

The suite could not see it because it mocks past those callers. `mypy --strict`
catches it exactly — verified with a positive control by reintroducing the bug,
which produced two errors naming both lines. **The instrument was fine and had
not been run.**

Symlinking the corpus in to run the verification also un-skipped a Phase 1 test
that had been silently skipping since it was written, and which carried the same
defect.

### 6. A sentinel delivered, for the first time in this repository

**Amended `AGENTS.md`.** Dispatched without `name:`, per the cause found on
2026-08-04: eight objections in 400 seconds, one critical, five high. Seven
accepted, one deferred. `docs/superpowers/objections/collapse-guard.md` is the
first sentinel record here a sentinel actually produced.

Two of its claims were checked against the source before being acted on. **One
held and one did not** — O2's "the pending file is swept at the next daemon
start" is false, because `sweep_pending` expires by `retain_days` rather than
unlinking on sight. The disposition did not change: the objection was right for
a different reason than the one it led with.

---

## What was not established

**The false-positive direction is untested**, and §9 says so rather than
implying otherwise. Six samples from one speaker cannot produce a speaker the
guard is wrong about. Coverage removes the *known* mechanism by which a slow or
quiet speaker gets falsely refused; that is an argument, not a measurement.

**`retry_below_coverage = 0.7` is calibrated against one short sample.**

**The Phase 3 gate must record `coverage` and `retained_seconds` for every
dictation**, fired or not, so the live distribution can be compared against the
six samples these thresholds came from.

## Deferred

**Objection O6** — constraining `initial_prompt` at config load, since prose is
the only prompt shape ever observed to collapse a transcript. Not rejected: it
is an input-side mitigation for §5.6's boosting, which is still Phase 3, and
prose detection is itself a heuristic that would false-positive on legitimate
prompts. Revisit when `[boost]` is specified.
