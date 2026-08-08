---
target: "AMANUENSIS_PRD.md §5.7 (the collapse guard), with §5.3 [guard], §6.3 GuardVerdict / transcribe(..., biased=), §9 Phase 2b follow-up"
task_slug: collapse-guard
date: 2026-08-05
mode: spec
authored_by: "advocatus-diaboli sentinel — the first sentinel record in this repo that a sentinel actually produced"
objections:
  - id: O1
    category: premise
    severity: high
    claim: "Words-per-second measures the speaker, not the decoder. The failure is a decoder that stopped early, and faster-whisper already returns the signal that says so directly — segment end timestamps against retained duration. §5.7 does not weigh it."
    disposition: accepted
    disposition_rationale: "Human decision, 2026-08-05. Accepted in full and it reshaped the design. Decoded coverage becomes the primary instrument and the rate floor is demoted to a fallback for engines that cannot report a span. Verified before acting: faster_whisper.Segment carries start/end/avg_logprob/no_speech_prob/compression_ratio and _decode discarded all of it. Three properties decided it — coverage is duration-independent, which matters because the operator dictates short clips often and the rate floor's min_audio_seconds exemption was a blind spot over his most common input rather than a policy choice; coverage has no false-positive population, which retires O3 and most of O8 rather than mitigating them; and coverage distinguishes early termination from drift, which is dictionary objection O3's open question. transcribe() returns Transcription(text, decoded_seconds) on the InjectionResult.restore_ms precedent."
  - id: O2
    category: risk
    severity: critical
    claim: "Refusing to inject inverts the fail-open posture C4 and slice V1 both specified, and the withheld transcript has no reader — manu history is Phase 3."
    disposition: accepted
    disposition_rationale: "Human decision, 2026-08-05. The refusal stands — it is the operator's 2026-08-04 decision and reaffirming it here is not a drafting slip — and manu history --last ships with it, pulled forward from Phase 3. The objection's framing is what carried: written is not recoverable, and a guarantee mechanically preserved and practically unreachable is the failure §5.5 documented once already. §5.7 now records the override of choice-story C4 explicitly rather than citing C4 as support for a posture C4 rejects. The sweep limb is REJECTED as false: sweep_pending expires by retain_days rather than unlinking on sight, so a refused transcript survives thirty days at the default. That correction did not change the disposition, only the severity of the reasoning behind it."
  - id: O3
    category: risk
    severity: high
    claim: "The guard's stated false-positive population — slow or quiet speakers — overlaps §4's secondary user, and the retry does not protect them: an unbiased re-decode of genuinely slow speech fails the same floor."
    disposition: accepted
    disposition_rationale: "Human decision, 2026-08-05. Accepted, and answered by O1 rather than by mitigation. Coverage does not ask how fast or quietly anyone speaks, so the population this objection identified — overlapping §4's secondary user — is no longer selected for. The residue stands and is fixed separately: a recovered transcript was arriving at the cursor decoded without the bias the user configured, with no signal, which §5.7 now calls dictionary objection O5 re-committed and §5.4's indicator now distinguishes."
  - id: O4
    category: implementation
    severity: high
    claim: "One threshold makes two decisions with wildly asymmetric costs. Set low enough to be safe for withholding words, 0.5 w/s is blind to every partial collapse in the 4.4x band beneath genuine speech."
    disposition: accepted
    disposition_rationale: "Human decision, 2026-08-05. Split into retry_below_coverage = 0.8 and min_decoded_coverage = 0.5. The asymmetry argument is correct: spending a decode and withholding words do not want the same number. The unlooked-for benefit is that the middle band generates the evidence the guard otherwise had no way to produce — biased and unbiased output over the same audio, both recorded."
  - id: O5
    category: implementation
    severity: high
    claim: "The retry is a second full decode inside G1's window with no LatencyBreakdown field and no latency ceiling, contradicting §6.3's own standing rule."
    disposition: accepted
    disposition_rationale: "Human decision, 2026-08-05. guard_ms added to LatencyBreakdown inside g1_ms, and retry_max_latency_ms added so the retry is predicted from §2's model and skipped rather than paid. The objection's sharpest point is conceded in the PRD: §6.3's standing rule was broken in the same revision that restates it, making four phases in a row."
  - id: O6
    category: alternatives
    severity: medium
    claim: "The only prompt shape ever observed to collapse a transcript is prose. Constraining initial_prompt at config load is deterministic, costs no latency, and was never weighed."
    disposition: deferred
    disposition_rationale: "Human decision, 2026-08-05. Not rejected — the observation that prose is the only prompt shape ever seen to collapse a transcript is real and worth keeping. Deferred because prose detection is itself a heuristic that would false-positive on legitimate prose prompts, and because it is an input-side mitigation for a feature (§5.6's boosting) that is still Phase 3. Revisit when [boost] is specified."
  - id: O7
    category: specification-quality
    severity: medium
    claim: "§5.7 does not say whether min_audio_seconds is measured on raw or retained audio, and the two readings diverge precisely in the over-trim case O10 was written about."
    disposition: accepted
    disposition_rationale: "Human decision, 2026-08-05. Largely mooted by O1 — coverage has no duration gate, so the ambiguity has nothing to attach to on the primary path. Where it survives, on the fallback floor, §5.7 now says the gate is retained seconds, the same quantity as the denominator."
  - id: O8
    category: risk
    severity: high
    claim: "The stated verification cannot falsify the direction the guard is most likely wrong in. Six samples from one speaker is the entire negative control, and the positive control is not the failure that motivated the fix."
    disposition: accepted
    disposition_rationale: "Human decision, 2026-08-05. The verification could not fail and §9 now says so. Both limits are named — one speaker for the negative control, and a positive control that is not the failure that motivated the fix because store_audio did nothing and that audio is gone. The false-positive direction is labelled untested, which is materially different from tested and clean, and the Phase 3 gate must record coverage and retained_seconds for every dictation so the live distribution can be compared against the six samples the thresholds came from."
---

# Objection record — The collapse guard (PRD §5.7)

## Provenance

**A sentinel produced this one.** Dispatched without `name:`, per the cause
found on 2026-08-04 and recorded in `AGENTS.md`. It returned eight objections
in 400 seconds after every previous sentinel dispatch in this repository
returned nothing. The dictionary's three records are self-authored and say so;
this is the first that does not have to.

Two of its claims were checked against the source before anything was done with
them, because a sentinel is an instrument and this project's standing rule is
that instruments fabricate in both directions. One held and one did not — see
the verification notes under O1 and O2.

---

## O1 — The floor measures the speaker; the failure is in the decoder
**Severity: high. Verified against the library.**

Words per second is a property of *how the user talks* divided by *how long
they talked*. The failure being guarded is a property of *where the decoder
stopped*. §5.7 picks a proxy carrying an irreducible confound — speaking rate —
when a direct measurement was available and never weighed.

**Verified 2026-08-05.** `faster_whisper.transcribe.Segment` carries
`['id', 'seek', 'start', 'end', 'text', 'tokens', 'avg_logprob',
'compression_ratio', 'no_speech_prob', 'words', 'temperature']`, and
`faster_whisper.py:_decode` currently discards all of it —
`"".join(segment.text for segment in segments)`. The signal is already crossing
the boundary and being thrown away.

Coverage — last segment `end` against retained duration — has three properties
the rate floor does not:

- **No false-positive population.** A slow speaker still produces segments
  spanning their audio. §5.7's own stated worst outcome, and objections O3 and
  O8 with it, dissolve rather than being mitigated.
- **No corpus calibration.** A decode covering 6% of retained speech is broken
  regardless of who spoke. The 0.5 floor is "derived from six samples and one
  speaker" and admitted provisional.
- **It answers the open question instead of routing around it.** Dictionary
  objection O3: *"If the mechanism is early-termination, a floor is right. If it
  is domain drift, a floor is half a guard."* Coverage distinguishes those on
  every firing, which is the explanation §5.7 says it does not have.

The portability counter — Moonshine and Parakeet may not expose segments — is
the same argument §6.3 used to prefer `biased: bool` over `initial_prompt=""`,
and it resolves the same way: ask for the behaviour, let an engine decline.

---

## O2 — Refusing to inject reverses the prior records, and nothing reads the withheld words
**Severity: critical as filed. One limb verified false.**

**The reversal is real.** Choice-story C4 is titled *"The guard fails open"* and
its decision is that the transcript is kept. Slice V1 says the same. §5.7 cites
C4 as authority for the retry and then inverts C4's posture four paragraphs
later with one sentence of justification.

*Note on provenance:* the reversal is the operator's decision of 2026-08-04 —
*"retry, and if both fail, say so loudly (error state, do not inject)"* — not a
drafting slip. What the objection correctly identifies is that §5.7 does not
**record** it as a decision that overrode C4.

**The reader problem is real.** `manu history` refuses and names Phase 3. With
`retain = true` the words are in `history.db` and reachable only by opening
SQLite by hand.

**The sweep claim is false, and checking it mattered.** The objection states the
pending file "is swept at the next daemon start unread." It is not.
`HistoryStore.sweep_pending` expires by `retain_days`, and its docstring gives
the reason: *"Unlinking on sight would delete the words §8 wrote precisely so a
failed injection would not cost them."* At the default `retain_days = 30` a
refused transcript survives a month. The claim holds only at `retain_days = 0`,
which §5.5 already documents as meaning nothing is kept.

The core survives the correction: a refused transcript is written to a place no
shipped command can show the user.

---

## O3 — The false-positive population is §4's secondary user, and the retry does not help them
**Severity: high.**

§5.7 names its own worst outcome — refusing a genuine transcript from a slow or
quiet speaker — and mitigates it with a config key.

**The retry cannot save them.** It drops `initial_prompt` and re-checks against
the same floor. For a genuine slow speaker the prompt was never the cause, so
the unbiased decode returns approximately the same word count over the same
seconds and fails the same threshold. The retry recovers *true positives only*.
§5.7 reads as though it mitigates both and it does not.

**§4's secondary user is the population selected for.** *"Users with RSI or
motor impairment for whom dictation is not a convenience... a dropped
transcription is not a minor annoyance."* Motor impairment co-occurs with
slower, quieter speech. The guard's false-positive trigger and §4's secondary
user are not independent variables.

**The `recovered` path is silent too.** A different transcript — decoded without
the bias the user deliberately configured, and therefore systematically worse at
the proper nouns `initial_prompt` was set for — arrives at the cursor with no
live signal. This is dictionary objection O5 re-committed: the user sees wrong
text and has no signal that the system touched it.

---

## O4 — One threshold, two decisions, opposite cost profiles
**Severity: high.**

`min_words_per_second` triggers the retry *and* gates the refusal. A false retry
costs one decode. A false refusal costs the user their words with no reader.
These do not want the same number.

The band between 0.5 and 2.18 w/s is a **4.4× range in which the guard does
nothing**. A 30-second dictation whose true content is 65 words but which
decodes to 20 — a 70% loss — runs at 0.67 w/s and passes untouched. §5.7
presents the 4.4× margin as evidence of safety; it is equally a measure of how
much destruction is invisible.

---

## O5 — The retry is an unbudgeted stage inside G1, against this document's own standing rule
**Severity: high.**

§6.3, verbatim: *"A stage inside G1's window with no field is a stage that
cannot be defended when G1 is missed... Decide which side of 'text fully present
in the focused application' a new stage falls on, give it a field, and say which
summary property it belongs to."*

The retry decode is unambiguously inside the window. It has no field. **This is
the fourth instance of the pattern that rule was written to stop, arriving in
the same revision as the rule's own restatement.**

The cost is concentrated where the guard fires. `transcribe_ms ≈ 48.8 + 13.69 ×
seconds`: a 30 s dictation goes ~460 → ~920 ms, and Phase 3's ≥ 60 s gate case
~909 → ~1,818 ms. C4's affordability argument — *"transcription is ~200 ms"* —
was computed on a 10-second utterance, while both observed collapses were 25 s
and 30.5 s. There is no ceiling in `[guard]` on how long recovery may take.

---

## O6 — Constrain the prompt at load, not the transcript at runtime
**Severity: medium.**

The only prompt shape ever observed to collapse a transcript is prose: V3
measured 8/10 with terms alone, 9/10 with prose plus terms, **0/10 with prose
alone**. A config-load constraint is deterministic, costs no latency, and has no
false-positive population.

§5.3 already rejects `sample_rate` values other than 16000 at load with both
reasons named. Refusing a configuration known to break the product is
established practice here.

Weaker than it looks: prose detection is itself a heuristic, and it does not
cover collapses with no prompt involved. An addition, not a replacement.

---

## O7 — `min_audio_seconds` does not say which audio it measures
**Severity: medium.**

§5.7 is explicit that the *denominator* is trimmed audio and silent about the
*gate*. A 30-second capture trimmed to 4 seconds: read as raw the guard runs on
a 4 s denominator; read as retained it skips. **The two readings disagree
precisely on the over-trim case objection O10 was accepted about.**

`GuardVerdict` carries `retained_seconds` specifically so that case is
diagnosable, which implies the retained reading — but the prose does not say it.

A second hole in the same table: the guard disables itself on
`TrimResult.fell_back`, which is a condition correlated with anomalous audio and
therefore with bad decodes. Correct given a rate instrument; a further argument
for O1, since coverage still works when trimming falls back.

---

## O8 — The verification cannot falsify the direction the guard is most likely wrong in
**Severity: high.**

§9's verification is "fires on the measured collapse, does not fire on any of
the six Phase 1 corpus samples."

- **The negative control is one speaker.** The stated risk is refusing genuine
  transcripts from a slow or quiet speaker. Six samples from one speaker cannot
  produce a slow speaker who is not that speaker. The test passes by
  construction. **It is a control that can only confirm.**
- **The positive control is not the failure.** §5.5 records the live 30.5 s
  collapse as unreproducible. So the guard is validated against the *other*
  event — the 0.20 w/s prose-prompt collapse, which dictionary objection O3
  already flagged as n=1 of six with no explanation of why that sample.
- **Phase 3's gate has no false-positive population either**, being the
  operator's voice again, and it uses the longest audio, where the retry is most
  expensive.

This repository has a documented instrument failure directly on point:
*controls catch false failures, not just false passes.*

---

## Explicitly not objecting to

**Taking this now as Phase 2b defect work.** The phase-boundary reasoning is
clean and would not be reopened.

**`biased: bool` over `initial_prompt=""`.** The rejected alternative is stated
with the decision, and asking for behaviour rather than a mechanism-specific
parameter is what the ABC exists for.

**Implementing `store_audio` in the same change**, with its own retention.
Adding a writer without a reaper would have been the actual mistake.

**Recording `retained_seconds` even when the guard did not run.** Better than
what O10 asked for.

**Stating what the guard cannot see** — the hallucinated-expansion paragraph.

**Permitting the off switch here after refusing one for `[vad] enabled`.** The
§5.3 bounded exception is applied correctly and the condition for removing the
switch is named.

---

## Summary

| # | Severity | One line |
|---|---|---|
| O1 | high | The floor measures the speaker; segment coverage measures the failure |
| O2 | **critical** | Fail-closed reverses C4/V1, and the withheld transcript has no reader. Sweep limb verified false |
| O3 | high | The false-positive population is §4's secondary user, and the retry does not help them |
| O4 | high | One threshold for "re-decode" and "withhold words"; blind across a 4.4× band |
| O5 | high | Second decode inside G1 with no field and no ceiling — breaks §6.3's own standing rule |
| O6 | medium | Constrain `initial_prompt` at load; prose is the only observed hazard shape |
| O7 | medium | `min_audio_seconds`: raw or retained? The readings diverge in O10's case |
| O8 | high | Verification cannot falsify the false-positive direction: one speaker, wrong positive control |

**Five of eight are high or critical.** O1 is the one that changed the design
rather than refining it, and it did: coverage replaced the rate floor as the
primary instrument, which retired O3 and half of O8 rather than mitigating
them.

**Seven accepted, one deferred, one limb rejected as false.** Dispositions are
the operator's, taken 2026-08-05. The rejected limb is O2's claim that a refused
transcript is swept at the next daemon start; `sweep_pending` expires by
`retain_days`. Checking it did not change the disposition, which is the useful
thing to know about checking claims — the objection was right for reasons other
than the one it led with.
